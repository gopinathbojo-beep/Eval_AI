"""CBSE paper designs per standard (formatter/class10/, formatter/class12/, standards.py): each design adds up as the
board's sample paper does, an exam finds its own design, and a parsed paper is held against it."""
import pytest

from app.cbse.common import standards
from app.cbse.common.paper import DocumentStructure, StructuredQuestion

DESIGNS = [d for std in ("10", "12") for d in standards._designs(std)]


def _marks(spec):
    if "any" in spec:
        return sum(sorted(spec["parts"], reverse=True)[:spec["any"]])
    return sum(spec["parts"]) if "parts" in spec else spec["marks"]


@pytest.mark.parametrize("design", DESIGNS, ids=[d["subject"] for d in DESIGNS])
def test_design_adds_up(design):
    plan = standards.questions(design)
    assert sorted(plan) == list(range(1, len(plan) + 1))
    for section in design["sections"]:
        assert sum(q["marks"] for q in plan.values() if q["section"] == section["name"]) == section["marks"], section["name"]
    assert sum(s["marks"] for s in design["sections"]) == design["total_marks"]
    for n, spec in plan.items():
        assert _marks(spec) == spec["marks"], f"Q{n}"


def test_class10_has_the_nine_sample_papers():
    assert sorted(d["code"] for d in standards._designs("10")) == ["002", "041", "085", "086", "087", "101", "165", "184", "241"]


@pytest.mark.parametrize("cls, name, code, expected", [
    ("10-A", "Science", None, "086"),
    ("10-B", "Social Science", None, "087"),
    ("Class X", "English Communicative", None, "101"),
    ("10", "English", None, "184"),
    ("10-C", "Maths", None, "041"),
    ("10-C", "Maths Basic", None, "241"),
    ("10-A", "Hindi B", None, "085"),
    ("10-A", "Hindi", None, "002"),
    ("10-A", "Computer Applications", None, "165"),
    ("10-A", "Hindi", "085", "085"),
    ("XII-A", "Tamil", None, "106"),
])
def test_exam_finds_its_design(cls, name, code, expected):
    assert standards.load(standards.standard_of(cls), name, code)["code"] == expected


def test_no_design_for_unknown_standard_or_subject():
    assert standards.load(standards.standard_of("8-A"), "Science") is None
    assert standards.load("10", "Drawing") is None
    assert standards.standard_of("Grade") is None


def _q(n, marks=None, **kw):
    return StructuredQuestion(raw_question_number=n, normalized_number=n, display_number=n, question_text="...",
                              question_type=None, max_marks=marks, section=kw.pop("section", "A"), page_start=1,
                              page_end=1, bbox=None, ocr_confidence=None,
                              verification_status="NEEDS_REVIEW" if marks is None else "UNVERIFIED",
                              review_reason=None if marks is not None else standards.MARKS_NOT_FOUND, **kw)


def test_check_fills_flags_and_sets_any_n():
    design = standards.load("10", "English Language and Literature")
    doc = DocumentStructure(questions=[
        _q("1"), _q("2", 3),                                     # 1: marks missing; 2: wrong marks
        *[_q(f"3({r})", section="B") for r in ("i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii")],
        _q("4(a)", 5, choice_group="4"), _q("4(b)", choice_group="4"),
        _q("40", 2),
    ])
    problems = standards.check(doc, design)
    by = {q.normalized_number: q for q in doc.questions}
    assert by["1"].max_marks == 10 and by["1"].verification_status == "UNVERIFIED" and by["1"].review_reason is None
    assert by["2"].verification_status == "NEEDS_REVIEW" and "gives Q2 10 marks" in by["2"].review_reason
    assert {by[f"3({r})"].answer_any for r in ("i", "xii")} == {10} and by["3(i)"].section == "B / Q3"
    assert by["3(i)"].max_marks == 1
    assert by["4(b)"].max_marks == 5
    assert "no question 40" in by["40"].review_reason
    assert any(p.startswith("Q5 ") for p in problems)
    assert doc.exam_max_marks == 80 and doc.exam_duration_minutes == 180


def test_class12_tamil_sample_paper_matches_its_design():
    from app.services import paper_format
    from app.cbse.common.paper import parse_question_paper_structure
    from app.ocr.schemas import QuestionPageResult
    from tests.test_tamil_cbse_xii import PAGES, _pages
    with paper_format.use(paper_format.TAMIL):
        doc = parse_question_paper_structure(_pages(PAGES, QuestionPageResult))
    assert standards.check(doc, standards.load("12", "Tamil")) == []
    assert all(q.verification_status == "UNVERIFIED" for q in doc.questions)


@pytest.mark.parametrize("cls, subject, key", [
    ("10-A", "Science", "class10.subjects.science"),
    ("10-B", "Maths Basic", "class10.subjects.maths_basic"),
    ("XII-A", "Tamil", "class12.subjects.tamil"),
    ("8-A", "Tamil", "tamil"),        # no class 8 folder: the Tamil rules every class shares
    ("10-A", "Drawing", "common"),
])
def test_exam_takes_its_class_subject_folder(cls, subject, key):
    from types import SimpleNamespace
    from app.cbse import formatter
    exam = SimpleNamespace(school_class=SimpleNamespace(name=cls), subject=SimpleNamespace(name=subject, code=None))
    assert formatter.for_exam(exam) == key
    module = formatter.get(key)
    if key == "class12.subjects.tamil":  # the class folder starts from the shared Tamil rules
        assert module.uses_pdf_text() is False and module.parse_paper.__module__.endswith("subjects.tamil")
