from types import SimpleNamespace as NS
import pytest
from app.formatter.common.answers import segment_student_answers
from app.ocr.schemas import StudentPageResult, StudentAnswerItem
from app.services.mapping_service import _repair_misread_labels
from app.formatter.common.numbering import extract_label_from_text_prefix


def question(n, text, marks=3):
    return NS(id=str(n), normalized_number=str(n), display_number=str(n), position=n,
              question_type="mcq" if marks == 1 else "descriptive", max_marks=marks,
              structure={"root": n}, question_text=text)


def page(n, *blocks):
    return ({"page_number": n}, StudentPageResult.model_validate({"answers": list(blocks)}))


@pytest.mark.parametrize("first,second", [(4, 6), (18, 23), (51, 55)])
def test_separate_mcq_working_never_moves_to_previous_number(first, second):
    qs = [question(first, "Find a matrix entry", 1), question(second, "Evaluate the matrix product", 1)]
    def answer(pos, qid, text):
        return NS(position=pos, page_number=1, exam_question_id=str(qid), normalized_number=str(qid),
                  raw_question_number=f"Q{qid}", answer_text=text, status="MAPPED", mapping_note=None, mapping_candidates=[])
    rows = [answer(1, first, "D. 4"), answer(2, second, "B. -1"),
            answer(3, first, "a = 1/3; b = 2"), answer(4, second, "Matrix product\n" + "4 - 2x = 0\n" * 12)]
    _repair_misread_labels(rows, qs)
    assert rows[-1].exam_question_id == str(second)
    assert rows[-1].status == "MAPPED"


def test_repeated_mcq_number_is_not_automatically_advanced():
    qs = [question(8, "First question", 1), question(9, "Second question", 1)]
    rows = [NS(position=p, page_number=1, exam_question_id="8", normalized_number="8", raw_question_number="Q8",
               answer_text="A. first" if p == 1 else "Additional working", status="MAPPED", mapping_note=None,
               mapping_candidates=[]) for p in [1, 2]]
    _repair_misread_labels(rows, qs)
    assert [a.exam_question_id for a in rows] == ["8", "8"]


def test_main_option_and_rough_column_group_once_per_question_and_page():
    qs = [question(8, "First question", 1), question(9, "Second question", 1)]
    rows = segment_student_answers([page(1,
        {"question_number": "8", "answer_text": "A. result"},
        {"question_number": "9", "answer_text": "B. next"},
        {"question_number": "8", "answer_text": "Separate rough working"},
    )], qs)
    assert len(rows) == 2
    assert rows[0].answer_text == "A. result\nSeparate rough working"
    assert rows[1].answer_text == "B. next"


@pytest.mark.parametrize("line,graph", [(22, 23), (47, 49)])
def test_inserted_unnumbered_graph_belongs_to_equations_not_previous_page(line, graph):
    qs = [question(line, "Find a line passing through (1,2,3)"),
          question(graph, "Maximize Z=70x+20y with x+y<=9, 3x>=y, y>=1")]
    rows = segment_student_answers([
        page(1, {"question_number": str(line), "answer_text": "Line working"}),
        page(2, {"question_number": None, "answer_text": "[Diagram: lines x+y=9, 3x=y, y=1 and a shaded region]"}),
        page(3, {"question_number": str(line), "answer_text": "Cartesian line equation"},
                {"question_number": str(graph), "answer_text": f"{graph}) Maximize Z=70x+20y"}),
    ], qs)
    assert [(a.page_number, a.normalized_number) for a in rows] == [(1,str(line)), (2,str(graph)), (3,str(line)), (3,str(graph))]


def test_exact_same_source_block_is_deduplicated_but_separate_written_repetition_is_kept():
    block = {"question_number": "8", "answer_text": "x=2", "bbox": {"x":10,"y":20,"width":80,"height":30}}
    other = {**block, "bbox": {**block['bbox'], "y":100}}
    result = StudentPageResult(answers=[block, block, other])
    assert len(result.answers) == 2
    assert len(StudentPageResult(answers=[{"answer_text":"x=2"}, {"answer_text":"x=2"}]).answers) == 2


def test_matrix_dimensions_and_explicit_continuation_provenance_are_preserved():
    matrix = "[10 5 10 10; 5 7 5 5; 10 8 5 10; 10 5 10 10]"
    item = StudentAnswerItem(answer_text=matrix, label_origin="continuation", question_number="42")
    assert item.raw_question_label is None and item.answer_text == matrix
    qs = [question(42, "Compute a matrix")]
    rows = segment_student_answers([page(1, {"question_number":"42", "answer_text":"42) Matrix working"}),
        page(2, item.model_dump())], qs)
    assert len(rows) == 2 and rows[1].normalized_number == "42"
    assert matrix in rows[1].answer_text


def test_cartesian_answer_resumes_after_inserted_graph_without_stealing_graph():
    qs = [question(17, "Find a line through (1,2,3) on x-1=(y+2)/3=4-z"),
          question(18, "Maximize Z=80x+10y subject to x+y<=8, 3x>=y, y>=1")]
    rows = segment_student_answers([
        page(1, {"question_number":"17", "answer_text":"17) Foot of perpendicular working"}),
        page(2, {"question_number":None, "answer_text":"[Diagram: x+y=8, 3x=y, y=1]"}),
        page(3, {"label_origin":"continuation", "answer_text":"(x-5)/3=(y-2)/4=(z-1)/2"},
                {"question_number":"18", "answer_text":"18) Maximize Z=80x+10y"}),
    ], qs)
    assert [(a.page_number,a.normalized_number) for a in rows] == [(1,"17"),(2,"18"),(3,"17"),(3,"18")]


@pytest.mark.parametrize("text", ["0 = -cos(x+y)", "1/x = y", "8 = -sin(t)"])
def test_numeric_formula_start_never_becomes_question_label(text):
    assert extract_label_from_text_prefix(text) == (None,text)
