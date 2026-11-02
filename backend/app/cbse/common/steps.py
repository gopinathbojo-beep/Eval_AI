"""A maths or science answer graded step by step against its confirmed marking scheme (rubric.py points with marks).

The scheme is the authority and the backend adds up the marks; the model never gives a total. The whole-answer
grader was given the steps as a flat list: it did not know "(iii)(A) OR (iii)(B)" are alternatives, gave Q36 3/4 with
(iii) not attempted, and 1.5/2 to a Q21(a) with every step written. Here each step is decided on its own:
  - a step with results (4680, 4663; 80/3; a ratio 3:2 as 3/2) by them alone: all written, earned; any missing, not.
    The model is not asked: it "found" an unattempted (iii)(B) from the 360 and 22/7 of (i) and (ii);
  - a step without results ("Let the speed be x km/h") by the grading model, one narrow question: "is this step (or
    an equivalent one) in the answer?"; it must quote the student's working, nearly character for character.
An OR choice inside a question (points with alt_group / alt) counts once: each alternative is added up and the
better one counts, so the alternative the student did not choose costs nothing.

Questions whose scheme does not add up to the question's marks are not graded here (None): they keep the whole-answer
grading. rubric["question_text"], when the caller adds it, keeps the question's own numbers from proving a step.
"""
from __future__ import annotations
import difflib
import re
from fractions import Fraction
from typing import Any, Callable

from pydantic import BaseModel, field_validator

from ...ocr.schemas import EvaluationResult

Ask = Callable[[str, str, type], Any]

_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_FRACTION = re.compile(r"(\d+)\s*/\s*(\d+)")
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
_GENERIC = {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "100", "180", "90", "360"}

SYSTEM = (
    "You check ONE step of a maths or science marking scheme against a student's handwritten answer (read by OCR, so "
    "small reading slips are possible). Decide only whether the student's answer contains this step or an equivalent "
    "one: the same mathematical content in any notation, variable names or order, or the same step of a correct "
    "alternative method. A step that is missing, wrong, or only restates the question is NOT present. If it is "
    "present, copy the student's working that shows it into quote, exactly as written. Reply with a single JSON object "
    "and nothing else."
)


class StepVerdict(BaseModel):
    present: bool = False
    quote: str = ""

    @field_validator("quote", mode="before")
    @classmethod
    def _text(cls, v):
        return "" if v is None else str(v)


def prompt(step: str, student: str) -> str:
    return f"""MARKING SCHEME STEP
{step}

STUDENT ANSWER (OCR of handwriting)
{student}

Does the student's answer contain this step, or an equivalent one?
Return JSON in exactly this shape: {{"present": true, "quote": "the student's own working"}}"""


def _norm(text: str) -> str:
    return (text or "").replace("−", "-").replace("–", "-").replace("×", "x")


_NUMBER_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
                 "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
                 "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18",
                 "nineteen": "19", "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50", "sixty": "60",
                 "seventy": "70", "eighty": "80", "ninety": "90", "hundred": "100"}


def given(question_text: str | None) -> set[str]:
    """The numbers the question gives ("Twelve minutes", "520 and 468"): copying them proves no step."""
    t = _norm(question_text or "")
    words = {_NUMBER_WORDS[w] for w in re.findall(r"[a-z]+", t.lower()) if w in _NUMBER_WORDS}
    return set(_NUMBER.findall(t)) | words | {f"{a}/{b}" for a, b in _FRACTION.findall(t)}


def values(step: str, question_text: str | None = None) -> set[str]:
    """The step's distinctive numbers: results like 4680, 4663, 80/3; not 2 or 90 that any working has, nor the
    numbers the question gives."""
    t = _norm(step)
    fracs = {f"{a}/{b}" for a, b in _FRACTION.findall(t) if f"{a}/{b}" not in ("1/2",)}
    nums = {n for n in _NUMBER.findall(_FRACTION.sub(" ", t)) if n not in _GENERIC}
    return (fracs | nums) - given(question_text)


_RATIO = re.compile(r"(\d+)\s*:\s*(\d+)")


def _value(v: str) -> Fraction | None:
    try:
        a, _, b = v.partition("/")
        return Fraction(a) / Fraction(b) if b else Fraction(a)
    except (ValueError, ZeroDivisionError):
        return None


def has_values(want: set[str], student: str) -> bool:
    """Every value written, compared by value: 4/2 is the student's 2, a ratio 3:2 is 3/2."""
    t = _norm(student)
    pairs = _FRACTION.findall(t) + _RATIO.findall(t)
    have = {_value(f"{a}/{b}") for a, b in pairs} | {_value(n) for n in _NUMBER.findall(t)}
    return all(_value(v) in have for v in want)


def _squash(text: str) -> str:
    return re.sub(r"[\s.,;:]+", "", _norm(text).casefold())


def quote_found(quote: str, student: str) -> bool:
    """The model's quote is the student's working: (nearly) the same characters stand in the answer. Shared words are
    not enough: every step of a sector question shares 360 and 22/7 with the others."""
    q, s = _squash(quote), _squash(student)
    if len(q) < 4:
        return False
    if q in s:
        return True
    m = difflib.SequenceMatcher(None, q, s, autojunk=False).find_longest_match(0, len(q), 0, len(s))
    if m.size >= 0.7 * len(q):
        return True
    # a reading slip inside the quote ("fan 60°" for tan 60°): three quarters of its words and numbers are there
    words = [w.casefold() for w in _TOKEN.findall(_norm(quote))]
    have = {w.casefold() for w in _TOKEN.findall(_norm(student))}
    return len(words) >= 3 and sum(w in have for w in words) * 4 >= len(words) * 3


def _total(points: list[dict]) -> float:
    plain = sum(p["marks"] for p in points if not p.get("alt_group"))
    groups: dict[Any, dict[Any, float]] = {}
    for p in points:
        if p.get("alt_group"):
            g = groups.setdefault(p["alt_group"], {})
            g[p.get("alt")] = g.get(p.get("alt"), 0.0) + p["marks"]
    return plain + sum(max(g.values()) for g in groups.values())


def grade(rubric: dict | None, answer_text: str, max_marks: float, ask: Ask | None) -> EvaluationResult | None:
    points = (rubric or {}).get("points") or []
    if not points or any(not isinstance(p.get("marks"), (int, float)) for p in points):
        return None
    if abs(_total(points) - max_marks) > 1e-9:
        return None
    earned: list[bool] = []
    notes: list[str] = []
    by_values = by_model = asked = 0
    for p in points:
        step = p.get("text") or ""
        want = values(step, (rubric or {}).get("question_text"))
        if want:
            # a step with results is decided by them alone: the model "found" (iii)(B)'s 72° in a sheet without it
            ok = has_values(want, answer_text)
            note = f" (values {', '.join(sorted(want))} {'written' if ok else 'not written'})"
            by_values += ok
        elif ask is None:
            ok, note = False, " (not checked: no grading model)"
        else:
            v = ask(SYSTEM, prompt(step, answer_text), StepVerdict)
            asked += 1
            ok = bool(v.present) and quote_found(v.quote, answer_text)
            by_model += ok
            note = f" (\"{v.quote.strip()[:80]}\")" if ok else (" (quoted working not in the answer)" if v.present else "")
        earned.append(ok)
        notes.append(note)

    # plain steps add up; each OR choice counts its better alternative once
    marks = sum(p["marks"] for p, ok in zip(points, earned) if ok and not p.get("alt_group"))
    chosen: dict[Any, Any] = {}
    for g in {p["alt_group"] for p in points if p.get("alt_group")}:
        sums: dict[Any, float] = {}
        for p, ok in zip(points, earned):
            if p.get("alt_group") == g:
                sums[p.get("alt")] = sums.get(p.get("alt"), 0.0) + (p["marks"] if ok else 0.0)
        best = max(sums, key=lambda a: sums[a])
        chosen[g] = best
        marks += sums[best]

    matched, missing = [], []
    for p, ok, note in zip(points, earned, notes):
        alt = f"({p.get('alt')}) " if p.get("alt_group") else ""
        label = f"[{p['marks']:g}] {alt}{(p.get('text') or '').strip()}"
        if p.get("alt_group") and chosen.get(p["alt_group"]) != p.get("alt"):
            continue  # the alternative not chosen is neither matched nor missing
        (matched if ok else missing).append(label + note)
    marks = min(marks, max_marks)
    decision = "CORRECT" if marks >= max_marks - 1e-9 else "INCORRECT" if marks <= 0 else "PARTIALLY_CORRECT"
    alts = f" OR choice: the better alternative counted ({', '.join(str(a) for a in chosen.values())})." if chosen else ""
    feedback = (f"Graded step by step against the marking scheme: {len(matched)} step(s) earned "
                f"({by_values} by their values, {by_model} judged present by the model), {marks:g}/{max_marks:g}.{alts}")
    if asked:
        feedback += (f" Check the {asked} step(s) the model judged against the sheet (another method or other "
                     "letters may be right).")
    # a step the model judged, earned or not, is its opinion: low confidence sends the question to the teacher's review
    return EvaluationResult(marks_awarded=marks, max_marks=max_marks, decision=decision, matched_points=matched,
                            missing_points=missing, feedback=feedback, confidence=1.0 if not asked else 0.5)
