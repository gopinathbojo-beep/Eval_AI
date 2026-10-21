from __future__ import annotations
from pathlib import Path
import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from ..database import get_db
from ..deps import err, get_exam
from ..documents.storage import abs_path, doc_dir, read_validated_upload, rel
from ..models import (AnswerKey, AnswerKeyDocument, AnswerSheetDocument, Evaluation, EvaluationItem, ExamQuestion,
                      QuestionPaperDocument, Student, SchoolClass, StudentAnswer, Teacher)
from ..security import current_teacher
from ..serializers import doc_view, evaluation_view
from ..services.audit import audit
from ..services.pipeline import KINDS, process_document
from ..services.state import set_state
from ..services.student_identity import assign_student, identify_sheets, run_sheet

router = APIRouter(prefix="/api")
BUSY = {"UPLOADED", "RENDERING", "OCR_PROCESSING", "EXTRACTING", "IDENTIFYING"}
EXT = {
    "question-paper": {"pdf", "png", "jpg", "jpeg", "docx"},
    "answer-key": {"pdf", "docx", "png", "jpg", "jpeg"},
    "answer-sheet": {"pdf", "png", "jpg", "jpeg", "docx"},
}


def _save(db: Session, kind: str, exam_id: str, data: bytes, ext: str, mime: str, filename: str, **extra):
    model = KINDS[kind][0]
    doc_id = str(uuid.uuid4())
    d = doc_dir(kind, exam_id, doc_id, extra.get("student_id"))
    path = d / f"original.{ext}"
    with open(path, "xb") as f:  # 'x': never overwrite an original
        f.write(data)
    doc = model(id=doc_id, exam_id=exam_id, original_filename=filename[:290], original_file=rel(path),
                mime_type=mime, file_size=len(data), status="UPLOADED", stage="Queued", **extra)
    db.add(doc)
    return doc


def _busy_check(db: Session, model, **flt):
    if db.query(model).filter_by(is_active=True, **flt).filter(model.status.in_(BUSY)).first():
        raise err(409, "PROCESSING_IN_PROGRESS", "A document is still being processed. Wait for it to finish.")


# ---------- question paper ----------
@router.post("/exams/{exam_id}/question-paper", status_code=202)
async def upload_question_paper(exam_id: str, bg: BackgroundTasks, file: UploadFile = File(...),
                                db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    exam = get_exam(db, t, exam_id)
    if exam.status not in ("DRAFT", "QUESTION_PAPER_UPLOADED", "QUESTIONS_EXTRACTED"):
        raise err(409, "QUESTIONS_LOCKED", "Questions are already verified, so the question paper can no longer be replaced.")
    _busy_check(db, QuestionPaperDocument, exam_id=exam.id)
    data, ext, mime = await read_validated_upload(file, EXT["question-paper"])
    for old in db.query(QuestionPaperDocument).filter_by(exam_id=exam.id, is_active=True):
        old.is_active = False
    doc = _save(db, "question-paper", exam.id, data, ext, mime, file.filename or "upload")
    set_state(exam, "QUESTION_PAPER_UPLOADED")
    db.flush()
    audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="question_paper", entity_id=doc.id, action="question_paper_uploaded",
          new=doc.original_filename)
    db.commit()
    bg.add_task(process_document, "question-paper", doc.id)
    return doc_view(doc, "question-paper")


def _serve_document_pdf(doc) -> FileResponse:
    if not doc:
        raise err(404, "NOT_FOUND", "Document not found.")
    if not doc.original_file:
        raise err(404, "NOT_FOUND", "Document file record is missing.")
    orig_path = abs_path(doc.original_file)
    if not orig_path.is_file():
        raise err(404, "NOT_FOUND", "Original document file not found on disk.")

    ext = orig_path.suffix.lower()
    raw_filename = doc.original_filename or "document"
    stem = Path(raw_filename).stem or "document"
    download_filename = f"{stem}.pdf"

    if ext == ".pdf":
        return FileResponse(
            orig_path,
            media_type="application/pdf",
            filename=raw_filename if raw_filename.lower().endswith(".pdf") else download_filename,
            content_disposition_type="attachment",
        )

    docx_pdf = orig_path.parent / "converted-from-docx.pdf"
    if docx_pdf.is_file():
        return FileResponse(
            docx_pdf,
            media_type="application/pdf",
            filename=download_filename,
            content_disposition_type="attachment",
        )

    if ext == ".docx":
        from ..documents.renderer import _docx_to_pdf
        try:
            pdf_path = _docx_to_pdf(orig_path, orig_path.parent)
            return FileResponse(
                pdf_path,
                media_type="application/pdf",
                filename=download_filename,
                content_disposition_type="attachment",
            )
        except Exception:
            raise err(500, "CONVERSION_FAILED", "Failed to convert DOCX to PDF.")

    if ext in (".png", ".jpg", ".jpeg"):
        img_pdf = orig_path.parent / "original.pdf"
        if not img_pdf.is_file():
            from PIL import Image
            with Image.open(orig_path) as img:
                img.convert("RGB").save(img_pdf, "PDF")
        return FileResponse(
            img_pdf,
            media_type="application/pdf",
            filename=download_filename,
            content_disposition_type="attachment",
        )

    raise err(400, "UNSUPPORTED_FORMAT", f"Cannot export {ext} as PDF.")


@router.get("/exams/{exam_id}/question-paper")
def get_question_paper(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    exam = get_exam(db, t, exam_id)
    doc = (db.query(QuestionPaperDocument).filter_by(exam_id=exam.id, is_active=True)
           .order_by(QuestionPaperDocument.uploaded_at.desc()).first())
    return doc_view(doc, "question-paper")


@router.get("/exams/{exam_id}/question-paper/pdf")
@router.get("/exams/{exam_id}/question-paper/download")
def download_question_paper_pdf(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    exam = get_exam(db, t, exam_id)
    doc = (db.query(QuestionPaperDocument).filter_by(exam_id=exam.id, is_active=True)
           .order_by(QuestionPaperDocument.uploaded_at.desc()).first())
    if not doc:
        raise err(404, "NOT_FOUND", "No question paper uploaded for this exam.")
    return _serve_document_pdf(doc)


# ---------- answer key ----------
@router.post("/exams/{exam_id}/answer-key", status_code=202)
async def upload_answer_key(exam_id: str, bg: BackgroundTasks, file: UploadFile = File(...),
                            db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    exam = get_exam(db, t, exam_id)
    early = exam.status in EARLY_KEY_STATES
    if not early and exam.status not in ("QUESTIONS_VERIFIED", "ANSWER_KEY_UPLOADED", "ANSWER_KEY_VERIFIED", "READY_FOR_EVALUATION"):
        raise err(409, "ANSWER_KEY_LOCKED", "Evaluation has started, so the answer key can no longer be replaced.")
    if db.query(EvaluationItem).join(Evaluation, Evaluation.id == EvaluationItem.evaluation_id).filter(Evaluation.exam_id == exam.id).first():
        raise err(409, "ANSWER_KEY_LOCKED", "Evaluation has started, so the answer key can no longer be replaced.")
    _busy_check(db, AnswerKeyDocument, exam_id=exam.id)
    data, ext, mime = await read_validated_upload(file, EXT["answer-key"])
    for old in db.query(AnswerKeyDocument).filter_by(exam_id=exam.id, is_active=True):
        old.is_active = False
    for k in db.query(AnswerKey).filter_by(exam_id=exam.id, is_active=True):
        k.is_active = False
    doc = _save(db, "answer-key", exam.id, data, ext, mime, file.filename or "upload")
    if early:
        # read it only once the question list is final, so it maps onto verified questions (see release_waiting_key)
        doc.status, doc.stage = "WAITING", "Waiting for verified questions"
    else:
        set_state(exam, "ANSWER_KEY_UPLOADED")
    db.flush()
    audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="answer_key", entity_id=doc.id, action="answer_key_uploaded",
          new=doc.original_filename)
    db.commit()
    if not early:
        bg.add_task(process_document, "answer-key", doc.id)
    return doc_view(doc, "answer-key")


EARLY_KEY_STATES = ("DRAFT", "QUESTION_PAPER_UPLOADED", "QUESTIONS_EXTRACTED")


def release_waiting_key(db: Session, exam, bg: BackgroundTasks) -> bool:
    """Called once questions are verified: start reading an answer key that was uploaded early."""
    doc = db.query(AnswerKeyDocument).filter_by(exam_id=exam.id, is_active=True, status="WAITING").first()
    if doc is None:
        return False
    set_state(exam, "ANSWER_KEY_UPLOADED")
    doc.status, doc.stage = "UPLOADED", "Queued"
    db.commit()
    bg.add_task(process_document, "answer-key", doc.id)
    return True


@router.get("/exams/{exam_id}/answer-key")
def get_answer_key_doc(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    exam = get_exam(db, t, exam_id)
    doc = (db.query(AnswerKeyDocument).filter_by(exam_id=exam.id, is_active=True)
           .order_by(AnswerKeyDocument.uploaded_at.desc()).first())
    return doc_view(doc, "answer-key")


# ---------- answer sheets ----------
@router.post("/exams/{exam_id}/answer-sheets", status_code=202)
async def upload_answer_sheet(exam_id: str, bg: BackgroundTasks, file: UploadFile = File(...),
                              student_id: str | None = Form(None), student_name: str | None = Form(None),
                              roll_number: str | None = Form(None),
                              db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    exam = get_exam(db, t, exam_id)
    _require_sheet_state(exam)
    if not (student_id or student_name or roll_number):
        docs = await _save_unassigned(db, t, exam, [file])
        bg.add_task(identify_sheets, [d.id for d in docs], t.id)
        return _unassigned_view(db, docs[0])
    if student_id:
        st = db.get(Student, student_id)
        if not st or st.class_id != exam.class_id:
            raise err(400, "INVALID_STUDENT", "Choose a student from this exam's class.")
    else:
        if not student_name or not roll_number:
            raise err(400, "STUDENT_REQUIRED", "Select a student, or enter a name and roll number.")
        st = db.query(Student).filter_by(class_id=exam.class_id, roll_number=roll_number.strip()).first()
        if st is None:
            st = Student(class_id=exam.class_id, name=student_name.strip(), roll_number=roll_number.strip())
            db.add(st)
            db.flush()
    if db.query(Evaluation).filter_by(exam_id=exam.id, student_id=st.id).first():
        raise err(409, "ANSWER_SHEET_EXISTS",
                  f"{st.name} ({st.roll_number}) already has an answer sheet for this exam. Delete it first to upload again.")
    data, ext, mime = await read_validated_upload(file, EXT["answer-sheet"])
    doc = _save(db, "answer-sheet", exam.id, data, ext, mime, file.filename or "upload", student_id=st.id)
    db.flush()
    ev = Evaluation(exam_id=exam.id, student_id=st.id, answer_sheet_id=doc.id, status="DRAFT")
    db.add(ev)
    db.flush()
    audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="answer_sheet", entity_id=doc.id,
          action="answer_sheet_uploaded", new={"student": st.name, "roll": st.roll_number})
    db.commit()
    bg.add_task(process_document, "answer-sheet", doc.id)
    db.refresh(ev)
    return {**evaluation_view(ev), "document": doc_view(doc, "answer-sheet")}


SHEET_STATES = ("ANSWER_KEY_VERIFIED", "READY_FOR_EVALUATION", "EVALUATING", "REVIEW_REQUIRED")
MAX_BULK_FILES = 200


def _require_sheet_state(exam) -> None:
    if exam.status not in SHEET_STATES:
        raise err(409, "ANSWER_KEY_NOT_VERIFIED",
                  "Verify the answer key before uploading student answer sheets."
                  if exam.status != "FINALIZED" else "This exam is finalized.")


async def _save_unassigned(db: Session, t: Teacher, exam, files: list[UploadFile]) -> list:
    _require_sheet_state(exam)
    if not files:
        raise err(400, "NO_FILES", "Choose at least one answer sheet.")
    if len(files) > MAX_BULK_FILES:
        raise err(400, "TOO_MANY_FILES", f"Upload at most {MAX_BULK_FILES} answer sheets at a time.")
    validated = []
    for f in files:  # validate every file first, so one bad file rejects the batch before anything is stored
        try:
            validated.append((f.filename or "upload", *await read_validated_upload(f, EXT["answer-sheet"])))
        except HTTPException as e:
            msg = e.detail.get("message") if isinstance(e.detail, dict) else e.detail
            raise err(400, "INVALID_FILE", f"{f.filename}: {msg}")
    docs = []
    for name, data, ext, mime in validated:
        doc = _save(db, "answer-sheet", exam.id, data, ext, mime, name)
        doc.stage = "Waiting to read student details"
        docs.append(doc)
    db.flush()
    audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="exam", entity_id=exam.id, action="answer_sheets_bulk_uploaded",
          new=[d.original_filename for d in docs])
    db.commit()
    return docs


def _unassigned_view(db: Session, doc) -> dict:
    ident = doc.identity or {}
    cands = [db.get(Student, sid) for sid in ident.get("candidates") or []]
    return {**doc_view(doc, "answer-sheet"), "identity": ident,
            "candidates": [{"id": s.id, "name": s.name, "roll_number": s.roll_number,
                            "registration_number": s.registration_number, "section": s.section} for s in cands if s]}


@router.post("/exams/{exam_id}/answer-sheets/bulk", status_code=202)
async def upload_answer_sheets_bulk(exam_id: str, bg: BackgroundTasks, files: list[UploadFile] = File(...),
                                    db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    """Many sheets at once. Each is matched to its student from the details written on it, then read as usual."""
    exam = get_exam(db, t, exam_id)
    docs = await _save_unassigned(db, t, exam, files)
    bg.add_task(identify_sheets, [d.id for d in docs], t.id)
    return {"uploaded": len(docs), "documents": [_unassigned_view(db, d) for d in docs]}


@router.get("/exams/{exam_id}/answer-sheets/unassigned")
def list_unassigned_sheets(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    """Sheets not yet linked to a student: being identified, held for the teacher, or unreadable."""
    exam = get_exam(db, t, exam_id)
    docs = (db.query(AnswerSheetDocument).filter_by(exam_id=exam.id, is_active=True, student_id=None)
            .order_by(AnswerSheetDocument.uploaded_at).all())
    return [_unassigned_view(db, d) for d in docs]


def _unassigned_doc(db: Session, t: Teacher, doc_id: str):
    doc = db.get(AnswerSheetDocument, doc_id)
    if doc is None or not doc.is_active:
        raise err(404, "NOT_FOUND", "Answer sheet not found.")
    exam = get_exam(db, t, doc.exam_id)
    if doc.student_id is not None:
        raise err(409, "ALREADY_ASSIGNED", "This answer sheet is already linked to a student.")
    return doc, exam


class AssignBody(BaseModel):
    student_id: str


@router.post("/answer-sheets/{doc_id}/assign")
def assign_sheet_student(doc_id: str, body: AssignBody, bg: BackgroundTasks,
                         db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    doc, exam = _unassigned_doc(db, t, doc_id)
    _require_sheet_state(exam)
    if doc.status in BUSY:
        raise err(409, "PROCESSING_IN_PROGRESS", "The student details are still being read. Wait a moment.")
    if not doc.pages:
        raise err(409, "SHEET_UNREADABLE", "This file could not be opened. Delete it and upload it again.")
    st = db.get(Student, body.student_id)
    if not st or st.class_id != exam.class_id:
        raise err(400, "INVALID_STUDENT", "Choose a student from this exam's class.")
    if db.query(Evaluation).filter_by(exam_id=exam.id, student_id=st.id).first():
        raise err(409, "ANSWER_SHEET_EXISTS",
                  f"{st.name} ({st.roll_number}) already has an answer sheet for this exam. Delete it first to assign this one.")
    ev = assign_student(db, doc, st, t.id, "Picked by teacher")
    db.commit()
    bg.add_task(run_sheet, doc.id)
    db.refresh(ev)
    return {**evaluation_view(ev), "document": doc_view(doc, "answer-sheet")}


@router.post("/answer-sheets/{doc_id}/identify", status_code=202)
def retry_identify(doc_id: str, bg: BackgroundTasks, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    doc, exam = _unassigned_doc(db, t, doc_id)
    _require_sheet_state(exam)
    if doc.status in BUSY:
        raise err(409, "PROCESSING_IN_PROGRESS", "This answer sheet is already being processed.")
    doc.status, doc.stage, doc.error_message = "UPLOADED", "Waiting to read student details", None
    db.commit()
    bg.add_task(identify_sheets, [doc.id], t.id)
    return _unassigned_view(db, doc)


@router.delete("/answer-sheets/{doc_id}")
def delete_unassigned_sheet(doc_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    doc, exam = _unassigned_doc(db, t, doc_id)
    if doc.status == "IDENTIFYING":
        raise err(409, "PROCESSING_IN_PROGRESS", "Wait for the student details to be read before deleting.")
    doc.is_active = False  # original file stays on disk
    audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="answer_sheet", entity_id=doc.id,
          action="unassigned_answer_sheet_deleted", old=doc.original_filename)
    db.commit()
    return {"ok": True}


@router.get("/exams/{exam_id}/answer-sheets")
def list_answer_sheets(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    exam = get_exam(db, t, exam_id)
    out = []
    for ev in db.query(Evaluation).filter_by(exam_id=exam.id).order_by(Evaluation.created_at):
        doc = db.get(AnswerSheetDocument, ev.answer_sheet_id)
        answers = db.query(StudentAnswer).filter_by(evaluation_id=ev.id).all()
        out.append({**evaluation_view(ev), "document": doc_view(doc, "answer-sheet"),
                    "detected_answers": len(answers),
                    "unresolved_answers": sum(a.status in ("UNMAPPED", "NEEDS_REVIEW") for a in answers)})
    return out


@router.delete("/evaluations/{ev_id}")
def delete_answer_sheet(ev_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    from ..deps import get_evaluation
    ev = get_evaluation(db, t, ev_id)
    if ev.status == "FINALIZED":
        raise err(409, "EVALUATION_FINALIZED", "A finalized evaluation cannot be deleted.")
    if db.query(AnswerSheetDocument).filter_by(id=ev.answer_sheet_id, status="OCR_PROCESSING").first():
        raise err(409, "PROCESSING_IN_PROGRESS", "Wait for processing to finish before deleting.")
    audit(db, exam_id=ev.exam_id, teacher_id=t.id, entity_type="evaluation", entity_id=ev.id,
          action="answer_sheet_deleted", old={"student": ev.student.name, "status": ev.status})
    db.query(EvaluationItem).filter_by(evaluation_id=ev.id).delete()
    db.query(StudentAnswer).filter_by(evaluation_id=ev.id).delete()
    doc = db.get(AnswerSheetDocument, ev.answer_sheet_id)
    db.delete(ev)
    if doc:
        doc.is_active = False  # original file stays on disk
    db.commit()
    return {"ok": True}


# ---------- generic document access ----------
def _doc(db: Session, t: Teacher, kind: str, doc_id: str):
    if kind not in KINDS:
        raise err(404, "NOT_FOUND", "Unknown document kind.")
    doc = db.get(KINDS[kind][0], doc_id)
    if not doc:
        raise err(404, "NOT_FOUND", "Document not found.")
    get_exam(db, t, doc.exam_id)
    return doc


@router.get("/documents/{kind}/{doc_id}")
def document_status(kind: str, doc_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    return doc_view(_doc(db, t, kind, doc_id), kind)


@router.get("/documents/{kind}/{doc_id}/pdf")
@router.get("/documents/{kind}/{doc_id}/download")
def download_document_pdf(kind: str, doc_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    doc = _doc(db, t, kind, doc_id)
    return _serve_document_pdf(doc)


@router.get("/documents/{kind}/{doc_id}/pages/{page}/image")
def page_image(kind: str, doc_id: str, page: int, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    doc = _doc(db, t, kind, doc_id)
    for p in doc.pages:
        if p["page_number"] == page:
            f = abs_path(p["source_file"])
            if not f.is_file():
                raise err(404, "FILES_DELETED", "This page image is no longer stored (exam files are deleted after finalization).")
            return FileResponse(f, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})
    raise err(404, "NOT_FOUND", "Page not found.")


@router.get("/documents/{kind}/{doc_id}/pages/{page}/ocr")
def page_ocr_diagnostic(kind: str, doc_id: str, page: int, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    """Raw model output for a page. Shown to teachers as diagnostics, never as extracted data."""
    import json
    doc = _doc(db, t, kind, doc_id)
    for p in doc.pages:
        if p["page_number"] == page and p.get("ocr_file") and abs_path(p["ocr_file"]).is_file():
            d = json.loads(abs_path(p["ocr_file"]).read_text(encoding="utf-8"))
            return {"page_number": page, "status": d.get("status"), "error": d.get("error"),
                    "raw": (d.get("raw") or "")[:20000]}
    raise err(404, "NOT_FOUND", "No reading output stored for this page.")


@router.post("/documents/{kind}/{doc_id}/reprocess", status_code=202)
def reprocess(kind: str, doc_id: str, bg: BackgroundTasks, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    """Re-run OCR on pages that failed (or the whole document if AI was unavailable before rendering finished)."""
    doc = _doc(db, t, kind, doc_id)
    exam = get_exam(db, t, doc.exam_id)
    if doc.status in BUSY:
        raise err(409, "PROCESSING_IN_PROGRESS", "This document is already being processed.")
    if not doc.is_active:
        raise err(409, "DOCUMENT_INACTIVE", "This document was replaced by a newer upload.")
    if kind == "question-paper" and exam.status not in ("QUESTION_PAPER_UPLOADED", "QUESTIONS_EXTRACTED"):
        raise err(409, "QUESTIONS_LOCKED", "Questions are already verified.")
    if kind == "answer-key" and exam.status != "ANSWER_KEY_UPLOADED":
        raise err(409, "ANSWER_KEY_LOCKED", "The answer key is already verified.")
    if kind == "answer-sheet":
        ev = db.query(Evaluation).filter_by(answer_sheet_id=doc.id).first()
        if ev is None or ev.status == "FINALIZED" or db.query(EvaluationItem).filter_by(evaluation_id=ev.id).first():
            raise err(409, "EVALUATION_LOCKED", "Evaluation has started for this answer sheet. Delete it and upload again.")
    only_failed = bool(doc.pages) and all("ocr_status" in p for p in doc.pages)
    if kind == "question-paper" and exam.status == "QUESTIONS_EXTRACTED":
        set_state(exam, "QUESTION_PAPER_UPLOADED")
    from ..services.pipeline import _CANCEL_REQUESTED
    _CANCEL_REQUESTED.discard(doc.id)
    doc.status, doc.stage = "UPLOADED", "Queued"
    doc.error_message = None
    db.commit()
    bg.add_task(process_document, kind, doc.id, only_failed)
    return doc_view(doc, kind)


@router.post("/documents/{kind}/{doc_id}/cancel")
def cancel_processing(kind: str, doc_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    """Cancel ongoing OCR processing for a document."""
    doc = _doc(db, t, kind, doc_id)
    from ..services.pipeline import request_cancellation
    request_cancellation(doc.id)
    doc.status = "CANCELLED"
    doc.stage = "Cancelled by user"
    doc.error_message = "Reading was stopped by the user."
    db.commit()
    return doc_view(doc, kind)



@router.get("/crops/{entity}/{entity_id}")
def crop(entity: str, entity_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    model = {"question": ExamQuestion, "answer-key": AnswerKey, "student-answer": StudentAnswer}.get(entity)
    if model is None:
        raise err(404, "NOT_FOUND", "Unknown crop type.")
    row = db.get(model, entity_id)
    if row is None or not row.crop_file:
        raise err(404, "NOT_FOUND", "No crop stored for this item.")
    if entity == "student-answer":
        ev = db.get(Evaluation, row.evaluation_id)
        get_exam(db, t, ev.exam_id)
    else:
        get_exam(db, t, row.exam_id)
    p = abs_path(row.crop_file)
    if not p.exists():
        raise err(404, "NOT_FOUND", "No crop image found on disk.")
    return FileResponse(p, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})
