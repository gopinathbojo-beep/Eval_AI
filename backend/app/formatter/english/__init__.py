"""English subjects. Nothing of their own yet: every stage uses the shared code in common/.

To give English its own rule, define the hook here (see common/__init__.py); nothing else changes.
"""
from ..common import *  # noqa: F401,F403


def grading_rules(question_text: str | None, key_text: str | None) -> str:
    """Language marking rules (evaluation only): comprehension by meaning, literature exact, grammar exact."""
    from ..common.language import language_rules
    return language_rules(question_text, key_text)


def answer_sheet_format() -> str:
    """How this subject's answer sheets are laid out (common/answers.py)."""
    return """English sheets: a class/title line at the top (not an answer). Answers start with the question number
("Q1)", "2)", "3)", "4)") at the left margin; a number may stand alone with the answer below. Parts are a), b) (e.g.
reported speech, error correction). Long answers (paragraphs, letters, articles, notices) run for many lines and onto
later pages and stay one answer; a title line inside them ("The Tsunami") is not a new question. Two-column tables
("Incorrect word | Correct word") belong to the answer above them."""
