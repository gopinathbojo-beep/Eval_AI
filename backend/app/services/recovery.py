"""Startup recovery. Background jobs live in-process, so a restart orphans anything that was mid-run."""
from __future__ import annotations
import logging
from ..database import SessionLocal
from ..models import AnswerKeyDocument, AnswerSheetDocument, Evaluation, Exam, QuestionPaperDocument, StudentAnswer

log = logging.getLogger("adem.recovery")
BUSY = ("UPLOADED", "RENDERING", "OCR_PROCESSING", "EXTRACTING", "IDENTIFYING")
INTERRUPTED = "Processing was interrupted by a server restart. Use Reprocess to continue."
IDENTIFY_INTERRUPTED = "Reading the student details was interrupted by a server restart. Pick the student or retry."


def recover_interrupted_jobs() -> None:
    db = SessionLocal()
    try:
        from ..config import get_settings
        from .persistent_queue import protected_exams
        protected = protected_exams(db) if get_settings().durable_jobs else []
        n_docs = 0
        for model in (QuestionPaperDocument, AnswerKeyDocument, AnswerSheetDocument):
            for doc in db.query(model).filter(model.status.in_(BUSY), model.exam_id.notin_(protected)).all():
                if model is AnswerSheetDocument and doc.student_id is None:
                    # not yet identified: hand it to the teacher instead of failing it
                    doc.status, doc.stage = "NEEDS_STUDENT", "Pick the student"
                    doc.identity = {**(doc.identity or {}), "match": "HOLD", "note": IDENTIFY_INTERRUPTED,
                                    "candidates": (doc.identity or {}).get("candidates") or []}
                else:
                    doc.status, doc.stage, doc.error_message = "FAILED", "Interrupted", INTERRUPTED
                n_docs += 1
        running = db.query(Evaluation).filter(Evaluation.run_status == "RUNNING", Evaluation.exam_id.notin_(protected)).all()
        for ev in running:
            ev.run_status = "ERROR"
            for a in db.query(StudentAnswer).filter_by(evaluation_id=ev.id, status="EVALUATING").all():
                a.status = "MAPPED"
        for exam in db.query(Exam).filter(Exam.status == "EVALUATING", Exam.id.notin_(protected)).all():
            exam.status = "REVIEW_REQUIRED"
        db.commit()
        if n_docs or running:
            log.warning("Recovered %d interrupted document(s) and %d evaluation run(s)", n_docs, len(running))
    finally:
        db.close()
