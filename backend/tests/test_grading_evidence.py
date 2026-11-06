from types import SimpleNamespace as NS

import pytest

from app.cbse.grading import validate_result, scoring_tree
from app.formatter.common.mark_rules import EvaluationValidationError
from app.ocr.schemas import EvaluationResult
from app.services.mapping_service import conflicting_answer_heading
from app.services.evaluation_service import resolve_student_answer, STUDENT_ANSWER_MAPPING_REVIEW


def check(award, student, mcq=False):
    tree = {"id": "criterion", "kind": "point", "marks": 1, "response_type": "mcq" if mcq else "open"}
    key = NS(rubric={"cbse_tree": tree})
    q = NS(max_marks=1, question_type="mcq" if mcq else "numerical")
    return validate_result(EvaluationResult(marks_awarded=1, criterion_awards=[{"id": "criterion", "marks": 1, **award}]), q, key, {}, student)


def test_option_only_answer_accepts_legacy_commentary_without_inventing_work():
    assert check({"evidence": "Student selected option B."}, "B", True).marks_awarded == 1
    with pytest.raises(EvaluationValidationError):
        check({"evidence": "Student selected option C."}, "B", True)


def test_separate_exact_excerpts_allow_formatting_but_not_changed_working():
    student = "-6 = ( -8m - 3n ) / (m + n)\n2m = 3n\nm : n = 3 : 2"
    assert check({"evidence_quotes": ["2m=3n", "m : n = 3 : 2"]}, student).marks_awarded == 1
    with pytest.raises(EvaluationValidationError):
        check({"evidence_quotes": ["2m = 5n"]}, student)
    with pytest.raises(EvaluationValidationError):
        check({"evidence_quotes": ["2m=3n", "The student solved it correctly"]}, student)
    with pytest.raises(EvaluationValidationError):
        check({"evidence_quotes": []}, student)


def test_unicode_minus_and_spacing_do_not_cause_false_evidence_errors():
    assert check({"evidence_quotes": ["x²−1 = 0"]}, "x² - 1=0").marks_awarded == 1


def test_explicit_answer_header_conflict_is_reviewed_not_scored_under_wrong_question():
    assert conflicting_answer_heading("Section E\n36>\narea = 44", "34") == "36"
    assert conflicting_answer_heading("1. Given a triangle\n2. Apply theorem", "34") is None
    assert conflicting_answer_heading("(ii)\nArea = 44", "34") is None
    q = NS(id="q", normalized_number="34", display_number="34", structure={})
    answer = NS(exam_question_id="q", status="MAPPED", answer_text="Section E\n36>\nArea = 44", raw_question_number="Q34")
    snapshot = NS(answers={"ev": [answer]}, questions=[q])
    result = resolve_student_answer(None, NS(id="ev", exam_id="exam"), q, snapshot)
    assert result.status == STUDENT_ANSWER_MAPPING_REVIEW
    assert "question 36" in result.reason


def test_missing_extracted_allocations_use_scheme_text_without_guessing_step_marks():
    q = NS(max_marks=3, question_type="proof")
    key = NS(rubric={"cbse_tree": {"id": "source", "kind": "all", "children": [
        {"id": "step", "kind": "point", "marks": None},
    ]}})
    tree = scoring_tree(q, key, {})
    assert tree["id"] == "overall" and tree["marks"] == 3
    assert "children" not in tree
    result = EvaluationResult(marks_awarded=2, criterion_awards=[
        {"id": "overall", "marks": 2, "evidence_quotes": ["angle sum = 180°"]},
    ])
    assert validate_result(result, q, key, {}, "angle sum = 180°").marks_awarded == 2


def _choice_scheme():
    """A: 1 mark; then either C or D (2 marks each), as in a CBSE case-based question."""
    tree = {"id": "q", "kind": "all", "children": [
        {"id": "q.A", "kind": "point", "marks": 1},
        {"id": "q.CD", "kind": "choose", "limit": 1, "children": [
            {"id": "q.C", "kind": "point", "marks": 2}, {"id": "q.D", "kind": "point", "marks": 2}]}]}
    return NS(max_marks=3, question_type="case_based"), NS(rubric={"cbse_tree": tree})


def test_a_criterion_left_unawarded_counts_as_zero_not_as_an_error():
    q, key = _choice_scheme()
    student = "A) Silver is the best conductor\n(c) Yes, the time will increase"
    result = EvaluationResult(marks_awarded=3, criterion_awards=[
        {"id": "q.A", "marks": 1, "evidence_quotes": ["Silver is the best conductor"]},
        {"id": "q.C", "marks": 1, "evidence_quotes": ["Yes, the time will increase"]},
    ])  # D, the alternative not chosen, has no award
    assert validate_result(result, q, key, {}, student).marks_awarded == 2
    with pytest.raises(EvaluationValidationError):
        validate_result(EvaluationResult(marks_awarded=0, criterion_awards=[]), q, key, {}, student)


def test_unmatched_evidence_can_be_kept_for_the_teacher_instead_of_rejected():
    q, key = _choice_scheme()
    result = EvaluationResult(marks_awarded=1, criterion_awards=[
        {"id": "q.A", "marks": 1, "evidence_quotes": ["The student named silver correctly"]}])
    with pytest.raises(EvaluationValidationError):
        validate_result(result.model_copy(deep=True), q, key, {}, "A) Silver")
    unverified = []
    assert validate_result(result, q, key, {}, "A) Silver", unverified=unverified).marks_awarded == 1
    assert unverified == ["q.A"]
