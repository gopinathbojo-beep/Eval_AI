"""A mark always comes out of grading: a rejected reply is asked for again with the reason, and the last reply is
read leniently when every try is still off. The grader's spelling slips in field names are read as meant."""
from types import SimpleNamespace as NS

import pytest

from app.cbse.grading import validate_result
from app.formatter.common.mark_rules import EvaluationValidationError
from app.ocr.internvl import AIResponseError
from app.ocr.schemas import EvaluationResult
from app.services.evaluation_service import REGRADE_HINT, _grade_until_valid

TREE = {"id": "q", "kind": "all", "children": [{"id": "q.A", "kind": "point", "marks": 2},
                                                {"id": "q.B", "kind": "point", "marks": 1}]}
Q, KEY = NS(max_marks=3, question_type="short_answer"), NS(rubric={"cbse_tree": TREE})
STUDENT = "A. Rs = 7.5 ohm, I = 2 A\nB. V = 3 V"


def _check(parsed, unverified=None, lenient=False):
    return validate_result(parsed, Q, KEY, {}, STUDENT, unverified=unverified, lenient=lenient)


def _asker(*replies):
    calls = []

    def ask(user):
        calls.append(user)
        reply = replies[min(len(calls), len(replies)) - 1]
        if isinstance(reply, Exception):
            raise reply
        return NS(parsed=EvaluationResult.model_validate(reply), raw=str(reply))
    return ask, calls


def test_misspelled_award_field_is_read_as_meant():
    res = EvaluationResult.model_validate({"marks_awarded": 2, "criterions_awards": [
        {"id": "q.A", "marks": 2, "evidence": ["Rs = 7.5 ohm, I = 2 A"]}]})
    assert res.criterion_awards[0]["evidence_quotes"] == ["Rs = 7.5 ohm, I = 2 A"]
    assert _check(res).marks_awarded == 2


def test_a_rejected_reply_is_asked_again_with_the_reason():
    bad = {"marks_awarded": 2, "criterion_awards": [{"id": "q.A", "marks": 5, "evidence_quotes": ["I = 2 A"]}]}
    good = {"marks_awarded": 2, "criterion_awards": [{"id": "q.A", "marks": 2, "evidence_quotes": ["I = 2 A"]}]}
    ask, calls = _asker(bad, good)
    res, _ = _grade_until_valid(ask, "PROMPT", _check, "37")
    assert res.marks_awarded == 2 and len(calls) == 2
    assert calls[1].startswith("PROMPT") and "exceeds its printed allocation" in calls[1]
    assert REGRADE_HINT.split("{")[0] in calls[1]


def test_every_try_off_still_gives_a_capped_flagged_mark():
    bad = {"marks_awarded": 9, "criterion_awards": [{"id": "q.A", "marks": 5, "evidence_quotes": ["I = 2 A"]},
                                                    {"id": "q.Z", "marks": 1}]}
    ask, calls = _asker(bad)
    res, _ = _grade_until_valid(ask, "P", _check, "37")
    assert len(calls) == 3 and res.marks_awarded == 2            # q.A capped at its 2 marks; unknown q.Z skipped
    assert res.confidence <= 0.4 and res.feedback.startswith("Check this mark")


def test_no_criterion_at_all_falls_back_to_the_replys_own_total():
    ask, _ = _asker({"marks_awarded": 2.4, "criterion_awards": []})
    res, _ = _grade_until_valid(ask, "P", _check, "37")
    assert res.marks_awarded == 2.5 and res.feedback.startswith("Check this mark")


def test_invalid_json_on_one_try_is_retried():
    good = {"marks_awarded": 1, "criterion_awards": [{"id": "q.B", "marks": 1, "evidence_quotes": ["V = 3 V"]}]}
    ask, calls = _asker(AIResponseError("FAILED_PARSE", "not json"), good)
    res, _ = _grade_until_valid(ask, "P", _check, "37")
    assert res.marks_awarded == 1 and len(calls) == 2


def test_strict_reading_still_rejects_what_lenient_corrects():
    reply = EvaluationResult.model_validate({"marks_awarded": 5, "criterion_awards": [
        {"id": "q.A", "marks": 5, "evidence_quotes": ["I = 2 A"]}]})
    with pytest.raises(EvaluationValidationError):
        _check(reply.model_copy(deep=True))
    assert _check(reply, lenient=True).marks_awarded == 2
