"""Hindi subjects. Reading papers, keys and sheets uses the shared code in common/ unchanged;
only the grader gets the language marking rules."""
from __future__ import annotations

from ..common import *  # noqa: F401,F403


def grading_rules(question_text: str | None, key_text: str | None) -> str:
    """Language marking rules (evaluation only): comprehension by meaning, literature exact, grammar exact."""
    from ..common.language import language_rules
    return language_rules(question_text, key_text)


def answer_sheet_format() -> str:
    """How this subject's answer sheets are laid out (common/answers.py)."""
    return """Hindi sheets: answers start with the question number ("1)", "प्रश्न 1", "उत्तर 1") at the left margin; parts are
(क), (ख), (ग) or (i), (ii). Letters, essays and paragraphs run for many lines and onto later pages and stay one answer."""
