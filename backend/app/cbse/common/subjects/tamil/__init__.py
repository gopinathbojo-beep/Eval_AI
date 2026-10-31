"""Tamil subjects: their own paper, key and answer-sheet layout, rubrics and grading checks.

  format.py   Tamil text rules: labels அ) ஆ), வினா numbers, marks phrases, section headings, stemming
  blocks.py   IndicOCR blocks split at the question headings inside them
  paper.py    question paper structure and answer key segmentation
  answers.py  answer sheets, any-one-topic attempts, deductions checked against the student's text
  rubric.py   question kinds (letter / essay / paragraph / points) and their criteria
"""
from __future__ import annotations
from typing import Any

from ... import *  # noqa: F401,F403  the shared defaults; the hooks below override them


def parse_paper(page_results: list[tuple[dict, Any]]) -> Any | None:
    from .paper import parse
    doc = parse(page_results)
    return doc if doc.questions else None  # nothing found: let the shared parser try


def segment_keys(page_results: list[tuple[dict, Any]], canonical_questions: list[Any] | None = None) -> list[Any] | None:
    from .paper import segment_keys as segment
    return segment(page_results, canonical_questions) or None


def segment_answers(page_results: list[tuple[dict, Any]], canonical_questions: list[Any] | None = None) -> list[Any]:
    from .answers import segment
    return segment(page_results, canonical_questions)


def grading_attempts(question_text: str | None, answer_text: str) -> list[tuple[str, str]]:
    from .answers import one_of_attempts
    return one_of_attempts(question_text, answer_text)


def check_deductions(result: Any, answer_text: str, key_text: str | None, max_marks: float) -> Any:
    from .answers import check_deductions as check
    return check(result, answer_text, key_text, max_marks)


def uses_pdf_text() -> bool:
    # Tamil PDFs often use legacy Tamil fonts whose text layer is mojibake; IndicOCR reads the page image instead
    return False


def build_rubric(question_text: str | None, key_text: str | None, key_criteria: list[str] | None,
                 max_marks: float | None) -> Any:
    from .rubric import build_rubric as build
    return build(question_text, key_text, key_criteria, max_marks)
