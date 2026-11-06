from types import SimpleNamespace as NS
from app.services.mapping_service import _confirm_content_mappings

QS = [NS(id=f"q{i}", position=i) for i in range(1, 9)]


def _ans(pos, qid, status="MAPPED", label="Q"):
    return NS(position=pos, exam_question_id=qid, status=status, normalized_number=qid[1:] if qid else None,
              raw_question_number=f"{label}{qid[1:]}" if label and qid else None, mapping_note=None)


def _sheet(*unlabelled):
    """Q1, Q2 labelled; the given unlabelled suggestions; then Q6, Q7 labelled."""
    sug = [(_ans(3 + i, qid, "NEEDS_REVIEW", None), det) for i, (qid, det) in enumerate(unlabelled)]
    n = 3 + len(sug)
    answers = [_ans(1, "q1"), _ans(2, "q2"), *(a for a, _ in sug), _ans(n, "q6"), _ans(n + 1, "q7")]
    return answers, sug


def test_strong_content_in_answer_order_is_mapped_without_review():
    answers, sug = _sheet(("q4", [{"id": "q4", "num": "4", "score": 0.95}]),
                          ("q5", [{"id": "q5", "num": "5", "score": 0.81}]))
    _confirm_content_mappings(answers, QS, sug)
    assert [a.status for a, _ in sug] == ["MAPPED", "MAPPED"]


def test_weak_or_close_content_stays_for_review():
    answers, sug = _sheet(("q4", [{"id": "q4", "num": "4", "score": 0.55}]),
                          ("q5", [{"id": "q5", "num": "5", "score": 0.85}, {"id": "q3", "num": "3", "score": 0.78}]))
    _confirm_content_mappings(answers, QS, sug)
    assert [a.status for a, _ in sug] == ["NEEDS_REVIEW", "NEEDS_REVIEW"]


def test_content_against_answer_order_stays_for_review():
    answers, sug = _sheet(("q8", [{"id": "q8", "num": "8", "score": 0.95}]))  # between Q2 and Q6 but says Q8
    _confirm_content_mappings(answers, QS, sug)
    assert sug[0][0].status == "NEEDS_REVIEW"


def test_question_already_answered_stays_for_review():
    answers, sug = _sheet(("q4", [{"id": "q4", "num": "4", "score": 0.95}]))
    answers.append(_ans(9, "q4"))
    _confirm_content_mappings(answers, QS, sug)
    assert sug[0][0].status == "NEEDS_REVIEW"


def test_content_from_sixty_percent_is_mapped_without_review():
    answers, sug = _sheet(("q4", [{"id": "q4", "num": "4", "score": 0.62}]))
    _confirm_content_mappings(answers, QS, sug)
    assert sug[0][0].status == "MAPPED"


def test_unnumbered_subparts_continue_the_question_of_the_previous_part():
    """Q24 "I. ... VI." answered as "i." ... "vi." with no number: a short part ("iv. d. 30000") the content cannot
    place continues Q24; a part label the question does not print, or a broken sequence, is left alone."""
    from types import SimpleNamespace as N
    from app.services.mapping_service import _attach_subpart_runs
    q24 = N(id="q24", normalized_number="24", question_text="Case study\nI. The net sacrifice ...\nII. Entry\n"
                                                             "III. Goodwill\nIV. Net gain\nV. Ratio\nVI. Capital")
    def a(pos, text, status="MAPPED", qid="q24"):
        return N(position=pos, answer_text=text, status=status, exam_question_id=qid if status == "MAPPED" else None,
                 raw_question_number=None, mapping_confirmed=False, mapping_candidates=[], mapping_note=None)
    rows = [a(1, "iii. b. 30000"), a(2, "iv. d. 30000", "UNMAPPED"), a(3, "v. C: Old ratio"),
            a(4, "vi. b. 2,35,000", "UNMAPPED"), a(5, "viii. something", "UNMAPPED")]
    _attach_subpart_runs(rows, [q24])
    assert [r.status for r in rows] == ["MAPPED", "MAPPED", "MAPPED", "MAPPED", "UNMAPPED"]
    assert rows[1].exam_question_id == "q24" and rows[3].exam_question_id == "q24"
