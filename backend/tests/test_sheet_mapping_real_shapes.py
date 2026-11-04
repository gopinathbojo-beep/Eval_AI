"""Shapes from a real CBSE Science answer sheet (synthetic text): every written number maps, the shared
assertion-reason options belong to the assertion-reason questions, an empty page reading is retried, and evidence
the model copied with a garbled symbol still counts."""
from types import SimpleNamespace as NS

import pytest

from app.cbse.build import share_assertion_reason_options
from app.cbse.extraction import Fragment, Page
from app.cbse.grading import _quoted
from app.formatter.common.answers import segment_student_answers
from app.ocr.schemas import StudentAnswerItem, StudentPageResult
from app.services import pipeline


class Q:
    def __init__(self, num, text, kind="mcq"):
        self.id, self.normalized_number, self.display_number = f"id-{num}", num, num
        self.position, self.question_text, self.question_type, self.max_marks = int(num), text, kind, 1.0


AR = ("\nA. Both A and R are true, and R is the correct explanation of A.\nB. Both A and R are true, and R is not the "
      "correct explanation of A.\nC. A is true but R is false.\nD. A is false but R is true.")
QUESTIONS = [
    Q("7", "A fish feeds on insect larvae. What is the trophic level of the fish?\nA. Producer\nB. Primary consumer\n"
           "C. Secondary consumer\nD. Tertiary consumer" + AR),  # the shared options misread onto the MCQ before them
    Q("8", "Assertion (A): Breathing rate in aquatic organisms is faster.\nReason (R): Water holds less oxygen.", "ar"),
    Q("9", "Assertion (A): 1% of energy is transferred.\nReason (R): 10% of food is available.", "ar"),
    Q("18", "Chlor-alkali products\nI Hydrogen\nII Chlorine\nIII Sodium hydroxide\nIV Bleach\nA. I, II\nB. II, IV"),
    Q("19", "Soap and detergent in hard water\nA. scum\nB. foam"),
    Q("20", "Which salts contain water of crystallisation: (i) Plaster of Paris (ii) Washing soda (iii) Baking soda "
            "(iv) Gypsum\nA. (i), (ii) and (iii)\nD. (i), (ii) and (iv)"),
]


def _page(number, *answers):
    return ({"page_number": number}, StudentPageResult(page_number=number, answers=[
        StudentAnswerItem(question_number=label, answer_text=text) for label, text in answers]))


def test_written_numbers_beat_option_wording_shared_with_other_questions():
    pages = [_page(1, ("Q7", "C) Secondary consumer."), ("Q8", "D) A is false but R is true.")),
             _page(2, ("Q9", "D) A is false but R is true")),
             _page(3, ("Q18", "A. I, II and III"), ("Q19", "C. Soap forms scum"), ("Q20", "D. (i), (ii) and (iv)"))]
    got = [(a.normalized_number, a.answer_text) for a in segment_student_answers(pages, canonical_questions=QUESTIONS)]
    assert [n for n, _ in got] == ["7", "8", "9", "18", "19", "20"]
    assert got[1][1] == "D) A is false but R is true."  # Q9's answer is not merged into Q8


def test_page_top_words_finishing_the_last_answer_go_back_to_it():
    qs = [Q("13", "How do muscles move at the cellular level?", "short"),
          Q("14", "Study the food chain. A. energy at producer level B. more trophic levels", "short")]
    pages = [_page(3, ("Q13", "* Muscles change the shape of their\n* They also change the arrangement of")),
             _page(4, ("Q14", "cells to move.\n\nA) The energy at the producer level is 10000 kJ"))]
    got = segment_student_answers(pages, canonical_questions=qs)
    assert got[0].answer_text.endswith("cells to move.")
    assert got[1].answer_text.startswith("A) The energy")


def test_shared_assertion_reason_options_move_to_the_assertion_reason_questions():
    p2 = ({"page_number": 2, "page_text": "Answer by selecting the option given below:\n"
                                          "A. Both A and R are true, and R is the correct explanation of A.\n"
                                          "B. Both A and R are true, and R is not the correct explanation of A."},
          Page(page_number=2, fragments=[Fragment(root=7, text="Trophic level of fish?\nA. Producer\nB. Consumer",
                                                  question_type="mcq")]))
    p3 = ({"page_number": 3, "page_text": "C. A is true but R is false.\nD. A is false but R is true."},
          Page(page_number=3, fragments=[
              Fragment(root=7, text="C. A is true but R is false.\nD. A is false but R is true.", continues=True,
                       question_type="assertion_reason"),
              Fragment(root=8, text="Assertion (A): Breathing is faster.\nReason (R): Less oxygen.",
                       question_type="assertion_reason")]))
    share_assertion_reason_options([p2, p3])
    assert [f.root for f in p3[1].fragments] == [8]  # the piece holding only the shared options is gone
    assert p2[1].fragments[0].text == "Trophic level of fish?\nA. Producer\nB. Consumer"
    eight = p3[1].fragments[0].text
    assert "R is the correct explanation of A." in eight and eight.endswith("D. A is false but R is true.")


def test_paper_without_assertion_reason_questions_is_untouched():
    page = ({"page_number": 1, "page_text": ""}, Page(page_number=1, fragments=[
        Fragment(root=1, text="Which is a metal?\nA. Iron\nB. Sulphur", question_type="mcq")]))
    share_assertion_reason_options([page])
    assert page[1].fragments[0].text == "Which is a metal?\nA. Iron\nB. Sulphur"


def test_evidence_copied_with_a_garbled_symbol_still_counts_but_changed_numbers_do_not():
    student = "1 Ω , 3/2 Ω , 5 Ω → series\nI = 2A ∴ Total current is 2A"
    assert _quoted("1Ω , 3/2 ≤ 5 ≤ series", student)
    assert _quoted("I = 2A ≤ Total current is 2A", student)
    assert not _quoted("I = 7A ≤ Total current is 7A", student)


@pytest.mark.parametrize("second, expected", [(["Q28", "A. Silver is the best conductor"], 1), (None, 0)])
def test_an_answer_page_read_empty_is_read_again(monkeypatch, second, expected):
    calls = []

    def fake(system, user, schema, img):
        calls.append(user)
        answers = [StudentAnswerItem(question_number=second[0], answer_text=second[1])] if second and len(calls) > 1 else []
        return NS(parsed=StudentPageResult(page_number=10, answers=answers), raw="{}", attempts=1)

    monkeypatch.setattr(pipeline, "chat_structured", fake)
    first = fake("s", "read", StudentPageResult, "img")
    got = pipeline._reread_empty_page(first, "s", "read", StudentPageResult, "img")
    assert len(calls) == 2 and pipeline.EMPTY_PAGE_HINT in calls[1]
    assert len(got.parsed.answers) == expected
