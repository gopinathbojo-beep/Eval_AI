from __future__ import annotations
import math
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
