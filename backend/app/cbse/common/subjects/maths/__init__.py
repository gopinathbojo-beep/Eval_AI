"""Maths subjects: answers are graded step by step against the marking scheme (grade_points, common/steps.py);
every other stage uses the shared code in common/.

To give Maths its own rule, define the hook here (see common/__init__.py); nothing else changes.
"""
from ... import *  # noqa: F401,F403


def grade_points(rubric, answer_text, max_marks, ask):
    """Step by step against the confirmed marking scheme, its OR choices counted once (common/steps.py)."""
    from ...steps import grade
    return grade(rubric, answer_text, max_marks, ask)
