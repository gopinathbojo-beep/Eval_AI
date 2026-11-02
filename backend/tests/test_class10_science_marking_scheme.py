"""The CBSE Class 10 Science sample paper and marking scheme 2026-27 (typed PDFs, ruled tables). The scheme is laid
out unlike the Mathematics one: an either/or answer is one row split by "OR" (or by option heads "A." / "B."), step
marks sit at the ends of lines ("(1)", "(0.5+0.5)") with only the total in the marks column, an MCQ's answer is its
option ("C. R"), and the visually impaired solution sits inside the row. Every question and option still gets its
key with the paper's marks, a rubric that adds up, and its own figures."""
from pathlib import Path

import pymupdf
import pytest

from app.cbse import formatter
from app.cbse.common.keys import segment_answer_keys
from app.cbse.common.paper import parse_question_paper_structure
from app.cbse.common.rubric import build_rubric
from app.documents.renderer import page_text, table_cell_lines, table_figures, table_rows
from app.ocr.schemas import AnswerKeyPageResult, QuestionPageResult

FIXTURES = Path(__file__).parent / "fixtures"


def _pages(name: str, result):
    pdf = pymupdf.open(FIXTURES / name)
    return [({"page_number": i + 1, "page_text": page_text(p), "table_rows": table_rows(p), "table_cells": table_cell_lines(p),
              "table_figures": table_figures(p)}, result(page_number=i + 1)) for i, p in enumerate(pdf)]


@pytest.fixture(scope="module")
def mapped():
    with formatter.use("class10.subjects.science"):
        paper = parse_question_paper_structure(_pages("cbse_x_science_sqp_2026-27.pdf",
                                                      lambda page_number: QuestionPageResult(page_number=page_number, questions=[])))
        keys = segment_answer_keys(_pages("cbse_x_science_ms_2026-27.pdf", AnswerKeyPageResult), paper.questions)
    return paper, {q.normalized_number: q for q in paper.questions}, {k.normalized_number: k for k in keys}


def test_paper_rows_marks_and_figures(mapped):
    paper, questions, _ = mapped
    assert paper.from_pdf_table and paper.exam_max_marks == 80 and len(questions) == 45
    assert sorted(paper.figures) == ["14", "16", "2", "21", "22", "28", "35", "37", "38"]
    # a question row the table's ruling split in two keeps its number, text and marks
    assert questions["10"].question_text.startswith("A. Due to narrowing of the bile duct") and questions["10"].max_marks == 2
    # justified prose is no table
    assert "|" not in questions["12"].question_text and "|" not in questions["9"].question_text


def test_assertion_reason_instruction_opens_the_questions_it_is_for(mapped):
    _, questions, _ = mapped
    for n in ("8", "9", "24", "32"):
        assert questions[n].question_text.startswith("The following") and "\nAssertion" in questions[n].question_text, n
    for n in ("7", "23", "31"):
        assert "Assertion (A) and Reason (R)" not in questions[n].question_text, n


def test_every_question_maps_to_a_key_whose_rubric_adds_up(mapped):
    _, questions, keys = mapped
    assert sorted(keys) == sorted(questions)
    for n, q in questions.items():
        k = keys[n]
        assert k.marks == q.max_marks, n
        r = build_rubric(q.question_text, k.answer_text, k.criteria, q.max_marks)
        assert r.problems == [], (n, r.problems)


def test_mcq_answers_are_their_options(mapped):
    _, _, keys = mapped
    assert [keys[n].accepted_answers for n in ("1", "2", "7", "17", "31")] == [["A"], ["C"], ["C"], ["C"], ["C"]]
    assert "visually" not in keys["2"].answer_text.casefold()


def test_one_row_either_or_answers_split_into_their_options(mapped):
    _, _, keys = mapped
    assert keys["16(b)"].answer_text.startswith("B.") and "A depicts inhalation" in keys["16(b)"].answer_text
    assert keys["39(a)"].answer_text.startswith("A.") and "Dispersion" not in keys["39(a)"].answer_text
    assert "visually" not in keys["39(b)"].answer_text.casefold()


def test_step_marks_at_line_ends_and_sub_part_choices(mapped):
    _, _, keys = mapped
    assert [c.split(":")[0] for c in keys["16(b)"].criteria] == ["1 Mark", "½ Mark", "½ Mark", "½ Mark", "½ Mark", "2 Marks"]
    crit = keys["28"].criteria  # A (1), B (1), then C OR D (2), and not the visually impaired version after it
    assert len(crit) == 4 and ": Either (C): " in crit[2] and ": Or (D): " in crit[3]


def test_each_key_has_only_its_own_figures(mapped):
    _, _, keys = mapped
    assert sorted(n for n, k in keys.items() if k.figures) == ["26(a)", "36", "37", "39(a)", "39(b)"]
    assert len(keys["39(a)"].figures) == 1 and len(keys["39(b)"].figures) == 1  # eye diagram vs prism
