"""Objective questions (MCQ, assertion-reason) marked against the key's option, without the grading model.

The key names the option ("Answer: (D) ... (D) 1650"). A student writes the letter ("8> D"), the letter and the option
("1> D. 1650"), or only the option's value ("13> 9m", "14> -2"). The grading model, given the key's working as marking
points, asked for that working and gave 0 or 0.5 to correct choices; an MCQ carries no marks for working, so it is
marked here:
  - the correct letter: full marks, whatever follows it ("C. p+4" is p≠4 misread; the letter is the choice);
  - no letter, a value that is the correct option's: full marks ("9m" = (B) 9 m);
  - a wrong letter, or a value that is another option's: 0;
  - a letter and a value naming different options ("A. 26" when (B) is 26), or a value matching no option ("a/c"):
    the teacher decides; proposed 0 at low confidence, with what was compared.
Anything else (no option in the key) goes to the grading model as before (None).
"""
from __future__ import annotations
import re
from typing import Any

from ...ocr.schemas import EvaluationResult

_KEY_OPTION = re.compile(r"^\s*(?:answer|ans)\s*[:.\-]?\s*\(?\s*([A-D])\s*\)", re.I)
_ANY_OPTION = re.compile(r"\(\s*([A-D])\s*\)")
_OPTIONS = re.compile(r"\(\s*([A-D])\s*\)\s*(.*?)(?=\(\s*[A-D]\s*\)|$)", re.S)
_LABEL = re.compile(r"^\s*(?:Q\s*)?\d{1,3}\s*(?:\(\s*[a-z]\s*\))?\s*[>).:\-]\s*", re.I)
_LETTER = re.compile(r"^\s*\(?\s*([A-Da-d])\s*(?:\)|\.|:|,|-|\s|$)")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_OPTION_END = re.compile(r"\s{3,}|\n|\b(?:assertion|directions?)\b", re.I)
_LOW = 0.3


def _norm(text: str) -> str:
    # "α" is how the reader writes a handwritten "a" ("α = C" for a = c)
    t = (text or "").lower().replace("−", "-").replace("–", "-").replace("×", "x").replace("α", "a")
    return re.sub(r"[\s.,;]+", "", t)


def key_option(key_text: str | None) -> str | None:
    """The option the key marks correct: "Answer: (D) ..." -> "D"."""
    if not key_text:
        return None
    if m := _KEY_OPTION.match(key_text):
        return m.group(1).upper()
    first = key_text.strip().splitlines()[0] if key_text.strip() else ""
    m = _ANY_OPTION.match(first.strip())
    return m.group(1).upper() if m else None


def options(question_text: str | None) -> dict[str, str]:
    """The printed options, first set only: "(A) 165 (B) 1600 ..." -> {"A": "165", "B": "1600", ...}."""
    out: dict[str, str] = {}
    for letter, text in _OPTIONS.findall(question_text or ""):
        if letter in out:
            break  # a second set (assertion-reason directions printed after the options)
        out[letter] = _OPTION_END.split(text.strip(), 1)[0].strip()
    return out if len(out) >= 3 else {}


def _matching(value: str, opts: dict[str, str]) -> set[str]:
    """The options the written value is: the same text, else the same numbers ("9m" is "9 m", "-2" is "−2")."""
    v = _norm(value)
    if not v:
        return set()
    same = {k for k, o in opts.items() if _norm(o) and _norm(o) == v}
    if same:
        return same
    nums = _NUMBER.findall(v)
    if not nums or re.search(r"[a-z]{2,}", re.sub(r"(cm|mm|km|m|kg|g|°|th|st|nd|rd|units?)", "", v)):
        return set()
    sign = v.startswith("-")
    return {k for k, o in opts.items()
            if _NUMBER.findall(_norm(o)) == nums and _norm(o).startswith("-") == sign}


def _split(answer_text: str) -> tuple[str | None, str]:
    """The letter and the value written: "17> D. 1650" -> ("D", "1650"), "13> 9 m" -> (None, "9 m")."""
    first = (answer_text or "").strip().splitlines()[0] if (answer_text or "").strip() else ""
    answer = _LABEL.sub("", first)
    m = _LETTER.match(answer)
    return (m.group(1).upper(), answer[m.end():].strip()) if m else (None, answer.strip())


def names_option(answer_text: str, question_text: str | None) -> bool | None:
    """Whether the value written is one of the question's printed options; None when it cannot tell (a letter alone,
    no options printed)."""
    opts = options(question_text)
    _, value = _split(answer_text)
    if not opts or not value:
        return None
    return bool(_matching(value, opts))


def option_of(answer_text: str, question_text: str | None) -> bool:
    """The value written is one of this question's printed options ("1650" of Q1's (D) 1650)."""
    opts = options(question_text)
    _, value = _split(answer_text)
    return bool(opts and value and _matching(value, opts))


def _result(marks: float, max_marks: float, decision: str, feedback: str, confidence: float,
            matched: list[str] | None = None, missing: list[str] | None = None) -> EvaluationResult:
    return EvaluationResult(marks_awarded=marks, max_marks=max_marks, decision=decision, feedback=feedback,
                            confidence=confidence, matched_points=matched or [], missing_points=missing or [])


def grade(question_type: str | None, question_text: str | None, key_text: str | None, answer_text: str,
          max_marks: float) -> EvaluationResult | None:
    """The objective question marked against the key's option, or None when it is not one (or the key names none)."""
    correct = key_option(key_text)
    if not correct or (question_type or "").lower() not in ("mcq", "assertion_reason", "objective"):
        return None
    opts = options(question_text)
    letter, value = _split(answer_text)
    named = _matching(value, opts) if value and opts else set()
    right = f"({correct}) {opts[correct]}".strip() if correct in opts else f"({correct})"

    if letter == correct and not (named and correct not in named):
        return _result(max_marks, max_marks, "CORRECT", f"Chose option {right}, the key's answer.", 1.0,
                       matched=[f"Correct option {right}"])
    if letter and letter != correct and not (named and correct in named):
        return _result(0, max_marks, "INCORRECT", f"Chose option ({letter}); the key's answer is {right}.", 1.0,
                       missing=[f"Correct option {right}"])
    if letter is None and named == {correct}:
        return _result(max_marks, max_marks, "CORRECT", f"Wrote {value!r}, which is option {right}, the key's answer.",
                       1.0, matched=[f"Correct option {right}"])
    if letter is None and named and correct not in named:
        chosen = ", ".join(f"({k}) {opts[k]}" for k in sorted(named))
        return _result(0, max_marks, "INCORRECT", f"Wrote {value!r}, which is option {chosen}; the key's answer is "
                       f"{right}.", 1.0, missing=[f"Correct option {right}"])
    # a letter and a value naming different options, or a value that is no option: the teacher reads the sheet
    if letter:
        seen = f"wrote option ({letter}) with the value {value!r}, which is option " + \
               ", ".join(f"({k})" for k in sorted(named))
    else:
        seen = f"wrote {value!r}, which matches no printed option" if value else "wrote no option"
    return _result(0, max_marks, "INCORRECT", f"Check the sheet: the student {seen}; the key's answer is {right}.",
                   _LOW, missing=[f"Correct option {right}"])
