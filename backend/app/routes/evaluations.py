from __future__ import annotations
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload
from ..database import get_db
from ..deps import err, get_evaluation, get_exam
from ..models import (AnswerKey, AnswerSheetDocument, AuditLog, Evaluation, EvaluationItem, Exam, ExamQuestion,
                      Student, StudentAnswer, Teacher)
from ..security import current_teacher
from ..serializers import (EVALUATION_VIEW_LOAD, answer_view, doc_view, evaluation_view, item_view, question_view,
                           student_view)
from ..formatter.common import choices
from ..services.audit import audit
from ..services.job_queue import submit
from ..services.exam_files import purge_exam_files, save_reports_and_schedule
from ..services.evaluation_service import (ExamSnapshot, approve_clean_items, finalize, finalize_issues,
                                           refresh_evaluation_status, review_reasons, run_evaluation)
from ..formatter.common.k_level import summarize as summarize_outcomes
from ..formatter.common.mapping import map_label
from ..services.mapping_service import apply_student_mapping, exam_questions, mapping_summary
from ..formatter.common.numbering import normalize_question_number
from ..services.school_reports import build_evaluation_pdf_report, build_exam_pdf_report
from ..services.state import set_state
from ..services.student_identity import in_flight
from ..config import get_settings
from ..workspaces import exams_query

router = APIRouter(prefix="/api")


def _not_finalized(ev: Evaluation):
    if ev.status == "FINALIZED":
        raise err(409, "EVALUATION_FINALIZED", "This evaluation is finalized and can no longer be changed.")


@router.get("/evaluations")
def list_evaluations(exam_id: str | None = Query(None), db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    if exam_id:
        get_exam(db, t, exam_id)
    exam_ids = [e.id for e in exams_query(db, t)]
    q = db.query(Evaluation).options(*EVALUATION_VIEW_LOAD).filter(Evaluation.exam_id.in_(exam_ids or [""]))
    if exam_id:
        q = q.filter(Evaluation.exam_id == exam_id)
    return [evaluation_view(e) for e in q.order_by(Evaluation.created_at.desc())]


@router.get("/evaluations/{ev_id}")
def evaluation_detail(ev_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    ev = get_evaluation(db, t, ev_id)
    exam = db.get(Exam, ev.exam_id)
    doc = db.get(AnswerSheetDocument, ev.answer_sheet_id)
    qs = exam_questions(db, ev.exam_id)
    keys = {k.exam_question_id: k for k in db.query(AnswerKey).filter_by(exam_id=ev.exam_id, is_active=True, mapping_status="MAPPED")}
    answers = db.query(StudentAnswer).filter_by(evaluation_id=ev.id).order_by(StudentAnswer.position).all()
    items = db.query(EvaluationItem).filter_by(evaluation_id=ev.id).all()
    return {
        "evaluation": evaluation_view(ev), "exam": {"id": exam.id, "name": exam.name, "status": exam.status},
        "document": doc_view(doc, "answer-sheet"),
        "questions": [{**question_view(q), "official_answer": keys[q.id].answer_text if q.id in keys else None,
                       "criteria": keys[q.id].criteria if q.id in keys else []} for q in qs],
        "answers": [answer_view(a) for a in answers],
        "items": [item_view(i) for i in items],
        "summary": mapping_summary(db, ev),
        "issues": [] if ev.status == "FINALIZED" else finalize_issues(db, ev),
        "outcomes": summarize_outcomes(choices.counted(qs, marks := {i.exam_question_id: i.final_marks for i in items}),
                                       marks),
    }


# ---------- mapping ----------
@router.get("/evaluations/{ev_id}/mapping")
def get_mapping(ev_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    ev = get_evaluation(db, t, ev_id)
    qs = {q.id: q for q in exam_questions(db, ev.exam_id)}
    answers = db.query(StudentAnswer).filter_by(evaluation_id=ev.id).order_by(StudentAnswer.position).all()
    rows = [{**answer_view(a),
             "mapped_question": ({"id": qs[a.exam_question_id].id, "display_number": qs[a.exam_question_id].display_number,
                                  "question_text": qs[a.exam_question_id].question_text}
                                 if a.exam_question_id in qs else None)} for a in answers]
    summary = mapping_summary(db, ev)
    missing = [{"id": qid, "display_number": qs[qid].display_number, "question_text": qs[qid].question_text}
               for qid in summary.pop("missing_question_ids") if qid in qs]
    return {"summary": summary, "answers": rows, "missing_questions": missing,
            "questions": [{"id": q.id, "display_number": q.display_number, "question_text": q.question_text} for q in qs.values()]}


@router.post("/evaluations/{ev_id}/mapping")
def recompute_mapping(ev_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    """Re-run the deterministic mapping for answers the teacher has not decided yet."""
    ev = get_evaluation(db, t, ev_id)
    _not_finalized(ev)
    apply_student_mapping(db, ev)
    db.commit()
    refresh_evaluation_status(db, ev)
    return mapping_summary(db, ev) | {"status": ev.status}


class MappingPatch(BaseModel):
    exam_question_id: str | None = None
    confirm: bool | None = None            # accept the current automatic mapping
    accept_suggestion: bool | None = None  # accept top candidate suggestion
    unmap: bool | None = None
    raw_question_number: str | None = None
    answer_text: str | None = None
    ignore: bool | None = None
    restore: bool | None = None
    reason: str | None = None


@router.patch("/evaluations/{ev_id}/mapping/{answer_id}")
def patch_mapping(ev_id: str, answer_id: str, body: MappingPatch, bg: BackgroundTasks,
                  db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    ev = get_evaluation(db, t, ev_id)
    _not_finalized(ev)
    a = db.get(StudentAnswer, answer_id)
    if not a or a.evaluation_id != ev.id:
        raise err(404, "NOT_FOUND", "Answer not found.")
    qs = exam_questions(db, ev.exam_id)
    d = body.model_dump(exclude_unset=True)
    reason = d.pop("reason", None)
    affected: set[str] = {a.exam_question_id} if a.exam_question_id else set()

    def log(action, old, new):
        audit(db, exam_id=ev.exam_id, teacher_id=t.id, entity_type="student_answer", entity_id=a.id,
              action=action, old=old, new=new, reason=reason)

    if d.get("answer_text") is not None and d["answer_text"] != a.answer_text:
        log("student_answer_edited", a.answer_text, d["answer_text"])
        a.answer_text = d["answer_text"]
    if d.get("raw_question_number") is not None and d["raw_question_number"] != a.raw_question_number:
        log("student_answer_label_changed", a.raw_question_number, d["raw_question_number"])
        a.raw_question_number, a.mapping_confirmed = d["raw_question_number"], False
        if a.status not in ("IGNORED",):
            a.status = "UNMAPPED"
            res = map_label(a.raw_question_number, qs, a.ocr_confidence, get_settings().min_label_confidence,
                            answer_text=a.answer_text, answer_position=a.position)
            a.normalized_number, a.exam_question_id = res.normalized_number, res.question_id
            a.mapping_note, a.mapping_candidates = res.note, res.candidates
            a.status = res.status if res.status != "MAPPED" else "MAPPED"
    if d.get("accept_suggestion"):
        if not a.mapping_candidates:
            raise err(400, "NO_SUGGESTION", "This answer has no candidate suggestions.")
        top_qid = a.mapping_candidates[0]
        q = next((x for x in qs if x.id == top_qid), None)
        if not q:
            raise err(400, "INVALID_QUESTION", "Candidate question not found in exam.")
        log("student_answer_suggestion_accepted", a.exam_question_id, q.id)
        a.exam_question_id, a.normalized_number = q.id, q.normalized_number
        a.mapping_confirmed, a.status, a.mapping_note, a.mapping_candidates = True, "MAPPED", "Accepted candidate suggestion", []
    elif d.get("exam_question_id"):
        q = next((x for x in qs if x.id == d["exam_question_id"]), None)
        if not q:
            raise err(400, "INVALID_QUESTION", "That question does not belong to this exam.")
        log("student_answer_mapping_changed", a.exam_question_id, q.id)
        a.exam_question_id, a.normalized_number = q.id, q.normalized_number
        a.mapping_confirmed, a.status, a.mapping_note, a.mapping_candidates = True, "MAPPED", "Confirmed by teacher", []
    elif d.get("confirm"):
        if not a.exam_question_id:
            raise err(400, "NOTHING_TO_CONFIRM", "This answer has no suggested question. Choose one.")
        log("student_answer_mapping_confirmed", None, a.exam_question_id)
        a.mapping_confirmed, a.status, a.mapping_note = True, "MAPPED", "Confirmed by teacher"
    elif d.get("unmap"):
        log("student_answer_unmapped", a.exam_question_id, None)
        a.exam_question_id, a.mapping_confirmed, a.status, a.mapping_note = None, False, "UNMAPPED", "Unmapped by teacher"
    if d.get("ignore"):
        log("student_answer_ignored", a.status, "IGNORED")
        a.status, a.mapping_confirmed = "IGNORED", False
    elif d.get("restore") and a.status == "IGNORED":
        log("student_answer_restored", "IGNORED", "UNMAPPED")
        a.status = "UNMAPPED"
    if a.exam_question_id:
        affected.add(a.exam_question_id)
    # any change to an answer invalidates evaluation of the questions it touched
    if a.status in ("EVALUATING", "EVALUATED", "APPROVED"):
        a.status = "MAPPED"
    db.flush()
    apply_student_mapping(db, ev)
    stale = [i for i in db.query(EvaluationItem).filter(EvaluationItem.evaluation_id == ev.id,
                                                        EvaluationItem.exam_question_id.in_(affected or [""])).all()]
    for i in stale:
        i.status = "PENDING"
        i.final_marks = i.ai_marks = None
        i.teacher_overridden = False
        log_audit = audit
        log_audit(db, exam_id=ev.exam_id, teacher_id=t.id, entity_type="evaluation_item", entity_id=i.id,
                  action="evaluation_invalidated_by_answer_change", reason=reason)
    db.commit()
    refresh_evaluation_status(db, ev)
    # re-run evaluation for the affected questions (only if the full run already happened)
    rerun = [i.exam_question_id for i in stale
             if not any(x.status in ("UNMAPPED", "NEEDS_REVIEW") for x in db.query(StudentAnswer).filter_by(evaluation_id=ev.id))]
    if rerun and ev.run_status == "DONE":
        ev.run_status = "RUNNING"
        db.commit()
        bg.add_task(submit, ev.exam_id, run_evaluation, ev.id, rerun, grading=True)
    return {**answer_view(a), "evaluation_status": ev.status, "reevaluating": bool(rerun and ev.run_status == "RUNNING")}


@router.post("/evaluations/{ev_id}/confirm-all-mappings")
def confirm_all_mappings(ev_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    ev = get_evaluation(db, t, ev_id)
    _not_finalized(ev)
    answers = db.query(StudentAnswer).filter_by(evaluation_id=ev.id).all()
    count = 0
    for a in answers:
        if (
            a.status == "MAPPED"
            and a.exam_question_id
            and not a.mapping_confirmed
            and not (a.mapping_note or "").startswith("DUPLICATE")
        ):
            a.mapping_confirmed = True
            count += 1
            audit(db, exam_id=ev.exam_id, teacher_id=t.id, entity_type="student_answer", entity_id=a.id,
                  action="student_answer_mapping_confirmed_batch", reason="Batch confirmed by teacher")
    db.commit()
    refresh_evaluation_status(db, ev)
    return {"confirmed": count, "evaluation_status": ev.status}


class SplitAnswerIn(BaseModel):

    at_char: int = Field(gt=0)
    new_label: str


@router.post("/evaluations/{ev_id}/answers/{answer_id}/split")
def split_student_answer(ev_id: str, answer_id: str, body: SplitAnswerIn,
                         db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    ev = get_evaluation(db, t, ev_id)
    _not_finalized(ev)
    a = db.get(StudentAnswer, answer_id)
    if not a or a.evaluation_id != ev.id:
        raise err(404, "NOT_FOUND", "Answer not found.")
    if body.at_char >= len(a.answer_text):
        raise err(400, "INVALID_SPLIT", "Split position is beyond the end of the text.")
    norm = normalize_question_number(body.new_label)
    head, tail = a.answer_text[:body.at_char].rstrip(), a.answer_text[body.at_char:].lstrip()

    for other in db.query(StudentAnswer).filter(StudentAnswer.evaluation_id == ev.id, StudentAnswer.position > a.position):
        other.position += 1

    new_ans = StudentAnswer(
        evaluation_id=ev.id,
        raw_question_number=body.new_label,
        normalized_number=norm,
        answer_text=tail,
        raw_ocr_text=tail,
        page_number=a.page_number,
        position=a.position + 1,
        status="UNMAPPED",
    )
    a.answer_text = head
    db.add(new_ans)
    db.flush()
    apply_student_mapping(db, ev)
    audit(db, exam_id=ev.exam_id, teacher_id=t.id, entity_type="student_answer", entity_id=a.id,
          action="student_answer_split", old=a.raw_ocr_text, new={"head": head, "tail": tail, "new_label": body.new_label})
    db.commit()
    refresh_evaluation_status(db, ev)
    return {"original": answer_view(a), "new": answer_view(new_ans)}


class MergeAnswerIn(BaseModel):
    other_id: str


@router.post("/evaluations/{ev_id}/answers/{answer_id}/merge")
def merge_student_answer(ev_id: str, answer_id: str, body: MergeAnswerIn,
                         db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    ev = get_evaluation(db, t, ev_id)
    _not_finalized(ev)
    a = db.get(StudentAnswer, answer_id)
    o = db.get(StudentAnswer, body.other_id)
    if not a or not o or a.evaluation_id != ev.id or o.evaluation_id != ev.id or a.id == o.id:
        raise err(400, "INVALID_MERGE", "Choose a different answer from the same evaluation.")

    audit(db, exam_id=ev.exam_id, teacher_id=t.id, entity_type="student_answer", entity_id=a.id,
          action="student_answers_merged", old={"kept": answer_view(a), "absorbed": answer_view(o)})
    a.answer_text = (a.answer_text.rstrip() + "\n" + o.answer_text.lstrip()).strip()
    a.raw_ocr_text = (a.raw_ocr_text.rstrip() + "\n" + o.raw_ocr_text.lstrip()).strip()
    db.delete(o)
    db.flush()

    for i, ans in enumerate(db.query(StudentAnswer).filter_by(evaluation_id=ev.id).order_by(StudentAnswer.position), 1):
        ans.position = i

    apply_student_mapping(db, ev)
    db.commit()
    refresh_evaluation_status(db, ev)
    return answer_view(a)


# ---------- evaluation run ----------
@router.post("/evaluations/{ev_id}/run", status_code=202)
def run(ev_id: str, bg: BackgroundTasks, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    ev = get_evaluation(db, t, ev_id)
    _not_finalized(ev)
    exam = db.get(Exam, ev.exam_id)
    if exam.status == "ANSWER_KEY_VERIFIED":
        set_state(exam, "READY_FOR_EVALUATION")
        db.flush()
    if exam.status not in ("READY_FOR_EVALUATION", "EVALUATING", "REVIEW_REQUIRED"):
        raise err(409, "EXAM_NOT_READY", "The exam must have a verified question paper and answer key before evaluating.")
    if ev.run_status == "RUNNING":
        raise err(409, "ALREADY_RUNNING", "Evaluation is already running.")
    doc = db.get(AnswerSheetDocument, ev.answer_sheet_id)
    if doc.status not in ("READY", "NEEDS_ATTENTION"):
        raise err(409, "OCR_NOT_FINISHED", "The answer sheet is still being read.")
    unresolved = [a for a in db.query(StudentAnswer).filter_by(evaluation_id=ev.id) if a.status in ("UNMAPPED", "NEEDS_REVIEW")]
    if unresolved or doc.status == "NEEDS_ATTENTION":
        issues = [{"question": a.raw_question_number or "(no question number)",
                   "reason": "Student answer is unmapped" if a.status == "UNMAPPED" else (a.mapping_note or "Needs mapping review")}
                  for a in unresolved]
        if doc.status == "NEEDS_ATTENTION":
            issues.append({"question": "Answer sheet", "reason": "Some pages could not be read. Retry them first."})
        raise err(400, "MAPPING_INCOMPLETE", f"{len(issues)} issue(s) must be resolved before evaluation can run.", issues)
    ev.run_status, ev.run_progress = "RUNNING", 0
    db.commit()
    bg.add_task(submit, ev.exam_id, run_evaluation, ev.id, grading=True)
    return {"run_status": "RUNNING"}


class ItemPatch(BaseModel):
    final_marks: float | None = Field(None, ge=0)
    teacher_feedback: str | None = None
    approve: bool | None = None
    confirm_not_attempted: bool | None = None
    reason: str | None = None


@router.patch("/evaluations/{ev_id}/items/{item_id}")
def patch_item(ev_id: str, item_id: str, body: ItemPatch, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    ev = get_evaluation(db, t, ev_id)
    _not_finalized(ev)
    it = db.get(EvaluationItem, item_id)
    if not it or it.evaluation_id != ev.id:
        raise err(404, "NOT_FOUND", "Item not found.")
    q = db.get(ExamQuestion, it.exam_question_id)
    d = body.model_dump(exclude_unset=True)
    reason = (d.pop("reason", None) or "").strip()
    if it.status == "PENDING":
        raise err(409, "NOT_EVALUATED", "This question has not been evaluated yet.")

    def log(action, old, new):
        audit(db, exam_id=ev.exam_id, teacher_id=t.id, entity_type="evaluation_item", entity_id=it.id,
              action=action, old=old, new=new, reason=reason or None)

    if "final_marks" in d and d["final_marks"] is not None:
        m = d["final_marks"]
        if q.max_marks is None or m > q.max_marks + 1e-9:
            raise err(400, "MARKS_EXCEED_MAXIMUM", f"Marks cannot exceed {q.max_marks:g} for question {q.display_number}.")
        if it.ai_marks is None or abs(m - it.ai_marks) > 1e-9:
            if not reason:
                raise err(400, "REASON_REQUIRED", "Give a reason when changing marks from the AI's mark.")
            it.teacher_overridden = True
        elif it.ai_marks is not None:
            it.teacher_overridden = False
        if m != it.final_marks:
            log("marks_changed", {"ai": it.ai_marks, "was": it.final_marks}, m)
        it.final_marks = m
        if it.status == "APPROVED":
            it.status = "EVALUATED" if it.ai_marks is not None else it.status
    if "teacher_feedback" in d:
        log("teacher_feedback_changed", it.teacher_feedback, d["teacher_feedback"])
        it.teacher_feedback = d["teacher_feedback"]
    if d.get("confirm_not_attempted"):
        if it.status != "MISSING":
            raise err(400, "NOT_MISSING", "Only questions without an answer can be confirmed as not attempted.")
        it.not_attempted_confirmed = True
        if it.final_marks is None:
            it.final_marks = 0.0
        log("not_attempted_confirmed", None, True)
    if d.get("approve") is True:
        if it.status == "EVALUATION_ERROR" and it.final_marks is None:
            raise err(400, "NEEDS_MARKS", "Enter marks yourself for this question before approving.")
        if it.status == "MISSING" and not it.not_attempted_confirmed:
            raise err(400, "NEEDS_CONFIRMATION", "Confirm the question was not attempted, or map an answer to it.")
        if it.final_marks is None:
            raise err(400, "NEEDS_MARKS", "There are no marks to approve.")
        it.status = "APPROVED"
        log("item_approved", None, it.final_marks)
        if it.student_answer_id and (a := db.get(StudentAnswer, it.student_answer_id)):
            a.status = "APPROVED"
    elif d.get("approve") is False and it.status == "APPROVED":
        it.status = "EVALUATED" if it.ai_marks is not None else ("MISSING" if it.student_answer_id is None else "EVALUATION_ERROR")
        log("item_unapproved", None, None)
        if it.student_answer_id and (a := db.get(StudentAnswer, it.student_answer_id)):
            a.status = "EVALUATED"
    db.commit()
    refresh_evaluation_status(db, ev)
    return {"item": item_view(it), "evaluation_status": ev.status}


@router.post("/evaluations/{ev_id}/items/approve-all")
def approve_all(ev_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    """Approve every cleanly evaluated item and confirm genuine unattempted items."""
    ev = get_evaluation(db, t, ev_id)
    _not_finalized(ev)
    n = approve_clean_items(db, ev)
    audit(db, exam_id=ev.exam_id, teacher_id=t.id, entity_type="evaluation", entity_id=ev.id, action="items_bulk_approved", new=n)
    db.commit()
    refresh_evaluation_status(db, ev)
    return {"approved": n, "evaluation_status": ev.status}


@router.post("/evaluations/{ev_id}/items/{item_id}/rerun", status_code=202)
def rerun_item(ev_id: str, item_id: str, bg: BackgroundTasks, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    ev = get_evaluation(db, t, ev_id)
    _not_finalized(ev)
    it = db.get(EvaluationItem, item_id)
    if not it or it.evaluation_id != ev.id:
        raise err(404, "NOT_FOUND", "Item not found.")
    if ev.run_status == "RUNNING":
        raise err(409, "ALREADY_RUNNING", "Evaluation is already running.")
    audit(db, exam_id=ev.exam_id, teacher_id=t.id, entity_type="evaluation_item", entity_id=it.id, action="evaluation_rerun",
          old={"ai": it.ai_marks, "final": it.final_marks})
    ev.run_status = "RUNNING"
    db.commit()
    bg.add_task(submit, ev.exam_id, run_evaluation, ev.id, [it.exam_question_id], grading=True)
    return {"run_status": "RUNNING"}


# ---------- finalize + results ----------
@router.post("/evaluations/{ev_id}/finalize")
def finalize_evaluation(ev_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    ev = get_evaluation(db, t, ev_id)
    _not_finalized(ev)
    all_answers = db.query(StudentAnswer).filter_by(evaluation_id=ev.id).all()
    if not any(a.status in ("UNMAPPED", "NEEDS_REVIEW") for a in all_answers):
        for it in db.query(EvaluationItem).filter_by(evaluation_id=ev.id, status="MISSING").all():
            if not it.not_attempted_confirmed:
                it.not_attempted_confirmed = True
                if it.final_marks is None:
                    it.final_marks = 0.0
        db.commit()
    refresh_evaluation_status(db, ev)
    issues = finalize_issues(db, ev)
    if issues or ev.run_status == "RUNNING":
        if ev.run_status == "RUNNING":
            issues.insert(0, {"question": "Evaluation", "reason": "Evaluation is still running"})
        raise err(400, "EVALUATION_NOT_READY",
                  f"Evaluation cannot be finalized. {len(issues)} issue(s) still need attention.", issues)
    finalize(db, ev)
    audit(db, exam_id=ev.exam_id, teacher_id=t.id, entity_type="evaluation", entity_id=ev.id, action="evaluation_finalized",
          new={"total": ev.total_marks, "max": ev.maximum_marks, "percentage": ev.percentage})
    db.commit()
    return evaluation_view(ev)


@router.get("/evaluations/{ev_id}/result")
def result(ev_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    ev = get_evaluation(db, t, ev_id)
    exam = db.get(Exam, ev.exam_id)
    keys = {k.exam_question_id: k for k in db.query(AnswerKey).filter_by(exam_id=ev.exam_id, is_active=True, mapping_status="MAPPED")}
    items = {i.exam_question_id: i for i in db.query(EvaluationItem).filter_by(evaluation_id=ev.id)}
    answers = {a.id: a for a in db.query(StudentAnswer).filter_by(evaluation_id=ev.id)}
    rows, total, maxm = [], 0.0, 0.0
    qs = exam_questions(db, ev.exam_id)
    marks = {qid: it.final_marks for qid, it in items.items()}
    counts = {q.id for q in choices.counted(qs, marks)}
    for q in qs:
        it = items.get(q.id)
        a = answers.get(it.student_answer_id) if it and it.student_answer_id else None
        fm = it.final_marks if it else None
        if q.id in counts:
            total += fm or 0
            maxm += q.max_marks or 0
        rows.append({"question_id": q.id, "question": q.display_number, "question_text": q.question_text,
                     "choice_group": q.choice_group, "counted": q.id in counts,
                     "max_marks": q.max_marks, "final_marks": fm, "ai_marks": it.ai_marks if it else None,
                     "k_level": q.k_level, "course_outcome": q.course_outcome,
                     "teacher_overridden": bool(it and it.teacher_overridden),
                     "student_answer": a.answer_text if a else None,
                     "official_answer": keys[q.id].answer_text if q.id in keys else None,
                     "feedback": (it.teacher_feedback or it.ai_feedback) if it else None,
                     "status": it.status if it else "PENDING"})
    return {"finalized": ev.status == "FINALIZED", "evaluation": evaluation_view(ev),
            "exam": {"id": exam.id, "name": exam.name, "subject": exam.subject.name, "class": exam.school_class.name},
            "total_marks": ev.total_marks if ev.status == "FINALIZED" else total,
            "maximum_marks": ev.maximum_marks if ev.status == "FINALIZED" else maxm,
            "percentage": ev.percentage if ev.status == "FINALIZED" else (round(100 * total / maxm, 2) if maxm else 0),
            "questions": rows,
            "outcomes": summarize_outcomes(choices.counted(qs, marks), marks)}


@router.get("/evaluations/{ev_id}/report.pdf")
@router.get("/evaluations/{ev_id}/report")
def download_evaluation_report(ev_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    # Relative grades depend on the current finalized cohort; an archived PDF can be stale.
    # Re-render from retained database results, including after original files are purged.
    pdf_bytes, filename = build_evaluation_pdf_report(db, t, ev_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-cache",
        },
    )


@router.get("/exams/{exam_id}/report.pdf")
def download_exam_report(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    pdf_bytes, filename = build_exam_pdf_report(db, t, exam_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-cache",
        },
    )


@router.get("/results")
def list_results(db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    exam_ids = [e.id for e in exams_query(db, t)]
    evs = (db.query(Evaluation).options(*EVALUATION_VIEW_LOAD)
           .filter(Evaluation.exam_id.in_(exam_ids or [""]), Evaluation.status == "FINALIZED")
           .order_by(Evaluation.finalized_at.desc()))
    return [evaluation_view(e) for e in evs]


@router.get("/exams/{exam_id}/results")
def exam_results(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    exam = get_exam(db, t, exam_id)
    return [evaluation_view(e) for e in db.query(Evaluation).filter_by(exam_id=exam.id).order_by(Evaluation.created_at)]


@router.get("/exams/{exam_id}/outcome-summary")
def exam_outcome_summary(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    """Class performance per Bloom's K level and course outcome, over evaluations with finalized marks."""
    exam = get_exam(db, t, exam_id)
    qs = exam_questions(db, exam.id)
    evs = db.query(Evaluation).filter_by(exam_id=exam.id, status="FINALIZED").all()
    students = []
    for ev in evs:
        marks = {i.exam_question_id: i.final_marks for i in db.query(EvaluationItem).filter_by(evaluation_id=ev.id)}
        students.append({"evaluation_id": ev.id, "student_id": ev.student_id, "name": ev.student.name,
                         "roll_number": ev.student.roll_number, **summarize_outcomes(choices.counted(qs, marks), marks)})

    def overall(key: str) -> list[dict]:
        if not students:
            return summarize_outcomes(qs, {})[key]
        rows = {}
        for s in students:
            for r in s[key]:
                a = rows.setdefault(r["key"], {**r, "scored": 0.0, "max_marks": 0.0})
                a["scored"] += r["scored"]
                a["max_marks"] += r["max_marks"]
        for a in rows.values():
            a["average_scored"] = round(a["scored"] / len(students), 2)
            a["max_marks"] = a["max_marks"] / len(students)
            a["percentage"] = round(100.0 * a["average_scored"] / a["max_marks"], 1) if a["max_marks"] else None
            del a["scored"]
        return list(rows.values())
    return {"finalized_students": len(students), "k_levels": overall("k_levels"),
            "course_outcomes": overall("course_outcomes"), "students": students}


_BUSY_DOC = ("UPLOADED", "RENDERING", "OCR_PROCESSING", "EXTRACTING", "IDENTIFYING")


def _batch(db: Session, exam: Exam) -> dict:
    """Every sheet of the exam sorted into: still being worked on, ready to finalize together, or needing the teacher."""
    loose = db.query(AnswerSheetDocument).filter_by(exam_id=exam.id, is_active=True, student_id=None).all()
    processing = sum(d.status in _BUSY_DOC or in_flight(d.id) for d in loose)
    out = {"unassigned": len(loose) - processing, "finalized": 0, "ready": [], "needs_review": []}
    evs = (db.query(Evaluation).options(selectinload(Evaluation.student).selectinload(Student.school_class))
           .filter_by(exam_id=exam.id).order_by(Evaluation.created_at).all())
    open_evs = [ev for ev in evs if ev.status != "FINALIZED"]
    out["finalized"] = len(evs) - len(open_evs)
    snap = ExamSnapshot(db, exam.id, open_evs)
    for ev in open_evs:
        doc = snap.docs.get(ev.answer_sheet_id)
        if ev.run_status == "RUNNING" or in_flight(ev.answer_sheet_id) or (doc and doc.status in _BUSY_DOC):
            processing += 1
            continue
        row = {"evaluation_id": ev.id, "student": student_view(ev.student), "status": ev.status, "_ev": ev}
        reasons = review_reasons(db, ev, snap)
        if reasons:
            out["needs_review"].append({**row, "reasons": reasons})
        else:
            out["ready"].append(row)
    return {"total": len(evs) + len(loose), "processing": processing, **out}


def _public(batch: dict) -> dict:
    strip = lambda rows: [{k: v for k, v in r.items() if k != "_ev"} for r in rows]  # noqa: E731
    return {**batch, "ready": strip(batch["ready"]), "needs_review": strip(batch["needs_review"])}


@router.get("/exams/{exam_id}/review-summary")
def review_summary(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    """Where the uploaded batch stands, with the reasons each held-back sheet needs the teacher."""
    return _public(_batch(db, get_exam(db, t, exam_id)))


@router.post("/exams/{exam_id}/finalize-ready")
def finalize_ready(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    """The teacher has reviewed the batch: approve the AI marks and finalize every sheet with nothing left to fix.

    Sheets that still need the teacher are skipped and returned with their reasons.
    """
    exam = get_exam(db, t, exam_id)
    batch = _batch(db, exam)
    if not batch["ready"]:
        raise err(400, "NOTHING_READY", "No answer sheet is ready to finalize.", [
            {"question": r["student"]["name"], "reason": r["reasons"][0]["reason"]} for r in batch["needs_review"]])
    done = []
    for row in batch["ready"]:
        ev = row["_ev"]
        approve_clean_items(db, ev)
        db.commit()
        refresh_evaluation_status(db, ev)
        if finalize_issues(db, ev):  # changed since the summary was built; leave it for the teacher
            continue
        finalize(db, ev)
        audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="evaluation", entity_id=ev.id, action="evaluation_finalized",
              new={"total": ev.total_marks, "max": ev.maximum_marks, "percentage": ev.percentage, "bulk": True})
        db.commit()
        done.append(ev.id)
    return {**_public(_batch(db, exam)), "finalized_now": len(done)}


@router.post("/exams/{exam_id}/finalize")
def finalize_exam(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    exam = get_exam(db, t, exam_id)
    evs = db.query(Evaluation).filter_by(exam_id=exam.id).all()
    pending = [{"question": e.student.name, "reason": f"Evaluation is {e.status.replace('_', ' ').lower()}"} for e in evs if e.status != "FINALIZED"]
    if not evs or pending:
        raise err(400, "EXAM_NOT_READY", "Every student's evaluation must be finalized first.",
                  pending or [{"question": "Exam", "reason": "No answer sheets uploaded"}])
    if exam.status != "REVIEW_REQUIRED":
        set_state(exam, "REVIEW_REQUIRED") if exam.status in ("READY_FOR_EVALUATION", "EVALUATING") else None
    set_state(exam, "FINALIZED")
    audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="exam", entity_id=exam.id, action="exam_finalized")
    db.commit()
    reports = 0
    if exam.files_purge_at is None:  # finalizing again must not restart the 24-hour clock
        reports = save_reports_and_schedule(db, t, exam)
        db.commit()
    return {"status": exam.status, "reports_saved": reports, "files_purge_at": exam.files_purge_at.isoformat()}


@router.post("/exams/{exam_id}/purge-files")
def purge_files_now(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    """Delete a finalized exam's uploaded and generated files now instead of waiting for the 24-hour deadline."""
    exam = get_exam(db, t, exam_id)
    if exam.status != "FINALIZED":
        raise err(409, "EXAM_NOT_FINALIZED", "Files can only be deleted after the exam is finalized.")
    if exam.files_purged_at is None:
        purge_exam_files(db, exam, t.id)
        db.commit()
    return {"files_purged_at": exam.files_purged_at.isoformat()}


@router.get("/exams/{exam_id}/audit-logs")
def audit_logs(exam_id: str, limit: int = Query(200, le=1000), db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    exam = get_exam(db, t, exam_id)
    rows = db.query(AuditLog).filter_by(exam_id=exam.id).order_by(AuditLog.created_at.desc()).limit(limit).all()
    names = {x.id: x.name for x in db.query(Teacher)}
    return [{"id": r.id, "entity_type": r.entity_type, "entity_id": r.entity_id, "action": r.action,
             "old_value": r.old_value, "new_value": r.new_value, "reason": r.reason,
             "user": names.get(r.teacher_id), "created_at": r.created_at.isoformat()} for r in rows]
