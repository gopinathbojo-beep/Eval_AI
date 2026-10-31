"""What every subject shares: the default of each formatter hook. A subject formatter does
`from ..common import *` and overrides the hooks its papers need.

A hook returning None means the shared parser does the work: paper.py for question papers, keys.py for answer
keys, answers.py for answer sheets. The rest of common/ is shared by them and by the subjects: numbering.py (question
numbers), choices.py (either/or, answer any N), recovery.py and mapping.py (answers to questions), outcomes.py,
mark_rules.py (checks on the grader's marks).
"""
from __future__ import annotations
from typing import Any

__all__ = ["parse_paper", "segment_keys", "segment_answers", "grading_attempts", "check_deductions",
           "uses_pdf_text", "build_rubric"]


def parse_paper(page_results: list[tuple[dict, Any]]) -> Any | None:
    """The question paper's structure (DocumentStructure), or None for the shared parser."""
    return None


def segment_keys(page_results: list[tuple[dict, Any]], canonical_questions: list[Any] | None = None) -> list[Any] | None:
    """One answer key per question (SegmentedKey), or None for the shared segmenter."""
    return None


def segment_answers(page_results: list[tuple[dict, Any]], canonical_questions: list[Any] | None = None) -> list[Any] | None:
    """The student's answers (SegmentedAnswer), or None for the shared segmenter."""
    return None


def grading_attempts(question_text: str | None, answer_text: str) -> list[tuple[str, str]]:
    """Several attempts in one answer, each graded and the best counted: [(title, text)]; [] grades it as one."""
    return []


def check_deductions(result: Any, answer_text: str, key_text: str | None, max_marks: float) -> Any:
    """The grader's validated result, after the subject's own checks of its deductions."""
    return result


def uses_pdf_text() -> bool:
    """Whether a PDF's own text layer may be read (it is exact for typed papers)."""
    return True


def build_rubric(question_text: str | None, key_text: str | None, key_criteria: list[str] | None,
                 max_marks: float | None) -> Any:
    """The question's marking rubric (see common/rubric.py): marking points with marks and kinds, notes, deductions,
    and the problems the teacher should look at once."""
    from .rubric import build_rubric as build
    return build(question_text, key_text, key_criteria, max_marks)
