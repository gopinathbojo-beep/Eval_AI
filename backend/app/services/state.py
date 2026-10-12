"""Exam state machine. Transitions are explicit; verification steps cannot be skipped."""
from __future__ import annotations
from fastapi import HTTPException
from ..models import Exam

STATES = ["DRAFT", "QUESTION_PAPER_UPLOADED", "QUESTIONS_EXTRACTED", "QUESTIONS_VERIFIED",
          "ANSWER_KEY_UPLOADED", "ANSWER_KEY_VERIFIED", "READY_FOR_EVALUATION",
          "EVALUATING", "REVIEW_REQUIRED", "FINALIZED"]

ALLOWED: dict[str, set[str]] = {
    "DRAFT": {"QUESTION_PAPER_UPLOADED"},
    "QUESTION_PAPER_UPLOADED": {"QUESTIONS_EXTRACTED", "QUESTION_PAPER_UPLOADED"},
    "QUESTIONS_EXTRACTED": {"QUESTIONS_VERIFIED", "QUESTION_PAPER_UPLOADED"},
    "QUESTIONS_VERIFIED": {"ANSWER_KEY_UPLOADED"},
    "ANSWER_KEY_UPLOADED": {"ANSWER_KEY_VERIFIED", "ANSWER_KEY_UPLOADED"},
    "ANSWER_KEY_VERIFIED": {"READY_FOR_EVALUATION", "ANSWER_KEY_UPLOADED"},
    "READY_FOR_EVALUATION": {"EVALUATING", "ANSWER_KEY_UPLOADED", "REVIEW_REQUIRED"},
    "EVALUATING": {"REVIEW_REQUIRED", "READY_FOR_EVALUATION", "EVALUATING"},
    "REVIEW_REQUIRED": {"EVALUATING", "FINALIZED", "READY_FOR_EVALUATION", "ANSWER_KEY_UPLOADED"},
    "FINALIZED": set(),
}


def set_state(exam: Exam, new: str) -> None:
    if new == exam.status:
        return
    if new not in ALLOWED.get(exam.status, set()):
        raise HTTPException(409, detail={"code": "INVALID_EXAM_STATE",
                                         "message": f"Exam is {exam.status}; it cannot move to {new}."})
    exam.status = new


def at_least(exam: Exam, state: str) -> bool:
    return STATES.index(exam.status) >= STATES.index(state)


def require_at_least(exam: Exam, state: str, what: str) -> None:
    if not at_least(exam, state):
        raise HTTPException(409, detail={
            "code": "EXAM_STATE_TOO_EARLY",
            "message": f"{what} is not available until the exam reaches {state.replace('_', ' ').title()} "
                       f"(currently {exam.status.replace('_', ' ').title()})."})
