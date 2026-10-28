"""GPU job queue: jobs grouped by engine, several at a time on the loaded engine, switching engines between groups.

Every job that uses a model (reading papers/keys/sheets, identifying students, grading) is queued here instead of
running as its own background task. The engine its exam needs is the only one on the GPU:
  internvl : InternVL in Ollama
  indic    : IndicOCR service + INDIC_TEXT_MODEL in Ollama (InternVL if no text model is set)
Up to INTERNVL_PARALLEL_JOBS / INDIC_PARALLEL_JOBS jobs run at once on the loaded engine. A waiting job for the loaded
engine may start ahead of older jobs for the other engine, so an English, Tamil, English, Tamil upload runs both English
jobs, switches once, then both Tamil jobs. A job is passed over at most MAX_SKIPS times; then the running jobs finish,
the engine switches and it runs. Switching unloads the models the next engine does not use, and only happens with no
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
from . import paper_format

log = logging.getLogger("adem.queue")

MAX_SKIPS = 4  # times a job may be passed over for jobs of the loaded engine before the queue switches to it


@dataclass(eq=False)
class _Job:
    engine: str
    fn: Callable
    args: tuple
    paper_format: str | None = None  # the exam subject's format, see services/paper_format.py
    skips: int = 0


_cond = threading.Condition()  # guards _waiting, _running, _switching and _current_engine
_waiting: list[_Job] = []  # queue order
_running = 0
_switching = False  # a worker is changing engines outside the lock: no other job starts until it is done
_workers: list[threading.Thread] = []
_inline_lock = threading.RLock()  # inline jobs may queue more jobs (identify -> read), which run in the same thread
_current_engine: str | None = None  # None: unknown (e.g. after start), so a first switch frees everything else

_key_locks: dict[str, threading.RLock] = {}
_key_guard = threading.Lock()


def keyed_lock(key: str) -> threading.RLock:
    """One lock per key (e.g. "exam:<id>"), for work that jobs running in parallel must not do at the same time."""
    with _key_guard:
        return _key_locks.setdefault(key, threading.RLock())


def engine_for(exam_id: str | None) -> str:
    db = SessionLocal()
    try:
        exam = db.get(Exam, exam_id) if exam_id else None
        return "indic" if exam and exam.subject and uses_indic_ocr(exam.subject.name) else "internvl"
    finally:
        db.close()


def format_for(exam_id: str | None) -> str | None:
    db = SessionLocal()
    try:
        return paper_format.for_exam(db.get(Exam, exam_id) if exam_id else None)
    finally:
        db.close()


def slots(engine: str) -> int:
    s = get_settings()
    return max(1, s.indic_parallel_jobs if engine == "indic" else s.internvl_parallel_jobs)


def _ollama_models(engine: str) -> set[str]:
    s = get_settings()
    return {s.indic_text_model.strip() or s.internvl_model} if engine == "indic" else {s.internvl_model}


def switch_engine(engine: str) -> None:
    """Make `engine` the only one holding GPU memory. No-op when it already is. Call only with no job running."""
    global _current_engine
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
    try:
        with paper_format.use(job.paper_format):
            job.fn(*job.args)
    except Exception:  # a failed job must never stop the queue; the job itself records errors on its document
        log.exception("Queued job %s%r crashed", getattr(job.fn, "__name__", job.fn), job.args)


def _pick() -> _Job | None:
    """The job a free worker should start now, or None. Caller holds _cond."""
    if _switching or not _waiting or (_running and _running >= slots(_current_engine)):
        return None
    for i, job in enumerate(_waiting):
        if job.engine == _current_engine:
            passed = _waiting[:i]
            if any(j.skips >= MAX_SKIPS for j in passed):
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


def submit(exam_id: str | None, fn: Callable, *args: Any) -> None:
    """Queue `fn(*args)` for the GPU. `exam_id` decides which engine the job runs on."""
    job = _Job(engine_for(exam_id), fn, args, format_for(exam_id))
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
