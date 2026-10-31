"""The CBSE Class 10 Mathematics Basic marking scheme 2026-27 (typed PDF, ruled "Q.No | Solution | Marks" table): every
question and option of the paper gets its key with the paper's marks, each rubric adds up to the question's marks
(an "(iii)(A) OR (iii)(B)" choice counted once), steps of working name no false expected value, and each key's crop
is its own figure, never the figure of the "visually impaired" solution printed beside it."""
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
    with formatter.use("class10.subjects.maths_basic"):
        paper = parse_question_paper_structure(_pages("cbse_x_maths_basic_sqp_2026-27.pdf",
                                                      lambda page_number: QuestionPageResult(page_number=page_number, questions=[])))
        keys = segment_answer_keys(_pages("cbse_x_maths_basic_ms_2026-27.pdf", AnswerKeyPageResult), paper.questions)
    return {q.normalized_number: q for q in paper.questions}, {k.normalized_number: k for k in keys}


def test_every_question_maps_to_one_key_with_its_marks(mapped):
    questions, keys = mapped
    assert sorted(keys) == sorted(questions) and len(keys) == 44
    assert all(keys[n].marks == q.max_marks for n, q in questions.items())


def test_every_rubric_adds_up_and_names_no_false_values(mapped):
    questions, keys = mapped
    for n, k in keys.items():
        r = build_rubric(questions[n].question_text, k.answer_text, k.criteria, questions[n].max_marks)
        assert r.problems == [], (n, r.problems)
        # only an MCQ's option is an exact answer; equation labels "(1)", ratios "3:2" and "(324)" are no values
        assert all(p.kind == "meaning" for p in r.points) or k.accepted_answers, (n, [(p.kind, p.expected) for p in r.points])


def test_a_choice_inside_part_iii_counts_once(mapped):
    _, keys = mapped
    for n in ("36", "37", "38"):
        crit = keys[n].criteria
        assert any(": Either (A): " in c for c in crit) and any(": Or (B): " in c for c in crit), n
    r = build_rubric("", keys["37"].answer_text, keys["37"].criteria, 4)
    assert r.total == 4 and {p.alt for p in r.points if p.alt_group} == {"A", "B"}


def test_step_marks_quote_whole_steps(mapped):
    _, keys = mapped
    assert "1.5 Marks: = 6a² – πr² + 2 πr²" in "\n".join(keys["34"].criteria)  # "½+1" beside the step
    assert keys["31"].criteria[1] == "½ Mark: ATQ x + y = 9"  # the "-------(1)" label is not part of the step
    assert keys["25(b)"].criteria[1] == "1 Mark: ⇒x² − 2x + 1 + y² − 8y + 16 = x² + 2x + 1 + y² − 4y + 4"
    # stacked fractions are rebuilt, also at the start of a line and when longer than the line they sit on
    assert keys["22"].criteria[0] == "1 Mark: sinθ/cosθ = 4/3 ⇒ tan θ = 4/3"
    assert "√5 = (p − 2q)/3q" in keys["26"].answer_text
    assert keys["38"].criteria[1] == "1 Mark: (ii) P(Trader buys T-shirt) = (312+54)/400 = 366/400 or 183/200"
    assert not any(c.endswith(" OR") or ": OR " in c for k in keys.values() for c in k.criteria)


def test_each_key_crops_its_own_figure(mapped):
    _, keys = mapped
    assert sorted(n for n, k in keys.items() if k.figure) == ["10", "17", "22", "27(b)", "29", "34", "35(a)", "35(b)"]
    assert keys["24"].figure is None  # the concentric circles belong to the visually impaired solution, not to Q24
    b = keys["35(b)"].figure
    assert keys["35(b)"].page_number == 9 and 0 < b["x"] < 1 and 0 < b["width"] < 0.5 and b["y"] < 0.3
