"""GPU job queue: jobs grouped by engine, several at a time on the loaded engine, switching engines between groups.

Every job that uses a model (reading papers/keys/sheets, identifying students, grading) is queued here instead of
running as its own background task. The engine its exam needs is the only one on the GPU:
  internvl : InternVL in Ollama
  indic    : IndicOCR service (+ INDIC_TEXT_MODEL in Ollama when one is set). Grading an Indian-language exam with
             InternVL (no text model set) is an "internvl" job, so InternVL never shares the GPU with IndicOCR.
Up to INTERNVL_PARALLEL_JOBS / INDIC_PARALLEL_JOBS jobs run at once on the loaded engine. A waiting job for the loaded
engine may start ahead of older jobs for the other engine, so an English, Tamil, English, Tamil upload runs both English
jobs, switches once, then both Tamil jobs. A job is passed over at most MAX_SKIPS times; then the running jobs finish,
the engine switches and it runs. Tamil papers go one after another: a Tamil grading job is passed over only by jobs of
its own exam (its other sheets still being read), never by another exam's, so a Tamil paper is read with IndicOCR
(question paper, key, sheets), InternVL loads and grades it, and only then does the next paper's reading start.
English jobs (InternVL only) follow the grouping and MAX_SKIPS rule above. Switching unloads the models the next engine does not use, and only happens with no
job running. Jobs live in-process: a restart drops the queue and startup recovery hands the interrupted documents back
to the teacher.
"""
from __future__ import annotations
import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable
from ..config import get_settings
from ..database import SessionLocal
from ..models import Exam
from ..ocr.indic import release_indic, uses_indic_ocr
from ..ocr.internvl import unload_model
from .. import formatter
from . import paper_format
from ..actor import actor_id
from ..models import Teacher
from ..workspaces import can_access_exam

log = logging.getLogger("adem.queue")

MAX_SKIPS = 4  # times a job may be passed over for jobs of the loaded engine before the queue switches to it


@dataclass(eq=False)
class _Job:
    engine: str
    fn: Callable
    args: tuple
    paper_format: str | None = None  # the exam subject's format, see services/paper_format.py
    subject: str | None = None  # the exam subject's formatter, see app/formatter
    tamil_grading: bool = False  # grading a paper IndicOCR read: passed over only by jobs of its own exam
    exam_id: str | None = None
    skips: int = 0
    actor_id: str | None = None
    session_version: int | None = None
    job_id: str | None = None


_cond = threading.Condition()  # guards _waiting, _running, _switching and _current_engine
_waiting: list[_Job] = []  # queue order
_running = 0
_switching = False  # a worker is changing engines outside the lock: no other job starts until it is done
_workers: list[threading.Thread] = []
_scheduled: set[str] = set()
_inline_lock = threading.RLock()  # inline jobs may queue more jobs (identify -> read), which run in the same thread
_current_engine: str | None = None  # None: unknown (e.g. after start), so a first switch frees everything else

_key_locks: dict[str, threading.RLock] = {}
_key_guard = threading.Lock()


def keyed_lock(key: str) -> threading.RLock:
    """One lock per key (e.g. "exam:<id>"), for work that jobs running in parallel must not do at the same time."""
    with _key_guard:
        return _key_locks.setdefault(key, threading.RLock())


def engine_for(exam_id: str | None, grading: bool = False) -> str:
    db = SessionLocal()
    try:
        exam = db.get(Exam, exam_id) if exam_id else None
        if not (exam and exam.subject and uses_indic_ocr(exam.subject.name)):
            return "internvl"
        return "internvl" if grading and not get_settings().indic_text_model.strip() else "indic"
    finally:
        db.close()


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


def slots(engine: str) -> int:
    s = get_settings()
    return max(1, s.indic_parallel_jobs if engine == "indic" else s.internvl_parallel_jobs)


def _ollama_models(engine: str) -> set[str]:
    s = get_settings()
    if engine == "indic":
        return {s.indic_text_model.strip()} - {""}  # no text model: IndicOCR alone, InternVL leaves the GPU
    return {s.internvl_model}


def switch_engine(engine: str) -> None:
    """Make `engine` the only one holding GPU memory. No-op when it already is. Call only with no job running."""
    global _current_engine
    if get_settings().ai_provider != "ollama" and not get_settings().indic_ocr_enabled:
        _current_engine = engine
        return
    if engine == _current_engine:
        return
    previous = [_current_engine] if _current_engine else ["internvl", "indic"]
    for model in set().union(*(_ollama_models(p) for p in previous)) - _ollama_models(engine):
        unload_model(model)
    if engine != "indic" and "indic" in previous:
        release_indic()
    log.info("GPU engine: %s -> %s", _current_engine or "unknown", engine)
    _current_engine = engine


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


def _pick() -> _Job | None:
    """The job a free worker should start now, or None. Caller holds _cond."""
    if _switching or not _waiting or (_running and _running >= slots(_current_engine)):
        return None
    for i, job in enumerate(_waiting):
        if job.engine == _current_engine:
            passed = _waiting[:i]
            if any(j.tamil_grading and j.exam_id != job.exam_id for j in passed):
                break  # another paper's grading comes first: switch to it once the running jobs finish
            if any(j.skips >= MAX_SKIPS and not j.tamil_grading for j in passed):
                break  # let the running jobs finish so the queue can switch to the job waiting longest
            for j in passed:
                j.skips += 1
            return job
    return _waiting[0] if not _running else None  # the GPU is free: switch to the oldest job's engine


def _work() -> None:
    global _running, _switching
    while True:
        with _cond:
            while (job := _pick()) is None:
                _cond.wait()
            _waiting.remove(job)
            # _pick only hands out another engine's job when nothing is running
            switch = _switching = job.engine != _current_engine
            _running += 1
            _cond.notify_all()  # another free worker may start alongside
        try:
            if switch:
                # Unloading takes seconds over the network: do it outside the lock so uploads queue meanwhile
                try:
                    switch_engine(job.engine)
                except Exception:  # the job still runs and records the engine error on its document
                    log.exception("Switching the GPU engine to %s failed", job.engine)
                finally:
                    with _cond:
                        _switching = False
                        _cond.notify_all()
            _call(job)
        finally:
            with _cond:
                _running -= 1
                _cond.notify_all()


def _ensure_workers() -> None:
    want = max(slots("internvl"), slots("indic"))
    _workers[:] = [w for w in _workers if w.is_alive()]
    while len(_workers) < want:
        w = threading.Thread(target=_work, name=f"gpu-job-queue-{len(_workers) + 1}", daemon=True)
        w.start()
        _workers.append(w)


def submit(exam_id: str | None, fn: Callable, *args: Any, grading: bool = False) -> None:
    """Queue `fn(*args)` for the GPU. `exam_id` decides which engine the job runs on (`grading`: the grading model's)."""
    engine = engine_for(exam_id, grading)
    tamil_grading = grading and engine != engine_for(exam_id)  # read by IndicOCR, graded by InternVL
    job = _Job(engine, fn, args, format_for(exam_id), subject_for(exam_id), tamil_grading, exam_id)
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
            switch_engine(job.engine)
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
