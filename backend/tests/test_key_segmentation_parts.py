"""Answer keys: parts labelled only "(b)" and marking schemes printed in the key text."""
from app.ocr.schemas import AnswerKeyPageResult
from app.services.key_segmentation import segment_answer_keys


def _key(pages):
    return segment_answer_keys(
        [({"page_number": i + 1}, AnswerKeyPageResult.model_validate({"answers": rows})) for i, rows in enumerate(pages)])


def test_bare_part_label_joins_the_answer_before_it():
    keys = _key([[{"question_number": "Q9", "answer_text": "(a) V = 3028.67 m3", "marks": 10}],
                 [{"question_number": "(b)", "answer_text": "Area = 968 m2", "marks": 4,
                   "criteria": ["2.5 Marks: volume", "1.5 Marks: area", "1 Mark: cost"]},
                  {"question_number": "Q10", "answer_text": "CI = 12400", "marks": 5}]])
    assert [(k.normalized_number, k.marks) for k in keys] == [("9", 5.0), ("10", 5.0)]
    assert "(b) Area = 968 m2" in keys[0].answer_text


def test_printed_marking_scheme_wins_over_copied_criteria():
    """The model copied Q9's points into Q10's criteria; the scheme printed under Q10 is what counts."""
    keys = _key([[{"question_number": "Q10", "answer_text": "CI1 = 12400\nCI2 = 12610", "marks": 10,
                   "criteria": ["2.5 Marks: volume", "1.5 Marks: area", "1 Mark: cost"]}],
                 [{"question_number": None, "answer_text": "Difference = Rs. 210\n\nMarking Scheme:\n"
                   "- 2 Marks: Annual compounding.\n- 2 Marks: Half-yearly compounding.\n- 1 Mark: Difference.",
                   "criteria": ["2 Marks: Annual compounding.", "2 Marks: Half-yearly compounding.", "1 Mark: Difference."]}]])
    assert len(keys) == 1 and keys[0].marks == 5.0
    assert keys[0].criteria == ["2 Marks: Annual compounding.", "2 Marks: Half-yearly compounding.", "1 Mark: Difference."]


def test_upper_case_roman_label_is_a_question_not_a_part():
    keys = _key([[{"question_number": "I.", "answer_text": "Newton's first law"},
                  {"question_number": "II.", "answer_text": "Inertia"}]])
    assert len(keys) == 2
