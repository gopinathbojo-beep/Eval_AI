"""Answer sheets scanned sideways on ruled notebook paper, with the school's details box on every continuation
sheet, copied section headings, and roman part numbers that read as question numbers (II as "11", B as "13").
Nothing here depends on particular question numbers."""
import random
from types import SimpleNamespace as S

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.documents.orientation import upright_turns
from app.formatter.common.answers import segment_student_answers
from app.ocr.schemas import StudentAnswerItem, StudentPageResult

_WORDS = "the blood moves from the atrium to the gills where gases exchange carbon dioxide and oxygen".split()


def _written_page(seed: int) -> Image.Image:
    """Lines of writing from a shared left margin, ragged on the right, like a page of answers."""
    rnd = random.Random(seed)
    img = Image.new("RGB", (850, 1200), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=30)
    for y in range(60, 1120, 52):
        draw.text((70, y), " ".join(rnd.choice(_WORDS) for _ in range(rnd.randint(2, 9))), fill="black", font=font)
    return img


@pytest.fixture(scope="module")
def pages():
    return [_written_page(i) for i in range(4)]


def test_upright_pages_are_left_alone(pages):
    assert upright_turns(pages) == [0, 0, 0, 0]


@pytest.mark.parametrize("scanned,turn", [(-90, 90), (90, 270)])
def test_a_document_scanned_sideways_is_turned_upright(pages, scanned, turn):
    sideways = [p.rotate(scanned, expand=True) for p in pages]
    turns = upright_turns(sideways)
    assert turns == [turn] * 4
    # the turned page reads like the original: wide side down again, lines across
    assert upright_turns([s.rotate(t, expand=True) for s, t in zip(sideways, turns)]) == [0] * 4


def test_one_page_alone_is_never_guessed(pages):
    assert upright_turns([pages[0].rotate(-90, expand=True)]) == [0]


def test_blank_pages_and_digital_pages_are_not_measured(pages):
    blank = Image.new("RGB", (850, 1200), "white")
    sideways = [p.rotate(-90, expand=True) for p in pages[:2]]
    assert upright_turns(sideways + [blank, None]) == [90, 90, 0, 0]


def test_a_sheet_photographed_on_a_dark_desk_stays_upright(pages):
    photos = []
    for page in pages:
        desk = Image.new("RGB", (1100, 1500), (60, 55, 50))
        desk.paste(page, (125, 150))
        photos.append(desk)
    assert upright_turns(photos) == [0] * 4


def test_pages_that_disagree_leave_the_document_alone(pages):
    mixed = [pages[0].rotate(-90, expand=True), pages[1].rotate(90, expand=True)]
    assert upright_turns(mixed) == [0, 0]


# --- answer grouping -----------------------------------------------------------------------------------------

_HEADER = "MADURAI PUBLIC SCHOOL (CBSE), MADURAI\nROLL NO.: 10C11  NAME: K. Rithika  CLASS & SEC:\nEXAM:  SUBJECT:  SIGN OF INVIGILATOR:"


def _questions(n=39):
    return [S(id=f"q{i}", normalized_number=str(i), display_number=str(i), position=i, max_marks=1,
              question_text="") for i in range(1, n + 1)]


def _page(number, *answers):
    return ({"page_number": number}, StudentPageResult(page_number=number, answers=[
        StudentAnswerItem(question_number=label, answer_text=text) for label, text in answers]))


def _sheet():
    """The shape of a real Science sheet's OCR: answers in order, parts on their own lines."""
    return [
        _page(1, (None, _HEADER), (None, "Total page - 12"), (None, "Section-A"),
              ("1", "C. Carbon dioxide loses oxygen, while water gains oxygen."),
              ("11", "B. The sensitive plant controlled and coordinated by electrical impulses."),
              ("13", "Receptor -> motor neuron -> spinal cord -> second neuron and receptor.")),
        _page(2, ("15", "A. VV x tt  F1 Vt"), (None, "B. F1 VV  TT  F2 VV VT TV TT")),
        _page(3, (None, _HEADER), ("B", "F2 VVTT VvTt"), ("16", "I. C is the heart present in both birds and mammals."),
              ("Q11", "B is the heart depicted. It is present in fishes and the circulation of blood takes place.")),
        _page(4, (None, "circulation. The blood will move from the atrium of heart to the gills.\nSection-B"),
              ("17", "B. C. physical change because the space between crystals is adjusted."),
              ("28", "A. Silver is the best conductor of heat because it takes less time."),
              ("13.", "20 s"), ("C", "Yes, the time reduces because the heating point is increased."),
              ("29", "A. Alisha told that the formation of ammonia is a reduction reaction."),
              ("11", "i) MgCl2 + AgNO3 -> AgCl2 + MgNO3  ii) Al + H2SO4 -> Al2SO4 + H2O")),
    ]


def test_sheet_furniture_never_reaches_an_answer():
    answers = segment_student_answers(_sheet(), _questions())
    text = "\n".join(a.answer_text for a in answers)
    for furniture in ("ROLL NO", "INVIGILATOR", "MADURAI PUBLIC SCHOOL", "Section-A", "Section-B", "Total page"):
        assert furniture not in text
    assert all(a.normalized_number for a in answers)  # no unnumbered leftovers made of headers


def test_roman_and_letter_parts_read_as_numbers_stay_in_their_question():
    answers = segment_student_answers(_sheet(), _questions())
    numbers = [a.normalized_number for a in answers]
    assert numbers == ["1", "11", "13", "15", "16", "17", "28", "29"]  # each question once, in the order written
    by_number = {a.normalized_number: a.answer_text for a in answers}
    assert "(ii) B is the heart depicted" in by_number["16"]
    assert "(b) 20 s" in by_number["28"] and "Yes, the time reduces" in by_number["28"]
    assert "(ii) i) MgCl2" in by_number["29"]
    # the part carried over to the next sheet, past the repeated details box, joins its question
    assert "F2 VVTT" in by_number["15"] and "gills" in by_number["16"]
    # the earlier, genuine Q11 and Q13 keep only their own answers
    assert by_number["11"].startswith("B. The sensitive plant") and "heart" not in by_number["11"]
    assert by_number["13"].startswith("Receptor") and "20 s" not in by_number["13"]


def test_a_skipped_question_answered_later_keeps_its_number():
    """Only numbers already answered are read as part markers: going back to a skipped question still works."""
    sheet = [_page(1, ("10", "The bile duct was obstructed."), ("12", "If the uterus ..."), ("11", "B. Electrical impulses."))]
    answers = segment_student_answers(sheet, _questions())
    assert [a.normalized_number for a in answers] == ["10", "12", "11"]


def test_parts_the_exam_scores_separately_are_used():
    qs = _questions(15) + [S(id=f"q16{p}", normalized_number=f"16({p})", display_number=f"16({p})", position=16,
                             max_marks=1, question_text="") for p in ("i", "ii")]
    sheet = [_page(1, ("11", "B. Electrical impulses."), ("16(i)", "C is the heart in birds."), ("11", "B is the heart in fishes."))]
    answers = segment_student_answers(sheet, qs)
    assert [a.normalized_number for a in answers] == ["11", "16(i)", "16(ii)"]
