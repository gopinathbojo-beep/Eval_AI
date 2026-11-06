"""Accountancy (CBSE 055): answers are read by the number the student wrote (see common/written.py); journal lines
and balance-sheet rows look like other questions' content, so content never moves a clearly numbered answer."""
from ..common import *  # noqa: F401,F403
from ..common.written import segment_answers  # noqa: F401


def answer_sheet_format() -> str:
    """How this subject's answer sheets are laid out (common/answers.py)."""
    return """Accountancy sheets (school answer booklet, often scanned sideways). Page 1 has the school header
(roll no., name, date, exam, subject, class & sec, invigilator's sign): not an answer. A heading like "Part A" may
appear: not an answer. Each answer starts with the question number at the left margin ("1.", "2.", "15."). MCQs are
one line each: number, option letter and value ("4. b ₹24000", "13. b (ii), (iii), (iv)"); every such line is its own
answer. Journal entries, ledger accounts and tables (columns of amounts, "To ... A/c", "Dr", "Cr") stay in the answer
of the number above them, even across pages; amounts at the right of a line are part of that line's answer."""
