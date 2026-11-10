from __future__ import annotations
import logging
import re
import time
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from ..database import SessionLocal, is_locked
from dataclasses import dataclass, field
from ..models import AnswerKey, AnswerSheetDocument, Evaluation, Exam, ExamQuestion, EvaluationItem, StudentAnswer
from ..ocr import prompts
from ..documents.storage import abs_path
from ..ocr.internvl import AIResponseError, AIUnavailable, chat_structured, check_model
from ..config import ai_bad_response_message
from ..ocr.schemas import EvaluationResult
from .. import formatter
from ..formatter.common import choices
from ..formatter.common.mark_rules import EvaluationValidationError, validate_evaluation
from .job_queue import keyed_lock, submit
from .mapping_service import exam_questions, conflicting_answer_heading
from ..formatter.common.numbering import parent_number
from .state import set_state
from .audit import audit

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
# how each unresolved state is worded in the error shown to teachers (the codes themselves stay as they are)
_RESOLUTION_TEXT = {
    STUDENT_ANSWER_UNMAPPED: "Answer not mapped",
    STUDENT_ANSWER_OCR_FAILED: "Answer sheet could not be read",
    STUDENT_ANSWER_MAPPING_REVIEW: "Answer mapping needs review",
    STUDENT_ANSWER_GROUPING_ERROR: "Answer grouping problem",
    STUDENT_ANSWER_RELATIONSHIP_ERROR: "Answer record problem",
    DATA_INTEGRITY_ERROR: "Data integrity problem",
}


@dataclass
class ResolvedAnswer:
    status: str
    combined_text: str = ""
    primary_answer: StudentAnswer | None = None
    constituent_answers: list[StudentAnswer] = field(default_factory=list)
    reason: str | None = None


class ExamSnapshot:
    """The rows needed to judge sheets of one exam, fetched in a few bulk queries.

    The database is remote, so every query is a round trip; checking sheets question by question, sheet by sheet,
    made the review pages take tens of seconds. Rows are loaded fresh on construction: build a new one after changes.
    """

    def __init__(self, db: Session, exam_id: str, evs: list[Evaluation]):
        ids = [e.id for e in evs] or [""]
        self.questions = exam_questions(db, exam_id)
        self.keys: dict[str | None, list[AnswerKey]] = {}
        for k in db.query(AnswerKey).filter_by(exam_id=exam_id, is_active=True):
            self.keys.setdefault(k.exam_question_id, []).append(k)
        self.answers: dict[str, list[StudentAnswer]] = {i: [] for i in ids}
        for a in (db.query(StudentAnswer).filter(StudentAnswer.evaluation_id.in_(ids))
                  .order_by(StudentAnswer.page_number, StudentAnswer.position)):
            self.answers[a.evaluation_id].append(a)
        self.items: dict[str, list[EvaluationItem]] = {i: [] for i in ids}
        for it in db.query(EvaluationItem).filter(EvaluationItem.evaluation_id.in_(ids)):
            self.items[it.evaluation_id].append(it)
        doc_ids = [e.answer_sheet_id for e in evs if e.answer_sheet_id] or [""]
        self.docs = {d.id: d for d in db.query(AnswerSheetDocument).filter(AnswerSheetDocument.id.in_(doc_ids))}

    def unresolved(self, ev: Evaluation) -> bool:
        return any(a.status in ("UNMAPPED", "NEEDS_REVIEW") for a in self.answers.get(ev.id, []))


def resolve_student_answer(db: Session, ev: Evaluation, q: ExamQuestion, snap: ExamSnapshot | None = None) -> ResolvedAnswer:
    """Resolve student's answer for canonical question q.id across multiple sources:
    1. verified direct student_answer_group.question_id
    2. verified parent / subquestion mappings
    3. answer blocks belonging to mapped group (including cross-page continuations)
    4. precise diagnostic states if missing (not attempted vs mapping review vs unmapped vs ocr failed).
    """
    all_answers = snap.answers.get(ev.id, []) if snap else (
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
    all_exam_qs = snap.questions if snap else exam_questions(db, ev.exam_id)
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
        # Combine all answer blocks / cross-page continuations
        combined_parts = [a.answer_text.strip() for a in constituent if a.answer_text and a.answer_text.strip()]
        if getattr(q,"structure",None):
            combined_parts = [f"[{a.raw_question_number or q.display_number}]\n{a.answer_text.strip()}" for a in constituent if a.answer_text and a.answer_text.strip()]
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
        for answer in constituent:
            conflict = conflicting_answer_heading(answer.answer_text or "", q.normalized_number)
            if conflict:
                return ResolvedAnswer(
                    status=STUDENT_ANSWER_MAPPING_REVIEW,
                    primary_answer=answer,
                    constituent_answers=constituent,
                    reason=f"Answer text starts with question {conflict}, but is mapped to {q.display_number}. Review the mapping before grading.",
                )
        if combined_text.strip():
            return ResolvedAnswer(
                status=STUDENT_ANSWER_FOUND,
                combined_text=combined_text,
                primary_answer=constituent[0],
                constituent_answers=constituent,
            )
        # only the question number was written, nothing under it: not answered (0 marks), nothing to review
        return ResolvedAnswer(
            status=STUDENT_ANSWER_NOT_ATTEMPTED,
            primary_answer=constituent[0],
            constituent_answers=constituent,
            reason=f"Only the number {q.display_number} was written; no answer under it.",
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
    doc = None
    if ev.answer_sheet_id:
        doc = snap.docs.get(ev.answer_sheet_id) if snap else db.get(AnswerSheetDocument, ev.answer_sheet_id)
    if doc and doc.pages:
        failed_pages = [p.get("page_number") for p in doc.pages if p.get("ocr_status") != "OK"]
        if failed_pages:
            return ResolvedAnswer(
                status=STUDENT_ANSWER_OCR_FAILED,
                reason=f"Student answer sheet could not be read on page(s): {', '.join(map(str, failed_pages))}.",
            )

    # Truly not attempted
    return ResolvedAnswer(
        status=STUDENT_ANSWER_NOT_ATTEMPTED,
        reason="No student answer region detected anywhere for this question.",
    )


def active_key_for(db: Session, exam_id: str, question_id: str) -> AnswerKey | None:
    return (db.query(AnswerKey).filter_by(exam_id=exam_id, exam_question_id=question_id, is_active=True,
                                          mapping_status="MAPPED").first())


_POINT_CHECK = {"number": "final value", "unit": "SI unit", "equation": "equation", "exact": "exact answer",
                "meaning": "same meaning", "criterion": "band"}


def rubric_criteria(key: AnswerKey) -> list[str]:
    """The marking points the grader is given: the key's rubric as "[1 mark] (a) exact answer: since - Correct
    preposition choice", or the key's criteria lines when it has no rubric."""
    rubric = getattr(key, "rubric", None) or {}
    points = rubric.get("points") or []
    if not points:
        return list(key.criteria or [])
    out = []
    for p in points:
        m = p.get("marks")
        mark = f"{m:g} mark{'' if m == 1 else 's'}" if isinstance(m, (int, float)) else "marks"
        part = f" ({p['part']})" if p.get("part") else ""
        expects = f": {' / '.join(p['expected'])}" if p.get("expected") else ""
        out.append(f"[{mark}]{part} {_POINT_CHECK.get(p.get('kind'), 'same meaning')}{expects} - {p.get('text', '')}")
    for d in rubric.get("deductions") or []:
        out.append(f"[deduction] {d}")
    return out


def _reset_item(item: EvaluationItem) -> None:
    item.ai_marks = item.ai_decision = item.ai_feedback = item.ai_confidence = None
    item.matched_points, item.missing_points = [], []
    item.raw_response = item.error = None
    item.final_marks, item.teacher_overridden, item.teacher_feedback = None, False, None
    item.not_attempted_confirmed = False


_DRAWING = re.compile(r"\b(?:draw|drawn|diagram|sketch|figure|graph|plot|label(?:l?ed)?|flow\s?chart|circuit|"
                      r"ray\s+diagram|structure)\b|\[diagram", re.I)
DRAWING_NOTE = ("\nThe scanned page(s) the student wrote this answer on are attached. Use them only to check drawings, "
                "diagrams, graphs, structures and their labels that the transcription may describe incompletely; "
                "the transcription stays the student's answer for everything else.")

# TEMPORARY (2026-11-04): liberal marking on the user's request. Set False to go back to the normal rules.
LIBERAL_GRADING = False
LIBERAL_RULES = """LIBERAL MARKING (overrides any stricter rule above):
1. If the student's answer is partly correct against the key (the main idea, the right fact, the right method or the
   right final answer is present), award FULL marks for that question or criterion.
2. Give the benefit of the doubt everywhere: brief, incomplete, unclear or loosely worded answers that point the right
   way earn full credit; when torn between two marks, always choose the higher.
3. Do not deduct for missing steps, units, reasons, spelling, grammar, wording, format or presentation.
4. Award zero only when the answer is blank, entirely wrong, or unrelated to the question. MCQ: credit if the letter
   OR the option text is correct.
5. Never exceed the maximum marks; still note what was missing in feedback for the teacher."""


def drawing_image(db: Session, ev: Evaluation, q: ExamQuestion, key_text: str, answers: list, text: str):
    """The student's page(s) for a question that asks for or contains a drawing, as one image for the grader.

    Only such questions get an image (it costs more); others are graded on the transcription alone."""
    if not (_DRAWING.search(q.question_text or "") or _DRAWING.search(key_text or "") or "[Diagram" in (text or "")):
        return None
    doc = db.get(AnswerSheetDocument, ev.answer_sheet_id)
    numbers = sorted({a.page_number for a in answers if a.page_number})[:3]
    pages = {p.get("page_number"): p for p in (doc.pages if doc else [])}
    files = [abs_path(pages[n]["source_file"]) for n in numbers if n in pages and pages[n].get("source_file")]
    files = [f for f in files if f.exists()]
    if not files:
        return None
    from PIL import Image
    images = [Image.open(f).convert("RGB") for f in files]
    width = 1100
    images = [im.resize((width, round(im.height * width / im.width))) for im in images]
    sheet = Image.new("RGB", (width, sum(im.height for im in images)), "white")
    y = 0
    for im in images:
        sheet.paste(im, (0, y))
        y += im.height
    out = abs_path(doc.original_file).parent / "grading" / f"{q.id}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, "JPEG", quality=80)
    return out


_references: dict = {}


def textbook_references(db: Session, exam, q: ExamQuestion, key) -> list:
    """NCERT passages for a question, found once per question and key and reused for every student.
    Background reference only: the answer key's marking scheme alone decides the marks."""
    from ..config import get_settings
    if not get_settings().reference_in_grading:
        return []
    cache_key = (getattr(q, "id", None), getattr(key, "id", None), getattr(q, "question_text", ""), getattr(key, "answer_text", ""))
    if cache_key not in _references:
        try:
            from ..reference.search import retrieve, subject_of
            scope = subject_of(exam)
            _references[cache_key] = retrieve(db, f"{q.question_text}\n{key.answer_text}", *scope,
                                              kinds=["TEXTBOOK", "TEXTBOOK_ANSWERS"], k=3) if scope else []
        except Exception:  # the library is reference only: grading goes on without it
            log.exception("Textbook reference lookup failed for question %s", q.id)
            _references[cache_key] = []
        if len(_references) > 500:
            _references.pop(next(iter(_references)))
    return _references[cache_key]


REGRADE_HINT = ("\n\nIMPORTANT: your previous reply was rejected: {problem}. Reply again. Give an award for each "
                "criterion of the scheme you can judge, and for every mark above 0 copy evidence_quotes character for "
                "character from the student's answer above (same symbols, numbers and spacing); never describe or "
                "paraphrase the answer inside a quote.")
UNVERIFIED_CONFIDENCE = 0.4  # below LOW_CONFIDENCE: the teacher is told before a bulk finalize
GRADING_TRIES = 2  # the first reply and one retry told what was wrong (strict marking)


def _grade_until_valid(ask, prompt, check, number):
    """Strict marking: the grader's reply must pass the marking-scheme check. A rejected reply is asked for once more
    (GRADING_TRIES in all), told exactly what was wrong; a reply still rejected raises EvaluationValidationError, so the
    question shows an error for the teacher instead of a mark the check could not confirm. Quoted evidence must be
    found in the student's transcription; there is no lenient fallback."""
    problem = None
    for attempt in range(GRADING_TRIES):
        try:
            call = ask(prompt if problem is None else prompt + REGRADE_HINT.format(problem=problem))
        except AIResponseError as e:
            problem = f"the reply was not valid JSON ({e.detail[:120]})"
            if attempt == GRADING_TRIES - 1:
                raise
            continue
        try:
            return check(call.parsed), call.raw
        except EvaluationValidationError as e:
            problem = str(e)
            log.info("Q%s grading reply %d rejected (%s)", number, attempt + 1, e)
            if attempt == GRADING_TRIES - 1:
                raise
    raise EvaluationValidationError(problem or "no usable grading reply")


def _flag(res, why):
    res.confidence = min(res.confidence if res.confidence is not None else 1.0, UNVERIFIED_CONFIDENCE)
    res.feedback = f"Check this mark: {why}.\n{res.feedback or ''}".strip()


def evaluate_item(db: Session, ev: Evaluation, q: ExamQuestion, item: EvaluationItem, model: str | None = None) -> None:
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
        fmt = formatter.current()  # the subject's own grading rules, see app/formatter
        # "write on any one topic" answered on several: each graded, the best counts
        attempts = fmt.grading_attempts(q.question_text, resolved.combined_text) or [(None, resolved.combined_text)]
        from ..cbse import grading
        exam_record = db.get(Exam, ev.exam_id)
        cbse = bool(getattr(exam_record, "standard_profile_id", None))
        options = _grading_options(exam_record, ev) if cbse else {}  # with the Part B option this student answered
        references = textbook_references(db, exam_record, q, key)  # with an answer key too: reference only
        instructions = []
        if cbse:
            from ..cbse.validation import active_doc
            from ..models import AnswerKeyDocument
            scheme_doc = active_doc(db, AnswerKeyDocument, exam_record.id)
            instructions = ((scheme_doc.extraction if scheme_doc else None) or {}).get("instructions", [])
        rules = fmt.grading_rules(q.question_text, key.answer_text)  # language subjects: by question kind
        try:
            graded = []
            for title, text in attempts:
                if cbse:
                    prompt = grading.prompt(q, key, text, options, instructions, references)
                    system = grading.SYSTEM
                else:
                    prompt = prompts.evaluation_prompt(q.display_number, q.question_text, key.answer_text, rubric_criteria(key),
                                                       key.accepted_answers, key.keywords, q.max_marks, text)
                    prompt += "\n" + grading.textbook_block(references)
                    system = prompts.EVAL_SYSTEM
                if rules:
                    prompt += "\n" + rules
                if LIBERAL_GRADING:
                    prompt += "\n" + LIBERAL_RULES
                audit(db, exam_id=ev.exam_id, teacher_id=exam_record.teacher_id, entity_type="evaluation", entity_id=ev.id,
                      action="ai_grading_request")
                db.commit()
                try:
                    picture = drawing_image(db, ev, q, key.answer_text, resolved.constituent_answers, text)
                except Exception:  # a page image that cannot be read: grade on the transcription alone
                    log.exception("Could not build the drawing image for question %s", q.id)
                    picture = None

                def ask(user, picture=picture, system=system):
                    if picture:  # only drawing questions carry the sheet picture (and its extra cost)
                        return chat_structured(system, user + DRAWING_NOTE, EvaluationResult, image_path=picture, model=model)
                    return chat_structured(system, user, EvaluationResult, model=model)

                def check(parsed, text=text):
                    if cbse:
                        return grading.validate_result(parsed, q, key, options, text)
                    res = validate_evaluation(parsed, q.max_marks)  # type: ignore[arg-type]
                    return fmt.check_deductions(res, text, key.answer_text, q.max_marks)

                res, raw = _grade_until_valid(ask, prompt, check, q.display_number)
                item.raw_response = raw
                graded.append((title, res, raw))
            title, res, _ = max(graded, key=lambda g: g[1].marks_awarded)  # the first of equal best
            item.ai_marks, item.ai_decision = res.marks_awarded, res.decision
            item.matched_points, item.missing_points = res.matched_points, res.missing_points
            item.ai_feedback, item.ai_confidence = res.feedback, res.confidence
            if len(graded) > 1:
                item.raw_response = "\n\n".join(f"--- {t} ---\n{raw}" for t, _, raw in graded)
                scores = "; ".join(f"{t}: {r.marks_awarded:g}/{q.max_marks:g}" for t, r, _ in graded)
                item.ai_feedback = (f"Asked for one topic; {len(graded)} were answered. Each was graded and the best "
                                    f"counts: {title}. Scores: {scores}.\n{res.feedback or ''}").strip()
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
            item.status, item.error = "EVALUATION_ERROR", f"{ai_bad_response_message()} {e.detail}"
            for a in resolved.constituent_answers:
                a.status = "MAPPED"
            log.error("Eval AI error q=%s: %s", q.display_number, e.detail)
        except AIUnavailable:
            for a in resolved.constituent_answers:
                a.status = "MAPPED"
            db.commit()
            raise
        except Exception as e:  # never leave answers stuck in EVALUATING: record the failure on this question
            log.exception("Grading failed for question %s", q.display_number)
            db.rollback()
            item.status, item.error = "EVALUATION_ERROR", f"Grading failed: {e}"
            for a in resolved.constituent_answers:
                a.status = "MAPPED"
        db.commit()
        return

    elif resolved.status == STUDENT_ANSWER_NOT_ATTEMPTED:
        item.status = "MISSING"
        item.final_marks = 0.0
        item.not_attempted_confirmed = True
        if q.choice_group:
            item.ai_feedback = f"Either/or question {q.choice_group}: this alternative was not answered; only one counts."
        elif q.answer_any and not q.compulsory:
            item.ai_feedback = f"Not answered. The section asks for any {q.answer_any}; the best {q.answer_any} count."
        elif resolved.constituent_answers:
            item.ai_feedback = "Not answered: only the question number was written."
        else:
            item.ai_feedback = "Question was not attempted by student."
        item.error = None
        db.commit()
        return

    else:
        item.status = "EVALUATION_ERROR"
        item.error = f"{_RESOLUTION_TEXT.get(resolved.status, resolved.status)}: {resolved.reason}"
        db.commit()
        return


# A run stopped because the AI service was down is started again by itself, waiting longer each time.
RUN_RETRY_DELAYS = (60, 180, 600, 1800)  # seconds
_run_retries: dict[str, int] = {}


def _schedule_run_retry(ev_id: str, exam_id: str, only_question_ids: list[str] | None) -> None:
    import threading
    from ..config import get_settings
    from .job_queue import submit
    tries = _run_retries.get(ev_id, 0)
    if get_settings().job_queue_inline or tries >= len(RUN_RETRY_DELAYS):
        _run_retries.pop(ev_id, None)
        return  # the teacher runs it again (review_reasons says so)
    _run_retries[ev_id] = tries + 1
    timer = threading.Timer(RUN_RETRY_DELAYS[tries], submit, (exam_id, run_evaluation, ev_id, only_question_ids))
    timer.daemon = True
    timer.start()
    log.info("Evaluation %s: AI unavailable, running again in %ss (try %s)", ev_id, RUN_RETRY_DELAYS[tries], tries + 1)
LOCK_RETRIES = 4


def _still_to_grade(ev_id: str) -> list[str]:
    """Questions of the sheet without a mark yet (a run interrupted by a busy database resumes with only these)."""
    db = SessionLocal()
    try:
        ev = db.get(Evaluation, ev_id)
        done = {it.exam_question_id for it in db.query(EvaluationItem).filter_by(evaluation_id=ev_id)
                if it.status in ("EVALUATED", "APPROVED") or it.teacher_overridden}
        return [q.id for q in exam_questions(db, ev.exam_id) if q.id not in done]
    finally:
        db.close()


def _grading_options(exam: Exam, ev: Evaluation) -> dict:
    """The exam's version choices, with the Part B option this student answered."""
    options = dict(exam.standard_options or {})
    if ev.part_b_option and not options.get("accountancy_option"):
        options["accountancy_option"] = ev.part_b_option
    return options


def run_evaluation(ev_id: str, only_question_ids: list[str] | None = None) -> None:
    with keyed_lock(f"evaluation:{ev_id}"):  # jobs run in parallel; one grading run per sheet at a time
        todo = only_question_ids
        for attempt in range(1, LOCK_RETRIES + 1):
            if _run_evaluation(ev_id, todo, last=attempt == LOCK_RETRIES):
                break
            log.warning("Database busy while grading %s; retrying (%d/%d)", ev_id, attempt, LOCK_RETRIES)
            time.sleep(3 * attempt)
            todo = [q for q in _still_to_grade(ev_id) if not only_question_ids or q in only_question_ids]
            if not todo:
                break
        if not only_question_ids:  # a whole-sheet run; a teacher re-grading one question finishes it themselves
            from . import autopilot
            autopilot.after_grading(ev_id)


def _run_evaluation(ev_id: str, only_question_ids: list[str] | None, last: bool = True) -> bool:
    """False when the run hit a busy database and should be run again for the questions still unmarked."""
    db = SessionLocal()
    try:
        ev = db.get(Evaluation, ev_id)
        exam = db.get(Exam, ev.exam_id)
        ev.run_status = "RUNNING"
        audit(db, exam_id=exam.id, teacher_id=exam.teacher_id, entity_type="evaluation", entity_id=ev.id,
              action="ai_evaluation_started", new={"question_retry": bool(only_question_ids)})
        if exam.status in ("READY_FOR_EVALUATION", "REVIEW_REQUIRED", "EVALUATING"):
            set_state(exam, "EVALUATING")
        db.commit()
        try:
            model = None  # the configured grading model grades every language
            check_model()
            qs = [q for q in exam_questions(db, ev.exam_id) if not only_question_ids or q.id in only_question_ids]
            ev.run_total, ev.run_progress = len(qs), 0
            db.commit()
            if not ev.part_b_option:
                from .part_b import student_option
                ev.part_b_option = student_option(db, ev)
                db.commit()
            existing = {}
            for it in db.query(EvaluationItem).filter_by(evaluation_id=ev.id).all():
                existing.setdefault(it.exam_question_id, it)
            for q in qs:
                item = existing.get(q.id)
                if item is None:
                    item = EvaluationItem(evaluation_id=ev.id, exam_question_id=q.id)
                    db.add(item)
                    db.flush()
                # bulk runs never overwrite a teacher's approved/overridden work
                if not only_question_ids and (item.status == "APPROVED" or item.teacher_overridden):
                    ev.run_progress += 1
                    db.commit()
                    continue
                evaluate_item(db, ev, q, item, model)
                ev.run_progress += 1
                db.commit()
            ev.run_status = "DONE"
        except AIUnavailable as e:
            log.error("AI unavailable during evaluation: %s", e.detail)
            ev.run_status = "ERROR"
            _schedule_run_retry(ev.id, exam.id, only_question_ids)
        else:
            _run_retries.pop(ev.id, None)
        db.refresh(exam)
        others_running = db.query(Evaluation).filter(Evaluation.exam_id == exam.id, Evaluation.id != ev.id,
                                                     Evaluation.run_status == "RUNNING").first()
        if exam.status == "EVALUATING" and not others_running:  # the last sheet still grading moves the exam on
            set_state(exam, "REVIEW_REQUIRED")
        db.commit()
        refresh_evaluation_status(db, ev)
        audit(db, exam_id=exam.id, teacher_id=exam.teacher_id, entity_type="evaluation", entity_id=ev.id,
              action="ai_evaluation_failed" if ev.run_status == "ERROR" else "ai_evaluation_completed")
        db.commit()
    except Exception as e:
        db.rollback()
        if is_locked(e) and not last:
            return False
        log.exception("Evaluation run crashed")
        ev = db.get(Evaluation, ev_id)
        if ev:
            ev.run_status = "ERROR"
            failed_exam = db.get(Exam, ev.exam_id)
            audit(db, exam_id=ev.exam_id, teacher_id=failed_exam.teacher_id, entity_type="evaluation", entity_id=ev.id,
                  action="ai_evaluation_failed")
            db.commit()
    finally:
        db.close()
    return True


def confirm_not_attempted(db: Session, ev: Evaluation, snap: ExamSnapshot | None = None) -> None:
    """Once every student answer is mapped, a MISSING question with no answer on the sheet is not attempted: 0 marks."""
    snap = snap or ExamSnapshot(db, ev.exam_id, [ev])
    if snap.unresolved(ev):
        return
    qs = {q.id: q for q in snap.questions}
    for it in snap.items[ev.id]:
        if _settled_as_not_answered(db, ev, it, qs, snap):
            # graded before "only the number written" counted as not answered: settle it the same way now
            it.status, it.error, it.final_marks = "MISSING", None, 0.0
            it.ai_feedback = "Not answered: only the question number was written."
        if it.status != "MISSING" or it.not_attempted_confirmed:
            continue
        q = qs.get(it.exam_question_id)
        if q is not None and resolve_student_answer(db, ev, q, snap).status == STUDENT_ANSWER_NOT_ATTEMPTED:
            it.not_attempted_confirmed = True
            if it.final_marks is None:
                it.final_marks = 0.0


def _settled_as_not_answered(db: Session, ev: Evaluation, it: EvaluationItem, qs: dict, snap: ExamSnapshot) -> bool:
    """An item left in error only because its answer had a number but no text: now that is simply not answered."""
    if it.status != "EVALUATION_ERROR" or it.final_marks is not None or "no transcribed text" not in (it.error or ""):
        return False
    q = qs.get(it.exam_question_id)
    return q is not None and resolve_student_answer(db, ev, q, snap).status == STUDENT_ANSWER_NOT_ATTEMPTED


def finalize_issues(db: Session, ev: Evaluation, snap: ExamSnapshot | None = None) -> list[dict]:
    """Read-only: lists what still blocks finalizing. Call confirm_not_attempted() first to settle unanswered items."""
    snap = snap or ExamSnapshot(db, ev.exam_id, [ev])
    qs = snap.questions
    issues: list[dict] = []

    def add(question: str, reason: str):
        issues.append({"question": question, "reason": reason})

    if not qs or any(q.verification_status != "VERIFIED" for q in qs):
        add("Exam", "Question paper is not verified")
    for q in qs:
        mapped = [k for k in snap.keys.get(q.id, []) if k.mapping_status == "MAPPED"]
        if len(mapped) != 1 or mapped[0].verification_status != "VERIFIED":
            add(q.display_number, "Answer key is missing, duplicated or not verified")
        elif mapped[0].mark_mismatch:
            add(q.display_number, "Answer key marks disagree with the question's maximum marks")
    for a in snap.answers[ev.id]:
        if a.status in ("UNMAPPED", "NEEDS_REVIEW"):
            label = a.raw_question_number or "(no question number)"
            add(label, "Student answer is unmapped" if a.status == "UNMAPPED"
                else f"Student answer needs mapping review: {a.mapping_note or ''}".strip())
    items = {i.exam_question_id: i for i in snap.items[ev.id]}
    by_id = {q.id: q for q in qs}
    for q in qs:
        it = items.get(q.id)
        if it is None or it.status == "PENDING":
            add(q.display_number, "Not evaluated yet")
        elif _settled_as_not_answered(db, ev, it, by_id, snap):
            pass  # confirm_not_attempted() turns it into "not answered" (0 marks) on the next refresh or finalize
        elif it.status == "EVALUATION_ERROR":
            add(q.display_number, it.error or "AI evaluation failed")
        elif it.status == "MISSING":
            if not getattr(it, "not_attempted_confirmed", False):
                res = resolve_student_answer(db, ev, q, snap)
                if res.status == STUDENT_ANSWER_NOT_ATTEMPTED:
                    pass  # an unanswered question is 0 marks, not a review
                elif res.status == STUDENT_ANSWER_MAPPING_REVIEW:
                    add(q.display_number, f"Student answer detected but mapping needs review: {res.reason}")
                elif res.status == STUDENT_ANSWER_UNMAPPED:
                    add(q.display_number, f"Student answer detected on page but remains unmapped: {res.reason}")
                elif res.status == STUDENT_ANSWER_OCR_FAILED:
                    add(q.display_number, f"Answer sheet could not be read: {res.reason}")
                elif res.status in (STUDENT_ANSWER_RELATIONSHIP_ERROR, DATA_INTEGRITY_ERROR):
                    add(q.display_number, f"Database relationship error: {res.reason}")
        elif it.status == "EVALUATED":
            add(q.display_number, "Awaiting teacher approval")
        if it and it.final_marks is not None and q.max_marks is not None and it.final_marks > q.max_marks + 1e-9:
            add(q.display_number, f"Marks {it.final_marks:g} exceed maximum {q.max_marks:g}")
    return issues


def refresh_evaluation_status(db: Session, ev: Evaluation) -> None:
    if ev.status == "FINALIZED":
        return
    db.flush()  # the snapshot is read from the database, so pending changes must be there first
    snap = ExamSnapshot(db, ev.exam_id, [ev])
    confirm_not_attempted(db, ev, snap)
    items = snap.items[ev.id]
    if snap.unresolved(ev):
        ev.status = "MAPPING_REVIEW"
    elif not items or all(i.status == "PENDING" for i in items):
        ev.status = "OCR_REVIEW"
    elif not finalize_issues(db, ev, snap):
        ev.status = "FINALIZABLE"
    elif any(i.status == "APPROVED" or i.teacher_overridden for i in items):
        ev.status = "TEACHER_REVIEW"
    elif any(i.status == "EVALUATED" for i in items):
        ev.status = "AI_EVALUATED"
    else:
        ev.status = "TEACHER_REVIEW"
    db.commit()


def approve_clean_items(db: Session, ev: Evaluation) -> int:
    """Approve every cleanly evaluated item and confirm genuine unattempted items; returns how many were approved."""
    mapping_complete = not any(a.status in ("UNMAPPED", "NEEDS_REVIEW")
                               for a in db.query(StudentAnswer).filter_by(evaluation_id=ev.id).all())
    n = 0
    for it in db.query(EvaluationItem).filter_by(evaluation_id=ev.id):
        if it.status == "EVALUATED":
            it.status = "APPROVED"
            n += 1
            if it.student_answer_id and (a := db.get(StudentAnswer, it.student_answer_id)):
                a.status = "APPROVED"
        elif it.status == "MISSING" and (it.not_attempted_confirmed or mapping_complete):
            it.not_attempted_confirmed = True
            if it.final_marks is None:
                it.final_marks = 0.0
            it.status = "APPROVED"
            n += 1
    return n


_EVALUATABLE_EXAM = ("READY_FOR_EVALUATION", "EVALUATING", "REVIEW_REQUIRED")


def auto_evaluate_sheet(doc_id: str) -> None:
    """Grade a freshly read sheet straight away when nothing needs the teacher first (pages read, answers mapped).

    Sheets with unread pages or unmapped answers are left for the teacher; review_reasons() lists why. Grading is
    queued as its own OpenRouter job, using the subject's model (Settings.model_for).
    """
    from . import autopilot
    db = SessionLocal()
    try:
        ev = db.query(Evaluation).filter_by(answer_sheet_id=doc_id).first()
        doc = db.get(AnswerSheetDocument, doc_id)
        if ev is None or doc is None or ev.status == "FINALIZED" or ev.run_status == "RUNNING":
            return
        if doc.status == "NEEDS_ATTENTION" and autopilot.enabled():
            identity = dict(doc.identity or {})
            if not identity.get("autopilot_reread"):  # one more reading of the pages that failed, then grade
                identity["autopilot_reread"] = True
                doc.identity = identity
                db.commit()
                from .student_identity import run_sheet
                submit(ev.exam_id, run_sheet, doc_id)
                return
            doc.status, doc.stage = "READY", "Ready (some pages could not be read)"
            db.commit()
        if doc.status != "READY":
            return
        if db.get(Exam, ev.exam_id).status not in _EVALUATABLE_EXAM:
            return
        try:
            autopilot.settle_answers(db, ev)  # answers the rules could not place, settled by the AI
        except AIUnavailable:
            pass
        except Exception:
            log.exception("Autopilot could not settle the answers of sheet %s", doc_id)
        if any(a.status in ("UNMAPPED", "NEEDS_REVIEW") for a in db.query(StudentAnswer).filter_by(evaluation_id=ev.id)):
            return
        ev.run_status, ev.run_progress = "RUNNING", 0
        db.commit()
        ev_id, exam_id = ev.id, ev.exam_id
    finally:
        db.close()
    submit(exam_id, run_evaluation, ev_id, grading=True)


def review_reasons(db: Session, ev: Evaluation, snap: ExamSnapshot) -> list[dict]:
    """Why this sheet cannot be finalized together with the others.

    AI marks still awaiting approval are not listed: finalizing all sheets approves them.
    """
    doc = snap.docs.get(ev.answer_sheet_id)
    issues = [i for i in finalize_issues(db, ev, snap) if i["reason"] != "Awaiting teacher approval"]
    items = snap.items[ev.id]
    check = ((doc.identity or {}).get("roll_check") or {}) if doc is not None else {}
    nothing_graded = not items or all(i.status == "PENDING" for i in items)
    if snap.unresolved(ev) or check.get("status") == "MISMATCH" or nothing_graded:
        # every question reads "Not evaluated yet" until the sheet is graded; one line with the cause says it better
        issues = [i for i in issues if i["reason"] != "Not evaluated yet"]
        if check.get("status") == "MISMATCH":
            reason = (f"Roll number check: typed {check.get('typed')}, the sheet says {check.get('written')}. "
                      "Choose the right roll number in the answer sheets list; grading starts after that.")
        elif snap.unresolved(ev):
            reason = "Not graded yet. Fix the answer mapping, then run the evaluation."
        else:
            reason = "Not graded yet. Run the evaluation for this sheet."
        issues.append({"question": "Roll number" if check.get("status") == "MISMATCH" else "Evaluation", "reason": reason})
    other = ((doc.identity or {}).get("other_roll_pages") or []) if doc is not None else []
    if other:
        # an additional sheet carries the student's own roll number, often misread ("16202" for 12B02): only a roll
        # number of ANOTHER student of this class means another student's page
        from .sheet_pages import roll_key
        from ..models import Student
        exam_row = db.get(Exam, ev.exam_id)
        others = {roll_key(s.roll_number) for s in db.query(Student).filter(Student.class_id == exam_row.class_id,
                                                                            Student.id != ev.student_id)}
        other = [o for o in other if roll_key(o.get("roll_number")) in others]
    if other:
        listed = ", ".join(f"page {o['page']} ({o['roll_number']})" for o in other)
        issues.insert(0, {"question": "Answer sheet", "reason": f"Some pages show another roll number: {listed}. "
                                                               "Check they belong to this student."})
    if doc is not None and doc.status == "NEEDS_ATTENTION":
        issues.insert(0, {"question": "Answer sheet", "reason": "Some pages could not be read. Retry them first."})
    if ev.run_status == "ERROR":
        issues.insert(0, {"question": "Evaluation", "reason": "The AI evaluation stopped with an error. Run it again."})
    # reviews are raised only for an unmapped question or answer and for marks that disagree; empty pages, unanswered
    # questions and the AI's own confidence in its marks are not reasons to hold a sheet
    return issues


def finalize(db: Session, ev: Evaluation) -> None:
    qs = exam_questions(db, ev.exam_id)
    items = {i.exam_question_id: i for i in db.query(EvaluationItem).filter_by(evaluation_id=ev.id).all()}
    counted_qs = choices.counted(qs, {qid: it.final_marks for qid, it in items.items()})
    ev.total_marks = sum(((items[q.id].final_marks if q.id in items else None) or 0.0) for q in counted_qs)
    ev.maximum_marks = sum((q.max_marks or 0.0) for q in counted_qs)
    ev.percentage = round(100.0 * ev.total_marks / ev.maximum_marks, 2) if ev.maximum_marks else 0.0
    ev.status, ev.finalized_at = "FINALIZED", datetime.now(timezone.utc)
    db.commit()
