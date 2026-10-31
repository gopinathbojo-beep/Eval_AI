"""Durable job metadata for one API service. Interrupted AI work requires explicit retry."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import json
import logging
import threading
import uuid
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from ..config import get_settings
from ..database import SessionLocal
from ..models import BackgroundJob, Exam, Evaluation, QuestionPaperDocument, AnswerKeyDocument, AnswerSheetDocument

log = logging.getLogger("adem.jobs")
WORKER = str(uuid.uuid4())
STALE_SECONDS = 120
HANDLERS = {"app.services.pipeline:process_document", "app.services.student_identity:identify_sheets",
            "app.services.student_identity:run_sheet", "app.services.student_identity:_read_sheet",
            "app.services.evaluation_service:run_evaluation"}


def now():
    return datetime.now(timezone.utc)


def persist(job):
    handler = job.fn.__module__ + ":" + job.fn.__name__
    if handler not in HANDLERS:
        raise ValueError("This background handler is not registered for durable execution")
    active_key = hashlib.sha256(json.dumps([handler, job.exam_id, job.args], sort_keys=True).encode()).hexdigest()
    with SessionLocal() as db:
        exam = db.get(Exam, job.exam_id) if job.exam_id else None
        row = BackgroundJob(exam_id=job.exam_id, workspace_id=exam.workspace_id if exam else None,
            actor_id=job.actor_id, session_version=job.session_version, handler=handler, active_key=active_key,
            payload={"args": list(job.args), "engine": job.engine, "paper_format": job.paper_format,
                     "subject": job.subject, "tamil_grading": job.tamil_grading}, status="QUEUED")
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return None  # The same operation is already queued/running.
        return row.id


def claim(job_id):
    with SessionLocal() as db:
        changed = db.query(BackgroundJob).filter_by(id=job_id, status="QUEUED").update({
            BackgroundJob.status: "RUNNING", BackgroundJob.started_at: now(),
            BackgroundJob.worker_id: WORKER, BackgroundJob.heartbeat_at: now()})
        db.commit()
        return bool(changed)


def heartbeat(job_id, stopped):
    while not stopped.wait(20):
        try:
            with SessionLocal() as db:
                db.query(BackgroundJob).filter_by(id=job_id, worker_id=WORKER, status="RUNNING").update({BackgroundJob.heartbeat_at: now()})
                db.commit()
        except Exception:
            log.warning("Could not update background job heartbeat")


def finish(job_id, outcome):
    with SessionLocal() as db:
        row = db.get(BackgroundJob, job_id)
        if not row or row.worker_id != WORKER or row.status != "RUNNING":
            return
        if outcome == "COMPLETED":
            args = row.payload.get("args") or []
            if row.handler.endswith(":process_document") and len(args) >= 2:
                model = {"question-paper": QuestionPaperDocument, "answer-key": AnswerKeyDocument, "answer-sheet": AnswerSheetDocument}.get(args[0])
                doc = db.get(model, args[1]) if model else None
                if not doc or doc.status in {"FAILED", "AI_ERROR"}:
                    outcome = "FAILED"
            elif row.handler.endswith(":run_evaluation") and args:
                evaluation = db.get(Evaluation, args[0])
                if not evaluation or evaluation.run_status == "ERROR":
                    outcome = "FAILED"
        row.status, row.finished_at, row.active_key = outcome, now(), None
        row.error = "Processing failed; review the document/evaluation and retry." if outcome == "FAILED" else None
        db.commit()


def recover_stale():
    cutoff = now() - timedelta(seconds=STALE_SECONDS)
    with SessionLocal() as db:
        rows = db.query(BackgroundJob).filter(BackgroundJob.status == "RUNNING",
             or_(BackgroundJob.heartbeat_at.is_(None), BackgroundJob.heartbeat_at < cutoff))
        for row in rows:
            row.status, row.active_key, row.finished_at = "INTERRUPTED", None, now()
            row.error = "Worker stopped before completion. Review and retry; AI calls are not automatically charged again."
        db.commit()


def protected_exams(db):
    cutoff = now() - timedelta(seconds=STALE_SECONDS)
    return [r[0] for r in db.query(BackgroundJob.exam_id).filter(or_(
        BackgroundJob.status == "QUEUED", (BackgroundJob.status == "RUNNING") & (BackgroundJob.heartbeat_at >= cutoff))).distinct()]


def restore_queued():
    from . import job_queue
    with SessionLocal() as db:
        for row in db.query(BackgroundJob).filter_by(status="QUEUED").order_by(BackgroundJob.created_at):
            if row.handler not in HANDLERS:
                row.status, row.active_key, row.error = "FAILED", None, "Unknown background handler"
                continue
            module, function = row.handler.split(":", 1)
            payload = row.payload
            job = job_queue._Job(payload["engine"], getattr(importlib.import_module(module), function), tuple(payload["args"]),
                paper_format=payload.get("paper_format"), subject=payload.get("subject"),
                tamil_grading=bool(payload.get("tamil_grading")), exam_id=row.exam_id,
                actor_id=row.actor_id, session_version=row.session_version, job_id=row.id)
            with job_queue._cond:
                if row.id not in job_queue._scheduled:
                    job_queue._scheduled.add(row.id)
                    job_queue._waiting.append(job)
                    job_queue._ensure_workers()
                    job_queue._cond.notify_all()
        db.commit()


def start_recovery():
    if not get_settings().durable_jobs:
        return
    from .recovery import recover_interrupted_jobs
    def tick():
        recover_stale()
        recover_interrupted_jobs()
        restore_queued()
    tick()
    def loop():
        while True:
            threading.Event().wait(30)
            try:
                tick()
            except Exception:
                log.warning("Background recovery is temporarily unavailable")
    threading.Thread(target=loop, name="durable-job-recovery", daemon=True).start()
