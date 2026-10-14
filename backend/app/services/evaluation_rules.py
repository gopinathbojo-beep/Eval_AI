from __future__ import annotations
import math
from ..ocr.schemas import EvaluationResult

VALID_DECISIONS = {"CORRECT", "PARTIALLY_CORRECT", "INCORRECT", "NOT_ATTEMPTED"}


class EvaluationValidationError(ValueError):
    pass


def validate_evaluation(result: EvaluationResult, official_max: float) -> EvaluationResult:
    """Backend is the mark authority. Impossible AI output is rejected (EVALUATION_ERROR), not clamped."""
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
    # Snap to the 0.5-mark grid the prompt asks for (e.g. 1.3 -> 1.5); never past the official maximum.
    result.marks_awarded = min(official_max, round(m * 2) / 2)
    # The decision label is derived from the marks so it can never contradict them.
    result.decision = derive_decision(result.marks_awarded, official_max)
    return result


def derive_decision(marks: float, official_max: float) -> str:
    if official_max > 0 and marks >= official_max - 1e-9:
        return "CORRECT"
    if marks <= 1e-9:
        return "INCORRECT"
    return "PARTIALLY_CORRECT"
