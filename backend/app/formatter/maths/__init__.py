"""Maths subjects. Nothing of their own yet: every stage uses the shared code in common/.

To give Maths its own rule, define the hook here (see common/__init__.py); nothing else changes.
"""
from ..common import *  # noqa: F401,F403


def grading_rules(question_text: str | None, key_text: str | None) -> str:
    """Maths keeps marking by the scheme's steps alone: no understanding-based rules."""
    return ""
