"""The paper's skeleton: numbered question slots grouped into sections, each slot with its marks and type.

A board-pattern paper follows the subject's CBSE 2026-27 profile (sections, per-question marks, internal choices).
A custom paper is built from a mark mix such as {1: 10, 2: 5, 3: 4, 5: 2}, one section per mark value."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..cbse.catalog import get_profile

_TYPES = {
    1: "Objective (MCQ or assertion-reason) with four options (a)-(d)",
    2: "Very short answer (about 30-50 words)",
    3: "Short answer (about 50-80 words)",
    4: "Case-based / source-based question: a short passage or data followed by 3 sub-parts whose marks add up to 4",
    5: "Long answer (about 120 words), may have sub-parts",
    6: "Long answer / numerical problem, may have sub-parts",
}
DEFAULT_MIX = {1: 20, 2: 5, 3: 6, 5: 4, 4: 3}  # the usual 80-mark CBSE shape when a subject has no profile
LANGUAGE = ("english", "hindi", "tamil")


@dataclass
class Slot:
    number: int
    section: str
    marks: float
    kind: str
    with_choice: bool = False  # an internal OR alternative is written for this question


@dataclass
class Blueprint:
    title: str
    total_marks: float
    duration_minutes: int
    sections: list[dict] = field(default_factory=list)  # {key, slots: [Slot]}
    instructions: list[str] = field(default_factory=list)

    def slots(self) -> list[Slot]:
        return [s for sec in self.sections for s in sec["slots"]]

    def as_dict(self) -> dict:
        return {"title": self.title, "total_marks": self.total_marks, "duration_minutes": self.duration_minutes,
                "instructions": self.instructions,
                "sections": [{"key": s["key"], "slots": [asdict(x) for x in s["slots"]]} for s in self.sections]}


def _kind(marks: float, language: bool) -> str:
    if language:
        if marks >= 8:
            return "Reading comprehension: an unseen passage followed by sub-questions whose marks add up"
        if marks >= 5:
            return "Writing / long literature question (letter, analytical paragraph, or extract-based)"
        return "Literature / grammar short answer"
    return _TYPES.get(int(marks), _TYPES[5] if marks > 5 else _TYPES[3])


def _duration(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    parts = ([f"{h} hour{'s' if h != 1 else ''}"] if h else []) + ([f"{m} minutes"] if m else [])
    return " ".join(parts)


def _instructions(sections: list[dict], total: float, minutes: int) -> list[str]:
    lines = [f"This question paper has {len(sections)} sections and {sum(len(s['slots']) for s in sections)} questions. "
             "All questions are compulsory.",
             f"Maximum marks: {total:g}. Time allowed: {_duration(minutes)}."]
    for s in sections:
        sl = s["slots"]
        marks = sorted({x.marks for x in sl})
        each = f"carry {marks[0]:g} mark{'s' if marks[0] != 1 else ''} each" if len(marks) == 1 else "carry the marks shown"
        lines.append(f"Section {s['key']} has {len(sl)} question(s) (Q{sl[0].number}-Q{sl[-1].number}); they {each}.")
    if any(x.with_choice for s in sections for x in s["slots"]):
        lines.append("Internal choice is provided in some questions; attempt only one of the alternatives.")
    return lines


def board(profile_id: str, subject_name: str, standard: int, choices: bool = True) -> Blueprint | None:
    p = get_profile(profile_id)
    if p is None or p.get("upload_driven") or not p["sections"]:
        return None
    language = any(w in p["name"].lower() for w in LANGUAGE)
    marks = p["parent_marks"]
    sections = []
    for sec in p["sections"]:
        nums = list(range(sec["start"], sec["end"] + 1))
        n_choice = sec.get("internal_choices") or 0
        slots = [Slot(n, sec["key"], float(marks[n - 1]) if n - 1 < len(marks) else float(sec["each"] or 1),
                      "", bool(n_choice) and i >= len(nums) - n_choice) for i, n in enumerate(nums)]
        for s in slots:
            s.kind = _kind(s.marks, language)
        sections.append({"key": sec["key"], "slots": slots})
    if choices and not language and not any(x.with_choice for sec in sections for x in sec["slots"]):
        # the profile records no choices: offer an OR in about a third of the 2-mark-and-above questions
        for sec in sections:
            big = [x for x in sec["slots"] if x.marks >= 2]
            for x in big[len(big) - len(big) // 3:]:
                x.with_choice = True
    if not choices:
        for x in (x for sec in sections for x in sec["slots"]):
            x.with_choice = False
    title = f"CBSE Class {standard} {p['name']} ({subject_name}) - Sample Question Paper"
    return Blueprint(title, float(p["total_marks"]), int(p["duration_minutes"]), sections,
                     _instructions(sections, p["total_marks"], p["duration_minutes"]))


def custom(mix: dict, subject_name: str, standard: int, minutes: int, language: bool = False,
           choices: bool = True) -> Blueprint:
    """mix: {marks: count}. Sections are ordered by marks (1-mark questions first) like a CBSE paper."""
    sections, n = [], 0
    clean = sorted((float(m), int(c)) for m, c in mix.items() if int(c) > 0 and float(m) > 0)
    for i, (marks, count) in enumerate(clean):
        key = chr(ord("A") + i)
        slots = []
        for j in range(count):
            n += 1
            # like the board: about a third of the 2-mark-and-above questions offer an OR alternative
            slots.append(Slot(n, key, marks, _kind(marks, language), choices and marks >= 2 and j >= count - max(1, count // 3)))
        sections.append({"key": key, "slots": slots})
    total = sum(m * c for m, c in clean)
    return Blueprint(f"Class {standard} {subject_name} - Question Paper", total, minutes, sections,
                     _instructions(sections, total, minutes))
