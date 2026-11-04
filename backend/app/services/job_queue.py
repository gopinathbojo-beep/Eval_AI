"""Background AI job queue for OpenRouter; AI_PARALLEL_JOBS documents are read at once."""
from __future__ import annotations
import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable
from ..config import get_settings
from ..database import SessionLocal
from ..models import Exam
from .. import formatter
from . import paper_format
from ..actor import actor_id
from ..models import Teacher
from ..workspaces import can_access_exam

log = logging.getLogger("adem.queue")


@dataclass(eq=False)
class _Job:
    fn: Callable
    args: tuple
    paper_format: str | None = None  # the exam subject's format, see services/paper_format.py
    subject: str | None = None  # the exam subject's formatter, see app/formatter
    exam_id: str | None = None
    actor_id: str | None = None
    session_version: int | None = None
    job_id: str | None = None


_cond = threading.Condition()  # guards _waiting and _running
_waiting: list[_Job] = []  # queue order
_running = 0
_workers: list[threading.Thread] = []
_scheduled: set[str] = set()
_inline_lock = threading.RLock()  # inline jobs may queue more jobs (identify -> read), which run in the same thread

_key_locks: dict[str, threading.RLock] = {}
_key_guard = threading.Lock()


def keyed_lock(key: str) -> threading.RLock:
    """One lock per key (e.g. "exam:<id>"), for work that jobs running in parallel must not do at the same time."""
    with _key_guard:
        return _key_locks.setdefault(key, threading.RLock())


def format_for(exam_id: str | None) -> str | None:
    db = SessionLocal()
    try:
        return paper_format.for_exam(db.get(Exam, exam_id) if exam_id else None)
    finally:
        db.close()


def subject_for(exam_id: str | None) -> str | None:
    if not exam_id:
        return None
    db = SessionLocal()
    try:
        return formatter.for_exam(db.get(Exam, exam_id))
    except Exception:  # no database (scripts, some tests): the paper format alone still picks Tamil
        return None
    finally:
        db.close()


def slots() -> int:
    return max(1, get_settings().ai_parallel_jobs)


def _call(job: _Job) -> None:
    from . import persistent_queue
    stopped, outcome = threading.Event(), "COMPLETED"
    if job.job_id:
        try:
            claimed = persistent_queue.claim(job.job_id)
        except Exception:
            claimed = False
            log.warning("Could not claim durable job; recovery will retry.")
        if not claimed:
            with _cond:
                _scheduled.discard(job.job_id)
            return
        threading.Thread(target=persistent_queue.heartbeat, args=(job.job_id, stopped), daemon=True).start()
    context = actor_id.set(job.actor_id)
    try:
        if job.actor_id:
            with SessionLocal() as db:
                user = db.get(Teacher, job.actor_id)
                exam = db.get(Exam, job.exam_id) if job.exam_id else None
                if not user or user.session_version != job.session_version or (exam and not can_access_exam(db, user, exam)):
                    outcome = "CANCELLED"
                    log.warning("Skipped job after access changed: %s", job.exam_id)
                    if exam:
                        from ..models import Evaluation, QuestionPaperDocument, AnswerKeyDocument, AnswerSheetDocument
                        for model in (QuestionPaperDocument, AnswerKeyDocument, AnswerSheetDocument):
                            for document in db.query(model).filter_by(exam_id=exam.id).filter(model.status.in_(("UPLOADED", "RENDERING", "OCR_PROCESSING", "EXTRACTING"))):
                                document.status = "NEEDS_ATTENTION"
                                document.stage = "Access changed; retry when access is restored"
                        for evaluation in db.query(Evaluation).filter_by(exam_id=exam.id, run_status="RUNNING"):
                            evaluation.run_status = "ERROR"
                        db.commit()
                    return
        with paper_format.use(job.paper_format), formatter.use(job.subject):
            job.fn(*job.args)
    except Exception:  # a failed job must never stop the queue; the job itself records errors on its document
        outcome = "FAILED"
        log.exception("Queued job %s%r crashed", getattr(job.fn, "__name__", job.fn), job.args)
    finally:
        stopped.set()
        if job.job_id:
            try:
                persistent_queue.finish(job.job_id, outcome)
            except Exception:
                log.warning("Could not save background job completion")
            with _cond:
                _scheduled.discard(job.job_id)
        actor_id.reset(context)


def _work() -> None:
    global _running
    while True:
        with _cond:
            while not _waiting or _running >= slots():
                _cond.wait()
            job = _waiting.pop(0)
            _running += 1
        try:
            _call(job)
        finally:
            with _cond:
                _running -= 1
                _cond.notify_all()


def _ensure_workers() -> None:
    want = slots()
    _workers[:] = [w for w in _workers if w.is_alive()]
    while len(_workers) < want:
        w = threading.Thread(target=_work, name=f"ai-job-queue-{len(_workers) + 1}", daemon=True)
        w.start()
        _workers.append(w)


def submit(exam_id: str | None, fn: Callable, *args: Any, grading: bool = False) -> None:
    """Queue `fn(*args)` for the AI workers, oldest first. `grading` is accepted from older callers and has no effect."""
    job = _Job(fn, args, format_for(exam_id), subject_for(exam_id), exam_id)
    job.actor_id = actor_id.get()
    if job.actor_id:
        with SessionLocal() as db:
            user = db.get(Teacher, job.actor_id)
            job.session_version = user.session_version if user else None
    if get_settings().durable_jobs:
        from .persistent_queue import persist
        job.job_id = persist(job)
        if not job.job_id:
            return
        with _cond:
            _scheduled.add(job.job_id)
    if get_settings().job_queue_inline:  # run in the caller's thread (tests: the result is there when the request returns)
        with _inline_lock:
            _call(job)
        return
    with _cond:
        _ensure_workers()
        _waiting.append(job)
        _cond.notify_all()


def pending() -> int:
    """Jobs waiting, not counting the ones running."""
    with _cond:
        return len(_waiting)


def wait_idle(timeout: float | None = None) -> bool:
    """Block until no job is waiting or running. False on timeout."""
    with _cond:
        return _cond.wait_for(lambda: not _waiting and not _running, timeout)
