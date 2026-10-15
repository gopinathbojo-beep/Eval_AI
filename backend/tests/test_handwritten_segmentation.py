"""Handwritten sheets: the model reads "1)" as "17" and returns several answers as one block."""
from app.ocr.schemas import StudentPageResult
from app.services.student_segmentation import segment_student_answers

KNOWN = [str(i) for i in range(1, 11)]


def _sheet(pages, known=KNOWN):
    return segment_student_answers(
        [({"page_number": i + 1}, StudentPageResult.model_validate({"answers": rows})) for i, rows in enumerate(pages)],
        known)


def A(label, text):
    return {"question_number": label, "answer_text": text}


def _nums(out):
    return [a.normalized_number for a in out]


def test_bracket_read_as_seven_is_repaired():
    out = _sheet([[A(17, "a) Mg + O2 -> MgO"), A("37", "calorific value")]])
    assert _nums(out) == ["1", "3"]


def test_real_question_17_is_kept():
    out = _sheet([[A("17", "text")]], known=[str(i) for i in range(1, 21)])
    assert _nums(out) == ["17"]


def test_merged_page_is_split_at_later_question_numbers():
    text = ("a) magnesium + oxygen -> magnesium oxide.\n2Mg + O2 -> 2MgO\nb) Fe + CuSO4 -> FeSO4 + Cu\n\n"
            "3) The calorific value of a fuel is the heat produced.\n\n"
            "4) A displacement reaction is ...\n\n"
            "6) Destructive distillation of coal ...\n-> coke\n-> coal tar.")
    out = _sheet([[A("17", text)]])
    assert _nums(out) == ["1", "3", "4", "6"]
    assert out[1].answer_text.startswith("The calorific value")
    assert "-> coal tar." in out[3].answer_text


def test_points_inside_an_answer_are_not_split():
    text = ("c) A candle flame has three zones:\n1) Outer zone\n2) Middle zone\n3) Inner zone\n"
            "10) Plastics are widely used because they are\n1) lightweight\n2) strong")
    out = _sheet([[A("7", text)]])
    assert _nums(out) == ["7", "10"]
    assert "3) Inner zone" in out[0].answer_text
    assert "2) strong" in out[1].answer_text


def test_running_list_above_question_number_stays_in_answer():
    out = _sheet([[A("2", "1) first point\n2) second point\n3) third point\n4) fourth point")]])
    assert _nums(out) == ["2"]


def test_answered_question_is_not_split_off_again():
    out = _sheet([[A("3", "x"), A("5", "y\n3) a point")]])
    assert _nums(out) == ["3", "5"]


def test_unlabelled_page_with_inline_labels():
    out = _sheet([[A(None, "1) first answer\n2) second answer")]])
    assert _nums(out) == ["1", "2"]


def test_without_exam_labels_nothing_is_split():
    out = _sheet([[A("1", "a\n3) b")]], known=None)
    assert _nums(out) == ["1"]


def test_bare_number_labels_with_answer_below():
    text = "1\nPhotosynthesis makes food in leaves.\n2\nx = 5\n25\n3\nThe heart pumps blood."
    out = _sheet([[A(None, text)]])
    assert _nums(out) == ["1", "2", "3"]
    assert "25" in out[-2].answer_text            # a bare result inside an answer is not a question label
    assert out[-1].answer_text == "The heart pumps blood."


def test_label_outside_the_exam_on_a_part_continues_the_answer():
    """"11" over "c) 5R Principles" in a 10 question exam is a misread mark on part (c) of question 10."""
    out = _sheet([[A("10", "a) Plastics are light"), A("11", "c) 5R Principles\nReduce -> Reuse")]])
    assert _nums(out) == ["10"] and "c) 5R Principles" in out[0].answer_text


def test_sub_parts_written_by_the_student_stay_in_one_answer():
    """"1", "1a", "1b", "1c" is one answer to question 1; starting straight at "1a" is too."""
    out = _sheet([[A("1", "stem"), A("1a", "part a"), A("1b", "part b"), A("1c)", "part c"), A("2", "two")]])
    assert _nums(out) == ["1", "2"]
    assert all(s in out[0].answer_text for s in ("1a part a", "1b part b", "1c) part c"))
    out = _sheet([[A("1a", "part a"), A("1b", "part b"), A("2", "two")]])
    assert _nums(out) == ["1", "2"] and out[0].answer_text.startswith("1a part a")
