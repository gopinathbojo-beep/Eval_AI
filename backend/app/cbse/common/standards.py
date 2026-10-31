"""CBSE question paper design per standard and subject: format.json in the subject's own folder
(class10/subjects/science/format.json, class12/subjects/tamil/format.json).
Taken from the board's sample paper and marking scheme of the session ("session").

    {"subject": "Science", "code": "086", "names": ["science"], "total_marks": 80, "duration_minutes": 180,
     "sections": [{"name": "A", "title": "Biology", "marks": 30, "questions": [
         {"q": "1-7", "marks": 1, "kind": "mcq"},                         a range: each question the same
         {"q": 11, "marks": 2, "kind": "short", "choice": ["A", "B"]},    either/or: each alternative worth the marks
         {"q": 15, "marks": 4, "kind": "case", "parts": [1, 1, 2], "part_labels": "A", "part_choice": "C/D"},
         {"q": 8, "marks": 12, "parts": [3, 3, 3, 3, 3], "any": 4},       answer any 4 of the parts
         {"q": 11, "marks": 7, "kind": "essay", "one_of": 3}]}]}           write on one of 3 topics: one question

A question's "marks" is what it adds to the paper's total (one alternative; the best "any" parts). The design is
matched to an exam by the class's standard ("10-A" -> class10/) and the subject: its code first, else the longest of
its "names" found in the subject's name ("Social Science" is not "Science", "English Communicative" is not "English").
The matched folder is also the exam's formatter ("formatter": "class10.subjects.science", see cbse/formatter.py).

check() holds a parsed paper against its design: marks the parser could not find are taken from the design; marks that
disagree, questions the design does not have, an "any N" over a question's own parts and the paper total are put to
the teacher (NEEDS_REVIEW with the reason). The design never renumbers or drops a question.
"""
from __future__ import annotations
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import choices
from .numbering import parent_number

ROOT = Path(__file__).parent.parent  # app/cbse
_ROMAN_STD = {"ix": "9", "x": "10", "xi": "11", "xii": "12"}
MARKS_NOT_FOUND = "Marks not found"


def standard_of(class_name: str | None) -> str | None:
    """'10-A' -> '10', 'Class X' -> '10', 'XII-B' -> '12'; None when the name carries no standard."""
    std = (class_name or "").rpartition("-")[0] or (class_name or "")
    std = re.sub(r"(?i)\b(?:class|std|standard|grade)\b\.?", " ", std).strip().casefold()
    if m := re.fullmatch(r"\d{1,2}", std):
        return str(int(m.group(0)))
    return _ROMAN_STD.get(std)


@lru_cache(maxsize=None)
def _designs(standard: str) -> tuple[dict, ...]:
    files = sorted((ROOT / f"class{standard}" / "subjects").glob("*/format.json"))
    return tuple({**json.loads(p.read_text(encoding="utf-8")), "formatter": f"class{standard}.subjects.{p.parent.name}"}
                 for p in files)


def load(standard: str | None, subject_name: str | None, subject_code: str | None = None) -> dict | None:
    """The design of a class ('10') and subject; None when no file has been added for it."""
    if not standard:
        return None
    designs = _designs(standard)
    code = (subject_code or "").strip().lstrip("0")
    if code and (hit := next((d for d in designs if d["code"].lstrip("0") == code), None)):
        return hit
    name = (subject_name or "").casefold()
    found = [(len(alias), d) for d in designs for alias in d["names"] if alias in name]
    return max(found, key=lambda x: x[0])[1] if found else None


def for_exam(exam: Any) -> dict | None:
    cls, subject = getattr(exam, "school_class", None), getattr(exam, "subject", None)
    return load(standard_of(getattr(cls, "name", None)), getattr(subject, "name", None), getattr(subject, "code", None))


def questions(design: dict) -> dict[int, dict]:
    """Question number -> its design (with its section), ranges ("1-18") expanded."""
    out: dict[int, dict] = {}
    for section in design["sections"]:
        for spec in section["questions"]:
            first, _, last = str(spec["q"]).partition("-")
            for n in range(int(first), int(last or first) + 1):
                out[n] = {**spec, "q": n, "section": section["name"]}
    return out


def _flag(q: Any, reason: str) -> None:
    q.verification_status = "NEEDS_REVIEW"
    q.review_reason = "; ".join(filter(None, [q.review_reason, reason]))


def _fill(q: Any, marks: float) -> None:
    """Marks from the design for a question the parser found none for; not a review reason any more."""
    q.max_marks = marks
    reasons = [r for r in (q.review_reason or "").split("; ") if r and r != MARKS_NOT_FOUND]
    q.review_reason = "; ".join(reasons) or None
    if not reasons:
        q.verification_status = "UNVERIFIED"


def _set_marks(members: list[Any], marks: float, label: str) -> None:
    for q in members:
        if q.max_marks is None:
            _fill(q, marks)
        elif abs(q.max_marks - marks) > 1e-9:
            _flag(q, f"The CBSE design gives {label} {marks:g} marks, the paper {q.max_marks:g}")


def _check_question(n: int, spec: dict, qs: list[Any]) -> None:
    units = choices.units(qs)  # one per either/or choice
    members = {id(u): [q for q in qs if q is u or (u.choice_group and q.choice_group == u.choice_group)] for u in units}
    parts = spec.get("parts")
    if len(units) == 1:
        _set_marks(members[id(units[0])], spec["marks"], f"Q{n}")
    elif parts and len(units) == len(parts):
        for u, marks in zip(units, parts):
            _set_marks(members[id(u)], marks, f"Q{u.display_number}")
        if (any_n := spec.get("any")) and not any(q.answer_any for q in qs):
            for q in qs:  # "answer any N" over this question's parts: they count as a section of their own
                q.answer_any, q.section = any_n, f"{q.section} / Q{n}" if q.section else f"Q{n}"
    if "choice" in spec or "part_choice" in spec or any(q.max_marks is None for q in qs):
        return  # alternatives nested in parts are not reliably grouped; a total over them could double-count
    total = choices.max_total(qs)
    if abs(total - spec["marks"]) > 1e-9:
        for q in qs:
            _flag(q, f"Q{n} adds up to {total:g} marks, the CBSE design gives {spec['marks']:g}")


def check(doc: Any, design: dict) -> list[str]:
    """Hold a parsed paper (DocumentStructure) against its design, see the module docstring; the problems for the log."""
    plan = questions(design)
    groups: dict[str, list[Any]] = {}
    for q in doc.questions:
        groups.setdefault(parent_number(q.normalized_number or ""), []).append(q)
    problems: list[str] = []
    for n, spec in plan.items():
        if qs := groups.get(str(n)):
            _check_question(n, spec, qs)
        else:
            problems.append(f"Q{n} ({spec['marks']:g} marks) is in the CBSE design but was not found on the paper")
    for top, qs in groups.items():
        if top.isdigit() and int(top) not in plan:
            for q in qs:
                _flag(q, f"The CBSE {design['subject']} paper has no question {top}")
    if not doc.exam_max_marks:
        doc.exam_max_marks = design["total_marks"]
    elif abs(doc.exam_max_marks - design["total_marks"]) > 1e-9:
        problems.append(f"The paper states {doc.exam_max_marks:g} marks, the CBSE design {design['total_marks']}")
    if not doc.exam_duration_minutes:
        doc.exam_duration_minutes = design["duration_minutes"]
    return problems
