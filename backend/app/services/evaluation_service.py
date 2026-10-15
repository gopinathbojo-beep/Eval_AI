from __future__ import annotations
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from ..config import AI_UNAVAILABLE_MESSAGE
from ..database import SessionLocal
from dataclasses import dataclass, field
from ..models import AnswerKey, AnswerSheetDocument, Evaluation, Exam, ExamQuestion, EvaluationItem, StudentAnswer
from ..ocr import prompts
from ..ocr.internvl import AIResponseError, AIUnavailable, chat_structured, check_model
from ..ocr.schemas import EvaluationResult
from .evaluation_rules import EvaluationValidationError, validate_evaluation
from .mapping_service import exam_questions
from .numbering import parent_number
from .state import set_state

log = logging.getLogger("adem.evaluation")
_ANSWER_STATES = {"MAPPED", "EVALUATING", "EVALUATED", "APPROVED"}

# Valid student answer resolution states
STUDENT_ANSWER_FOUND = "STUDENT_ANSWER_FOUND"
STUDENT_ANSWER_NOT_ATTEMPTED = "STUDENT_ANSWER_NOT_ATTEMPTED"
STUDENT_ANSWER_UNMAPPED = "STUDENT_ANSWER_UNMAPPED"
STUDENT_ANSWER_OCR_FAILED = "STUDENT_ANSWER_OCR_FAILED"
STUDENT_ANSWER_MAPPING_REVIEW = "STUDENT_ANSWER_MAPPING_REVIEW"
STUDENT_ANSWER_GROUPING_ERROR = "STUDENT_ANSWER_GROUPING_ERROR"
STUDENT_ANSWER_RELATIONSHIP_ERROR = "STUDENT_ANSWER_RELATIONSHIP_ERROR"
DATA_INTEGRITY_ERROR = "DATA_INTEGRITY_ERROR"


@dataclass
class ResolvedAnswer:
    status: str
    combined_text: str = ""
    primary_answer: StudentAnswer | None = None
    constituent_answers: list[StudentAnswer] = field(default_factory=list)
    reason: str | None = None


def resolve_student_answer(db: Session, ev: Evaluation, q: ExamQuestion) -> ResolvedAnswer:
    """Resolve student's answer for canonical question q.id across multiple sources:
    1. verified direct student_answer_group.question_id
    2. verified parent / subquestion mappings
    3. answer blocks belonging to mapped group (including cross-page continuations)
    4. precise diagnostic states if missing (not attempted vs mapping review vs unmapped vs ocr failed).
    """
    all_answers = (
        db.query(StudentAnswer)
        .filter_by(evaluation_id=ev.id)
        .order_by(StudentAnswer.page_number, StudentAnswer.position)
        .all()
    )

    # 1. Direct verified answer blocks mapped to canonical q.id
    direct_answers = [
        a for a in all_answers
        if a.exam_question_id == q.id and a.status in _ANSWER_STATES
    ]

    # 2. Check canonical subquestions if q is a parent question
    all_exam_qs = exam_questions(db, ev.exam_id)
    canonical_sub_qs = [
        sq for sq in all_exam_qs
        if sq.id != q.id and sq.normalized_number and q.normalized_number
        and parent_number(sq.normalized_number) == q.normalized_number
    ]
    sub_answers = []
    if canonical_sub_qs:
        sub_q_ids = {sq.id for sq in canonical_sub_qs}
        sub_answers = [
            a for a in all_answers
            if a.exam_question_id in sub_q_ids and a.status in _ANSWER_STATES
        ]

    # Constituent answers: use direct_answers if present; if empty and sub_answers exist, use sub_answers
    constituent: list[StudentAnswer] = []
    if direct_answers:
        constituent = direct_answers
        # Combine all answer blocks / cross-page continuations; label the parts of a question kept whole
        # ("9(a)", "9(b)" -> question 9) so the grader can tell them apart
        labelled = len({a.normalized_number for a in constituent}) > 1
        combined_parts = [
            (f"[{a.raw_question_number or a.normalized_number}]\n"
             if labelled and (a.raw_question_number or a.normalized_number) else "") + a.answer_text.strip()
            for a in constituent if a.answer_text and a.answer_text.strip()
        ]
        combined_text = "\n\n".join(combined_parts)
    elif sub_answers:
        constituent = sub_answers
        combined_parts = []
        for a in sub_answers:
            lbl = a.raw_question_number or a.normalized_number or ""
            txt = a.answer_text.strip() if a.answer_text else ""
            if txt:
                combined_parts.append(f"[{lbl}]\n{txt}" if lbl else txt)
        combined_text = "\n\n".join(combined_parts)
    else:
        combined_text = ""

    if constituent:
        if combined_text.strip():
            return ResolvedAnswer(
                status=STUDENT_ANSWER_FOUND,
                combined_text=combined_text,
                primary_answer=constituent[0],
                constituent_answers=constituent,
            )
        else:
            return ResolvedAnswer(
                status=STUDENT_ANSWER_GROUPING_ERROR,
                primary_answer=constituent[0],
                constituent_answers=constituent,
                reason=f"Student answer block exists for {q.display_number} but contains no transcribed text.",
            )

    # 3. If no verified answer found, resolve exact state
    # Check for mapping review / unresolved mapping for this question
    review_candidates = [
        a for a in all_answers
        if a.status in ("NEEDS_REVIEW", "UNMAPPED") and (
            a.exam_question_id == q.id
            or q.id in (a.mapping_candidates or [])
            or (a.normalized_number and q.normalized_number and a.normalized_number == q.normalized_number)
        )
    ]
    if review_candidates:
        ca = review_candidates[0]
        return ResolvedAnswer(
            status=STUDENT_ANSWER_MAPPING_REVIEW,
            primary_answer=ca,
            constituent_answers=review_candidates,
            reason=ca.mapping_note or f"Student answer detected ({ca.raw_question_number or 'unlabelled'}) but mapping is unresolved.",
        )

    # Check for relationship error (e.g. mapped answer marked IGNORED)
    ignored = [a for a in all_answers if a.exam_question_id == q.id and a.status == "IGNORED"]
    if ignored:
        return ResolvedAnswer(
            status=STUDENT_ANSWER_RELATIONSHIP_ERROR,
            primary_answer=ignored[0],
            constituent_answers=ignored,
            reason=f"Student answer for {q.display_number} is marked as IGNORED in mapping records.",
        )

    # Check for unmapped answer blocks on the sheet
    unmapped = [a for a in all_answers if a.status == "UNMAPPED"]
    if unmapped:
        return ResolvedAnswer(
            status=STUDENT_ANSWER_UNMAPPED,
            primary_answer=unmapped[0],
            constituent_answers=unmapped,
            reason=f"Unmapped student answer block exists on sheet (page {unmapped[0].page_number or 'unknown'}).",
        )

    # Check for failed OCR on answer sheet document
    doc = db.get(AnswerSheetDocument, ev.answer_sheet_id) if ev.answer_sheet_id else None
    if doc and doc.pages:
        failed_pages = [p.get("page_number") for p in doc.pages if p.get("ocr_status") != "OK"]
        if failed_pages:
            return ResolvedAnswer(
                status=STUDENT_ANSWER_OCR_FAILED,
                reason=f"Student answer sheet OCR failed on page(s): {', '.join(map(str, failed_pages))}.",
            )

    # Truly not attempted
    return ResolvedAnswer(
        status=STUDENT_ANSWER_NOT_ATTEMPTED,
        reason="No student answer region detected anywhere for this question.",
    )


def active_key_for(db: Session, exam_id: str, question_id: str) -> AnswerKey | None:
    return (db.query(AnswerKey).filter_by(exam_id=exam_id, exam_question_id=question_id, is_active=True,
                                          mapping_status="MAPPED").first())


def answer_for(db: Session, ev_id: str, question_id: str) -> StudentAnswer | None:
    ev = db.get(Evaluation, ev_id)
    q = db.get(ExamQuestion, question_id)
    if ev and q:
        res = resolve_student_answer(db, ev, q)
        if res.status == STUDENT_ANSWER_FOUND:
            return res.primary_answer
    return (db.query(StudentAnswer).filter(StudentAnswer.evaluation_id == ev_id,
                                           StudentAnswer.exam_question_id == question_id,
                                           StudentAnswer.status.in_(_ANSWER_STATES)).first())


def _reset_item(item: EvaluationItem) -> None:
    item.ai_marks = item.ai_decision = item.ai_feedback = item.ai_confidence = None
    item.matched_points, item.missing_points = [], []
    item.raw_response = item.error = None
    item.final_marks, item.teacher_overridden, item.teacher_feedback = None, False, None
    item.not_attempted_confirmed = False


def evaluate_item(db: Session, ev: Evaluation, q: ExamQuestion, item: EvaluationItem) -> None:
    """Evaluate one question. Raises AIUnavailable only; every other failure is recorded on the item."""
    _reset_item(item)
    resolved = resolve_student_answer(db, ev, q)
    item.student_answer_id = resolved.primary_answer.id if resolved.primary_answer else None

    if resolved.status == STUDENT_ANSWER_FOUND:
        key = active_key_for(db, ev.exam_id, q.id)
        if key is None or q.max_marks is None:
            item.status, item.error = "EVALUATION_ERROR", "No mapped answer key or maximum marks for this question."
            db.commit()
            return
        for a in resolved.constituent_answers:
            a.status = "EVALUATING"
        db.commit()
        prompt = prompts.evaluation_prompt(q.display_number, q.question_text, key.answer_text, key.criteria,
                                           key.accepted_answers, key.keywords, q.max_marks, resolved.combined_text)
        try:
            call = chat_structured(prompts.EVAL_SYSTEM, prompt, EvaluationResult)
            item.raw_response = call.raw
            res = validate_evaluation(call.parsed, q.max_marks)  # type: ignore[arg-type]
            item.ai_marks, item.ai_decision = res.marks_awarded, res.decision
            item.matched_points, item.missing_points = res.matched_points, res.missing_points
            item.ai_feedback, item.ai_confidence = res.feedback, res.confidence
            item.final_marks = res.marks_awarded  # proposal; becomes official only on teacher approval
            item.status = "EVALUATED"
            for a in resolved.constituent_answers:
                a.status = "EVALUATED"
        except EvaluationValidationError as e:
            item.status, item.error = "EVALUATION_ERROR", f"Invalid AI evaluation: {e}"
            for a in resolved.constituent_answers:
                a.status = "MAPPED"
        except AIResponseError as e:
            item.raw_response = e.raw
            item.status, item.error = "EVALUATION_ERROR", "InternVL3.5 4B failed to return a valid structured response."
            for a in resolved.constituent_answers:
                a.status = "MAPPED"
            log.error("Eval AI error q=%s: %s", q.display_number, e.detail)
        except AIUnavailable:
            for a in resolved.constituent_answers:
                a.status = "MAPPED"
            db.commit()
            raise
        db.commit()
        return

    elif resolved.status == STUDENT_ANSWER_NOT_ATTEMPTED:
        item.status = "MISSING"
        item.error = "Question was not attempted by student."
        db.commit()
        return

    else:
        item.status = "EVALUATION_ERROR"
        item.error = f"{resolved.status}: {resolved.reason}"
        db.commit()
        return


def run_evaluation(ev_id: str, only_question_ids: list[str] | None = None) -> None:
    db = SessionLocal()
    try:
        ev = db.get(Evaluation, ev_id)
        exam = db.get(Exam, ev.exam_id)
        ev.run_status = "RUNNING"
        if exam.status in ("READY_FOR_EVALUATION", "REVIEW_REQUIRED", "EVALUATING"):
            set_state(exam, "EVALUATING")
        db.commit()
        try:
            check_model()
            qs = [q for q in exam_questions(db, ev.exam_id) if not only_question_ids or q.id in only_question_ids]
            ev.run_total, ev.run_progress = len(qs), 0
            db.commit()
            for q in qs:
                item = db.query(EvaluationItem).filter_by(evaluation_id=ev.id, exam_question_id=q.id).first()
                if item is None:
                    item = EvaluationItem(evaluation_id=ev.id, exam_question_id=q.id)
                    db.add(item)
                    db.flush()
                # bulk runs never overwrite a teacher's approved/overridden work
                if not only_question_ids and (item.status == "APPROVED" or item.teacher_overridden):
                    ev.run_progress += 1
                    db.commit()
                    continue
                evaluate_item(db, ev, q, item)
                ev.run_progress += 1
                db.commit()
            ev.run_status = "DONE"
        except AIUnavailable as e:
            log.error("AI unavailable during evaluation: %s", e.detail)
            ev.run_status = "ERROR"
        if exam.status == "EVALUATING":
            set_state(exam, "REVIEW_REQUIRED")
        db.commit()
        refresh_evaluation_status(db, ev)
    except Exception:
        log.exception("Evaluation run crashed")
        db.rollback()
        ev = db.get(Evaluation, ev_id)
        if ev:
            ev.run_status = "ERROR"
            exam = db.get(Exam, ev.exam_id)
            if exam and exam.status == "EVALUATING":  # don't leave the exam stuck mid-evaluation
                set_state(exam, "REVIEW_REQUIRED")
            db.commit()
    finally:
        db.close()


def finalize_issues(db: Session, ev: Evaluation) -> list[dict]:
    exam = db.get(Exam, ev.exam_id)
    qs = exam_questions(db, ev.exam_id)
    issues: list[dict] = []

    def add(question: str, reason: str):
        issues.append({"question": question, "reason": reason})

    if not qs or any(q.verification_status != "VERIFIED" for q in qs):
        add("Exam", "Question paper is not verified")
    for q in qs:
        keys = db.query(AnswerKey).filter_by(exam_id=exam.id, exam_question_id=q.id, is_active=True).all()
        mapped = [k for k in keys if k.mapping_status == "MAPPED"]
        if len(mapped) != 1 or mapped[0].verification_status != "VERIFIED":
            add(q.display_number, "Answer key is missing, duplicated or not verified")
        elif mapped[0].mark_mismatch:
            add(q.display_number, "Answer key marks disagree with the question's maximum marks")
    for a in db.query(StudentAnswer).filter_by(evaluation_id=ev.id).all():
        if a.status in ("UNMAPPED", "NEEDS_REVIEW"):
            label = a.raw_question_number or "(no question number)"
            add(label, "Student answer is unmapped" if a.status == "UNMAPPED"
                else f"Student answer needs mapping review: {a.mapping_note or ''}".strip())
    items = {i.exam_question_id: i for i in db.query(EvaluationItem).filter_by(evaluation_id=ev.id).all()}
    for q in qs:
        it = items.get(q.id)
        if it is None or it.status == "PENDING":
            add(q.display_number, "Not evaluated yet")
        elif it.status == "EVALUATION_ERROR":
            add(q.display_number, it.error or "AI evaluation failed")
        elif it.status == "MISSING":
            if not getattr(it, "not_attempted_confirmed", False):
                res = resolve_student_answer(db, ev, q)
                if res.status == STUDENT_ANSWER_NOT_ATTEMPTED:
                    add(q.display_number, "No student answer found. Map an answer or confirm it was not attempted")
                elif res.status == STUDENT_ANSWER_MAPPING_REVIEW:
                    add(q.display_number, f"Student answer detected but mapping needs review: {res.reason}")
                elif res.status == STUDENT_ANSWER_UNMAPPED:
                    add(q.display_number, f"Student answer detected on page but remains unmapped: {res.reason}")
                elif res.status == STUDENT_ANSWER_OCR_FAILED:
                    add(q.display_number, f"Answer sheet OCR failed: {res.reason}")
                elif res.status in (STUDENT_ANSWER_RELATIONSHIP_ERROR, DATA_INTEGRITY_ERROR):
                    add(q.display_number, f"Database relationship error: {res.reason}")
                else:
                    add(q.display_number, "No student answer found. Map an answer or confirm it was not attempted")
        elif it.status == "EVALUATED":
            add(q.display_number, "Awaiting teacher approval")
        if it and it.final_marks is not None and q.max_marks is not None and it.final_marks > q.max_marks + 1e-9:
            add(q.display_number, f"Marks {it.final_marks:g} exceed maximum {q.max_marks:g}")
    return issues


def refresh_evaluation_status(db: Session, ev: Evaluation) -> None:
    if ev.status == "FINALIZED":
        return
    answers = db.query(StudentAnswer).filter_by(evaluation_id=ev.id).all()
    items = db.query(EvaluationItem).filter_by(evaluation_id=ev.id).all()
    if any(a.status in ("UNMAPPED", "NEEDS_REVIEW") for a in answers):
        ev.status = "MAPPING_REVIEW"
    elif not items or all(i.status == "PENDING" for i in items):
        ev.status = "OCR_REVIEW"
    elif not finalize_issues(db, ev):
        ev.status = "FINALIZABLE"
    elif any(i.status == "APPROVED" or i.teacher_overridden for i in items):
        ev.status = "TEACHER_REVIEW"
    elif any(i.status == "EVALUATED" for i in items):
        ev.status = "AI_EVALUATED"
    else:
        ev.status = "TEACHER_REVIEW"
    db.commit()


def finalize(db: Session, ev: Evaluation) -> None:
    qs = exam_questions(db, ev.exam_id)
    items = {i.exam_question_id: i for i in db.query(EvaluationItem).filter_by(evaluation_id=ev.id).all()}
    ev.total_marks = sum((items[q.id].final_marks or 0.0) for q in qs)
    ev.maximum_marks = sum((q.max_marks or 0.0) for q in qs)
    ev.percentage = round(100.0 * ev.total_marks / ev.maximum_marks, 2) if ev.maximum_marks else 0.0
    ev.status, ev.finalized_at = "FINALIZED", datetime.now(timezone.utc)
    db.commit()
