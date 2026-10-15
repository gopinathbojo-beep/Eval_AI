from dataclasses import dataclass
import pytest
from app.services.numbering import normalize_question_number as n
from app.services.mapping import map_label, flag_duplicates, MAPPED, NEEDS_REVIEW, UNMAPPED


@dataclass
class Q:
    id: str
    normalized_number: str | None


def exam(*labels):
    return [Q(f"id-{l}", n(l)) for l in labels]


@pytest.mark.parametrize("raw,exp", [
    ("Q1", "1"), ("Question 1", "1"), ("1.", "1"), ("1)", "1"), ("q.1", "1"), ("Q. 1", "1"),
    ("3 (a)", "3(a)"), ("3-a", "3(a)"), ("3a", "3(a)"), ("3(a)", "3(a)"), ("Q3(a)", "3(a)"),
    ("3.a", "3(a)"), ("3(A)", "3(a)"), ("4(i)", "4(i)"), ("4 (ii)", "4(ii)"),
    ("3(a)(i)", "3(a)(i)"), ("3a(i)", "3(a)(i)"), ("01", "1"), ("10", "10"), ("Ans 2", "2"),
    ("Question 12)", "12"), ("3(a).", "3(a)"),
    (None, None), ("", None), ("unknown", None), ("null", None), ("abc", None),
    ("3 explain", None), ("[UNCLEAR]", None), ("3(zzzzz)", None),
])
def test_normalize(raw, exp):
    assert n(raw) == exp


def test_distinctness():
    assert n("1") != n("10")
    assert n("2") != n("12")
    assert n("3(a)") != n("3(b)")
    assert n("3(a)") != n("3(a)(i)")


def test_case1_all_exact():
    qs = exam("1", "2", "3", "10")
    for l in ["1", "2", "3", "10"]:
        r = map_label(l, qs)
        assert r.status == MAPPED and r.question_id == f"id-{l}"


def test_case2_1_never_maps_to_10():
    r = map_label("1", exam("1", "10"))
    assert r.status == MAPPED and r.question_id == "id-1"


def test_case3_10_maps_to_10():
    r = map_label("10", exam("1", "10"))
    assert r.question_id == "id-10"


def test_case4_3a():
    r = map_label("3(a)", exam("3(a)", "3(b)"))
    assert r.status == MAPPED and r.question_id == "id-3(a)"


def test_case5_bare_3_needs_review():
    r = map_label("3", exam("3(a)", "3(b)"))
    assert r.status == NEEDS_REVIEW and r.question_id is None
    assert set(r.candidates) == {"id-3(a)", "id-3(b)"}


def test_case6_7_prefix_forms():
    assert map_label("Q1", exam("1.")).status == MAPPED
    assert map_label("Question 1", exam("1")).status == MAPPED


def test_case8_unknown_unmapped():
    r = map_label("unknown", exam("1", "2"))
    assert r.status == UNMAPPED and r.question_id is None
    assert map_label(None, exam("1")).status == UNMAPPED


def test_q10_never_to_1():
    r = map_label("Q10", exam("1"))
    assert r.question_id is None and r.status == UNMAPPED


def test_3a_vs_3b_never():
    r = map_label("3(a)", exam("3(b)"))
    assert r.question_id is None


def test_sub_label_maps_to_question_kept_whole():
    # question 3 is stored as one question with its parts inside, so "3(a)" is part of it
    r = map_label("3(a)", exam("3"))
    assert r.status == MAPPED and r.question_id == "id-3"


def test_sub_label_with_parent_and_other_parts_needs_review():
    r = map_label("3(a)", exam("3", "3(b)"))
    assert r.status == NEEDS_REVIEW and r.question_id is None


def test_duplicate_exam_numbers_review():
    qs = [Q("a", "1"), Q("b", "1")]
    r = map_label("1", qs)
    assert r.status == NEEDS_REVIEW and r.question_id is None


def test_low_confidence_exact_goes_to_review():
    r = map_label("1", exam("1"), ocr_confidence=0.1, min_confidence=0.4)
    assert r.status == NEEDS_REVIEW


def test_case9_duplicate_mapping_detected():
    @dataclass
    class A:
        exam_question_id: str | None
    rows = [A("q3"), A("q3"), A("q4"), A(None)]
    assert flag_duplicates(rows) == {"q3"}
