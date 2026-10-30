"""English paper layouts (Half Yearly English, Class 10): question groups ("Q 1-3:"), a Part B whose numbering restarts
at Q1, an OR with no label after it, and part labels printed without their question number."""
from types import SimpleNamespace

from app.ocr.schemas import AnswerKeyItem, AnswerKeyPageResult, QuestionItem, QuestionPageResult
from app.cbse.formatter.common import choices
from app.cbse.formatter.common.paper import parse_question_paper_structure
from app.cbse.formatter.common.keys import segment_answer_keys
from app.cbse.formatter.common.numbering import normalize_question_number, part_labels

PASSAGE = ("Almost all creatures care for their young ones. Many animals play with their babies and show their love by "
           "touching and hugging them. Birds also teach their fledglings how to go about in the world as adults.")


def _q(label, text, marks=None, section=None):
    return QuestionItem(raw_question_number=label, question_text=text, marks=marks, section=section)


def _parse(*pages):
    return parse_question_paper_structure(
        [({"page_number": i}, QuestionPageResult(page_number=i, questions=list(p))) for i, p in enumerate(pages, 1)])


def _paper():
    # As InternVL returned it: the group header, its passage and questions 1-3 in one block; Part B restarting at Q1
    return _parse(
        [_q(None, f"Q 1-3: Read the following passage carefully and choose the correct option-\n{PASSAGE}\n"
                  "(1) Which of the following is not called nature's engineers?\nA-weaver birds\nB-tailor birds\nC-goats\nD-ants\n"
                  "(2) How do animals show their love with their young ones?\nA-singing\nB-by touching\nC-enjoying\nD-dancing\n"
                  "(3) Which word means 'baby bird' in the following?\nA-birds\nB-fledglings\nC-animals\nD-ants", 1),
         _q(None, "(4) He is worried .................. examination.\nA-on\nB-in\nC-of\nD-about", 1)],
        [_q("Q1", f"Read the following passage and answer the questions that follow: {PASSAGE}", 2, "PART B Reading"),
         _q(None, "A- What is important for teachers?\nB- Which word means 'tolerable' in the passage?", 2, "PART B Reading"),
         _q("Q2", "Write a letter to Father requesting money for books. OR\nWrite an application to the librarian.", 4, "Writing"),
         _q("b)", "Change the following into passive voice. 1. The children sang the national anthem.", 4, "Grammar"),
         _q("b)", "Change the following into active voice. 1. Were the cards distributed by Rahul?", 2, "Grammar")])


def test_part_b_restarting_at_q1_is_b1():
    doc = _paper()
    nums = [q.display_number for q in doc.questions]
    assert nums == ["1", "2", "3", "4", "B1", "B2(a)", "B2(b)", "B3"]
    by = {q.display_number: q for q in doc.questions}
    assert "B- Which word means 'tolerable'" in by["B1"].question_text      # lettered sub-questions stay in B1
    assert by["B2(a)"].choice_group == "B2" and by["B2(b)"].question_text == "Write an application to the librarian."
    # Grammar prints only "b)" labels: one inferred question, both parts, marked for review
    assert "(b) Change the following into active voice." in by["B3"].question_text
    assert by["B3"].verification_status == "NEEDS_REVIEW" and by["B3"].section == "Grammar"


def test_group_header_shares_its_passage_and_is_no_question():
    by = {q.display_number: q for q in _paper().questions}
    assert all(by[n].question_text.startswith("[Reading Passage Context]\nAlmost all creatures") for n in ("1", "2", "3"))
    assert "Which word means 'baby bird'" in by["3"].question_text and by["3"].question_text.endswith("D-ants")
    assert "baby bird" not in by["2"].question_text                          # each question gets only its own text
    assert by["4"].question_text.startswith("He is worried")                # "examination" in a question is no header


def test_numbered_steps_inside_a_question_do_not_start_a_part():
    doc = _parse([_q("Q9(a)", "A sonar wave returns after 2.4 seconds. Calculate the depth.", 2, "SECTION C"),
                  _q("(b)", "A string completes 1200 oscillations in 15 seconds. Calculate its:", 3, "SECTION C"),
                  _q("1.", "Frequency in Hertz.", 1.5, "SECTION C"), _q("2.", "Time period in seconds.", 1.5, "SECTION C")])
    assert not any(q.display_number.startswith("C") for q in doc.questions)


def test_part_numbers_normalize():
    assert [normalize_question_number(x) for x in ("B1", "B-5(a)", "Part B 3", "B-are present", "b1")] == \
        ["B1", "B5(a)", "B3", None, None]


QS = [SimpleNamespace(normalized_number=n, question_type=t) for n, t in
      [("1", "mcq"), ("2", "mcq"), ("B1", "descriptive"), ("B2", "descriptive")]]


def _ans(label, text="C"):
    return SimpleNamespace(raw_question_number=label, answer_text=text, status="UNMAPPED")


def test_student_part_b_answers_by_repeat_mark_and_length():
    # Part A then Part B on one sheet: the second "1" starts Part B
    assert part_labels([_ans("1"), _ans("2"), _ans("1", "Teachers need a sound personality."), _ans("2", "Dear Father")], QS) == \
        [None, None, "B1", "B2"]
    # "Part B" written at the top of an answer
    assert part_labels([_ans("2"), _ans("1", "PART B  The most important thing is personality.")], QS) == [None, "B1"]
    # no Part A answers on this sheet: a written answer under an MCQ's number belongs to Part B
    long = "For teachers the most important thing is a sound and well developed personality, not preaching."
    assert part_labels([_ans("1", long), _ans("2", "Respected Father, I need money for books and hostel dues.")], QS) == \
        ["B1", "B2"]


def test_answer_key_part_b_does_not_merge_into_part_a():
    canonical = [SimpleNamespace(display_number=n, normalized_number=n, question_type=t, choice_group=None, max_marks=m)
                 for n, t, m in [("1", "mcq", 1), ("2", "mcq", 1), ("B1", "descriptive", 7), ("B2", "descriptive", 4)]]
    page = AnswerKeyPageResult(page_number=1, answers=[
        AnswerKeyItem(question_number="1", answer_text="C - goats", marks=1),
        AnswerKeyItem(question_number="2", answer_text="B - by touching and hugging", marks=1),
        AnswerKeyItem(question_number="Q1", answer_text="A sound, well-developed personality.", marks=7),
        AnswerKeyItem(question_number="Q2", answer_text="Respected Father, I need money for books.", marks=4)])
    keys = {k.normalized_number: k.answer_text for k in segment_answer_keys([({"page_number": 1}, page)], canonical)}
    assert keys == {"1": "C - goats", "2": "B - by touching and hugging", "B1": "A sound, well-developed personality.",
                    "B2": "Respected Father, I need money for books."}


def test_counted_total_with_parts():
    doc = _paper()
    assert choices.max_total(doc.questions) == 1 + 1 + 1 + 1 + 2 + 4 + 6     # B2 either/or once; B3 = 4 + 2
