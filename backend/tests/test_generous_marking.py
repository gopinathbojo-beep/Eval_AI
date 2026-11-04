"""Marking as the school's teachers do: related answers earn marks, struck-out or second attempts cost nothing, and
OCR-garbled wording still counts as the student's evidence. Zero stays for wrong, opposite or unrelated answers."""
from types import SimpleNamespace as NS

import pytest

from app.cbse.grading import SYSTEM, _to_scheme_step, prompt, validate_result
from app.formatter.common.language import THEORY_RULES
from app.formatter.common.mark_rules import EvaluationValidationError
from app.ocr.prompts import EVAL_SYSTEM, GENEROUS_MARKING
from app.ocr.schemas import EvaluationResult


def grade(marks, quotes, student, allocation=2, mcq=False, **award):
    tree = {"id": "c", "kind": "point", "marks": allocation, "response_type": "mcq" if mcq else "open"}
    q = NS(max_marks=allocation, question_type="mcq" if mcq else "short_answer")
    result = EvaluationResult(marks_awarded=marks, criterion_awards=[
        {"id": "c", "marks": marks, "evidence_quotes": quotes, **award}])
    return validate_result(result, q, NS(rubric={"cbse_tree": tree}), {}, student).marks_awarded


def test_every_grader_is_told_to_mark_generously():
    for text in (SYSTEM, EVAL_SYSTEM):
        assert GENEROUS_MARKING in text
    assert "strict" not in EVAL_SYSTEM.split("\n")[0]
    for rule in ("80%", "best matches the key", "letter OR the option's content", "three or more different options"):
        assert rule in GENEROUS_MARKING
    assert "best matches the key" in THEORY_RULES
    q = NS(display_number="7", max_marks=1, question_text="", structure={}, question_type="mcq")
    text = prompt(q, NS(rubric={}, answer_text="(C) X 19,000", accepted_answers=[]), "d. X 19,000", {}, [])
    assert "three or more different options" in text and "best matches the scheme" in text


def test_a_small_related_credit_is_kept():
    assert grade(0.2, ["thick soft lining of the uterus"], "The thick soft lining of the uterus will be formed") == 0.5
    assert _to_scheme_step(0, 1) == 0


def test_ocr_garbled_words_still_match_the_student_answer():
    student = "Herbivores have longer smal intestine, while carnivores have shorter intestine"
    # the grader quotes the term spelt right; the transcription has it misspelt
    assert grade(2, ["Herbivores have longer small intestine"], student) == 2


def test_quotes_with_changed_numbers_or_invented_text_still_fail():
    student = "Bank A/c Dr 3,75,000 To Share Application A/c 3,75,000"
    with pytest.raises(EvaluationValidationError):
        grade(1, ["Bank A/c Dr 3,00,000 To Share Application"], student)
    with pytest.raises(EvaluationValidationError):
        grade(1, ["The student passed the correct entry"], student)
    assert grade(1, ["Bank A/c Dr 3,75,000"], student) == 1


def test_only_a_blanket_mcq_guess_loses_the_mark():
    assert grade(1, ["C"], "B ~ C. 19,000", allocation=1, mcq=True, multiple_answers=False) == 1
    assert grade(1, ["C"], "A B C D", allocation=1, mcq=True, multiple_answers=True) == 0
