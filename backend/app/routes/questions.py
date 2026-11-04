from __future__ import annotations
import re
from fastapi import APIRouter, BackgroundTasks, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ..database import get_db
from ..deps import err, get_exam
from ..models import Exam, ExamQuestion, QuestionPaperDocument, Teacher
from ..security import current_teacher
from ..serializers import question_view
from ..formatter.common import choices
from ..services.audit import audit
from ..formatter.common.numbering import normalize_question_number
from ..services.state import set_state

router = APIRouter(prefix="/api")
EDITABLE = ("QUESTION_PAPER_UPLOADED", "QUESTIONS_EXTRACTED")


def _get_q(db: Session, t: Teacher, qid: str) -> ExamQuestion:
    q = db.get(ExamQuestion, qid)
    if not q:
        raise err(404, "NOT_FOUND", "Question not found.")
    get_exam(db, t, q.exam_id)
    return q


def _require_editable(db: Session, exam_id: str):
    exam = db.get(Exam, exam_id)
    if exam.status not in EDITABLE:
        raise err(409, "QUESTIONS_LOCKED", "Questions are verified and locked.")
    return exam


def _resequence(db: Session, exam_id: str):
    for i, q in enumerate(db.query(ExamQuestion).filter_by(exam_id=exam_id).order_by(ExamQuestion.position, ExamQuestion.created_at), 1):
        q.position = i


def _validate_for_verified(q: ExamQuestion, siblings: list[ExamQuestion]) -> list[str]:
    probs = []
    if not q.normalized_number:
        probs.append("question number is missing or unreadable")
    elif sum(s.normalized_number == q.normalized_number for s in siblings if s.id != q.id):
        probs.append(f"question number {q.normalized_number} is used more than once")
    if not (q.question_text or "").strip():
        probs.append("question text is empty")
    if q.max_marks is None or q.max_marks <= 0:
        probs.append("maximum marks must be greater than 0")
    return probs


BUSY = {"UPLOADED", "RENDERING", "OCR_PROCESSING", "EXTRACTING"}


@router.get("/exams/{exam_id}/questions")
def list_questions(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    exam = get_exam(db, t, exam_id)
    qs = db.query(ExamQuestion).filter_by(exam_id=exam.id).order_by(ExamQuestion.position).all()
    doc = db.query(QuestionPaperDocument).filter_by(exam_id=exam.id, is_active=True).order_by(QuestionPaperDocument.uploaded_at.desc()).first()
    # Reconcile state if extraction completed and questions exist but exam status is still QUESTION_PAPER_UPLOADED
    if exam.status == "QUESTION_PAPER_UPLOADED" and qs and (not doc or doc.status in ("READY", "NEEDS_ATTENTION")):
        set_state(exam, "QUESTIONS_EXTRACTED")
        db.commit()
    total = choices.max_total(qs)

    # Read structure.json if available
    struct_info = {}
    if doc:
        from ..config import get_settings
        import json
        struct_file = get_settings().data_path / "exams" / exam.id / "question-paper" / doc.id / "structure.json"
        if struct_file.exists():
            try:
                with open(struct_file, "r", encoding="utf-8") as f:
                    struct_info = json.load(f)
            except Exception:
                pass

    sections_summary = {}
    counts = {q.id for q in choices.counted(qs)}  # an "answer any N" section counts its best N
    for q in choices.units(qs):  # an either/or choice is one question
        sec = q.section or "General"
        if sec not in sections_summary:
            sections_summary[sec] = {"section": sec, "count": 0, "marks": 0.0, "answer_any": q.answer_any}
        sections_summary[sec]["count"] += 1
        if q.id in counts:
            sections_summary[sec]["marks"] += (q.max_marks or 0.0)

    stated_qc = struct_info.get("stated_question_count")

    return {
        "questions": [question_view(q) for q in qs],
        "document_id": doc.id if doc else None,
        "document_status": doc.status if doc else None,
        "document_stage": doc.stage if doc else None,
        "exam_status": exam.status,
        "can_verify": exam.status == "QUESTIONS_EXTRACTED" and len(qs) > 0 and (not doc or doc.status == "READY"),
        "sum_of_marks": total,
        "exam_total_marks": exam.total_marks,
        "marks_warning": (f"Questions add up to {total:g} marks but the exam total is {exam.total_marks:g}."
                          if qs and abs(total - exam.total_marks) > 1e-9 else None),
        "locked": exam.status not in EDITABLE,
        "exam_name": exam.name,
        "exam_subject": exam.subject.name if exam.subject else None,
        "exam_duration_minutes": exam.duration_minutes,
        "exam_instructions": exam.instructions,
        "stated_question_count": stated_qc,
        "stated_printed_pages": struct_info.get("stated_printed_pages"),
        "qp_code": struct_info.get("qp_code"),
        "sections_summary": list(sections_summary.values()),
        "unclassified_blocks": struct_info.get("unclassified_blocks", []),
    }


@router.get("/exams/{exam_id}/questions/export.pdf")
def export_questions_pdf(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    from ..services.extracted_pdf import questions_pdf

    exam = get_exam(db, t, exam_id)
    rows = db.query(ExamQuestion).filter_by(exam_id=exam.id).order_by(ExamQuestion.position).all()
    if not rows:
        raise err(409, "NO_EXTRACTED_QUESTIONS", "There are no extracted questions to download.")
    filename = re.sub(r"[^A-Za-z0-9_-]+", "_", exam.name).strip("_") or "Exam"
    return Response(questions_pdf(exam, rows), media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{filename}_Extracted_Questions.pdf"',
    })


@router.get("/exams/{exam_id}/extraction-report.pdf")
def export_extraction_report_pdf(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    """Question paper and answer key as extracted, with the AI's review notes, for checking against the uploads."""
    from ..models import AnswerKey, AnswerKeyDocument
    from ..services.extracted_pdf import exam_extraction_report_pdf

    exam = get_exam(db, t, exam_id)
    paper = db.query(QuestionPaperDocument).filter_by(exam_id=exam.id, is_active=True).first()
    key_doc = db.query(AnswerKeyDocument).filter_by(exam_id=exam.id, is_active=True).first()
    if paper is None and key_doc is None:
        raise err(409, "NOTHING_UPLOADED", "Upload the question paper or answer key first.")
    questions = db.query(ExamQuestion).filter_by(exam_id=exam.id).order_by(ExamQuestion.position).all()
    positions = {q.id: q.position for q in questions}
    keys = db.query(AnswerKey).filter_by(exam_id=exam.id, is_active=True).all()
    keys.sort(key=lambda k: (positions.get(k.exam_question_id, 10**9), k.created_at))
    filename = re.sub(r"[^A-Za-z0-9_-]+", "_", exam.name).strip("_") or "Exam"
    return Response(exam_extraction_report_pdf(exam, paper, key_doc, questions, keys), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}_Extraction_Report.pdf"'})


class QuestionPatch(BaseModel):
    display_number: str | None = None
    question_text: str | None = None
    max_marks: float | None = Field(None, gt=0)
    section: str | None = None
    question_type: str | None = None
    verification_status: str | None = None
    reason: str | None = None


@router.patch("/exam-questions/{qid}")
def patch_question(qid: str, body: QuestionPatch, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    q = _get_q(db, t, qid)
    exam = _require_editable(db, q.exam_id)
    data = body.model_dump(exclude_unset=True)
    status = data.pop("verification_status", None)
    reason = data.pop("reason", None)
    content_changed = False
    for field, new in data.items():
        if field == "display_number":
            norm = normalize_question_number(new)
            if norm is None:
                raise err(400, "INVALID_QUESTION_NUMBER", f"'{new}' is not a readable question number. Use forms like 1, 3(a) or 4(i).")
            if norm != q.normalized_number:
                audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="exam_question", entity_id=q.id,
                      action="question_number_changed", old=q.display_number, new=norm, reason=reason)
            q.display_number, q.normalized_number = norm, norm
            if exam.standard_profile_id:
                if not norm.isdigit():
                    raise err(400,"CBSE_WHOLE_QUESTION","Use a whole-question number; edit subparts in the CBSE hierarchy.")
                q.structure = {**(q.structure or {}),"root":int(norm)}
            content_changed = True
            continue
        old = getattr(q, field)
        if new != old:
            audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="exam_question", entity_id=q.id,
                  action=f"question_{field}_changed", old=old, new=new, reason=reason)
            setattr(q, field, new)
            content_changed = True
    if content_changed:
        q.verification_status, q.review_reason = "UNVERIFIED", None
        if exam.standard_profile_id:
            from ..models import AnswerKey
            for key in db.query(AnswerKey).filter_by(exam_question_id=q.id,is_active=True):
                key.verification_status,key.rubric_status="UNVERIFIED","UNREVIEWED"
    if status:
        if status not in ("VERIFIED", "UNVERIFIED", "NEEDS_REVIEW"):
            raise err(400, "INVALID_STATUS", "Unknown verification status.")
        if status == "VERIFIED":
            sibs = db.query(ExamQuestion).filter_by(exam_id=exam.id).all()
            probs = _validate_for_verified(q, sibs)
            if probs:
                raise err(400, "QUESTION_INCOMPLETE", f"Question {q.display_number} cannot be accepted: " + "; ".join(probs) + ".")
        q.verification_status = status
        q.review_reason = reason if status == "NEEDS_REVIEW" else None
        audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="exam_question", entity_id=q.id,
              action=f"question_{status.lower()}", reason=reason)
    if exam.status == "QUESTION_PAPER_UPLOADED":
        set_state(exam, "QUESTIONS_EXTRACTED")
    db.commit()
    return question_view(q)


class QuestionCreate(BaseModel):
    display_number: str
    question_text: str = ""
    max_marks: float | None = Field(None, gt=0)
    section: str | None = None


@router.post("/exams/{exam_id}/questions", status_code=201)
def add_question(exam_id: str, body: QuestionCreate, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    exam = get_exam(db, t, exam_id)
    if exam.status not in EDITABLE:
        raise err(409, "QUESTIONS_LOCKED", "Questions are verified and locked.")
    norm = normalize_question_number(body.display_number)
    if norm is None:
        raise err(400, "INVALID_QUESTION_NUMBER", f"'{body.display_number}' is not a readable question number.")
    last = db.query(ExamQuestion).filter_by(exam_id=exam.id).count()
    q = ExamQuestion(exam_id=exam.id, display_number=norm, normalized_number=norm, question_text=body.question_text,
                     raw_ocr_text="", max_marks=body.max_marks, section=body.section, position=last + 1,
                     verification_status="UNVERIFIED")
    db.add(q)
    db.flush()
    if exam.status == "QUESTION_PAPER_UPLOADED":
        set_state(exam, "QUESTIONS_EXTRACTED")
    audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="exam_question", entity_id=q.id, action="question_added_manually", new=norm)
    db.commit()
    return question_view(q)


@router.delete("/exam-questions/{qid}")
def delete_question(qid: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    q = _get_q(db, t, qid)
    exam = _require_editable(db, q.exam_id)
    audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="exam_question", entity_id=q.id,
          action="question_deleted", old=question_view(q))
    db.delete(q)
    _resequence(db, exam.id)
    db.commit()
    return {"ok": True}


@router.post("/exams/{exam_id}/questions/accept-valid")
def accept_valid(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    """Convenience: mark every UNVERIFIED, structurally complete question as VERIFIED. NEEDS_REVIEW rows are never touched."""
    exam = get_exam(db, t, exam_id)
    if exam.status not in EDITABLE:
        raise err(409, "QUESTIONS_LOCKED", "Questions are verified and locked.")
    doc = db.query(QuestionPaperDocument).filter_by(exam_id=exam.id, is_active=True).order_by(QuestionPaperDocument.uploaded_at.desc()).first()
    if doc and doc.status in BUSY:
        raise err(409, "INVALID_EXAM_STATE", "Question paper extraction is still in progress. Please wait for extraction to complete.")
    qs = db.query(ExamQuestion).filter_by(exam_id=exam.id).all()
    if not qs:
        raise err(409, "INVALID_EXAM_STATE", "Questions can only be accepted after they have been extracted.")
    if exam.status == "QUESTION_PAPER_UPLOADED" and qs and (not doc or doc.status in ("READY", "NEEDS_ATTENTION")):
        set_state(exam, "QUESTIONS_EXTRACTED")
    n = 0
    for q in qs:
        if q.verification_status == "UNVERIFIED" and not _validate_for_verified(q, qs):
            q.verification_status = "VERIFIED"
            n += 1
    audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="exam", entity_id=exam.id, action="questions_bulk_accepted", new=n)
    db.commit()
    return {"accepted": n}


@router.post("/exams/{exam_id}/questions/verify")
def verify_questions(exam_id: str, bg: BackgroundTasks, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    exam = get_exam(db, t, exam_id)
    doc = db.query(QuestionPaperDocument).filter_by(exam_id=exam.id, is_active=True).order_by(QuestionPaperDocument.uploaded_at.desc()).first()
    qs = db.query(ExamQuestion).filter_by(exam_id=exam.id).order_by(ExamQuestion.position).all()

    # 1. Idempotency: If already verified, return verified count and marks
    if exam.status == "QUESTIONS_VERIFIED":
        total = choices.max_total(qs)
        return {"verified": len(qs), "sum_of_marks": total,
                "marks_warning": (f"Questions add up to {total:g} marks but the exam total is {exam.total_marks:g}."
                                  if abs(total - exam.total_marks) > 1e-9 else None)}

    # 2. Check if locked past editable
    if exam.status not in EDITABLE:
        raise err(409, "QUESTIONS_LOCKED", "Questions are already verified and locked.")

    # 3. Guard against premature verification while extraction is actively running
    if doc and doc.status in BUSY:
        raise err(409, "INVALID_EXAM_STATE", "Question paper extraction is still in progress. Please wait for extraction to complete.")

    # 4. Check if questions have actually been extracted/saved
    if not qs:
        raise err(409, "INVALID_EXAM_STATE", "Questions can only be verified after they have been extracted. Please upload a question paper or add questions.")

    # 5. Reconcile state if extraction completed and questions exist but exam status is still QUESTION_PAPER_UPLOADED
    if exam.status == "QUESTION_PAPER_UPLOADED" and qs and (not doc or doc.status in ("READY", "NEEDS_ATTENTION")):
        set_state(exam, "QUESTIONS_EXTRACTED")
        db.flush()

    # 6. Verify exam is in QUESTIONS_EXTRACTED
    if exam.status != "QUESTIONS_EXTRACTED":
        raise err(409, "INVALID_EXAM_STATE", "Questions can only be verified after they have been extracted.")

    # 7. Collect validation issues
    issues = []
    if doc is None or doc.status != "READY":
        unread = [str(p.get("page_number")) for p in (doc.pages if doc else []) if p.get("ocr_status") != "OK"]
        if doc is not None and doc.status == "FAILED" and "interrupted" in (doc.error_message or "").lower():
            reason = (f"Reading was interrupted before page(s) {', '.join(unread)} were read. "
                      "Use Reprocess on the question paper to finish them.")
        elif unread:
            reason = f"Page(s) {', '.join(unread)} could not be read. Retry them before verifying."
        else:
            reason = "The question paper is still being read. Verify once it is ready."
        issues.append({"question": "Question paper", "reason": reason})
    for q in qs:
        for p in _validate_for_verified(q, qs):
            issues.append({"question": q.display_number, "reason": p})
        if q.verification_status != "VERIFIED":
            issues.append({"question": q.display_number, "reason": f"Not accepted yet ({q.verification_status.replace('_', ' ').lower()})"})
    if issues:
        raise err(400, "QUESTIONS_NOT_READY", f"{len(issues)} issue(s) must be resolved before the questions can be verified.", issues)

    set_state(exam, "QUESTIONS_VERIFIED")
    audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="exam", entity_id=exam.id, action="questions_verified", new=len(qs))
    db.commit()
    from .documents import release_waiting_key
    key_started = release_waiting_key(db, exam, bg)
    total = choices.max_total(qs)
    return {"verified": len(qs), "sum_of_marks": total, "answer_key_started": key_started,
            "marks_warning": (f"Questions add up to {total:g} marks but the exam total is {exam.total_marks:g}."
                              if abs(total - exam.total_marks) > 1e-9 else None)}


class PromoteBlockBody(BaseModel):
    page_number: int | None = None
    label: str | None = None
    text: str
    marks: float = 1.0
    section: str | None = None


@router.post("/exams/{exam_id}/promote-block")
def promote_block(exam_id: str, body: PromoteBlockBody, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    get_exam(db,t,exam_id)
    exam = _require_editable(db, exam_id)
    doc = db.query(QuestionPaperDocument).filter_by(exam_id=exam.id, is_active=True).order_by(QuestionPaperDocument.uploaded_at.desc()).first()
    qs = db.query(ExamQuestion).filter_by(exam_id=exam.id).order_by(ExamQuestion.position).all()
    next_pos = len(qs) + 1
    display_num = body.label.strip() if body.label else str(next_pos)
    norm = normalize_question_number(display_num)

    new_q = ExamQuestion(
        exam_id=exam.id,
        document_id=doc.id if doc else None,
        display_number=display_num,
        normalized_number=norm,
        question_text=body.text.strip(),
        raw_ocr_text=body.text.strip(),
        question_type="descriptive",
        max_marks=body.marks,
        section=body.section,
        position=next_pos,
        page_start=body.page_number,
        page_end=body.page_number,
        verification_status="VERIFIED",
    )
    db.add(new_q)

    # Remove from structure.json unclassified_blocks if present
    if doc:
        from ..config import get_settings
        import json
        struct_file = get_settings().data_path / "exams" / exam.id / "question-paper" / doc.id / "structure.json"
        if struct_file.exists():
            try:
                with open(struct_file, "r", encoding="utf-8") as f:
                    s_data = json.load(f)
                ub = s_data.get("unclassified_blocks", [])
                s_data["unclassified_blocks"] = [b for b in ub if b.get("text", "").strip() != body.text.strip()]
                with open(struct_file, "w", encoding="utf-8") as f:
                    json.dump(s_data, f, indent=2)
            except Exception:
                pass

    db.commit()
    return list_questions(exam_id, db, t)


class DismissBlockBody(BaseModel):
    text: str
    mark_as_instruction: bool = True


@router.post("/exams/{exam_id}/dismiss-block")
def dismiss_block(exam_id: str, body: DismissBlockBody, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    get_exam(db,t,exam_id)
    exam = _require_editable(db, exam_id)
    doc = db.query(QuestionPaperDocument).filter_by(exam_id=exam.id, is_active=True).order_by(QuestionPaperDocument.uploaded_at.desc()).first()

    if body.mark_as_instruction and body.text.strip():
        cur_inst = exam.instructions or ""
        if body.text.strip() not in cur_inst:
            exam.instructions = f"{cur_inst}\n{body.text.strip()}".strip()

    if doc:
        from ..config import get_settings
        import json
        struct_file = get_settings().data_path / "exams" / exam.id / "question-paper" / doc.id / "structure.json"
        if struct_file.exists():
            try:
                with open(struct_file, "r", encoding="utf-8") as f:
                    s_data = json.load(f)
                ub = s_data.get("unclassified_blocks", [])
                s_data["unclassified_blocks"] = [b for b in ub if b.get("text", "").strip() != body.text.strip()]
                with open(struct_file, "w", encoding="utf-8") as f:
                    json.dump(s_data, f, indent=2)
            except Exception:
                pass

    db.commit()
    return list_questions(exam_id, db, t)

