"""Regression tests for OCR reading, cross-page grouping and mapping accuracy."""
from app.ocr.parser import salvage_truncated_object
from app.ocr.schemas import AnswerKeyPageResult, EvaluationResult, QuestionItem, QuestionPageResult, StudentPageResult
from app.services.doc_structure import parse_question_paper_structure
from app.services.key_segmentation import extract_from_full_pdf_text, parse_criteria_marks
from app.services.numbering import normalize_question_number
from app.services.ocr_recovery import find_recovery_candidates
from app.services.student_segmentation import segment_student_answers


def _sheet(pages, known=None):
    return segment_student_answers(
        [({"page_number": i + 1}, StudentPageResult.model_validate({"answers": rows})) for i, rows in enumerate(pages)],
        known)


def A(label, text):
    return {"question_number": label, "answer_text": text}


# ---- model output that used to throw away a whole page ----

def test_lenient_fields_do_not_drop_the_page():
    r = QuestionPageResult.model_validate({"questions": [
        {"raw_question_number": 1, "question_text": None, "marks": "2 marks", "confidence": "high", "bbox": [1, 2, 30, 40]},
        {"question_number": "2", "text": "Explain", "marks": "1+1", "bbox": {"x": 1}},
    ]})
    assert [q.marks for q in r.questions] == [2.0, 2.0]
    assert r.questions[0].question_text == "" and r.questions[0].confidence == 0.9
    assert r.questions[1].raw_question_number == "2" and r.questions[1].question_text == "Explain"
    assert r.questions[1].bbox is None


def test_list_root_and_aliases():
    k = AnswerKeyPageResult.model_validate([{"question_number": "3(a)", "answer": "glucose", "criteria": [{"text": "1 Mark: x"}]}])
    assert k.answers[0].answer_text == "glucose" and k.answers[0].criteria == ["1 Mark: x"]
    s = StudentPageResult.model_validate({"page": "2", "items": [{"label": "Q2", "text": ["l1", "l2"], "ocr_confidence": "85%"}]})
    assert s.page_number == 2 and s.answers[0].answer_text == "l1\nl2" and s.answers[0].ocr_confidence == 0.85


def test_written_label_wins_over_model_correction():
    s = StudentPageResult.model_validate({"answers": [
        {"question_number": "Q1", "raw_question_label": "Q17", "answer_text": "x"}]})
    assert s.answers[0].question_number == "Q17"


def test_eval_marks_as_fraction():
    assert EvaluationResult.model_validate({"marks_awarded": "2/5"}).marks_awarded == 2.0


def test_truncated_json_keeps_finished_items():
    raw = '{"page_number": 1, "answers": [{"question_number": "1", "answer_text": "abc"}, {"question_number": "2", "answer_text": "de'
    assert salvage_truncated_object(raw) == {"page_number": 1, "answers": [{"question_number": "1", "answer_text": "abc"}]}
    assert salvage_truncated_object("not json") is None


# ---- labels ----

def test_handwritten_label_forms():
    cases = {"1a)": "1(a)", "1 a)": "1(a)", "3(a": "3(a)", "Ql2": "12", "1O": "10", "Q.l0": "10",
             "1(a)i)": "1(a)(i)", "I": "1", "(b)": None, "1.5 marks": None}
    for raw, want in cases.items():
        assert normalize_question_number(raw) == want, raw


def test_digit_recovery_generalised_but_never_10_to_1():
    class Q:
        def __init__(s, i, n, p):
            s.id, s.normalized_number, s.position, s.question_text = i, n, p, ""
    qs = [Q("a", "1", 1), Q("b", "4(a)", 2), Q("c", "4(b)", 3)]
    assert find_recovery_candidates("14(b)", None, qs, 3, 3)[0].normalized_number == "4(b)"
    assert find_recovery_candidates("9(a)", None, qs, 2, 3)[0].normalized_number == "4(a)"
    assert not any(c.normalized_number == "1" for c in find_recovery_candidates("10", None, qs, 1, 3))


# ---- answers split across pages ----

def test_student_answer_continues_across_page_break():
    res = _sheet([[A("Q1", "osmosis"), A("Q2", "diffusion starts")], [A(None, "and continues here"), A("Q3", "three")]])
    assert [(r.normalized_number, r.answer_text) for r in res] == \
        [("1", "osmosis"), ("2", "diffusion starts\nand continues here"), ("3", "three")]
    assert res[1].page_number == 1


def test_repeated_label_on_next_page_is_one_answer_but_same_page_is_duplicate():
    res = _sheet([[A("Q3", "part one")], [A("Q3", "part two"), A("Q3 contd", "part three")]])
    assert len(res) == 1 and res[0].answer_text == "part one\npart two\npart three"
    res = _sheet([[A("1", "first try"), A("Q1", "second try")]])
    assert len(res) == 2


def test_parts_and_points():
    res = _sheet([[A("Q7(a)", "benefits:"), A("1)", "co2"), A("2)", "soil"), A("(b)", "second"), A("c)", "third")]])
    # one answer for question 7, its parts and points inside it
    assert [r.normalized_number for r in res] == ["7"]
    assert all(s in res[0].answer_text for s in ("Q7(a) benefits:", "1) co2", "2) soil", "(b) second", "c) third"))


def test_known_labels_split_points_from_out_of_order_questions():
    res = _sheet([[A("1.", "one"), A("5.", "five"), A("1)", "p1"), A("2)", "p2"), A("3.", "three")]],
                 ["1", "2", "3", "4", "5"])
    assert [r.normalized_number for r in res] == ["1", "5", "3"]
    assert "1) p1" in res[1].answer_text and "2) p2" in res[1].answer_text


def test_question_continues_at_top_of_next_page():
    pages = [
        ({"page_number": 1}, QuestionPageResult(questions=[
            QuestionItem(raw_question_number="Q1", question_text="Define osmosis.", marks=2),
            QuestionItem(raw_question_number="Q2", question_text="Correct the errors in the passage below.", marks=4)])),
        ({"page_number": 2}, QuestionPageResult(questions=[
            QuestionItem(raw_question_number=None, question_text="Page 2"),
            QuestionItem(raw_question_number=None, question_text="The boy go to school every day."),
            QuestionItem(raw_question_number="Q3", question_text="Explain diffusion.", marks=3)])),
    ]
    doc = parse_question_paper_structure(pages)
    assert [q.display_number for q in doc.questions] == ["1", "2", "3"]
    assert "The boy go to school" in doc.questions[1].question_text and doc.questions[1].page_end == 2


# ---- answer key ----

def test_key_marks_never_guessed_from_mark_each():
    assert parse_criteria_marks(["1 mark each for any three points"]) is None
    assert parse_criteria_marks(["1 Mark: a", "1.5 Marks: b"]) == 2.5


def test_key_text_layer_handles_subquestions_and_decimals():
    text = "1. Define osmosis\nAnswer: water moves\nMarking Scheme:\n1.5 Marks: movement\n1.5 Marks: membrane\n" \
           "3(a) What is x\nx is y\n3 (b) z\nzz\n10. ten\ntenans\n"
    ans, crit = extract_from_full_pdf_text(text, "1")
    assert ans == "water moves" and crit == ["1.5 Marks: movement", "1.5 Marks: membrane"]
    assert extract_from_full_pdf_text(text, "3(a)")[0] == "x is y"
    assert extract_from_full_pdf_text(text, "3(b)")[0] == "zz"
    assert extract_from_full_pdf_text(text, "10")[0] == "tenans"
