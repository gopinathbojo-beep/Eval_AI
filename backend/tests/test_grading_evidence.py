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


def test_partial_awards_keep_quarter_marks_and_non_mcq_flag_cannot_erase_them():
    q = NS(max_marks=1, question_type="descriptive")
    key = NS(rubric={"cbse_tree": {"id": "part", "kind": "point", "marks": 1}})
    result = EvaluationResult(marks_awarded=.25, criterion_awards=[
        {"id": "part", "marks": .25, "evidence_quotes": ["correct step"], "multiple_answers": True},
    ])
    validated = validate_result(result, q, key, {}, "correct step")
    assert validated.marks_awarded == .25 and validated.decision == "PARTIALLY_CORRECT"
