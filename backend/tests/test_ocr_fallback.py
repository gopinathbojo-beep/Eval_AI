import pytest
from pathlib import Path
from backend.app.ocr.internvl import fallback_parse_plain_text
from backend.app.ocr.schemas import StudentPageResult, QuestionPageResult, AnswerKeyPageResult


def test_fallback_parse_student_answers():
    raw_md = """
    Here is what I read from the student sheet:
    
    1> Force is a push or pull on an object. Atmospheric pressure is force per unit area.
    
    2> (a) She said that she was reading a book.
    (b) The toaster connected the microphone.
    
    3> The cricket went to the ant's house because it was starving in the winter.
    """
    res = fallback_parse_plain_text(raw_md, StudentPageResult)
    assert res is not None
    assert len(res.answers) == 3
    assert res.answers[0].raw_question_label == "1"
    assert "Force is a push or pull" in res.answers[0].answer_text
    assert res.answers[1].raw_question_label == "2"
    assert "She said that she was reading" in res.answers[1].answer_text
    assert res.answers[2].raw_question_label == "3"
    assert "The cricket went to the ant's house" in res.answers[2].answer_text


def test_fallback_parse_question_paper():
    raw_md = """
    Q1. Define atmospheric pressure and state its SI unit. (2 marks)
    
    Q2. Differentiate between conductors and insulators. Give two examples of each. (3 marks)
    
    Q3. Solve: 2x + 5 = 15. (2 marks)
    """
    res = fallback_parse_plain_text(raw_md, QuestionPageResult)
    assert res is not None
    assert len(res.questions) == 3
    assert res.questions[0].raw_question_number == "Q1"
    assert "Define atmospheric pressure" in res.questions[0].question_text
    assert res.questions[1].raw_question_number == "Q2"
    assert res.questions[2].raw_question_number == "Q3"


def test_fallback_parse_answer_key():
    raw_md = """
    # Answer Key
    
    Question 1:
    Atmospheric pressure is the force exerted by the weight of air per unit area.
    SI unit: Pascal (Pa).
    
    Question 2:
    Conductors allow electricity to pass (e.g. Copper, Iron).
    Insulators do not allow electricity to pass (e.g. Rubber, Plastic).
    """
    res = fallback_parse_plain_text(raw_md, AnswerKeyPageResult)
    assert res is not None
    assert len(res.answers) == 2
    assert res.answers[0].question_number == "Q1"
    assert "Atmospheric pressure" in res.answers[0].answer_text
    assert res.answers[1].question_number == "Q2"
