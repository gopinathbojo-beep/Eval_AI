"""Which paper format's rules apply, chosen by the exam's subject.

English and Tamil papers are laid out differently; tamil_format.py holds the Tamil rules, the shared parsers the
English ones. The Tamil rules apply only under a Tamil subject, so a Tamil word in an English, Maths or Science paper
is plain text. A Tamil subject keeps the English rules as well: its papers carry English parts too ("choose the
correct answer", "1x5=5").

The format is set per request (deps.get_exam) and per queued job (job_queue.submit). With no exam in hand
(scripts, unit tests) it is None and the text's script decides, as before.
"""
from __future__ import annotations
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

ENGLISH, TAMIL = "english", "tamil"
_TAMIL_SUBJECTS = ("tamil", "தமிழ்")

_active: ContextVar[str | None] = ContextVar("paper_format", default=None)


def for_subject(subject_name: str | None) -> str | None:
    """TAMIL for 'Tamil', 'Tamil II', 'தமிழ்'; ENGLISH for every other subject; None when there is no subject."""
    if not subject_name:
        return None
    name = subject_name.casefold()
    return TAMIL if any(k in name for k in _TAMIL_SUBJECTS) else ENGLISH


def for_exam(exam) -> str | None:
    return for_subject(exam.subject.name if exam is not None and exam.subject else None)


def active() -> str | None:
    return _active.get()


def set_for_exam(exam) -> None:
    """For the rest of this request (each request runs in its own context)."""
    _active.set(for_exam(exam))


@contextmanager
def use(fmt: str | None) -> Iterator[None]:
    token = _active.set(fmt)
    try:
        yield
    finally:
        _active.reset(token)


def tamil_rules_apply() -> bool:
    return _active.get() != ENGLISH
