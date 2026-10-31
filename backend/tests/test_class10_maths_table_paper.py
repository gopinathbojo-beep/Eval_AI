"""CBSE Class X Mathematics Basic (241) sample paper 2026-27, a typed PDF whose questions sit in a ruled table
"Q.No. | Question | Marks": the rows come from the table's cells (renderer.table_rows, paper.rows_from_pdf_tables),
not from the model's reading of the page, where a number cell centred beside a three-line question and the marks
column mixed into the text broke the paper into 53 questions worth 118 marks."""
from pathlib import Path

import pymupdf
import pytest

from app.cbse import formatter
from app.cbse.common import choices, standards
from app.cbse.common.paper import parse_question_paper_structure
from app.documents.renderer import page_text, table_figures, table_rows
from app.ocr.schemas import QuestionPageResult

PAPER = Path(__file__).parent / "fixtures" / "cbse_x_maths_basic_sqp_2026-27.pdf"


@pytest.fixture(scope="module")
def doc():
    pdf = pymupdf.open(PAPER)
    pages = [({"page_number": i + 1, "page_text": page_text(pdf[i]), "table_rows": table_rows(pdf[i]),
               "table_figures": table_figures(pdf[i])},
              QuestionPageResult(page_number=i + 1, questions=[])) for i in range(len(pdf))]
    with formatter.use("class10.subjects.maths_basic"):
        return parse_question_paper_structure(pages)


def _by(doc):
    return {q.normalized_number: q for q in doc.questions}


def test_thirty_eight_questions_eighty_marks_matching_the_design(doc):
    assert doc.from_pdf_table
    assert sorted({int(q.normalized_number.partition("(")[0]) for q in doc.questions}) == list(range(1, 39))
    assert doc.exam_max_marks == 80 and choices.max_total(doc.questions) == 80 and doc.exam_duration_minutes == 180
    assert standards.check(doc, standards.load("10", "Mathematics Basic")) == []


def test_marks_and_sections_come_from_their_cells(doc):
    by = _by(doc)
    assert [by[n].max_marks for n in ("1", "20", "22", "26", "32", "36")] == [1, 1, 2, 3, 5, 4]
    assert by["1"].section.startswith("SECTION – A") and by["38"].section.startswith("SECTION – E")
    # the marks column never leaks into the text ("... the second triangle 1 is")
    assert by["15"].question_text.startswith("The perimeter of two similar triangles")
    assert "triangle 1 is" not in by["15"].question_text


def test_either_or_questions_split_into_their_options(doc):
    for n in ("21", "25", "27", "30", "33", "35"):
        assert sorted(q.normalized_number for q in doc.questions if q.choice_group == n) == [f"{n}(a)", f"{n}(b)"]
    assert "parallelogram ABCD" in _by(doc)["25(a)"].question_text


def test_case_study_stays_one_question_with_its_choice_inside_part_iii(doc):
    by = _by(doc)
    for n in ("36", "37", "38"):
        assert n in by and by[n].choice_group is None and by[n].max_marks == 4
    text = by["37"].question_text
    assert "\n(ii) What is the number of trees" in text and "\n(iii) (B) Identify the class" in text
    assert "section of class IV" in text  # a sentence wrapped onto "section of ..." is no section heading


def test_visually_impaired_alternatives_are_dropped(doc):
    by = _by(doc)
    assert not any("visually" in (q.question_text or "").casefold() for q in doc.questions)
    assert "concentric circles" not in by["24"].question_text and "motion sensor" not in by["36"].question_text


def test_data_tables_inside_a_question_stay_tables(doc):
    by = _by(doc)
    assert ("distribution\n| Class | 0-5 | 5-10 | 10-15 | 15-20 | 20-25 |\n|---|---|---|---|---|---|\n"
            "| Frequency | 10 | 15 | 12 | 20 | 9 |\nThe lower limit") in by["10"].question_text
    assert "| Number of students | 5 | 10 | 20 | 12 | 3 |" in by["30(b)"].question_text
    assert "| Frequency | 8 | 6 | x | 11 | y |" in by["30(a)"].question_text


def test_figures_belong_to_their_question_or_option(doc):
    assert sorted(doc.figures) == ["24", "27(a)", "36", "37", "38"]
    assert [page for page, _ in doc.figures["27(a)"]] == [5]  # drawn on the page after its question starts
    assert len(doc.figures["37"]) == 1  # two pictures side by side are one figure


def test_the_printed_subject_settles_an_ambiguous_subject_name():
    head = page_text(pymupdf.open(PAPER)[0])
    assert standards.load("10", "Math")["subject"] == "Mathematics Standard"
    assert standards.load("10", "Math", paper_text=head)["subject"] == "Mathematics Basic"


SCHEME = Path(__file__).parent / "fixtures" / "cbse_x_maths_basic_ms_2026-27.pdf"


@pytest.fixture(scope="module")
def keys(doc):
    from app.cbse.common.keys import segment_answer_keys
    from app.documents.renderer import table_cell_lines
    from app.ocr.schemas import AnswerKeyPageResult
    pdf = pymupdf.open(SCHEME)
    pages = [({"page_number": i + 1, "page_text": page_text(pdf[i]), "table_rows": table_rows(pdf[i]),
               "table_cells": table_cell_lines(pdf[i])}, AnswerKeyPageResult(page_number=i + 1)) for i in range(len(pdf))]
    with formatter.use("class10.subjects.maths_basic"):
        return {k.normalized_number: k for k in segment_answer_keys(pages, doc.questions)}


def test_every_question_and_option_gets_its_key_from_the_scheme_table(doc, keys):
    assert sorted(keys) == sorted(q.normalized_number for q in doc.questions)
    assert all(keys[q.normalized_number].marks == q.max_marks for q in doc.questions)


def test_mcq_keys_carry_the_answer_column(keys):
    assert keys["1"].accepted_answers == ["D"] and keys["1"].criteria == ["1 Mark: Correct option (D)"]
    assert keys["20"].answer_text.startswith("Answer: (B)")


def test_step_marks_become_criteria_beside_their_steps(keys):
    assert keys["21(a)"].criteria == ["1 Mark: 520 = 2³ x 5 x 13; 468 = 2² x 3² x 13",
                                      "½ Mark: LCM = 2³ x 3² x 5 x 13 = 4680",
                                      "½ Mark: ∴ The required number is (4680 – 17). i.e., 4663"]
    assert [c.split(":")[0] for c in keys["38"].criteria] == ["1 Mark", "1 Mark", "2 Marks", "2 Marks"]
    assert keys["32"].criteria == ["2 Marks: Correct figure, Given, To prove and Construction", "3 Marks: Correct proof of theorem"]


def test_visually_impaired_solutions_are_no_part_of_a_key(keys):
    assert "concentric" not in keys["24"].answer_text and "OC" not in keys["24"].answer_text
    assert "rhombus" not in keys["27(a)"].answer_text
