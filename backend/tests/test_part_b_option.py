"""Accountancy Part B: a student attempts one option; the sheet's option is read from its answers."""
from types import SimpleNamespace as NS

from app.cbse.branch import MIXED, branch_texts, vote


def _q(qid, fin, comp):
    return NS(id=qid, question_text=f"[Part B - Analysis of Financial Statements]\n{fin}\nOR\n"
                                    f"[Part B - Computerised Accounting]\n{comp}",
              structure={"tree": {"children": [{"audience": "financial"}, {"audience": "computerised"}]}})


QS = {"q27": _q("q27", "Cost of materials consumed, work in progress, raw material purchases",
                "Identify the error displayed when cell coordinates on a worksheet are invalid"),
      "q31": _q("q31", "Comparative statement of profit and loss of Uttu Machineries, revenue from operations",
                "Contra voucher, post-dated voucher, receipt voucher; advantages of pivot table report"),
      "q32": _q("q32", "Main head and sub-head: warranty claims payable, preliminary expenses, interest accrued",
                "Limitations of computerised accounting system")}


def test_branch_texts_split_the_two_options():
    texts = branch_texts(QS["q31"])
    assert "Uttu" in texts["financial"] and "Uttu" not in texts["computerised"]
    assert "voucher" in texts["computerised"]


def test_the_option_most_answers_match_is_the_students():
    answers = {"q27": "Cost of raw material consumed = opening raw material + purchases",
               "q31": "Comparative statement: revenue from operations increased 100%",
               "q32": "Warranty claims payable: current liabilities, short-term provisions"}
    assert vote(answers, QS) == "financial"
    assert vote({"q31": "A contra voucher records cash deposited into bank; a receipt voucher ...",
                 "q32": "Limitations of computerised accounting: cost of system, system failure"}, QS) == "computerised"


def test_even_split_is_mixed_and_nothing_written_is_none():
    assert vote({"q31": "Comparative statement revenue from operations Uttu",
                 "q32": "Limitations of computerised accounting system"}, QS) == MIXED
    assert vote({}, QS) is None and vote({"q31": "I do not know"}, QS) is None
