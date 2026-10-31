"""A Tamil point question graded point by point against its confirmed rubric (rubric.py). Tamil subjects only.

The key is the authority and the backend adds up the marks; the model never gives a total. Each marking point is
decided on its own:
  exact    fill-ins, word pairs, corrections, names: the expected words must be in the answer as written. Spaces and
           punctuation are ignored, nothing else: one changed ending is wrong.
  meaning  every content word of the key's answer is in the student's answer (case endings and a small spelling slip
           allowed) and the answer adds no negation the key does not have; otherwise the grading model is asked one
           narrow question, "same meaning?", and must quote the student's words, which the backend checks are there.
A point the student wrote under its own part label (அ) ஆ) ...) is looked for in that part only.

Letters, essays and paragraphs are not graded here (None): they keep the whole-answer grading.
"""
from __future__ import annotations
import re
from typing import Any, Callable

from pydantic import BaseModel, field_validator

from . import format as tamil_format
from .rubric import OPEN_KINDS
from .....ocr.schemas import EvaluationResult

# ask(system, prompt, schema) -> the parsed reply; None when no model may be asked (the replay harness)
Ask = Callable[[str, str, type], Any]

_PUNCT = re.compile(r"[^\w஀-௿]+")
_NEGATION = re.compile(r"இல்லை|அல்ல|வில்லை|மாட்ட|கூடாது|ாது(?![஀-௿])")
_PART_HEAD = re.compile(rf"(?m)^[ \t]*\(?[ \t]*([{tamil_format.SUB_LETTERS}a-h])[ \t]*\)")
_SCHEME_WORDS = tamil_format.indic_tokens("மதிப்பெண் மதிப்பெண்கள் சரியான விடை விடைகள் குறிப்பிடுதல் எழுதுதல் கூறுதல் "
                                          "விளக்குதல் ஒவ்வொரு")
_FULL_MATCH_WORDS = 5  # a key answer longer than this may miss one word and still match by key words

SYSTEM = (
    "You check ONE marking point of a Tamil answer sheet. Decide only whether the student's answer says the same "
    "thing as the answer key's point. Different wording, case endings, sandhi and small spelling slips are fine. A "
    "changed meaning, a wrong name or entity, or a negation the key does not have is NOT the same. If it is the same, "
    "copy the student's words that say it into quote, exactly as they are written. Reply with a single JSON object "
    "and nothing else."
)


class PointVerdict(BaseModel):
    same_meaning: bool = False
    quote: str = ""

    @field_validator("quote", mode="before")
    @classmethod
    def _text(cls, v):
        return "" if v is None else str(v)


def prompt(point: str, key_answer: str, student: str) -> str:
    return f"""MARKING POINT
{point}

ANSWER KEY FOR THIS POINT
{key_answer}

STUDENT ANSWER (OCR of handwriting)
{student}

Does the student's answer say the same thing as the answer key for this point?
Return JSON in exactly this shape: {{"same_meaning": true, "quote": "the student's own words"}}"""


def _plain(text: str) -> str:
    return " ".join(_PUNCT.sub(" ", text or "").split())


def _content(text: str) -> set[str]:
    return tamil_format.indic_tokens(re.sub(r"\d+(?:\.\d+)?|½", " ", text or "")) - _SCHEME_WORDS


def _one_slip(a: str, b: str) -> bool:
    """a and b differ by at most one inserted, dropped or changed character."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = next((k for k in range(len(a)) if a[k] != b[k]), len(a))
    return a[i + (len(a) == len(b)):] == b[i + 1:]


def _has_word(word: str, answer_words: set[str]) -> bool:
    if word in answer_words:
        return True
    return len(word) >= 5 and any(_one_slip(word, w) for w in answer_words)


def part_text(answer: str, part: str | None) -> str:
    """The student's text under part அ) (or a)), or the whole answer when the parts are not labelled."""
    if not part:
        return answer
    heads = list(_PART_HEAD.finditer(answer))
    want = {part, tamil_format.latin_subparts(part)}
    for i, m in enumerate(heads):
        if m.group(1) in want:
            return answer[m.end():heads[i + 1].start() if i + 1 < len(heads) else len(answer)]
    return answer


def key_answer(point: dict) -> str:
    """What the key says for a meaning point: "criterion: answer" points keep only their answer."""
    text = point.get("text") or ""
    head, sep, rest = text.partition(": ")
    return rest if sep and _content(rest) else text


def exact_match(expected: list[str], student: str) -> bool:
    words = f" {_plain(student)} "
    return any(f" {_plain(e)} " in words for e in expected if _plain(e))


def words_match(key: str, student: str) -> bool:
    """Every content word of the key in the answer (one may be missing from a long key), and no added negation."""
    want = _content(key)
    if not want or (_NEGATION.search(student) and not _NEGATION.search(key)):
        return False
    have = _content(student)
    found = sum(_has_word(w, have) for w in want)
    return found == len(want) or (len(want) > _FULL_MATCH_WORDS and found >= len(want) - 1)


def quote_found(quote: str, student: str) -> bool:
    """The model's quote is the student's text: two thirds of its content words are in the answer."""
    words = _content(quote)
    if not words:
        return False
    have = _content(student)
    return sum(_has_word(w, have) for w in words) * 3 >= len(words) * 2


def _label(p: dict) -> str:
    part = f"({p['part']}) " if p.get("part") else ""
    return f"{part}{p.get('text', '')}"


def grade(rubric: dict | None, answer_text: str, max_marks: float, ask: Ask | None) -> EvaluationResult | None:
    """The question's result, its marks the sum of the points earned; None when it is not a point question with a
    complete rubric (every point marked, adding up to the question's marks)."""
    points = (rubric or {}).get("points") or []
    if not points or (rubric or {}).get("kind") in OPEN_KINDS:
        return None
    if any(not isinstance(p.get("marks"), (int, float)) for p in points):
        return None
    if abs(sum(p["marks"] for p in points) - max_marks) > 1e-9:
        return None
    marks, matched, missing = 0.0, [], []
    by_words = by_model = unchecked = 0
    for p in points:
        student = part_text(answer_text, p.get("part"))
        if p.get("kind") == "exact" and p.get("expected"):
            earned = exact_match(p["expected"], student)
            by_words += earned
            note = "" if earned else f" (expected: {' / '.join(p['expected'])})"
        elif words_match(key_answer(p), student):
            earned, note = True, ""
            by_words += 1
        elif ask is None:
            earned, note = False, " (not checked: no grading model)"
            unchecked += 1
        else:
            verdict = ask(SYSTEM, prompt(_label(p), key_answer(p), student), PointVerdict)
            earned = bool(verdict.same_meaning) and quote_found(verdict.quote, student)
            by_model += earned
            note = f" (same meaning: \"{verdict.quote.strip()}\")" if earned else (
                " (the quoted words are not in the answer)" if verdict.same_meaning else "")
        if earned:
            marks += p["marks"]
            matched.append(f"{_label(p)}{note}")
        else:
            missing.append(f"{_label(p)}{note}")
    decision = "CORRECT" if marks >= max_marks - 1e-9 else "INCORRECT" if marks <= 0 else "PARTIALLY_CORRECT"
    how = f"{by_words} by the key's words" + (f", {by_model} judged same meaning" if by_model else "")
    feedback = f"Graded point by point: {len(matched)} of {len(points)} points earned ({how})."
    if unchecked:
        feedback += f" {unchecked} point(s) need the grading model."
    return EvaluationResult(marks_awarded=marks, max_marks=max_marks, decision=decision, matched_points=matched,
                            missing_points=missing, feedback=feedback, confidence=None if by_model else 1.0)
