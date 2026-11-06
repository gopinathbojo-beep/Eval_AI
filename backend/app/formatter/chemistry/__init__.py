"""Chemistry subjects. Nothing of their own yet: every stage uses the shared code in common/.

To give Chemistry its own rule, define the hook here (see common/__init__.py); nothing else changes.
"""
from ..common import *  # noqa: F401,F403


def answer_sheet_format() -> str:
    """How this subject's answer sheets are laid out (common/answers.py)."""
    return """Chemistry sheets: a "Chemistry" title at the top (not an answer). Each answer starts with its number at
the left margin ("1)", "3)", "4)"); a number may stand alone on its line with the answer starting below it. Parts are
a), b) under the number. Chemical equations ("2Mg + O2 -> 2MgO") and arrow lists ("-> Coke", "-> Coal tar") belong to
the answer above them."""
