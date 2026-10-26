from app.config import get_settings
from app.ocr.indic import blocks_to_result, uses_indic_ocr
from app.ocr.schemas import AnswerKeyPageResult, QuestionPageResult, StudentPageResult
from app.services.student_segmentation import segment_student_answers

PAGE = {
    "image": "page.png", "width": 1000, "height": 1400,
    "blocks": [
        {"order": 2, "label": "text", "type": "Text", "bbox_xyxy": [50, 400, 900, 600], "conf": 0.9,
         "text": "2) நீர் சுழற்சி என்பது ஆவியாதல், ஒடுக்கம், மழைப்பொழிவு ஆகும்."},
        {"order": 0, "label": "header", "type": "Text", "bbox_xyxy": [0, 0, 1000, 40], "conf": 0.9, "text": "தமிழ் தேர்வு"},
        {"order": 1, "label": "text", "type": "Text", "bbox_xyxy": [50, 100, 900, 380], "conf": 0.9,
         "text": "1) திருவள்ளுவர் திருக்குறளை இயற்றினார்."},
        {"order": 3, "label": "text", "type": "Text", "bbox_xyxy": [50, 620, 900, 700], "conf": 0.9,
         "text": "இது இரண்டாம் விடையின் தொடர்ச்சி."},
        {"order": 4, "label": "figure", "type": "Figure", "bbox_xyxy": [50, 720, 900, 900], "conf": 0.9, "text": ""},
    ],
}


def test_routes_only_matching_subjects(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "indic_ocr_enabled", True)
    assert uses_indic_ocr("Tamil")
    assert uses_indic_ocr("TAMIL - II")
    assert uses_indic_ocr("தமிழ்")
    assert uses_indic_ocr("Hindi")
    assert not uses_indic_ocr("Mathematics")
    assert not uses_indic_ocr("English")
    assert not uses_indic_ocr(None)
    monkeypatch.setattr(s, "indic_ocr_enabled", False)
    assert not uses_indic_ocr("Tamil")


def test_student_blocks_in_reading_order_with_labels():
    res = blocks_to_result(PAGE, StudentPageResult, 1)
    assert [a.raw_question_label for a in res.answers] == ["1", "2"]          # header and empty figure dropped
    assert res.answers[0].answer_text == "திருவள்ளுவர் திருக்குறளை இயற்றினார்."
    assert res.answers[1].answer_text.endswith("\nஇது இரண்டாம் விடையின் தொடர்ச்சி.")  # paragraph joined to answer 2
    assert res.answers[0].bbox.model_dump() == {"x": 50.0, "y": 100.0, "width": 850.0, "height": 280.0}
    assert res.answers[1].bbox.model_dump() == {"x": 50.0, "y": 400.0, "width": 850.0, "height": 300.0}
    assert all(a.ocr_confidence < 0.6 for a in res.answers)                  # handwriting always reviewed


def test_answer_continues_across_pages():
    page2 = {"blocks": [
        {"order": 0, "type": "Text", "bbox_xyxy": [50, 50, 900, 200], "text": "மேலும் மழை நீர் கடலை அடைகிறது."},
        {"order": 1, "type": "Text", "bbox_xyxy": [50, 250, 900, 400], "text": "3) கம்பர் கம்பராமாயணம் எழுதினார்."},
    ]}
    pages = [({"page_number": 1}, blocks_to_result(PAGE, StudentPageResult, 1)),
             ({"page_number": 2}, blocks_to_result(page2, StudentPageResult, 2))]
    got = [(a.normalized_number, a.answer_text) for a in segment_student_answers(pages)]
    assert [n for n, _ in got] == ["1", "2", "3"]
    assert got[1][1].endswith("மேலும் மழை நீர் கடலை அடைகிறது.")


def test_question_paper_and_answer_key_blocks():
    q = blocks_to_result(PAGE, QuestionPageResult, 1)
    assert [x.raw_question_number for x in q.questions] == ["1", "2", None]
    k = blocks_to_result(PAGE, AnswerKeyPageResult, 1)
    assert [x.question_number for x in k.answers] == ["1", "2", None]


TAMIL_QP = {"blocks": [
    {"order": 0, "type": "Text", "text": "பத்தாம் வகுப்பு தமிழ் தேர்வு\nநேரம் : 3 மணி    மொத்த மதிப்பெண்கள் : 100"},
    {"order": 1, "type": "Text", "text": "பகுதி – அ\nசரியான விடையைத் தேர்ந்தெடுத்து எழுதுக.  4 × 1 = 4"},
    {"order": 2, "type": "Text", "text": "1. திருக்குறளை இயற்றியவர் யார்?"},
    {"order": 3, "type": "Text", "text": "(அ) கம்பர்  (ஆ) திருவள்ளுவர்  (இ) இளங்கோவடிகள்  (ஈ) ஔவையார்"},
    {"order": 4, "type": "Text", "text": "2. கோடிட்ட இடத்தை நிரப்புக: சிலப்பதிகாரத்தை எழுதியவர் ________."},
    {"order": 5, "type": "Text", "text": "3. பொருத்துக: கம்பர் – இராமாயணம்; இளங்கோ – சிலப்பதிகாரம்"},
    {"order": 6, "type": "Text", "text": "4. சரியா தவறா: திருக்குறள் 1330 குறள்களைக் கொண்டது."},
    {"order": 7, "type": "Text", "text": "பகுதி – ஆ\nஏதேனும் இரண்டு வினாக்களுக்கு விடையளி.  2 × 5 = 10\n"
                                        "5. சங்க காலப் புலவர்களின் வாழ்க்கை முறை, அவர்கள் பாடிய பாடல்களின் சிறப்பு, அக்கால மக்களின் "
                                        "பண்பாடு, வணிகம், போர்முறை ஆகியவற்றைப் பற்றி உங்கள் பாடப்பகுதியில் படித்தவற்றைக் கொண்டு "
                                        "விரிவாக விளக்குக"},
    {"order": 8, "type": "Text", "text": "6. நாட்டுப்புறப் பாடல்களின் சிறப்புகளை எழுதுக. (5 மதிப்பெண்கள்)"},
]}


def test_tamil_question_paper_marks_sections_types():
    from app.services.doc_structure import parse_question_paper_structure
    res = blocks_to_result(TAMIL_QP, QuestionPageResult, 1)
    s = parse_question_paper_structure([({"page_number": 1}, res)])
    got = {q.display_number: (q.question_type, q.max_marks, q.section) for q in s.questions}
    assert s.exam_max_marks == 100
    assert list(got) == ["1", "2", "3", "4", "5", "6"]                     # options and headings are not questions
    assert got["1"] == ("mcq", 1.0, "பகுதி – அ")
    assert got["2"][0] == "fill_blank" and got["3"][0] == "match" and got["4"][0] == "true_false"
    assert got["5"] == ("descriptive", 5.0, "பகுதி – ஆ")                     # long Tamil question, not a passage
    assert got["6"] == ("descriptive", 5.0, "பகுதி – ஆ")
    assert "(ஆ) திருவள்ளுவர்" in s.questions[0].question_text


def test_tamil_answer_key_marks_and_criteria():
    from app.services.key_segmentation import extract_criteria_from_block, parse_criteria_marks
    t = "திருவள்ளுவர் திருக்குறளை இயற்றினார்.\n• ஆசிரியர் பெயர் – 1 மதிப்பெண்\n• நூல் பெயர் – 1 மதிப்பெண்"
    _, crit = extract_criteria_from_block(t)
    assert len(crit) == 2 and parse_criteria_marks(crit, t) == 2
    t2 = "சங்க காலம் ...\nமதிப்பீட்டுக் குறிப்பு (5 மதிப்பெண்கள்):\n2 மதிப்பெண்: கருத்து\n3 மதிப்பெண்: எடுத்துக்காட்டு"
    ans, crit = extract_criteria_from_block(t2)
    assert ans == "சங்க காலம் ..." and crit == ["2 மதிப்பெண்: கருத்து", "3 மதிப்பெண்: எடுத்துக்காட்டு"]
    assert parse_criteria_marks(crit, t2) == 5


def test_tamil_words_match_across_inflections():
    from app.services.ocr_recovery import _tokenize
    q = _tokenize("திருக்குறளை இயற்றியவர் யார்? விளக்குக")
    a = _tokenize("திருவள்ளுவர் திருக்குறள் எழுதினார்")
    assert q & a == {"திருக்குறள"}                     # same word, different case ending; "யார்"/"விளக்குக" are stop words
    assert _tokenize("Explain photosynthesis in plants") == {"explain", "photosynthesi", "plant"}  # English unchanged


def test_tamil_and_english_header_labels():
    from app.ocr.indic import parse_identity
    r = parse_identity("பெயர் : மு. கார்த்திக்    வகுப்பு : 10   பிரிவு : அ\nபதிவு எண் : 2024TN0153   தேர்வு எண்: 42")
    assert r == {"name": "மு. கார்த்திக்", "class_name": "10", "section": "அ",
                 "registration_number": "2024TN0153", "roll_number": "42"}
    assert parse_identity("Name: Priya  Roll No: 17")["roll_number"] == "17"


def test_grading_model_only_for_indian_language_subjects(monkeypatch):
    from app.ocr.indic import text_model_for
    s = get_settings()
    monkeypatch.setattr(s, "indic_ocr_enabled", True)
    monkeypatch.setattr(s, "indic_text_model", "tamil-llm")
    assert text_model_for("Tamil") == "tamil-llm"
    assert text_model_for("Science") is None
    monkeypatch.setattr(s, "indic_text_model", "")
    assert text_model_for("Tamil") is None          # not configured: InternVL grades, as before


def test_tamil_question_labels():
    from app.services.numbering import extract_label_from_text_prefix as label, normalize_question_number as norm
    assert label("வினா 1. திருக்குறளை இயற்றியவர் யார்?") == ("1", "திருக்குறளை இயற்றியவர் யார்?")
    assert label("வினா எண் 3 (அ) கம்பர்") == ("3(a)", "கம்பர்")
    assert label("கேள்வி 2: பாடல்") == ("2", "பாடல்")
    assert label("3(ஆ) இளங்கோ") == ("3(b)", "இளங்கோ")
    assert label("(இ) ஔவையார்") == ("(c)", "ஔவையார்")
    assert label("அவர் திருவள்ளுவர்")[0] is None                   # a word starting with அ is not a label
    assert norm("வினா எண் 3") == "3" and norm("1(அ)") == "1(a)" and norm("(ஆ)") == "(b)"


def test_student_tamil_labels_map_to_subparts():
    page = {"blocks": [
        {"order": 0, "type": "Text", "text": "வினா 1 (அ) திருவள்ளுவர்"},
        {"order": 1, "type": "Text", "text": "(ஆ) இளங்கோவடிகள்"},
        {"order": 2, "type": "Text", "text": "வினா 2 கம்பர் இராமாயணம் எழுதினார்"},
    ]}
    res = blocks_to_result(page, StudentPageResult, 1)
    assert [a.raw_question_label for a in res.answers] == ["1(a)", "(b)", "2"]


def _q(text, marks=None, source="default", qtype="descriptive"):
    from app.services.doc_structure import StructuredQuestion
    return StructuredQuestion(None, None, "1", text, qtype, marks, None, 1, 1, None, None, type_source=source)


def test_labeler_types_only_uncertain_questions(monkeypatch):
    from types import SimpleNamespace
    from app.ocr.schemas import QuestionTypeLabels
    from app.services import ai_labeler
    qs = [_q("இளங்கோவடிகள் இயற்றிய நூல் எது?", 2, "default", "short_answer"),
          _q("பொருத்துக: ...", 4, "rule", "match"),
          _q("கடிதம் வரைக.", 5, "default")]
    seen = []

    def fake(system, user, schema, image_path=None, model=None):
        seen.append(user)
        return SimpleNamespace(parsed=QuestionTypeLabels(labels=[
            {"id": "0", "question_type": "short_answer"}, {"id": "1", "question_type": "mcq"},
            {"id": "2", "question_type": "letter"}]))           # not a known type: ignored
    monkeypatch.setattr(ai_labeler, "chat_structured", fake)
    assert ai_labeler.label_question_types(qs, "tamil-llm") == 1
    assert (qs[0].question_type, qs[0].type_source) == ("short_answer", "ai")
    assert (qs[1].question_type, qs[1].type_source) == ("match", "rule")       # keyword result never sent or changed
    assert (qs[2].question_type, qs[2].type_source) == ("descriptive", "default")
    assert "பொருத்துக" not in seen[0]


def test_labeler_marking_points_are_checked(monkeypatch):
    from types import SimpleNamespace
    from app.ocr.schemas import KeyCriteriaLabels
    from app.services import ai_labeler
    from app.services.key_segmentation import SegmentedKey
    keys = [SegmentedKey("1", "1", "திருக்குறளை எழுதியவர் திருவள்ளுவர். அது 1330 குறள்களைக் கொண்டது.", None),
            SegmentedKey("2", "2", "சிலப்பதிகாரம் இளங்கோவடிகள் இயற்றியது.", None),
            SegmentedKey("3", "3", "கம்பர் இராமாயணம் இயற்றினார்.", None)]
    qs = [SimpleNamespace(normalized_number=n, max_marks=2.0, question_text="") for n in ("1", "2", "3")]

    def fake(system, user, schema, image_path=None, model=None):
        return SimpleNamespace(parsed=KeyCriteriaLabels(keys=[
            {"id": "0", "criteria": [{"point": "திருவள்ளுவர் எழுதியவர்", "marks": 1}, {"point": "1330 குறள்கள்", "marks": 1}]},
            {"id": "1", "criteria": [{"point": "இளங்கோவடிகள்", "marks": 1}]},                  # adds up to 1, not 2
            {"id": "2", "criteria": [{"point": "வால்மீகி சமஸ்கிருதத்தில் எழுதினார்", "marks": 2}]}]))  # not in the answer
    monkeypatch.setattr(ai_labeler, "chat_structured", fake)
    assert ai_labeler.label_key_criteria(keys, qs, "tamil-llm") == 1
    assert keys[0].criteria == ["1 Mark: திருவள்ளுவர் எழுதியவர்", "1 Mark: 1330 குறள்கள்"] and keys[0].marks == 2
    assert keys[1].criteria == [] and keys[2].criteria == []


def test_labeler_outage_keeps_rule_results(monkeypatch):
    from app.ocr.internvl import AIUnavailable
    from app.services import ai_labeler

    def down(*a, **k):
        raise AIUnavailable("tamil-llm not installed")
    monkeypatch.setattr(ai_labeler, "chat_structured", down)
    qs = [_q("கடிதம் வரைக.", 5)]
    assert ai_labeler.label_question_types(qs, "tamil-llm") == 0
    assert (qs[0].question_type, qs[0].type_source) == ("descriptive", "default")


def test_tamil_feedback_explains_a_deduction():
    from app.ocr.schemas import EvaluationResult
    from app.services.evaluation_rules import validate_evaluation

    def graded(feedback):
        return validate_evaluation(EvaluationResult(marks_awarded=1, decision="PARTIALLY_CORRECT",
                                                    feedback=feedback), 2).marks_awarded
    assert graded("நூல் பெயர் சரி; ஆசிரியர் பெயர் குறிப்பிடப்படவில்லை.") == 1     # gap described in Tamil: kept
    assert graded("விடை நன்றாக உள்ளது.") == 1.5                                   # no gap named: capped as before
