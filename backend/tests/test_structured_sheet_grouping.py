from types import SimpleNamespace as NS

from app.formatter.common.answers import segment_student_answers, _split_swallowed_answers
from app.formatter.common.numbering import extract_label_from_text_prefix
from app.ocr.schemas import StudentPageResult


def question(n, text, marks=3):
    return NS(id=str(n), normalized_number=str(n), display_number=str(n), position=n,
              max_marks=marks, question_type="descriptive", question_text=text, structure={"root": n})


def page(n, *answers):
    return ({"page_number": n}, StudentPageResult.model_validate({"page_number": n, "answers": list(answers)}))


def answer(label, text, raw=None):
    return {"question_number": label, "raw_question_label": raw, "answer_text": text}


def test_known_whole_question_parts_do_not_move_to_a_different_question_by_content():
    qs = [question(2, "Find the integral of 1/x"), question(12, "Solve the differential equations")]
    grouped = segment_student_answers([page(1,
        answer("12", "12(a) soln:\nFirst equation", "12(a)"),
        answer("12", "12(b) soln:\nI.F = e^integral(1/x)", "12(b)"),
    )], qs)
    assert len(grouped) == 1 and grouped[0].normalized_number == "12"
    assert "12(a)" in grouped[0].answer_text and "12(b)" in grouped[0].answer_text


def test_unnumbered_fraction_working_keeps_parent_and_page_provenance():
    qs = [question(12, "Use AX = B to solve the matrix equations")]
    grouped = segment_student_answers([page(1, answer("12", "12) Soln:\nAX = B")),
        page(2, answer(None, "1/187 [ x y z ]\n= [100 200 300]"))], qs)
    assert [(a.page_number, a.normalized_number) for a in grouped] == [(1, "12"), (2, "12")]
    assert grouped[1].raw_question_number is None
    assert grouped[1].answer_text.startswith("1/187")
    assert grouped[1].mapping_note == "Source grouping: continuation of question 12"


def test_matrix_continuation_is_not_assigned_the_next_questions_number():
    qs = [question(20, "Find RS and SR and their inverse"), question(21, "Find the rate of change of area")]
    grouped = segment_student_answers([page(1, answer("20", "20) Soln:\nRS = [2 0; 2 2]")),
        page(2, answer("21", "Sol:\n(RS)^-1 = 1/4 adj RS"),
             answer("21", "21) Soln:\ndr/dt = 6 and dA/dt = 528"))], qs)
    assert [(a.page_number, a.normalized_number) for a in grouped] == [(1, "20"), (2, "20"), (2, "21")]


def test_graph_objective_and_nested_subparts_keep_their_existing_parent():
    qs = [question(4, "Write constraints 3x + 2y >= 10"),
          question(9, "Maximize Z = 70x + 20y subject to constraints"),
          question(15, "Find shortest distances between lines")]
    grouped = segment_student_answers([page(1, answer("9", "9) Soln:\nZ = 70x + 20y")),
        page(2, answer("4", "Corner points\n| Z = 70x + 20y |\n| 100 |")),
        page(3, answer("15", "15) Soln:\nThe lines are parallel")),
        page(4, answer("4", "(iii) (a)\nDistance d = 4", "(iii) (a)"))], qs)
    assert [a.normalized_number for a in grouped] == ["9", "9", "15", "15"]


def test_arithmetic_is_not_an_embedded_question_or_prefix():
    text = "Graph working and corner points\nx + y = 6\n10 - 4 = 6"
    qs = [question(9, "Graph working"), question(10, "Another question")]
    assert _split_swallowed_answers("9", text, qs) == [("9", text)]
    assert extract_label_from_text_prefix("10 - 4 = 6") == (None, "10 - 4 = 6")
    assert extract_label_from_text_prefix("1/187 [x y z]")[0] is None


def test_cancelled_question_heading_does_not_split_or_redirect_active_work():
    qs = [question(8, "State Ohm's law"), question(9, "A different question")]
    grouped = segment_student_answers([page(1,
        answer("8", "8) V = IR\n~~9) old cancelled attempt~~\nR = V/I"),
        answer("9", "~~cancelled whole answer~~"),
    )], qs)
    assert len(grouped) == 1 and grouped[0].normalized_number == "8"
    assert "cancelled" not in grouped[0].answer_text
    assert "R = V/I" in grouped[0].answer_text


def test_descriptive_subpart_with_guessed_next_number_keeps_supported_parent():
    qs = [question(42, "Explain rusting of an iron bridge near the sea versus a dry hilly region"),
          question(43, "Compare heat conduction through aluminium copper and iron rods")]
    grouped = segment_student_answers([page(1,
        answer("42", "A) First part of the answer"),
        answer("43", "Because the iron bridge located near the sea has salts unlike the dry hilly region"),
    ), page(2, answer("43", "43) Copper is a conductor of heat"))], qs)
    assert [(a.page_number, a.normalized_number) for a in grouped] == [(1, "42"), (2, "43")]
    assert "bridge" in grouped[0].answer_text


def test_literal_new_question_heading_is_not_overridden_by_shared_matrix_symbols():
    qs = [question(20, "Compute RS and SR"), question(21, "Use matrices for a different task")]
    grouped = segment_student_answers([page(1, answer("20", "20) Soln:\nRS = 2")),
        page(2, answer("21", "21) Soln:\nRS = 4"))], qs)
    assert [a.normalized_number for a in grouped] == ["20", "21"]
