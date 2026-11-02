"""A handwritten Class 10 Mathematics Basic sheet written out of order (Dhananjay's, 9 pages): every answer lands
under the number the student wrote, even where content looks like a neighbour (7 vs 6, 36 vs 34) or the paper prints
the question only as parts (21 -> 21(a)), and a block continuing an earlier page's last answer (Q22 ending on page 4
after Section C, Q27(b) ending on page 6 after Q32) joins that answer, not the one before it."""
from types import SimpleNamespace as NS

import pytest

from app.cbse import formatter
from app.cbse.common.answers import segment_student_answers
from app.cbse.common.keys import segment_answer_keys
from app.cbse.common.paper import parse_question_paper_structure
from app.ocr.schemas import AnswerKeyPageResult, QuestionPageResult, StudentAnswerItem, StudentPageResult
from tests.test_class10_maths_marking_scheme import _pages

A = lambda l, t: StudentAnswerItem(raw_question_label=l, answer_text=t)
pages = {
 1: [A("1", "D. 1650"), A("2", "C. 14"), A("3", "C. p≠4"), A("5", "a=c"), A("6", "p+9q"), A("7", "B. 10th term"),
     A("8", "D"), A("9", "C"), A("10", "A"), A("11", "C. 6cm"), A("12", "A. 26"), A("13", "9m"), A("14", "-2"),
     A("15", "10cm"), A("16", "B"), A("17", "100°"), A("18", "160cm²"), A("19", "A"), A("20", "B")],
 2: [A("21", "(a) 520 = 2³x5x13  468 = 2²x3²x13  LCM = 2³x3²x5x13 = 4680. Let it be x, x+17=4680, x=4680-17=4663"),
     A("(b)", "25ⁿ=(5²)ⁿ=5²ⁿ. A number ending in zero must be divisible by 10. 10=2x5. But 25ⁿ contains only the prime factor 5 & no factor 2. 25ⁿ is not divisible by 10. So 25ⁿ will never end with digit zero."),
     A("22", "if 3sinθ = 4cosθ, sinθ+cos²θ-1=? given 3sinθ=4cosθ, tanθ=4/3, using the sinθ=4/5, cosθ=3/5")],
 3: [A("26", "To prove: 2+3√5 is irrational. given: √5 is irrational. lets assume 2+3√5 is rational. 2+3√5=p/q, 3√5=p/q-2, 3√5=(p-2q)/q, √5=(p-2q)/3q. Since p&q are integers, the RHS is rational. Hence 2+3√5 is irrational."),
     A("27", "(b) To prove: ∠APB = 2∠OAB. given: PA & PB are tangents to a circle with O as center. ∴ ∠OAP=∠OBP=90°. ∠AOB+∠APB+90°+90°=360°, ∠AOB+∠APB=150, ∠APB=180°-∠AOB")],
 4: [A(None, "= 4/5 + (3/5)² - 1 = 4/5 + 9/25 - 1 = (20+9-25)/25 = 4/25"),
     A("25", "(a) A(3,1), B(5,1), C(a,b), D(4,3). midpoint of AC = midpoint of BD. ((3+a)/2, (1+b)/2) = ((5+4)/2, (1+3)/2). (3+a)/2=9/2, 3+a=9, a=6. (1+b)/2=2, 1+b=4, b=3")],
 5: [A("32", "Given: In triangle ABC, DE is parallel to BC, where D lies on AB & E lies on AC. To prove: AD/DB = AE/EC. Area = 1/2 x AD x h. Therefore, Area(ΔADE)/Area(ΔBDE) = AD/DB (1). Similarly, area(ΔADE)/area(ΔBDE) = AE/EC (2). Since DE ∥ BC, area(ΔBDE) = area(ΔCDE). from (1)&(2) AD/DB = AE/EC")],
 6: [A(None, "In triangle AOB, OA=OB ∴ ∠OAB=∠OBA. using angle sum property, 2∠OAB+∠AOB=180°, 2∠OAB=180°-∠AOB. Hence, ∠APB=2∠OAB. Hence Proved."),
     A("28", "Determine the ratio and find the value of y. A(-3,-1), B(-8,9), P(-6,y). let P divide AB. -6=(-8m-3n)/(m+n). -6m-6n=-8m-3n. 2m=2n. m:n=3:2. y=(3(9)+2(-1))/(3+2) = (27-2)/5, y=5")],
 7: [A("36", "outer radius = 10cm, inner radius = 4cm, central angle = 60°. (i) area of sector: A=θ/360 x πr² = 60/360 x 22/7 x 10² = 1/6 x 22/7 x 100 = 1100/21 cm². (ii) A = θ/360 x π(R²-r²) = 1/6 x 22/7 (10²-4²) = 1/6 x 22/7 (100-16) = 1/6 x 22/7 x 84 = 44cm²")],
 8: [A("33", "(A) Distance = 360 km. Speed of train = x km/h. Time taken = 360/x. if speed increased by 5 km/h 360/(x+5). 360/x - 360/(x+5) = 1. (360(x+5)-360x)/(x(x+5)) = 1. 1800/(x(x+5)) = 1. x(x+5)=1800. x²+5x-1800=0. x(x+45)-40(x+45)=0. (x-40)(x+45)=0. x=40 (or) x=-45. ∴ x = 40 km/h")],
 9: [A("35", "(A) first angle of depression = 30°, second = 60°. Time interval = 12 min. height of the drone = h. first position, tan30° = h/x, 1/√3 = h/x, x = √3h (1). Second position, tan60° = h/y, √3 = h/y, y = h/√3 (2)")],
}


@pytest.fixture(scope="module")
def mapped():
    with formatter.use("class10.subjects.maths_basic"):
        paper = parse_question_paper_structure(_pages("cbse_x_maths_basic_sqp_2026-27.pdf",
                                                      lambda page_number: QuestionPageResult(page_number=page_number, questions=[])))
        keys = {k.normalized_number: k.answer_text
                for k in segment_answer_keys(_pages("cbse_x_maths_basic_ms_2026-27.pdf", AnswerKeyPageResult), paper.questions)}
        qs = [NS(id=q.normalized_number, normalized_number=q.normalized_number, question_text=q.question_text,
                 max_marks=q.max_marks, raw_question_number=q.normalized_number, parent_question_id=None, question_type=None,
                 choice_group=q.choice_group)
              for q in paper.questions]
        res = segment_student_answers([({"page_number": n}, StudentPageResult(page_number=n, answers=a))
                                       for n, a in pages.items()], qs, keys)
    return {s.normalized_number: s.answer_text for s in res}


def test_each_answer_lands_under_the_number_written(mapped):
    assert sorted(mapped, key=lambda n: (int(n.split("(")[0]), n)) == [
        "1", "2", "3", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20",
        "21(a)", "21(b)", "22", "25(a)", "26", "27(b)", "28", "32", "33(a)", "35(a)", "36"]
    assert mapped["7"] == "B. 10th term" and "sector" in mapped["36"] and "4663" in mapped["21(a)"]


def test_a_continuation_joins_the_earlier_answer_it_finishes(mapped):
    assert mapped["22"].endswith("= 4/25") and mapped["10"] == "A"
    assert mapped["27(b)"].endswith("Hence Proved.") and "Hence Proved" not in mapped["32"]


# What the 4B model returned for the same sheet on 2026-11-01: "25>" read "8>", "32>" replaced by "Q16" with Q16's
# opening copied in, "36>" read "24)", and "35> (A)" with its "(A)" lost
MODEL_READ = {
    1: [A(f"{n}>", t) for n, t in [(1, "D. 1650"), (2, "C. 14"), (3, "C. p+4"), (5, "a/c"), (6, "p+9q"), (7, "B. 10^4 km"),
                                   (8, "D"), (9, "C"), (10, "A"), (11, "C. 6 cm"), (12, "A. 26"), (13, "9m"),
                                   (14, "-2"), (15, "10cm"), (16, "B"), (17, "100°"), (18, "160cm²"), (19, "A"),
                                   (20, "B")]],
    2: pages[2], 3: pages[3],
    4: [A("8>", "(a) A(3,1), B(5,1), C(a,b), D(4,3)\nmidpoint of AC = midpoint of BD\n((3+a)/2, (1+b)/2) = ((5+4)/2, "
                "(1+4)/2)\n(3+a)/2 = 9/2\n1+b = 4\na=6\nb=3")],
    5: [A("Q16", "In ∆ABC and ∆PQR , ∠B = ∠Q, ∠R = ∠C and AB = 2PQ,\nthen prove that AD/DB = AE/EC.\n\nTo prove: \n"
                 "AD/DB = AE/EC\n\nArea = 1/2 x AD x h\n\nTherefore,\narea (ΔADE) / area (ΔBDE) = AD/DB = ...\n"
                 "Similarly, area (ΔADE) / area (ΔABE) = AE/EC = ...\nSince DE is parallel to BC\n"
                 "∴ area (ΔBDE) = area (ΔCDE)\nFrom ①x②\nAD/DB = AE/EC")],
    6: [pages[6][1]],
    7: [A("24)", "Area of sector: A = (60/360) x π x 10²\n= (1/6) x (22/7) x 100\n= (1/6) x (2200/7)\n= 1100/21 cm²\n"
                 "Area of shaded region: A = (1/360) x π x (R² - r²)\n= (1/6) x (22/7) x (10² - 4²)\n"
                 "= (1/6) x (22/7) x (100 - 16)\n= (1/6) x (22/7) x 84\n= 1 x (22/7) x 14\n= 44 cm²")],
    8: [A("33(a) (2 m): A. Find the smallest number", pages[8][0].answer_text)],
    9: [A("35>", "first angle of depression = 30°\nsecond ... = 60°\ntime interval = 12 min.\ndistance of the tower = h.\n"
                 "First position,\ntan 30° = h/x\n1/√3 = h/x\nx = √3 h ...(A)\nSecond position,\ntan 60° = h/y\n"
                 "√3 = h/y\ny = h/√3 ...(B)")],
}


def test_labels_the_model_misread_are_placed_by_the_key():
    from app.cbse.common.faithful import check_reading
    with formatter.use("class10.subjects.maths_basic"):
        paper = parse_question_paper_structure(_pages("cbse_x_maths_basic_sqp_2026-27.pdf",
                                                      lambda page_number: QuestionPageResult(page_number=page_number, questions=[])))
        keys = {k.normalized_number: k.answer_text
                for k in segment_answer_keys(_pages("cbse_x_maths_basic_ms_2026-27.pdf", AnswerKeyPageResult), paper.questions)}
        qs = [NS(id=q.normalized_number, normalized_number=q.normalized_number, question_text=q.question_text,
                 max_marks=q.max_marks, raw_question_number=q.normalized_number, parent_question_id=None, question_type=None,
                 choice_group=q.choice_group)
              for q in paper.questions]
        results = [({"page_number": n}, StudentPageResult(page_number=n, answers=[a.model_copy() for a in blocks]))
                   for n, blocks in MODEL_READ.items()]
        check_reading(results, qs, keys, None)
        got = {s.page_number: s for s in segment_student_answers(results, qs, keys) if s.page_number > 3}
    assert {p: s.normalized_number for p, s in got.items()} == {4: "25(a)", 5: "32", 6: "28", 7: "36", 8: "33(a)", 9: "35(a)"}
    assert "PQR" not in got[5].answer_text  # Q16's opening the model copied in


# The same pages as read on a later run: page 4 labelled "21(a)" (a two-mark question answered on page 2) and page 7
# labelled "24" with the working in LaTeX
LATEX_P7 = (r"A = \(\frac{60}{360} \times \pi \times 10^2\) = \(\frac{1}{6} \times \frac{22}{7} \times 100\) = "
            r"\(\frac{1100}{21}\) (cm²)" "\n"
            r"A = \(\frac{1}{360} \times \pi \times (R^2 - r^2)\) = \(\frac{1}{6} \times \frac{22}{7} \times (10^2 - 4^2)\)"
            "\n" r"= \(\frac{1}{6} \times \frac{22}{7} \times 84\) = \(4\) cm²")


@pytest.fixture(scope="module")
def paper_and_keys():
    with formatter.use("class10.subjects.maths_basic"):
        paper = parse_question_paper_structure(_pages("cbse_x_maths_basic_sqp_2026-27.pdf",
                                                      lambda page_number: QuestionPageResult(page_number=page_number, questions=[])))
        keys = {k.normalized_number: k.answer_text
                for k in segment_answer_keys(_pages("cbse_x_maths_basic_ms_2026-27.pdf", AnswerKeyPageResult), paper.questions)}
    qs = [NS(id=q.normalized_number, normalized_number=q.normalized_number, question_text=q.question_text,
             max_marks=q.max_marks, raw_question_number=q.normalized_number, parent_question_id=None, question_type=None,
             choice_group=q.choice_group, section=None) for q in paper.questions]
    return qs, keys


def test_a_long_answer_under_a_question_answered_earlier_goes_where_its_content_points(paper_and_keys):
    qs, keys = paper_and_keys
    read = {**MODEL_READ, 4: [A("21(a)", MODEL_READ[4][0].answer_text)], 7: [A("24", LATEX_P7)]}
    results = [({"page_number": n}, StudentPageResult(page_number=n, answers=[a.model_copy() for a in blocks]))
               for n, blocks in read.items()]
    from app.cbse.common.faithful import check_reading
    check_reading(results, qs, keys, None)  # LaTeX back to plain working first, as the pipeline does
    with formatter.use("class10.subjects.maths_basic"):
        got = {s.page_number: s.normalized_number for s in segment_student_answers(results, qs, keys) if s.page_number > 3}
    assert got[4] == "25(a)" and got[7] == "36"


def test_the_mapping_service_keeps_a_label_whose_key_fits_best(paper_and_keys):
    from app.cbse.common.mapping import MAPPED, map_label
    qs, keys = paper_and_keys
    res = map_label("Q36", qs, 0.9, 0.5, answer_text=LATEX_P7, keys=keys)
    assert res.status == MAPPED and res.normalized_number == "36"  # not Q11 on "10", "cm", "6"


def test_mcq_numbers_over_other_answers_go_where_the_content_points(paper_and_keys):
    """A second scan of the sheet: Q1 read "17>" (1650 is Q1's option D), the end of Q22 at the top of page 3 read
    "4>" (an MCQ number over working), and the Q32 proof read "16)" (Q16 answered on page 1)."""
    from app.cbse.common.faithful import check_reading
    qs, keys = paper_and_keys
    read = {1: [A("17>", "D. 1650")] + MODEL_READ[1][1:],
            2: pages[2],
            3: [A("4>", "= 4/5 + (3/5)² - 1\n= 4/5 + 9/25 - 1\n= (20+9-25)/25\n= 4/25"), MODEL_READ[4][0]],
            4: pages[3],
            5: [A("16)", MODEL_READ[5][0].answer_text.split("\n", 2)[2])],
            6: [pages[6][1]]}
    results = [({"page_number": n}, StudentPageResult(page_number=n, answers=[a.model_copy() for a in blocks]))
               for n, blocks in read.items()]
    check_reading(results, qs, keys, None)
    with formatter.use("class10.subjects.maths_basic"):
        got = segment_student_answers(results, qs, keys)
    numbers = [s.normalized_number for s in got]
    assert numbers.count("17") == 1 and "1" in numbers and "4" not in numbers
    by_number = {s.normalized_number: s for s in got}
    assert by_number["1"].answer_text.endswith("1650") and by_number["22"].answer_text.endswith("= 4/25")
    assert by_number["32"].page_number == 5 and "29" not in numbers
