"""Tamil point grading on the confirmed rubric (points.py) and answer sheets by alignment with self-repair (align.py)."""
from types import SimpleNamespace as NS

from app.ocr.schemas import StudentAnswerItem, StudentPageResult
from app.cbse.common.subjects.tamil import align
from app.cbse.common.subjects.tamil.answers import segment as by_numbers
from app.cbse.common.subjects.tamil.points import PointVerdict, grade

RUBRIC = {"kind": "points", "points": [
    {"id": "1", "marks": 1, "text": "உயர்வு - தாழ்வு", "kind": "exact", "part": "அ", "expected": ["தாழ்வு"]},
    {"id": "2", "marks": 2, "text": "மரங்களின் பயன்: மரங்கள் ஆக்சிஜனை வழங்குகின்றன", "kind": "meaning", "part": "ஆ",
     "expected": []},
]}


def _asker(verdict: PointVerdict, asked: list):
    def ask(system, prompt, schema):
        asked.append(prompt)
        return verdict
    return ask


def test_points_found_by_key_words_need_no_model():
    asked = []
    res = grade(RUBRIC, "அ) தாழ்வு\nஆ) மரங்கள் நமக்கு ஆக்ஸிஜனை வழங்குகின்றன.", 3.0, _asker(PointVerdict(), asked))
    assert res.marks_awarded == 3 and res.decision == "CORRECT" and not asked  # ஆக்ஸிஜனை: a one-letter slip


def test_exact_point_loses_its_mark_for_one_changed_ending():
    res = grade(RUBRIC, "அ) தாழ்வை\nஆ) மரங்கள் ஆக்சிஜனை வழங்குகின்றன.", 3.0, None)
    assert res.marks_awarded == 2 and res.missing_points == ["(அ) உயர்வு - தாழ்வு (expected: தாழ்வு)"]


def test_each_point_is_looked_for_in_its_own_part():
    res = grade(RUBRIC, "அ) உயர்வு\nஆ) தாழ்வு. மரங்கள் ஆக்சிஜனை வழங்குகின்றன.", 3.0, None)
    assert res.marks_awarded == 2  # "தாழ்வு" is written under ஆ), not under அ)


def test_added_negation_goes_to_the_model_and_its_no_costs_the_point():
    asked = []
    res = grade(RUBRIC, "அ) தாழ்வு\nஆ) மரங்கள் ஆக்சிஜனை வழங்குகின்றன இல்லை.", 3.0,
                _asker(PointVerdict(same_meaning=False), asked))
    assert len(asked) == 1 and res.marks_awarded == 1 and res.decision == "PARTIALLY_CORRECT"


def test_model_yes_counts_only_with_a_quote_from_the_answer():
    answer = "அ) தாழ்வு\nஆ) மரங்கள் உயிர்வளியைத் தருகின்றன."
    yes = grade(RUBRIC, answer, 3.0, _asker(PointVerdict(same_meaning=True, quote="மரங்கள் உயிர்வளியைத் தருகின்றன"), []))
    assert yes.marks_awarded == 3 and yes.confidence is None
    made_up = grade(RUBRIC, answer, 3.0, _asker(PointVerdict(same_meaning=True, quote="ஆக்சிஜனை வழங்குகின்றன"), []))
    assert made_up.marks_awarded == 1 and "not in the answer" in made_up.missing_points[0]


def test_open_questions_and_incomplete_rubrics_keep_whole_answer_grading():
    assert grade({**RUBRIC, "kind": "letter"}, "அன்புள்ள நண்பா", 3.0, None) is None
    assert grade(RUBRIC, "அ) தாழ்வு", 5.0, None) is None  # points add up to 3, the question has 5
    assert grade({"kind": "points", "points": [{**RUBRIC["points"][0], "marks": None}]}, "தாழ்வு", 1.0, None) is None
    assert grade(None, "தாழ்வு", 1.0, None) is None


# ---------------------------------------------------------------- alignment

KEYS = {
    "1": "தாய்மொழி உணர்வுகளை வெளிப்படுத்த உதவுகிறது. தாய்மொழி சிந்தனையை வளர்க்கிறது.",
    "2": "மரங்கள் ஆக்சிஜனை வழங்குகின்றன. மரங்கள் மண்ணரிப்பைத் தடுக்கின்றன. மரங்கள் மழை பெய்ய உதவுகின்றன.",
    "3": "ஒழுக்கம் உயிரினும் மேலானது என்று வள்ளுவர் கூறுகிறார்.",
}
QS = [NS(normalized_number=str(n), id=f"q{n}", question_text="") for n in (1, 2, 3)]


def _page(n, items):
    answers = [StudentAnswerItem(**{"bbox": {"x": 10, "y": 100 * i, "width": 500, "height": 90}, **it})
               for i, it in enumerate(items)]
    return ({"page_number": n}, StudentPageResult(page_number=n, answers=answers))


Q2_TEXT = ("மரங்கள் நமக்கு ஆக்சிஜனை வழங்குகின்றன.\nமரங்கள் மண்ணரிப்பைத் தடுக்கின்றன.\n"
           "மரங்கள் மழை பெய்ய உதவுகின்றன.")


def test_an_answer_whose_heading_was_lost_is_found_by_its_key():
    sheet = [_page(1, [
        {"answer_text": "வினா 1. தாய்மொழி உணர்வுகளை வெளிப்படுத்த உதவுகிறது."},
        {"answer_text": Q2_TEXT},  # "வினா 2." lost by the OCR
        {"answer_text": "வினா 3. ஒழுக்கம் உயிரினும் மேலானது என்று வள்ளுவர் கூறுகிறார்."},
    ])]
    assert [a.normalized_number for a in by_numbers(sheet, QS)] == ["1", "3"]  # Q2 swallowed by Q1
    res = align.segment(sheet, QS, KEYS)
    assert [a.normalized_number for a in res] == ["1", "2", "3"]
    assert res[1].answer_text == Q2_TEXT
    assert res[0].boundary_confidence > align.LOW_CONFIDENCE and res[2].boundary_confidence > align.LOW_CONFIDENCE
    assert res[1].boundary_confidence < res[2].boundary_confidence  # started on key evidence alone


def test_numbers_alone_without_a_key_give_the_same_answers():
    sheet = [_page(1, [
        {"answer_text": "எட்டாம் வகுப்பு - தமிழ் வினாத்தாள்"},
        {"answer_text": "வினா 1. தாய்மொழி உணர்வுகளை வெளிப்படுத்த உதவுகிறது."},
        {"question_number": "(a)", "answer_text": "தாய்மொழி சிந்தனையை வளர்க்கிறது."},
        {"answer_text": "வினா 3. ஒழுக்கம் உயிரினும் மேலானது."},
    ])]
    want = [(a.normalized_number, a.answer_text) for a in by_numbers(sheet, QS)]
    assert [(a.normalized_number, a.answer_text) for a in align.segment(sheet, QS, None)] == want
    assert want[0] == ("1", "தாய்மொழி உணர்வுகளை வெளிப்படுத்த உதவுகிறது.\nஅ) தாய்மொழி சிந்தனையை வளர்க்கிறது.")


def test_a_far_misread_number_is_read_as_the_question_between_its_neighbours():
    qs = [NS(normalized_number=str(n), id=f"q{n}", question_text="") for n in range(1, 11)]
    sheet = [_page(1, [
        {"answer_text": "வினா 1. தாய்மொழி உணர்வுகளை வெளிப்படுத்த உதவுகிறது."},
        {"answer_text": "வினா 9. மரங்கள் ஆக்சிஜனை வழங்குகின்றன."},  # a handwritten 2 read as 9
        {"answer_text": "வினா 3. ஒழுக்கம் உயிரினும் மேலானது."},
        {"answer_text": "வினா 4. நான்காம் விடை."},
        {"answer_text": "வினா 5. ஐந்தாம் விடை."},
    ])]
    assert [a.normalized_number for a in by_numbers(sheet, qs)] == ["1", "3", "4", "5"]  # Q2 inside Q1
    res = align.segment(sheet, qs, None)
    assert [a.normalized_number for a in res] == ["1", "2", "3", "4", "5"]
    assert res[1].answer_text == "9 மரங்கள் ஆக்சிஜனை வழங்குகின்றன."  # the misread number stays in the text


def test_reread_repairs_a_misread_heading_and_keeps_it_only_when_keys_match_better():
    bad = [_page(1, [
        {"answer_text": "வினா 1. தாய்மொழி உணர்வுகளை வெளிப்படுத்த உதவுகிறது."},
        {"answer_text": "வினா 3. " + Q2_TEXT},  # "வினா 2." read as 3
        {"answer_text": "வினா 3. ஒழுக்கம் உயிரினும் மேலானது."},
    ])]
    answers = by_numbers(bad, QS)
    assert [a.normalized_number for a in answers] == ["1", "3"] and align.failing(answers, KEYS)
    regions = []

    def reread(page, bbox):
        regions.append((page, bbox))
        return [StudentAnswerItem(answer_text="வினா 2. " + Q2_TEXT, bbox={"x": 10, "y": 100, "width": 500, "height": 90}),
                StudentAnswerItem(answer_text="வினா 3. ஒழுக்கம் உயிரினும் மேலானது.",
                                  bbox={"x": 10, "y": 200, "width": 500, "height": 90})]
    fixed = align.reread_failing(answers, bad, QS, KEYS, reread, lambda pages: by_numbers(pages, QS))
    assert regions and regions[0][0] == 1
    assert [a.normalized_number for a in fixed] == ["1", "2", "3"]
    assert align.key_score(fixed, KEYS) > align.key_score(answers, KEYS)

    same = align.reread_failing(answers, bad, QS, KEYS, lambda page, bbox: [], lambda pages: by_numbers(pages, QS))
    assert same is answers  # nothing read again: nothing changes
    assert align.reread_failing(answers, bad, QS, KEYS, None, lambda pages: []) is answers
