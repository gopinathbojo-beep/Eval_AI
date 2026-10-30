import pytest
from app.ocr.parser import extract_json_object, ParseError
from app.ocr.schemas import QuestionPageResult, EvaluationResult, StudentPageResult
from app.cbse.formatter.common.mark_rules import validate_evaluation, EvaluationValidationError


def test_plain():
    assert extract_json_object('{"a": 1}') == {"a": 1}


def test_bom_whitespace():
    assert extract_json_object('\ufeff  \n{"a": 1}\n ') == {"a": 1}


def test_fenced():
    assert extract_json_object('Here:\n```json\n{"a": {"b": 2}}\n```\nDone') == {"a": {"b": 2}}


def test_fence_without_lang():
    assert extract_json_object('```\n{"a": 1}\n```') == {"a": 1}


def test_prose_around():
    assert extract_json_object('Sure! {"questions": [{"t": "x }"}]} hope that helps') == {"questions": [{"t": "x }"}]}


def test_escaped_and_unicode():
    o = extract_json_object('{"t": "H\\u2082SO\\u2084 \\"quoted\\" தமிழ்"}')
    assert o["t"] == 'H₂SO₄ "quoted" தமிழ்'


def test_truncated_rejected():
    with pytest.raises(ParseError):
        extract_json_object('{"questions": [{"raw_question_number": "1", "question_text": "abc')


def test_garbage_rejected():
    with pytest.raises(ParseError):
        extract_json_object("I cannot read this page.")
    with pytest.raises(ParseError):
        extract_json_object("")


def test_question_schema_lenient_types():
    r = QuestionPageResult.model_validate({"page_number": 1, "questions": [
        {"raw_question_number": 3, "question_text": "x", "marks": "5", "confidence": 94,
         "bbox": {"x": 1, "y": 2, "width": 3, "height": 4}},
        {"raw_question_number": None, "question_text": "y", "marks": None, "bbox": "bad"}]})
    q = r.questions
    assert q[0].raw_question_number == "3" and q[0].marks == 5.0 and abs(q[0].confidence - 0.94) < 1e-9
    assert q[1].bbox is None and q[1].raw_question_number is None


def test_student_schema():
    r = StudentPageResult.model_validate({"answers": [{"question_number": "3(a)", "answer_text": "t", "ocr_confidence": 0.89}]})
    assert r.answers[0].question_number == "3(a)"


def test_case10_marks_exceed_rejected():
    r = EvaluationResult.model_validate({"marks_awarded": 8, "max_marks": 5})
    with pytest.raises(EvaluationValidationError):
        validate_evaluation(r, 5)


def test_negative_and_mismatched_max():
    with pytest.raises(EvaluationValidationError):
        validate_evaluation(EvaluationResult(marks_awarded=-1), 5)
    with pytest.raises(EvaluationValidationError):
        validate_evaluation(EvaluationResult(marks_awarded=2, max_marks=10), 5)


def test_valid_and_decision_normalised():
    r = validate_evaluation(EvaluationResult(marks_awarded=4, max_marks=5, decision="partially correct"), 5)
    assert r.decision == "PARTIALLY_CORRECT"
    r = validate_evaluation(EvaluationResult(marks_awarded=4, decision="nonsense"), 5)
    assert r.decision is None


def test_marks_must_be_numeric():
    with pytest.raises(Exception):
        EvaluationResult.model_validate({"marks_awarded": "lots"})


def test_unexplained_deduction_is_limited_to_half_mark():
    # "minor error ... final answer correct" with nothing named as missing: 2/3 -> 2.5/3
    r = validate_evaluation(EvaluationResult(marks_awarded=2, max_marks=3, decision="PARTIALLY_CORRECT",
                                             missing_points=[], feedback="Minor error, final answer correct."), 3)
    assert r.marks_awarded == 2.5 and "Deduction limited" in r.feedback


def test_named_missing_point_keeps_the_deduction():
    r = validate_evaluation(EvaluationResult(marks_awarded=1, max_marks=3, decision="PARTIALLY_CORRECT",
                                             missing_points=["Industrial uses of coke"]), 3)
    assert r.marks_awarded == 1


def test_wrong_or_blank_answers_are_not_lifted():
    assert validate_evaluation(EvaluationResult(marks_awarded=0, max_marks=3, decision="INCORRECT"), 3).marks_awarded == 0
    assert validate_evaluation(EvaluationResult(marks_awarded=1, max_marks=3, decision="INCORRECT"), 3).marks_awarded == 1
    # a half-mark deduction without a named point is already within the limit
    assert validate_evaluation(EvaluationResult(marks_awarded=2.5, max_marks=3, decision="PARTIALLY_CORRECT"), 3).marks_awarded == 2.5


def test_omission_described_only_in_feedback_keeps_the_deduction():
    r = validate_evaluation(EvaluationResult(marks_awarded=1.5, max_marks=3, decision="PARTIALLY_CORRECT", missing_points=[],
                                             feedback="You stated both laws. However, you did not provide any calculations for part (b)."), 3)
    assert r.marks_awarded == 1.5
