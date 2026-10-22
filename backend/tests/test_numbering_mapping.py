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


def test_sub_label_with_parent_only_exam_needs_review():
    r = map_label("3(a)", exam("3"))
    assert r.status == NEEDS_REVIEW and r.candidates == ["id-3"]


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


def test_physics_topic_comma_formats():
    """Verify that student handwritten headers copying topics with commas/colons normalize correctly."""
    assert n("Q1, force & pressure :") == "1"
    assert n("Q2, Sound wave Terminology :") == "2"
    assert n("Q3, Friction Types :") == "3"
    assert n("Q4, Chemical Effects of Electric current.") == "4"
    assert n("Q5, optics & Reflection :") == "5"
    assert n("Q6, Electrostatics & Natural phenomena :") == "6"
    assert n("Q7, Acoustics & noise pollution :") == "7"

    # Verify they map directly to canonical exam questions
    qs = exam("1", "2", "3", "4", "5", "6", "7", "8", "9", "10")
    for raw, exp_num in [
        ("Q1, force & pressure :", "1"),
        ("Q2, Sound wave Terminology :", "2"),
        ("Q3, Friction Types :", "3"),
        ("Q4, Chemical Effects of Electric current.", "4"),
        ("Q5, optics & Reflection :", "5"),
        ("Q6, Electrostatics & Natural phenomena :", "6"),
        ("Q7, Acoustics & noise pollution :", "7"),
    ]:
        res = map_label(raw, qs)
        assert res.status == MAPPED
        assert res.question_id == f"id-{exp_num}"


def test_maths_angle_bracket_formats_and_skipped_questions():
    """Verify angle bracket format '1>', '6>', '10>' and non-consecutive / skipped questions."""
    assert n("1>") == "1"
    assert n("2>") == "2"
    assert n("3>") == "3"
    assert n("4>") == "4"
    assert n("6>") == "6"
    assert n("7>") == "7"
    assert n("9>") == "9"
    assert n("10>") == "10"

    # Student answered 1, 2, 3, 4, 6, 7, 9, 10 (skipping 5 and 8)
    qs = exam("1", "2", "3", "4", "5", "6", "7", "8", "9", "10")
    attempted = ["1>", "2>", "3>", "4>", "6>", "7>", "9>", "10>"]
    for raw in attempted:
        res = map_label(raw, qs)
        assert res.status == MAPPED
        assert res.question_id == f"id-{n(raw)}"


def test_subquestion_tokens_with_commas_and_brackets():
    from app.services.numbering import extract_subquestion_token
    assert extract_subquestion_token("a,") == "a"
    assert extract_subquestion_token("b,") == "b"
    assert extract_subquestion_token("c,") == "c"
    assert extract_subquestion_token("a>") == "a"
    assert extract_subquestion_token("b>") == "b"
    assert extract_subquestion_token("c>") == "c"
    assert extract_subquestion_token("a)") == "a"
    assert extract_subquestion_token("(b)") == "b"
    assert extract_subquestion_token("10") is None


def test_extract_label_from_text_prefix():
    from app.services.numbering import extract_label_from_text_prefix
    lbl, rest = extract_label_from_text_prefix("Q1, force & pressure :\nThe pressure exerted...")
    assert lbl == "1"
    assert "force & pressure" in rest

    lbl, rest = extract_label_from_text_prefix("1> [ (2/3)^-2 ... ]")
    assert lbl == "1"
    assert rest == "[ (2/3)^-2 ... ]"

    lbl, rest = extract_label_from_text_prefix("6> Given: principle = 1,25,000")
    assert lbl == "6"
    assert "Given: principle" in rest

    lbl, rest = extract_label_from_text_prefix("10> Principal = Rs 80,000")
    assert lbl == "10"
    assert "Principal" in rest

    # Genuine continuation line has no question prefix
    lbl, rest = extract_label_from_text_prefix("For coating iron with copper:\nElectrolyte : copper sulphate...")
    assert lbl is None
    assert "For coating iron" in rest



@dataclass
class SQ:
    id: str
    normalized_number: str | None
    section: str | None = None


def test_deep_subpart_falls_back_to_nearest_ancestor():
    r = map_label("3(a)(i)", exam("3(a)", "3(b)"))
    assert r.status == NEEDS_REVIEW and r.question_id == "id-3(a)" and r.normalized_number == "3(a)"


def test_sub_label_with_deeper_exam_parts_lists_descendants():
    r = map_label("3(a)", exam("3(a)(i)", "3(a)(ii)", "3(b)"))
    assert r.status == NEEDS_REVIEW and r.question_id is None
    assert r.candidates == ["id-3(a)(i)", "id-3(a)(ii)"]


def test_parent_label_with_single_subpart_is_proposed():
    r = map_label("3", exam("3(a)", "4"))
    assert r.status == NEEDS_REVIEW and r.question_id == "id-3(a)"


def test_bare_subpart_forward_prefers_sibling():
    qs = exam("1(a)", "1(b)", "2(a)", "2(b)")
    r = map_label("(b)", qs, prev_question_id="id-1(a)")
    assert r.status == NEEDS_REVIEW and r.question_id == "id-1(b)"


def test_bare_subpart_restart_prefers_next_parent():
    qs = exam("1(a)", "1(b)", "2(a)", "2(b)", "3(a)")
    r = map_label("(a)", qs, prev_question_id="id-1(b)")
    assert r.status == NEEDS_REVIEW and r.question_id == "id-2(a)"


def test_bare_subpart_matches_own_level_not_children():
    r = map_label("(a)", exam("1(a)", "1(a)(i)", "1(a)(ii)"))
    assert r.question_id == "id-1(a)" and r.candidates == ["id-1(a)"]


def test_bare_subpart_without_context_is_not_preselected():
    r = map_label("(a)", exam("1(a)", "2(a)"))
    assert r.status == NEEDS_REVIEW and r.question_id is None


def test_section_prefix_does_not_confuse_part_i_and_part_ii():
    qs = [SQ("p1", "1", "Part I"), SQ("p2", "1", "Part II")]
    assert map_label("Part II - 1", qs).question_id == "p2"
    assert map_label("Part I - 1", qs).question_id == "p1"


def test_section_ambiguity_uses_previous_section_as_hint_only():
    qs = [SQ("a1", "1", "Section A"), SQ("b1", "1", "Section B"), SQ("b2", "2", "Section B")]
    r = map_label("1", qs, prev_question_id="b2")
    assert r.status == NEEDS_REVIEW and r.question_id == "b1" and r.candidates[0] == "b1"
