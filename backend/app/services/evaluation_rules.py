from __future__ import annotations
import math
import re
from ..ocr.schemas import EvaluationResult

VALID_DECISIONS = {"CORRECT", "PARTIALLY_CORRECT", "INCORRECT", "NOT_ATTEMPTED"}


class EvaluationValidationError(ValueError):
    pass


def validate_evaluation(result: EvaluationResult, official_max: float) -> EvaluationResult:
    """Backend is the mark authority. Impossible AI output is rejected (EVALUATION_ERROR), not clamped."""
    if official_max is None or official_max <= 0:
        raise EvaluationValidationError(f"official maximum marks {official_max} must be greater than 0")
    m = result.marks_awarded
    if m is None or math.isnan(m) or math.isinf(m):
        raise EvaluationValidationError("marks_awarded is not a finite number")
    if m < 0:
        raise EvaluationValidationError(f"marks_awarded {m} is negative")
    if m > official_max + 1e-9:
        raise EvaluationValidationError(f"marks_awarded {m} exceeds maximum marks {official_max}")
    if result.max_marks is not None and abs(result.max_marks - official_max) > 1e-9:
        raise EvaluationValidationError(
            f"AI reported max_marks {result.max_marks} but the official maximum is {official_max}")
    # Snap to the mark grid (0.5 as the prompt asks, e.g. 1.3 -> 1.5, 1.25 -> 1.5; 0.25 when the question itself
    # is worth quarter marks), rounding half up rather than Python's banker's rounding, never past the maximum.
    step = mark_step(official_max)
    result.marks_awarded = min(official_max, math.floor(m / step + 0.5) * step) if step else m
    # The decision label is derived from the marks so it can never contradict them; a zero-mark
    # NOT_ATTEMPTED verdict is consistent with the marks and is kept.
    if (result.decision or "").upper() == "NOT_ATTEMPTED" and result.marks_awarded <= 1e-9:
        result.decision = "NOT_ATTEMPTED"
    else:
        result.decision = derive_decision(result.marks_awarded, official_max)
    return result


def mark_step(official_max: float) -> float | None:
    """The 0.5 grid if the question's maximum sits on it, else 0.25; None when it fits neither (marks are then not snapped)."""
    for step in (0.5, 0.25):
        if abs(official_max / step - round(official_max / step)) < 1e-9:
            return step
    return None


def derive_decision(marks: float, official_max: float) -> str:
    if official_max > 0 and marks >= official_max - 1e-9:
        return "CORRECT"
    if marks <= 1e-9:
        return "INCORRECT"
    return "PARTIALLY_CORRECT"


_PART_LABEL = re.compile(r"(?:^|(?<=\s))\(\s*([a-h]|[ivx]{1,4})\s*\)\s|(?:^|(?<=\n))\s*([a-h]|[ivx]{1,4})\)\s")
_PART_MARKS = re.compile(r"\(\s*(\d+(?:\.\d+)?)\s*(?:marks?|m)\s*\)", re.IGNORECASE)
_LETTERS, _ROMAN = "abcdefgh", ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii"]


def question_parts(question_text: str, official_max: float | None) -> list[tuple[str, float]]:
    """The parts of a question with their printed marks, [("a", 1.5), ("b", 1.5)], when every part shows its marks
    and they add up to the question's maximum. Otherwise [] and the question is marked as a whole."""
    found = [(m.start(), (m.group(1) or m.group(2)).lower()) for m in _PART_LABEL.finditer(question_text or "")]
    # Keep the run of labels in sequence (a, b, c ... or i, ii, iii ...); "(v)" inside a sentence is not a part
    for seq in (_LETTERS, _ROMAN):
        run = []
        for pos, tok in found:
            if len(run) < len(seq) and tok == seq[len(run)]:
                run.append((pos, tok))
        if len(run) >= 2:
            break
    else:
        return []
    parts = []
    for i, (pos, tok) in enumerate(run):
        end = run[i + 1][0] if i + 1 < len(run) else len(question_text)
        marks = _PART_MARKS.findall(question_text[pos:end])
        if not marks:
            return []
        parts.append((tok, float(marks[-1])))
    if official_max is None or abs(sum(m for _, m in parts) - official_max) > 1e-9:
        return []
    return parts


def apply_part_marks(result: EvaluationResult, parts: list[tuple[str, float]]) -> None:
    """When the evaluator marked each part, the question's marks are the sum of the part marks, each kept within
    0 and that part's maximum and on the 0.5 grid. Without a mark for every part its total is used unchanged."""
    if not parts or not all(tok in result.part_marks for tok, _ in parts):
        return
    if any(math.isnan(result.part_marks[tok]) or math.isinf(result.part_marks[tok]) for tok, _ in parts):
        return
    for tok, pmax in parts:
        m, step = min(pmax, max(0.0, result.part_marks[tok])), mark_step(pmax)
        result.part_marks[tok] = min(pmax, math.floor(m / step + 0.5) * step) if step else m
    result.marks_awarded = sum(result.part_marks[tok] for tok, _ in parts)
