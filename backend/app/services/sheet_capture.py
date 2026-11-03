"""Page-by-page scanning by an uploader: the "bread package" flow.

The uploader types a roll number, photographs the pages one by one, then ends. The typed roll number alone says whose
sheet it is: nothing is read from the sheet to identify the student. On finish the pages become one PDF and a job
links it to that student and reads and grades it; a roll that already has a sheet in the exam is held for the school.

While pages arrive the sheet is status CAPTURING with its photos under <sheet dir>/pages/NNN.<ext>; startup recovery
leaves such sheets alone (the uploader may still finish them; the school or uploader can discard them)."""
from __future__ import annotations

import logging
from pathlib import Path

from ..config import get_settings
from ..database import SessionLocal
from ..documents.storage import abs_path
from ..models import AnswerSheetDocument, Evaluation, Student
from .job_queue import keyed_lock
from .student_identity import assign_student, run_sheet

log = logging.getLogger("adem.capture")
CAPTURING = "CAPTURING"


def page_files(doc: AnswerSheetDocument) -> list[Path]:
    """The photographed pages in order (pages/001.jpg, 002.png ...)."""
    folder = abs_path(doc.original_file).parent / "pages"
    if get_settings().storage_provider == "supabase":  # after a restart /tmp is empty: fetch the pages saved so far
        from ..documents.cloud import SupabaseStorage, hydrate
        data = get_settings().data_path
        for key in SupabaseStorage().keys(folder.resolve().relative_to(data.resolve()).as_posix()):
            hydrate(data / key)
    return sorted(folder.glob("[0-9][0-9][0-9].*")) if folder.is_dir() else []


def complete_sheet(doc_id: str, student_id: str, teacher_id: str | None) -> None:
    """Job after finish: link the sheet to the typed roll number's student, then read and grade it."""
    with keyed_lock(f"sheet:{doc_id}"):
        db = SessionLocal()
        try:
            doc = db.get(AnswerSheetDocument, doc_id)
            if doc is None or not doc.is_active or doc.student_id is not None:
                return
            identity = dict(doc.identity or {})
            student = db.get(Student, student_id)
            note = None if student else "Student not found."
            if student and db.query(Evaluation.id).filter_by(exam_id=doc.exam_id, student_id=student.id).first():
                note = f"Roll number {student.roll_number} already has an answer sheet in this exam."
            if note:
                doc.status, doc.stage = "NEEDS_STUDENT", "Pick the student"
                doc.identity = {**identity, "match": "HOLD", "student_id": None, "note": note,
                                "read": {"roll_number": identity.get("typed_roll")},
                                "candidates": [student.id] if student else []}
                db.commit()
                return
            doc.identity = {**identity, "match": "AUTO", "note": "Roll number typed by the uploader."}
            assign_student(db, doc, student, teacher_id, "typed roll number")
            db.commit()
        finally:
            db.close()
    run_sheet(doc_id)
