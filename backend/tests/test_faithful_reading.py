"""Only the student's own ink is kept (faithful.py): another question's text the reading model copied into an answer is
cut, a line that matches the key is removed only when the model says it is not on the page, and a student copying
the coordinates of their own question keeps them."""
from types import SimpleNamespace as NS

from app.cbse.common.faithful import check_reading
from app.ocr.schemas import StudentAnswerItem, StudentPageResult

QUESTIONS = [
    NS(normalized_number="16", question_text="If in ∆ABC and ∆PQR , ∠B = ∠Q, ∠R = ∠C and AB = 2PQ, then the two "
                                             "triangles are (A) Congruent but not similar"),
    NS(normalized_number="25(a)", question_text="A. Points A (3,1), B (5, 1), C (a, b) and D (4, 3) are vertices of a "
                                                "parallelogram ABCD. Find the values of a and b."),
    NS(normalized_number="32", question_text="Prove that if a line is drawn parallel to one side of a triangle "
                                             "intersecting the other two sides in distinct points"),
    NS(normalized_number="33(a)", question_text="A. A train travels a distance of 360 km at a uniform speed."),
]
KEYS = {"33(a)": "ATQ, 360/x − 360/(x+5) = 1 On simplifying, we get x² + 5x−1800 = 0 x= 40, −45 Hence, x= 40"}


def _pages(*blocks):
    return [({"page_number": 1}, StudentPageResult(page_number=1, answers=[
        StudentAnswerItem(raw_question_label=label, answer_text=text) for label, text in blocks]))]


def _text(pages, i=0):
    return pages[0][1].answers[i].answer_text


def test_another_questions_text_copied_into_an_answer_is_cut():
    pages = _pages(("32>", "In ∆ABC and ∆PQR , ∠B = ∠Q, ∠R = ∠C and AB = 2PQ, then prove that AD/DB = AE/EC.\n"
                           "Area = 1/2 x AD x h"))
    notes = check_reading(pages, QUESTIONS, KEYS, None)
    assert "PQR" not in _text(pages) and "AD/DB = AE/EC" in _text(pages) and "Area = 1/2 x AD x h" in _text(pages)
    assert len(notes) == 1


def test_coordinates_copied_from_the_question_are_kept_even_under_a_misread_label():
    pages = _pages(("8>", "A(3,1), B(5,1), C(a,b), D(4,3)\nmidpoint of AC = midpoint of BD"))
    assert check_reading(pages, QUESTIONS, KEYS, None) == []
    assert _text(pages).startswith("A(3,1), B(5,1), C(a,b), D(4,3)")


def test_a_line_matching_the_key_goes_only_when_the_model_says_it_is_not_written():
    asked = []
    pages = _pages(("33>", "360/x - 360/(x+5) = 1\nx² + 5x - 1800 = 0\nHence, x = 40"))
    check_reading(pages, QUESTIONS, KEYS, lambda p, ls: asked.append(ls) or [True, False])
    assert asked == [["360/x - 360/(x+5) = 1", "x² + 5x - 1800 = 0"]]  # "Hence, x = 40" is too short to look copied
    assert _text(pages) == "360/x - 360/(x+5) = 1\nHence, x = 40"


def test_the_reading_stands_when_the_check_cannot_run():
    def broken(page, ls):
        raise TimeoutError("remote model busy")

    pages = _pages(("33>", "360/x - 360/(x+5) = 1\nx = 40"))
    notes = check_reading(pages, QUESTIONS, KEYS, broken)
    assert _text(pages) == "360/x - 360/(x+5) = 1\nx = 40" and "could not check" in notes[-1]


def test_a_line_written_twice_by_the_reader_is_put_to_the_model():
    asked = []
    pages = _pages(("7>", "= 1/6 x 22/7 x 100\n= 1/6 x 22/7 x 100\n= 1100/21"))
    check_reading(pages, QUESTIONS, KEYS, lambda p, ls: asked.append(ls) or [False] * len(ls))
    assert asked == [["= 1/6 x 22/7 x 100"]] and _text(pages) == "= 1/6 x 22/7 x 100\n= 1100/21"


def test_latex_the_reader_wrote_comes_back_in_the_notation_on_the_sheet():
    from app.cbse.common.faithful import plain_math
    assert plain_math(r"A = \(\frac{60}{360} \times \pi \times 10^2\) = \(\frac{1100}{21}\) (cm²)") == \
        "A = 60/360 × π × 10² = 1100/21 (cm²)"
    assert plain_math(r"\((\frac{3+a}{2}, \frac{1+b}{2})\)") == "((3+a)/2, (1+b)/2)"
    assert plain_math(r"x^{2} + 5x - 1800 = 0") == "x² + 5x - 1800 = 0"
    assert plain_math("360/x - 360/(x+5) = 1") == "360/x - 360/(x+5) = 1"  # plain text untouched
