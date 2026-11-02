"""Exam files after finalization: keep each student's official PDF report, delete everything else from disk.

Deleted after a grace period: uploaded originals, rendered page images, answer crops and raw AI output.
The database (questions, answer text, marks, feedback, audit log) is kept, so results, the marksheet and
K-level analysis keep working.
"""
from __future__ import annotations
import logging
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..documents.storage import safe_join, data_root
from ..models import Evaluation, Exam, Teacher
from .audit import audit

log = logging.getLogger("adem.exam_files")
GRACE = timedelta(hours=24)
CHECK_EVERY_SECONDS = 15 * 60
REPORTS = "reports"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    # SQLite hands datetimes back without a timezone; they are stored in UTC
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def exam_dir(exam_id: str) -> Path:
    return safe_join(data_root(), "exams", exam_id)


def stored_report(ev: Evaluation) -> Path | None:
    d = exam_dir(ev.exam_id) / REPORTS
    return next(iter(sorted(d.glob(f"{ev.id}__*.pdf"))), None) if d.is_dir() else None


def save_reports_and_schedule(db: Session, teacher: Teacher, exam: Exam) -> int:
    """Called right after the exam is finalized: keep every student's PDF report, then start the 24-hour clock."""
    from .school_reports import build_evaluation_pdf_report
    out = exam_dir(exam.id) / REPORTS
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for ev in db.query(Evaluation).filter_by(exam_id=exam.id, status="FINALIZED"):
        pdf, filename = build_evaluation_pdf_report(db, teacher, ev.id)
        for old in out.glob(f"{ev.id}__*.pdf"):
            old.unlink()
        (out / f"{ev.id}__{filename}").write_bytes(pdf)
        from ..documents.cloud import sync_file
        sync_file(out / f"{ev.id}__{filename}")
        n += 1
    exam.files_purge_at = _now() + GRACE
    audit(db, exam_id=exam.id, teacher_id=teacher.id, entity_type="exam", entity_id=exam.id, action="exam_reports_saved",
          new={"reports": n, "files_delete_at": exam.files_purge_at.isoformat()})
    return n


def purge_exam_files(db: Session, exam: Exam, teacher_id: str | None = None) -> int:
    """Delete the exam's files from disk, keeping saved reports. Returns how many entries were removed."""
    root = exam_dir(exam.id)
    from ..documents.cloud import remove_prefix
    remove_prefix(f"exams/{exam.id}", keep_reports=True)
    removed = 0
    if root.is_dir():
        for child in root.iterdir():
            if child.name == REPORTS:
                continue
            shutil.rmtree(child) if child.is_dir() else child.unlink()
            removed += 1
    exam.files_purged_at = _now()
    audit(db, exam_id=exam.id, teacher_id=teacher_id, entity_type="exam", entity_id=exam.id, action="exam_files_deleted",
          new={"removed": removed})
    return removed


def purge_due() -> int:
    db = SessionLocal()
    n = 0
    try:
        from ..routes.uploads import purge_expired_uploads
        purge_expired_uploads(db)
        for exam in db.query(Exam).filter(Exam.status == "FINALIZED", Exam.files_purge_at.isnot(None),
                                          Exam.files_purged_at.is_(None)).all():
            if _aware(exam.files_purge_at) <= _now():
                try:
                    purge_exam_files(db, exam)
                    db.commit()
                    n += 1
                except OSError:
                    db.rollback()
                    log.exception("Could not delete files of exam %s; will retry", exam.id)
    finally:
        db.close()
    return n


def start_purge_scheduler() -> None:
    """Check now (catches deadlines that passed while the server was off), then every 15 minutes."""
    def loop():
        while True:
            try:
                purge_due()
            except Exception:
                log.exception("Scheduled file deletion failed")
            time.sleep(CHECK_EVERY_SECONDS)
    threading.Thread(target=loop, name="exam-file-purge", daemon=True).start()
