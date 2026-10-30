from __future__ import annotations
import math
import re
from ....ocr.schemas import EvaluationResult
from ..tamil import format as tamil_format

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
    if result.decision:
        result.decision = result.decision.strip().upper().replace(" ", "_")
        if result.decision not in VALID_DECISIONS:
            result.decision = None
    return _limit_unexplained_deduction(result, official_max)


_OMISSION_IN_FEEDBACK = re.compile(
    r"\b(?:did\s+not|didn'?t|does\s+not|doesn'?t|not\s+(?:provide|provided|mention|mentioned|include|included|give|given|answer|attempted|address|addressed|stated|calculate|calculated)"
    r"|missing|missed|omit(?:s|ted)?|lacks?|lacking|incomplete|incorrect(?:ly)?|wrong|no\s+(?:calculation|explanation|answer|attempt|working))\b",
    re.I,
)
UNEXPLAINED_DEDUCTION_CAP = 0.5
UNEXPLAINED_DEDUCTION_NOTE = "Deduction limited to 0.5: the AI named no missing marking point."


def _limit_unexplained_deduction(result: EvaluationResult, official_max: float) -> EvaluationResult:
    """A deduction must point at something missing; without one, treat it as a minor slip (at most 0.5 marks).

    Wholly wrong or blank answers (0 marks, INCORRECT / NOT_ATTEMPTED) are left alone.
    """
    m = result.marks_awarded
    named = [p for p in (result.missing_points or []) if str(p).strip()]
    if named or m <= 0 or result.decision in ("INCORRECT", "NOT_ATTEMPTED"):
        return result
    feedback = result.feedback or ""
    if _OMISSION_IN_FEEDBACK.search(feedback) or tamil_format.feedback_names_gap(feedback):  # described, not listed
        return result
    floor = max(0.0, official_max - UNEXPLAINED_DEDUCTION_CAP)
    if m < floor - 1e-9:
        result.marks_awarded = floor
        result.feedback = f"{(result.feedback or '').strip()} ({UNEXPLAINED_DEDUCTION_NOTE})".strip()
    return result
