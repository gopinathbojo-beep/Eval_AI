from __future__ import annotations
from pathlib import Path
import re
import uuid
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from ..database import get_db
from ..deps import err, get_exam
from ..documents.storage import abs_path, doc_dir, read_validated_upload, rel
from ..models import (
    AnswerKey,
    AnswerKeyDocument,
    Evaluation,
    EvaluationItem,
    ExamQuestion,
    QuestionPaperDocument,
    StudentAnswer,
    Teacher,
)
from ..security import current_teacher
from ..serializers import doc_view
from ..services.audit import audit
from ..services.pipeline import KINDS, process_document
from ..services.job_queue import submit
from ..services.state import set_state
from ..services.student_identity import run_sheet

router = APIRouter(prefix="/api")
BUSY = {"UPLOADED", "RENDERING", "OCR_PROCESSING", "EXTRACTING", "IDENTIFYING"}
ROLL_FORMAT = re.compile(r"^[A-Z0-9/-]{1,20}$")
EXT = {
    "question-paper": {"pdf", "png", "jpg", "jpeg", "docx"},
    "answer-key": {"pdf", "docx", "png", "jpg", "jpeg"},
    "answer-sheet": {"pdf", "png", "jpg", "jpeg", "docx"},
}


def _save(
    db: Session,
    kind: str,
    exam_id: str,
    data: bytes,
    ext: str,
    mime: str,
    filename: str,
    **extra,
):
    model = KINDS[kind][0]
    from .uploads import direct_upload_id

    doc_id = direct_upload_id.get() or str(uuid.uuid4())
    d = doc_dir(kind, exam_id, doc_id, extra.get("student_id"))
    path = d / f"original.{ext}"
    if direct_upload_id.get() and path.is_file():
        if path.read_bytes() != data:
            raise err(
                409, "UPLOAD_CONFLICT", "This upload already contains another file."
            )
    else:
        with open(path, "xb") as f:  # 'x': never overwrite an original
            f.write(data)
    doc = model(
        id=doc_id,
        exam_id=exam_id,
        original_filename=filename[:290],
        original_file=rel(path),
        mime_type=mime,
        file_size=len(data),
        status="UPLOADED",
        stage="Queued",
        **extra,
    )
    db.add(doc)
    return doc


def _busy_check(db: Session, model, **flt):
    if (
        db.query(model)
        .filter_by(is_active=True, **flt)
        .filter(model.status.in_(BUSY))
        .first()
    ):
        raise err(
            409,
            "PROCESSING_IN_PROGRESS",
            "A document is still being processed. Wait for it to finish.",
        )


# ---------- question paper ----------
@router.post("/exams/{exam_id}/question-paper", status_code=202)
async def upload_question_paper(
    exam_id: str,
    bg: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    t: Teacher = Depends(current_teacher),
):
    exam = get_exam(db, t, exam_id)
    if exam.status not in ("DRAFT", "QUESTION_PAPER_UPLOADED", "QUESTIONS_EXTRACTED"):
        raise err(
            409,
            "QUESTIONS_LOCKED",
            "Questions are already verified, so the question paper can no longer be replaced.",
        )
    _busy_check(db, QuestionPaperDocument, exam_id=exam.id)
    data, ext, mime = await read_validated_upload(file, EXT["question-paper"])
    for old in db.query(QuestionPaperDocument).filter_by(
        exam_id=exam.id, is_active=True
    ):
        old.is_active = False
    doc = _save(
        db, "question-paper", exam.id, data, ext, mime, file.filename or "upload"
    )
    set_state(exam, "QUESTION_PAPER_UPLOADED")
    db.flush()
    audit(
        db,
        exam_id=exam.id,
        teacher_id=t.id,
        entity_type="question_paper",
        entity_id=doc.id,
        action="question_paper_uploaded",
        new=doc.original_filename,
    )
    db.commit()
    bg.add_task(submit, exam.id, process_document, "question-paper", doc.id)
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
            filename=raw_filename
            if raw_filename.lower().endswith(".pdf")
            else download_filename,
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
def get_question_paper(
    exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)
):
    exam = get_exam(db, t, exam_id)
    doc = (
        db.query(QuestionPaperDocument)
        .filter_by(exam_id=exam.id, is_active=True)
        .order_by(QuestionPaperDocument.uploaded_at.desc())
        .first()
    )
    return doc_view(doc, "question-paper")


@router.get("/exams/{exam_id}/question-paper/pdf")
@router.get("/exams/{exam_id}/question-paper/download")
def download_question_paper_pdf(
    exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)
):
    exam = get_exam(db, t, exam_id)
    doc = (
        db.query(QuestionPaperDocument)
        .filter_by(exam_id=exam.id, is_active=True)
        .order_by(QuestionPaperDocument.uploaded_at.desc())
        .first()
    )
    if not doc:
        raise err(404, "NOT_FOUND", "No question paper uploaded for this exam.")
    return _serve_document_pdf(doc)


# ---------- answer key ----------
@router.post("/exams/{exam_id}/answer-key", status_code=202)
async def upload_answer_key(
    exam_id: str,
    bg: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    t: Teacher = Depends(current_teacher),
):
    exam = get_exam(db, t, exam_id)
    early = exam.status in EARLY_KEY_STATES
    if not early and exam.status not in (
        "QUESTIONS_VERIFIED",
        "ANSWER_KEY_UPLOADED",
        "ANSWER_KEY_VERIFIED",
        "READY_FOR_EVALUATION",
    ):
        raise err(
            409,
            "ANSWER_KEY_LOCKED",
            "Evaluation has started, so the answer key can no longer be replaced.",
        )
    if (
        db.query(EvaluationItem)
        .join(Evaluation, Evaluation.id == EvaluationItem.evaluation_id)
        .filter(Evaluation.exam_id == exam.id)
        .first()
    ):
        raise err(
            409,
            "ANSWER_KEY_LOCKED",
            "Evaluation has started, so the answer key can no longer be replaced.",
        )
    _busy_check(db, AnswerKeyDocument, exam_id=exam.id)
    data, ext, mime = await read_validated_upload(file, EXT["answer-key"])
    for old in db.query(AnswerKeyDocument).filter_by(exam_id=exam.id, is_active=True):
        old.is_active = False
    for k in db.query(AnswerKey).filter_by(exam_id=exam.id, is_active=True):
        k.is_active = False
    doc = _save(db, "answer-key", exam.id, data, ext, mime, file.filename or "upload")
    if not early:
        set_state(exam, "ANSWER_KEY_UPLOADED")
    # one by one: an early key waits, unread, until the question paper's questions are extracted
    # (pipeline._build_questions then queues it)
    if early and not db.query(ExamQuestion.id).filter_by(exam_id=exam.id).first():
        doc.status, doc.stage = "WAITING", "Waiting for the question paper"
    db.flush()
    audit(
        db,
        exam_id=exam.id,
        teacher_id=t.id,
        entity_type="answer_key",
        entity_id=doc.id,
        action="answer_key_uploaded",
        new=doc.original_filename,
    )
    db.commit()
    if doc.status != "WAITING":
        bg.add_task(submit, exam.id, process_document, "answer-key", doc.id)
    return doc_view(doc, "answer-key")


EARLY_KEY_STATES = ("DRAFT", "QUESTION_PAPER_UPLOADED", "QUESTIONS_EXTRACTED")


def release_waiting_key(db: Session, exam, bg: BackgroundTasks) -> bool:
    """Called once questions are verified: move the exam on to its answer key (read early, or still waiting)."""
    doc = (
        db.query(AnswerKeyDocument)
        .filter_by(exam_id=exam.id, is_active=True, status="WAITING")
        .first()
    )
    if doc is None:
        if (
            db.query(AnswerKeyDocument)
            .filter_by(exam_id=exam.id, is_active=True)
            .filter(AnswerKeyDocument.status.in_(("READY", "NEEDS_ATTENTION")))
            .first()
        ):
            set_state(exam, "ANSWER_KEY_UPLOADED")
            db.commit()
        return False
    set_state(exam, "ANSWER_KEY_UPLOADED")
    doc.status, doc.stage = "UPLOADED", "Queued"
    db.commit()
    bg.add_task(submit, exam.id, process_document, "answer-key", doc.id)
    return True


@router.get("/exams/{exam_id}/answer-key")
def get_answer_key_doc(
    exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)
):
    exam = get_exam(db, t, exam_id)
    doc = (
        db.query(AnswerKeyDocument)
        .filter_by(exam_id=exam.id, is_active=True)
        .order_by(AnswerKeyDocument.uploaded_at.desc())
        .first()
    )
    return doc_view(doc, "answer-key")


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
def document_status(
    kind: str,
    doc_id: str,
    db: Session = Depends(get_db),
    t: Teacher = Depends(current_teacher),
):
    return doc_view(_doc(db, t, kind, doc_id), kind)


@router.get("/documents/{kind}/{doc_id}/pdf")
@router.get("/documents/{kind}/{doc_id}/download")
def download_document_pdf(
    kind: str,
    doc_id: str,
    db: Session = Depends(get_db),
    t: Teacher = Depends(current_teacher),
):
    doc = _doc(db, t, kind, doc_id)
    return _serve_document_pdf(doc)


@router.get("/documents/{kind}/{doc_id}/pages/{page}/image")
def page_image(
    kind: str,
    doc_id: str,
    page: int,
    db: Session = Depends(get_db),
    t: Teacher = Depends(current_teacher),
):
    doc = _doc(db, t, kind, doc_id)
    for p in doc.pages:
        if p["page_number"] == page:
            f = abs_path(p["source_file"])
            if not f.is_file():
                raise err(
                    404,
                    "FILES_DELETED",
                    "This page image is no longer stored (exam files are deleted after finalization).",
                )
            return FileResponse(
                f,
                media_type="image/png",
                headers={"Cache-Control": "private, max-age=3600"},
            )
    raise err(404, "NOT_FOUND", "Page not found.")


@router.get("/documents/{kind}/{doc_id}/pages/{page}/ocr")
def page_ocr_diagnostic(
    kind: str,
    doc_id: str,
    page: int,
    db: Session = Depends(get_db),
    t: Teacher = Depends(current_teacher),
):
    """Raw model output for a page. Shown to teachers as diagnostics, never as extracted data."""
    import json

    doc = _doc(db, t, kind, doc_id)
    for p in doc.pages:
        if (
            p["page_number"] == page
            and p.get("ocr_file")
            and abs_path(p["ocr_file"]).is_file()
        ):
            d = json.loads(abs_path(p["ocr_file"]).read_text(encoding="utf-8"))
            return {
                "page_number": page,
                "status": d.get("status"),
                "error": d.get("error"),
                "raw": (d.get("raw") or "")[:20000],
            }
    raise err(404, "NOT_FOUND", "No reading output stored for this page.")


@router.post("/documents/{kind}/{doc_id}/reprocess", status_code=202)
def reprocess(
    kind: str,
    doc_id: str,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    t: Teacher = Depends(current_teacher),
):
    """Re-run OCR on pages that failed (or the whole document if AI was unavailable before rendering finished)."""
    doc = _doc(db, t, kind, doc_id)
    exam = get_exam(db, t, doc.exam_id)
    if doc.status in BUSY:
        raise err(
            409, "PROCESSING_IN_PROGRESS", "This document is already being processed."
        )
    if not doc.is_active:
        raise err(
            409, "DOCUMENT_INACTIVE", "This document was replaced by a newer upload."
        )
    if kind == "question-paper" and exam.status not in (
        "QUESTION_PAPER_UPLOADED",
        "QUESTIONS_EXTRACTED",
    ):
        raise err(409, "QUESTIONS_LOCKED", "Questions are already verified.")
    if kind == "answer-key" and exam.status != "ANSWER_KEY_UPLOADED":
        raise err(409, "ANSWER_KEY_LOCKED", "The answer key is already verified.")
    if kind == "answer-sheet":
        ev = db.query(Evaluation).filter_by(answer_sheet_id=doc.id).first()
        if ev is not None and (ev.status == "FINALIZED" or ev.run_status == "RUNNING"):
            raise err(
                409,
                "EVALUATION_LOCKED",
                "This answer sheet is finalized or being graded. It cannot be read again now.",
            )
        if ev is not None:
            # read again and graded again: earlier marks of this sheet were based on the old reading
            db.query(EvaluationItem).filter_by(evaluation_id=ev.id).delete()
            ev.status, ev.run_status, ev.total_marks, ev.percentage = "OCR_REVIEW", "IDLE", None, None
        identity = dict(doc.identity or {})
        if (identity.get("roll_check") or {}).get("status") == "NOT_WRITTEN":
            identity.pop("roll_check")  # look for the written roll number again
        identity.pop("excluded_pages", None)
        doc.identity = identity
    only_failed = bool(doc.pages) and all("ocr_status" in p for p in doc.pages)
    if kind == "question-paper" and exam.status == "QUESTIONS_EXTRACTED":
        set_state(exam, "QUESTION_PAPER_UPLOADED")
    from ..services.pipeline import _CANCEL_REQUESTED

    _CANCEL_REQUESTED.discard(doc.id)
    doc.status, doc.stage = "UPLOADED", "Queued"
    doc.error_message = None
    db.commit()
    if kind == "answer-sheet" and doc.student_id:
        bg.add_task(submit, exam.id, run_sheet, doc.id)  # read, check the roll number, then grade
    else:
        bg.add_task(submit, exam.id, process_document, kind, doc.id, only_failed)
    return doc_view(doc, kind)


@router.post("/documents/{kind}/{doc_id}/cancel")
def cancel_processing(
    kind: str,
    doc_id: str,
    db: Session = Depends(get_db),
    t: Teacher = Depends(current_teacher),
):
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
def crop(
    entity: str,
    entity_id: str,
    db: Session = Depends(get_db),
    t: Teacher = Depends(current_teacher),
):
    model = {
        "question": ExamQuestion,
        "answer-key": AnswerKey,
        "student-answer": StudentAnswer,
    }.get(entity)
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
    return FileResponse(
        p, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"}
    )


@router.get("/crops/{entity}/{entity_id}/visuals/{index}")
def visual_crop(
    entity: str,
    entity_id: str,
    index: int,
    db: Session = Depends(get_db),
    t: Teacher = Depends(current_teacher),
):
    model = {"question": ExamQuestion, "answer-key": AnswerKey}.get(entity)
    if model is None:
        raise err(404, "NOT_FOUND", "Unknown visual crop type.")
    row = db.get(model, entity_id)
    if row is None:
        raise err(404, "NOT_FOUND", "Visual crop not found.")
    get_exam(db, t, row.exam_id)
    values = (
        (row.structure or {}).get("visuals", [])
        if entity == "question"
        else (row.rubric or {}).get("visuals", [])
    )
    if index < 0 or index >= len(values) or not values[index].get("crop_file"):
        raise err(404, "NOT_FOUND", "Visual crop not found.")
    path = abs_path(values[index]["crop_file"])
    if not path.exists():
        raise err(404, "NOT_FOUND", "Visual crop image is no longer stored.")
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=86400"},
    )
