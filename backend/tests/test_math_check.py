import pytest
import sympy

from app.ocr import prompts
from app.services.math_check import (analyze, equations_equivalent, match_values, ocr_warnings, parse_math,
                                     review_note, safe_analyze)


@pytest.mark.parametrize("text,expected", [
    ("(a + b)²", "(a + b)**2"),
    ("2πRh", "2*pi*R*h"),
    ("((2/3)⁻² × (3/4)⁻³) ÷ (8/9)⁻²", "1024/243"),
    (r"\frac{1024}{243}", "1024/243"),
    (r"$\sqrt{16} \times 2$", "8"),
    ("16x⁴ - 81y⁴", "16*x**4 - 81*y**4"),
    ("√2", "sqrt(2)"),
    ("V₁", "V_1"),
    ("½", "1/2"),
])
def test_parses_unicode_caret_and_latex(text, expected):
    got = parse_math(text)
    assert got is not None
    assert sympy.simplify(got - sympy.sympify(expected, locals={"V_1": sympy.Symbol("V_1")})) == 0


@pytest.mark.parametrize("text", [
    "__import__('os').system('x')", "lambda: 1", "2^(3^(4^5))", "10^1000", "Volume of metal",
    "x2", "R 2 - r 2", "(a+b)2", "sqrt", "1; 2", "a.b",
])
def test_rejects_unsafe_or_ambiguous_input(text):
    assert parse_math(text) is None


def test_equivalent_numeric_forms():
    e = parse_math
    assert match_values(e("1024/243"), "1024/243", e("(4/3)^5"), "(4/3)^5") == "exact"
    assert match_values(e("2156/3"), "2156/3", e("718.67"), "718.67") == "rounded"
    assert match_values(e("1024/243"), "1024/243", e("4.21"), "4.21") == "rounded"
    assert match_values(e("22/7*28*14"), "", e("3.14*28*14"), "") == "approx"
    assert match_values(e("1232"), "1232", e("1144"), "1144") is None


def test_symbolic_equivalence_and_rearranged_formulas():
    e = parse_math
    assert match_values(e("(a+b)^2"), "", e("a^2 + 2ab + b^2"), "") == "exact"
    assert match_values(e("(a+b)^2"), "", e("a^2 + b^2"), "") is None
    assert equations_equivalent((e("V"), e("π(R² - r²)h")), (e("V"), e("πh(R^2-r^2)")))
    assert equations_equivalent((e("V"), e("πr²h")), (e("V_cyl"), e("π h r^2")))
    assert equations_equivalent((e("x^2 + 1/x^2"), e("34")), (e("x^2 + 1/x^2 - 34"), e("0")))
    # Two different identities must not match just because both are always true.
    assert not equations_equivalent((e("(a+b)^2"), e("a^2+b^2+2ab")), (e("(a-b)^2"), e("a^2-2ab+b^2")))


KEY = """Q8. Hollow cylinder
• Formulas Used:
1. V = π(R² - r²)h
Given: Outer radius R = 8 cm, Inner radius r = 6 cm, Height h = 14 cm, π = 22/7
R² - r² = 8² - 6² = 64 - 36 = 28 cm²
V = 22/7 × 28 × 14 = 22 × 4 × 14 = 1232 cm³
Final Answer: 1232 cm³"""


def test_correct_student_answer_is_recognised():
    stu = "V = πh(R² - r²)\n= 22/7 × (64 - 36) × 14\n= 1232 cm3\n∴ V = 1232 cm³"
    rep = analyze(KEY, stu)
    assert rep.final_status == "match"
    assert ("V = π(R² - r²)h", True) in rep.formulas
    assert rep.student_slips == []
    section = rep.prompt_section()
    assert "EQUIVALENT to the key" in section and "AUTOMATIC MATHS CHECK" in section


def test_wrong_answer_slip_and_lost_exponent_are_reported():
    stu = "R 2 - r 2 = 64 - 36 = 26\nV = 22/7 × 26 × 14 = 1144 cm3"
    rep = analyze(KEY, stu)
    assert rep.final_status == "mismatch"
    assert any("64 - 36 = 26" in s for s in rep.student_slips)
    assert any("lost exponent" in w for w in rep.ocr_warnings)
    assert "NOT equivalent" in rep.prompt_section()


def test_alternatives_and_accepted_answers():
    key = "2^4/3^1 × 2^6/3^4 = 2^{10}/3^5\nFinal Answer: (4/3)^5 or 1024/243"
    assert analyze(key, "Ans: 1024/243").final_status == "match"
    assert analyze(key, "= 4.214").final_status == "rounded"
    assert analyze("Answer: 0.5", "1/2").final_status == "match"
    assert analyze("Final Answer: 7", "x = 3.5", accepted=["3.5"]).final_status == "match"


def test_descriptive_answers_are_left_alone():
    assert safe_analyze("India became independent in 1947 after the freedom struggle.", "In 1947.") is None
    assert safe_analyze("Photosynthesis makes food using sunlight.", "Plants make food.") is None


def test_key_arithmetic_errors_are_flagged():
    rep = analyze("64 - 36 = 26\nFinal Answer: 26", "26")
    assert rep.key_slips


def test_ocr_warnings():
    assert ocr_warnings("(x + 1/x) 2 = 36")
    assert ocr_warnings("x2 + y2 = 25")
    assert not ocr_warnings("Step 2: H2O is water")


def test_review_note_flags_contradictions():
    good = analyze(KEY, "∴ V = 1232 cm³")
    note, cap = review_note(good, 0, 3)
    assert note and "equivalent to the key" in note and cap == 0.4
    assert review_note(good, 3, 3) == (None, None)
    bad = analyze(KEY, "V = 1144")
    note, cap = review_note(bad, 3, 3)
    assert note and "does not match" in note and cap == 0.4
    assert review_note(None, 0, 3) == (None, None)


def test_evaluation_prompt_includes_maths_facts():
    p = prompts.evaluation_prompt("1", "q", "k", [], [], [], 2, "s", maths_facts="AUTOMATIC MATHS CHECK\n- x")
    assert "AUTOMATIC MATHS CHECK" in p and p.index("AUTOMATIC") < p.index("HOW TO MARK")
    assert "AUTOMATIC" not in prompts.evaluation_prompt("1", "q", "k", [], [], [], 2, "s")
