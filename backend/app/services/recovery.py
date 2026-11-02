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
        resume: list[tuple[str, str, str, bool]] = []  # (exam, kind, document, only the pages not read yet)
        kinds = {QuestionPaperDocument: "question-paper", AnswerKeyDocument: "answer-key", AnswerSheetDocument: "answer-sheet"}
        for model in (QuestionPaperDocument, AnswerKeyDocument, AnswerSheetDocument):
            for doc in db.query(model).filter(model.status.in_(BUSY), model.exam_id.notin_(protected)).all():
                if model is AnswerSheetDocument and doc.student_id is None:
                    # not yet identified: hand it to the teacher instead of failing it
                    doc.status, doc.stage = "NEEDS_STUDENT", "Pick the student"
                    doc.identity = {**(doc.identity or {}), "match": "HOLD", "note": IDENTIFY_INTERRUPTED,
                                    "candidates": (doc.identity or {}).get("candidates") or []}
                elif getattr(doc, "is_active", True) is False:
                    doc.status, doc.stage, doc.error_message = "FAILED", "Interrupted", INTERRUPTED
                else:
                    # carry on where it stopped: the pages already read are kept, the rest are read now
                    doc.status, doc.stage, doc.error_message = "UPLOADED", "Resuming after a server restart", None
                    resume.append((doc.exam_id, kinds[model], doc.id,
                                   bool(doc.pages) and any("ocr_status" in p for p in doc.pages)))
                n_docs += 1
        running = db.query(Evaluation).filter(Evaluation.run_status == "RUNNING", Evaluation.exam_id.notin_(protected)).all()
        for ev in running:
            ev.run_status = "ERROR"
            for a in db.query(StudentAnswer).filter_by(evaluation_id=ev.id, status="EVALUATING").all():
                a.status = "MAPPED"
        for exam in db.query(Exam).filter(Exam.status == "EVALUATING", Exam.id.notin_(protected)).all():
            exam.status = "REVIEW_REQUIRED"
        db.commit()
        if resume:
            from .job_queue import submit
            from .pipeline import process_document
            for exam_id, kind, doc_id, only_failed in resume:
                submit(exam_id, process_document, kind, doc_id, only_failed)
        if n_docs or running:
            log.warning("Recovered %d interrupted document(s) (%d resumed) and %d evaluation run(s)",
                        n_docs, len(resume), len(running))
    finally:
        db.close()
