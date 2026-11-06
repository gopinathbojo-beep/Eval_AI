"""Science (CBSE 086): answers are read by the number the student wrote (see common/written.py); Assertion-Reason
options and terms shared between questions made content matching move answers ("9" to Q7, "20" to Q18)."""
from ..common import *  # noqa: F401,F403
from ..common.written import segment_answers  # noqa: F401


def answer_sheet_format() -> str:
    """How this subject's answer sheets are laid out (common/answers.py)."""
    return """Science sheets: answers start with the question number at the left margin ("1)", "Q1", "Ans 1"); parts are
a), b) or (i), (ii). Equations, diagrams' labels, units and point lists belong to the answer above them."""
