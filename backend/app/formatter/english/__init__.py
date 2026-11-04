"""English subjects. Nothing of their own yet: every stage uses the shared code in common/.

To give English its own rule, define the hook here (see common/__init__.py); nothing else changes.
"""
from ..common import *  # noqa: F401,F403


def grading_rules(question_text: str | None, key_text: str | None) -> str:
    """Language marking rules (evaluation only): comprehension by meaning, literature exact, grammar exact."""
    from ..common.language import language_rules
    return language_rules(question_text, key_text)
