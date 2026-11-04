from types import SimpleNamespace as NS

import pytest

from app.cbse.grading import validate_result
from app.formatter.common.mark_rules import EvaluationValidationError
from app.ocr.schemas import EvaluationResult, StudentAnswerItem
from app.ocr.student_text import active_student_text


def assess(marks=.5, credit="partial", quote="A = pi r^2", student="A = pi r^2; final answer = 99", scheme="Area formula and result", **extra):
    tree = {"id": "point", "kind": "point", "marks": 1, "text": "Area formula and result"}
    key = NS(rubric={"cbse_tree": tree}, answer_text="Area formula and result")
    award = dict(id="point", marks=marks, credit_type=credit, evidence="Correct formula; wrong final result.",
                 scheme_quote=scheme, evidence_quotes=[quote], **extra)
    return validate_result(EvaluationResult(marks_awarded=marks, criterion_awards=[award]),
                           NS(max_marks=1, question_type="numerical"), key, {}, student, require_support=True)


def test_partial_credit_retains_visible_method_despite_wrong_result():
    result = assess()
    assert result.marks_awarded == .5
    assert result.criterion_awards[0]["counted"] is True
    assert result.missing_points == ["point"]
    assert "wrong final result" in result.feedback


@pytest.mark.parametrize("changes", [
    {"credit": "full"}, {"scheme": "invented scheme point"},
    {"quote": "final answer = 12"}, {"quote": "40", "student": "140"},
    {"quote": "40", "student": "-40"},
    {"quote": "B", "student": "Beta"}, {"quote": "correct", "student": "~~correct~~ wrong"},
])
def test_unsupported_or_misclassified_credit_is_rejected(changes):
    with pytest.raises(EvaluationValidationError):
        assess(**changes)


def test_cancellation_annotations_never_become_positive_evidence():
    assert active_student_text("~~old~~ <del>old2</del> [crossed out: old3] new").strip() == "new"
    answer = StudentAnswerItem(content_blocks=[{"text": "old", "crossed_out": True}, {"text": "new"}])
    assert answer.answer_text == "new"


def test_alternatives_count_best_supported_branch_and_feedback_only_that_branch():
    tree = {"id": "root", "kind": "choose", "limit": 1, "children": [
        {"id": "a", "kind": "point", "marks": 1, "text": "formula"},
        {"id": "b", "kind": "point", "marks": 1, "text": "formula"},
    ]}
    awards = [dict(id=i, marks=m, credit_type="full" if m == 1 else "partial",
                   scheme_quote="formula", evidence="visible formula", evidence_quotes=[i]) for i, m in [("a", .5), ("b", 1)]]
    result = validate_result(EvaluationResult(marks_awarded=1.5, criterion_awards=awards),
        NS(max_marks=1, question_type="numerical"), NS(rubric={"cbse_tree": tree}, answer_text="formula"),
        {}, "a; b", require_support=True)
    assert result.marks_awarded == 1
    assert result.matched_points == ["b"] and result.missing_points == []
    assert [a["counted"] for a in result.criterion_awards] == [False, True]
