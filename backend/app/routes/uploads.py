"""Small authenticated requests coordinate large browser-to-private-storage uploads."""
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Literal
import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.datastructures import Headers
from ..config import get_settings
from ..database import get_db
from ..deps import err, get_exam
from ..documents.cloud import SupabaseStorage
from ..documents.storage import ALLOWED
from ..models import PendingUpload, Teacher, Evaluation
from ..security import current_teacher

direct_upload_id: ContextVar[str | None] = ContextVar("direct_upload_id", default=None)
router = APIRouter(prefix="/api")


class UploadIn(BaseModel):
    kind: Literal["question-paper", "answer-key", "answer-sheet"]
    filename: str = Field(min_length=1, max_length=290)
    file_size: int = Field(gt=0)
    student_id: str | None = None
    student_name: str | None = Field(None, max_length=200)
    roll_number: str | None = Field(None, max_length=50)


@router.post("/exams/{exam_id}/uploads", status_code=201)
def begin_upload(exam_id: str, body: UploadIn, db: Session = Depends(get_db), user: Teacher = Depends(current_teacher)):
    from .documents import EXT, _require_sheet_state
    exam = get_exam(db, user, exam_id)
    if get_settings().storage_provider != "supabase":
        raise err(409, "LOCAL_STORAGE", "Use the normal file upload for local storage.")
    if body.kind == "answer-sheet":
        _require_sheet_state(exam)
    if "/" in body.filename or "\\" in body.filename or ".." in body.filename or "\x00" in body.filename:
        raise err(400, "INVALID_FILENAME", "Use a plain filename.")
    ext = body.filename.rsplit(".", 1)[-1].lower()
    if ext not in EXT[body.kind]:
        raise err(400, "INVALID_FILE", "Unsupported file type.")
    if body.file_size > get_settings().max_upload_mb * 1024 * 1024:
        raise err(413, "FILE_TOO_LARGE", "The file exceeds the upload limit.")
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    if db.query(PendingUpload).filter(PendingUpload.actor_id == user.id, PendingUpload.created_at >= recent, PendingUpload.result.is_(None)).count() >= 200:
        raise err(429, "UPLOAD_LIMIT", "Finish existing uploads or try again later.")
    lease = PendingUpload(id=str(uuid.uuid4()), exam_id=exam.id, workspace_id=user.workspace_id, actor_id=user.id,
        object_key="", kind=body.kind, filename=body.filename, file_size=body.file_size, mime_type=ALLOWED[ext][0],
        fields=body.model_dump(include={"student_id", "student_name", "roll_number"}))
    lease.object_key = f"incoming/{user.workspace_id}/{lease.id}/original.{ext}"
    url = SupabaseStorage().signed_upload(lease.object_key)
    db.add(lease)
    db.commit()
    return {"id": lease.id, "upload_url": url, "content_type": lease.mime_type}


def owned_upload(db, user, upload_id):
    lease = db.get(PendingUpload, upload_id)
    if not lease or lease.actor_id != user.id or lease.workspace_id != user.workspace_id:
        raise err(404, "NOT_FOUND", "Upload not found.")
    get_exam(db, user, lease.exam_id)
    return lease


@router.post("/uploads/{upload_id}/complete")
async def complete_upload(upload_id: str, bg: BackgroundTasks, db: Session = Depends(get_db), user: Teacher = Depends(current_teacher)):
    from .documents import upload_question_paper, upload_answer_key, upload_answer_sheet, _unassigned_view
    from ..services.pipeline import KINDS, process_document
    from ..serializers import doc_view, evaluation_view
    from ..services.job_queue import submit
    from ..services.student_identity import identify_sheets
    lease = owned_upload(db, user, upload_id)
    if lease.result:
        return lease.result
    if lease.created_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc) - timedelta(hours=1):
        raise err(410, "UPLOAD_EXPIRED", "Start a new upload; this one has expired.")
    existing = db.get(KINDS[lease.kind][0], lease.id)
    if existing:
        if lease.kind == "answer-sheet" and existing.student_id:
            ev = db.query(Evaluation).filter_by(answer_sheet_id=existing.id).one()
            result = {**evaluation_view(ev), "document": doc_view(existing, lease.kind)}
        else:
            result = _unassigned_view(db, existing) if lease.kind == "answer-sheet" else doc_view(existing, lease.kind)
        if existing.status == "UPLOADED":
            if lease.kind == "answer-sheet" and existing.student_id is None:
                bg.add_task(submit, lease.exam_id, identify_sheets, [existing.id], user.id)
            else:
                bg.add_task(submit, lease.exam_id, process_document, lease.kind, existing.id)
    else:
        data = SupabaseStorage().get(lease.object_key)
        if data is None or len(data) != lease.file_size:
            raise err(400, "UPLOAD_INCOMPLETE", "The uploaded file is missing or its size does not match.")
        file = UploadFile(BytesIO(data), filename=lease.filename, headers=Headers({"content-type": lease.mime_type}))
        token = direct_upload_id.set(lease.id)
        try:
            if lease.kind == "question-paper":
                result = await upload_question_paper(lease.exam_id, bg, file, db, user)
            elif lease.kind == "answer-key":
                result = await upload_answer_key(lease.exam_id, bg, file, db, user)
            else:
                result = await upload_answer_sheet(lease.exam_id, bg, file, lease.fields.get("student_id"), lease.fields.get("student_name"), lease.fields.get("roll_number"), db, user)
        finally:
            direct_upload_id.reset(token)
    lease.result = result
    db.commit()
    SupabaseStorage().delete([lease.object_key])
    return result


def purge_expired_uploads(db):
    if get_settings().storage_provider != "supabase":
        return
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    for lease in db.query(PendingUpload).filter(PendingUpload.created_at < cutoff).limit(200):
        SupabaseStorage().delete([lease.object_key])
        db.delete(lease)
    db.commit()
