"""Tamil subjects: their own paper, key and answer-sheet layout, rubrics and grading checks.

  format.py   Tamil text rules: labels அ) ஆ), வினா numbers, marks phrases, section headings, stemming
  blocks.py   IndicOCR blocks split at the question headings inside them
  paper.py    question paper structure and answer key segmentation
  answers.py  answer sheets, any-one-topic attempts, deductions checked against the student's text
  align.py    answer sheets by alignment (numbers, titles, key, order) and their self-repair
  rubric.py   question kinds (letter / essay / paragraph / points) and their criteria
  points.py   point questions graded point by point on the confirmed rubric
"""
from __future__ import annotations
from typing import Any

from ... import *  # noqa: F401,F403  the shared defaults; the hooks below override them

# Answer sheets segmented by align.py instead of answers.py. Switch on only when the replay harness shows it doing
# better on the stored sheets: python scripts/accuracy_report.py --segmenter both
USE_ALIGNMENT = False


def parse_paper(page_results: list[tuple[dict, Any]]) -> Any | None:
    from .paper import parse
    doc = parse(page_results)
    return doc if doc.questions else None  # nothing found: let the shared parser try


def segment_keys(page_results: list[tuple[dict, Any]], canonical_questions: list[Any] | None = None) -> list[Any] | None:
    from .paper import segment_keys as segment
    return segment(page_results, canonical_questions) or None


def segment_answers(page_results: list[tuple[dict, Any]], canonical_questions: list[Any] | None = None,
                    keys: dict[str, str] | None = None) -> list[Any]:
    if USE_ALIGNMENT:
        from .align import segment as aligned
        return aligned(page_results, canonical_questions, keys)
    from .answers import segment
    return segment(page_results, canonical_questions)


def repair_answers(answers: list[Any], page_results: list[tuple[dict, Any]], canonical_questions: list[Any] | None,
                   keys: dict[str, str] | None, reread: Any | None) -> list[Any]:
    from .align import reread_failing
    return reread_failing(answers, page_results, canonical_questions, keys, reread,
                          lambda pages: segment_answers(pages, canonical_questions, keys))


def grading_attempts(question_text: str | None, answer_text: str) -> list[tuple[str, str]]:
    from .answers import one_of_attempts
    return one_of_attempts(question_text, answer_text)


def grade_points(rubric: dict | None, answer_text: str, max_marks: float, ask: Any) -> Any | None:
    from .points import grade
    return grade(rubric, answer_text, max_marks, ask)


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
