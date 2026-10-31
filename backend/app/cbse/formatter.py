"""Which formatter reads and grades an exam: how its question paper, answer key and answer sheets are read, and its
answers mapped and graded.

    class10/subjects/<subject>/   a subject of a standard: its formatter (__init__.py) and paper design (format.json)
    class12/subjects/<subject>/
    common/                       what every class and subject shares (paper, keys, answers, mapping, rubric ...)
    common/subjects/<subject>/    a subject's rules every class shares (tamil/, english/, maths/, physics/, chemistry/)

An exam takes its class's own subject folder when there is one (class "10-A" + subject "Science" ->
class10/subjects/science/, matched by common/standards.py); otherwise its subject's shared rules (subject "Tamil" ->
common/subjects/tamil/); otherwise common/ alone. A class subject starts from the shared rules and overrides only what
its papers do differently, so changing one class's subject touches only its own folder.

Every formatter offers the same hooks (see common/__init__.py). A hook that returns None means "nothing of my own
here, use the shared parser", so a subject can take over one stage (say answer sheets) and leave the rest shared.

The formatter is chosen per request (deps.get_exam) and per queued job (job_queue); with no exam in hand (scripts,
unit tests) a Tamil paper format (services/paper_format.py) still selects common/subjects/tamil/.
"""
from __future__ import annotations
from contextlib import contextmanager
from contextvars import ContextVar
from importlib import import_module
from types import ModuleType
from typing import Iterator

COMMON = "common"
# subject folder -> words that name the subject (matched in the exam's subject name, any case)
SUBJECTS: dict[str, tuple[str, ...]] = {
    "tamil": ("tamil", "தமிழ்"),
    "english": ("english",),
    "maths": ("math", "கணிதம்"),
    "physics": ("physics", "இயற்பியல்"),
    "chemistry": ("chemistry", "வேதியியல்"),
}

_subject: ContextVar[str | None] = ContextVar("formatter_subject", default=None)


def for_subject(subject_name: str | None) -> str | None:
    """The formatter for a subject name ('Tamil II' -> 'tamil', 'Maths' -> 'maths', 'Biology' -> 'common');
    None when there is no subject."""
    if not subject_name:
        return None
    name = subject_name.casefold()
    return next((key for key, words in SUBJECTS.items() if any(w in name for w in words)), COMMON)


def for_exam(exam) -> str | None:
    """The class's own subject folder ('class10.subjects.science'), else for_subject."""
    if exam is None:
        return None
    from .common import standards
    if design := standards.for_exam(exam):
        return design["formatter"]
    return for_subject(exam.subject.name if exam.subject else None)


def set_for_exam(exam) -> None:
    """For the rest of this request (each request runs in its own context)."""
    _subject.set(for_exam(exam))


@contextmanager
def use(subject: str | None) -> Iterator[None]:
    token = _subject.set(subject)
    try:
        yield
    finally:
        _subject.reset(token)


def active() -> str | None:
    return _subject.get()


def get(subject: str | None) -> ModuleType:
    """'tamil' -> common/subjects/tamil/, 'class10.subjects.science' -> class10/subjects/science/, else common/."""
    package = __name__.rpartition(".")[0]
    if subject in SUBJECTS:
        return import_module(f"{package}.{COMMON}.subjects.{subject}")
    if subject and subject.startswith("class"):
        return import_module(f"{package}.{subject}")
    return import_module(f"{package}.{COMMON}")


def current() -> ModuleType:
    """The formatter of the exam being worked on."""
    subject = _subject.get()
    if subject is None:
        from ..services import paper_format  # no exam in context: the paper format alone still says Tamil
        if paper_format.active() == paper_format.TAMIL:
            subject = "tamil"
    return get(subject)
