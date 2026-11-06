"""Maths subjects. Nothing of their own yet: every stage uses the shared code in common/.

To give Maths its own rule, define the hook here (see common/__init__.py); nothing else changes.
"""
from ..common import *  # noqa: F401,F403


def grading_rules(question_text: str | None, key_text: str | None) -> str:
    """Maths keeps marking by the scheme's steps alone: no understanding-based rules."""
    return ""


def answer_sheet_format() -> str:
    """How this subject's answer sheets are laid out (common/answers.py)."""
    return """Maths sheets: each answer starts with its number at the left margin ("1)", "2)", "Q3"). An answer is a
column of working: lines starting with "=", "given:", "LHS"/"RHS", steps of an equation, a boxed or underlined final
answer. All working lines stay in the answer they follow until the next question number. Rough work in a margin
column belongs to the answer beside it. A graph or figure page with no number continues the previous answer."""
