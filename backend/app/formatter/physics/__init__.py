"""Physics subjects. Nothing of their own yet: every stage uses the shared code in common/.

To give Physics its own rule, define the hook here (see common/__init__.py); nothing else changes.
"""
from ..common import *  # noqa: F401,F403


def answer_sheet_format() -> str:
    """How this subject's answer sheets are laid out (common/answers.py)."""
    return """Physics sheets: answers start with "A1", "A2" ... or "1)", "Q1" at the left margin, often followed by the
topic ("A1: Force & Pressure"). Parts are a), b) under it, each opening with the question's own words ("a) Define
atmospheric pressure ...") followed by the answer. Formulas, units ("SI unit: Pascal (Pa)") and derivations belong to
the part above them."""
