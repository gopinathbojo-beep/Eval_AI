"""Tamil format rules, against the layout of the TN SSLC Tamil paper (8501, 2025), and their separation from English."""
from app.ocr.indic import blocks_to_result
from app.ocr.schemas import QuestionPageResult
from app.cbse.common.subjects.tamil import format as tamil_format
from app.cbse.common.paper import extract_exam_total_marks, is_document_header, keyword_question_type
from app.cbse.common.numbering import extract_label_from_text_prefix

# Page 1 and 4 of the sample paper, as IndicOCR returns them
SSLC_QP = [
    {"blocks": [
        {"order": 0, "type": "Text", "text": "மொழிப்பாடம் - பகுதி I - தமிழ்"},
        {"order": 1, "type": "Text", "text": "கால அளவு : 3.00 மணி நேரம் ]    [ மொத்த மதிப்பெண்கள் : 6"},
   
        {"order": 2, "type": "Text", "text": "அறிவுரைகள் : (1) அனைத்து வினாக்களும் சரியாகப் பதிவாகி உள்ளனவா என்பதனைச் சரிபார்த்துக் கொள்ளவும்."},
        {"order": 3, "type": "Text", "text": "பகுதி - I\n(மதிப்பெண்கள் : 15)"},
        {"order": 4, "type": "Text", "text": "குறிப்பு : (i) அனைத்து வினாக்களுக்கும் விடையளிக்கவும். 15x1=15"},
        {"order": 5, "type": "Text", "text": "1. வெண்பா ________ ஓசை உடையது."},
        {"order": 6, "type": "Text", "text": "(அ) செப்பல்"},
        {"order": 7, "type": "Text", "text": "(ஆ) அகவல்"},
        {"order": 8, "type": "Text", "text": "(இ) துள்ளல்"},
        {"order": 9, "type": "Text", "text": "(ஈ) தூங்கல்"},
        {"order": 10, "type": "Text", "text": "2. 'வீசுதென்றல்' – தொகையின் வகையைத் தேர்க."},
        {"order": 11, "type": "Text", "text": "[ திருப்புக"},
    ]},
    {"blocks": [
        {"order": 0, "type": "Text", "text": "பகுதி - II\n(மதிப்பெண்கள் : 18)"},
        {"order": 1, "type": "Text", "text": "பிரிவு - 1"},
        {"order": 2, "type": "Text", "text": "குறிப்பு : எவையேனும் நான்கு வினாக்களுக்கு மட்டும் விடையளிக்கவும். 4x2=8"},
        {"order": 3, "type": "Text", "text": "3. விருந்தினரை மகிழ்வித்துக் கூறும் முகமன் சொற்களை எழுதுக."},
        {"order": 4, "type": "Text", "text": "பிரிவு - 2"},
        {"order": 5, "type": "Text", "text": "குறிப்பு : எவையேனும் ஐந்து வினாக்களுக்கு மட்டும் விடையளிக்கவும். 5x2=10"},
        {"order": 6, "type": "Text", "text": "4. தீவக அணியின் வகைகள் யாவை ?"},
    ]},
]


def _parse(pages):
    from app.cbse.common.paper import parse_question_paper_structure
    return parse_question_paper_structure(
        [({"page_number": i + 1}, blocks_to_result(p, QuestionPageResult, i + 1)) for i, p in enumerate(pages)])


def test_sslc_paper_total_sections_and_marks():
    s = _parse(SSLC_QP)
    got = {q.display_number: (q.question_type, q.max_marks, q.section) for q in s.questions}
    assert s.exam_max_marks == 6                                     # "(மதிப்பெண்கள் : 15)" is a section's, not the paper's
    assert s.exam_duration_minutes == 180
    assert list(got) == ["1", "2", "3", "4"]                       # options, notes and "[ திருப்புக" are not questions
    assert got["1"] == ("mcq", 1.0, "பகுதி - I")                      # a gap plus four options is an MCQ
    assert got["2"][0] == "mcq"                                      # "... தேர்க" (choose)
    assert got["3"] == ("short_answer", 2.0, "பகுதி - II / பிரிவு - 1")
    assert got["4"] == ("short_answer", 2.0, "பகுதி - II / பிரிவு - 2")


def test_section_marks_line_is_not_the_paper_total():
    assert extract_exam_total_marks("(மதிப்பெண்கள் : 15)") is None
    assert extract_exam_total_marks("[ மொத்த மதிப்பெண்கள் : 100") == 100
    assert not is_document_header("(மதிப்பெண்கள் : 15)")
    assert is_document_header("கால அளவு : 3.00 மணி நேரம்")


def test_number_inside_a_note_is_not_a_question_label():
    assert extract_label_from_text_prefix("34 -க்குக் கட்டாயமாக விடையளிக்கவும்.")[0] is None
    assert extract_label_from_text_prefix("21 -வது வினாவிற்குக் கட்டாயமாக விடையளிக்கவும்.")[0] is None
    assert extract_label_from_text_prefix("வினா எண் 3 (அ) கூறுக.")[0] == "3(a)"


def test_either_or_and_page_furniture():
    assert tamil_format.is_either_or_line("அல்லது")
    assert not tamil_format.is_either_or_line("இது அல்லது அது")
    assert tamil_format.strip_page_furniture("38. விளக்குக.\n[ திருப்புக") == "38. விளக்குக."
    assert tamil_format.strip_page_furniture("- o O o -") == ""


def test_english_text_never_meets_a_tamil_rule():
    # the English rule keeps its order: a gap decides before options do
    assert keyword_question_type("1. The sun rises in the ____ . (a) east (b) west (c) north (d) south") == "fill_blank"
    assert extract_exam_total_marks("Maximum Marks : 80") == 80
    assert not tamil_format.has_tamil("Section A (2 marks each)")


# Blocks as IndicOCR really returns them for the SSLC paper: "▁" for spaces, layout types, furniture
REAL_PAGES = [
    {"blocks": [
        {"order": 0, "type": "Text", "label": "Website-link", "text": "www.Padasalai.Net"},
        {"order": 1, "type": "PageNumber", "label": "Folio", "text": "No.▁of▁Printed▁Pages▁:▁11"},
        {"order": 2, "type": "Text", "label": "Dateline", "text": "8501"},
        {"order": 3, "type": "Table", "label": "Table", "text": "<table><tr><td>எண்</td><td>8</td><td>1</td></tr></table>"},
        {"order": 4, "type": "SectionHeader", "label": "Section-title", "text": "MAR-2025▁பதிவு▁எண்▁8▁1▁6\nமொழிப்பாடம்▁-▁பகுதி▁I▁-▁தமிழ்"},
        {"order": 5, "type": "PageNumber", "label": "Folio", "text": "கால▁அளவு▁:▁3.00▁மணி▁நேரம்▁]"},
        {"order": 6, "type": "PageNumber", "label": "Folio", "text": "[▁மொத்த▁மதிப்பெண்கள்▁:▁6"},
        {"order": 7, "type": "Text", "label": "List", "text": "அறிவுரைகள்▁:▁(1)▁அனைத்து▁வினாக்களும்▁சரியாகப்▁பதிவாகி▁உள்ளனவா\n"
                                                            "(2)▁நீலம்▁அல்லது▁கருப்பு▁மையினை▁மட்டுமே▁பயன்படுத்தவும்.\n"
                                                            "குறிப்புகள்▁:▁(i)▁இவ்வினாத்தாள்▁ஐந்து▁பகுதிகளைக்▁கொண்டது.\n(ii)▁விடைகள்▁தெளிவாக▁அமைதல்▁வேண்டும்."},
        {"order": 8, "type": "SectionHeader", "label": "Section-title", "text": "பகுதி▁-▁I\n(மதிப்பெண்கள்▁:▁1)"},
        {"order": 9, "type": "Text", "label": "List", "text": "குறிப்பு▁:▁(i)▁அனைத்து▁வினாக்களுக்கும்▁விடையளிக்கவும்.▁1x1=1"},
        {"order": 10, "type": "Text", "label": "Question", "text": "1.▁வெண்பா▁______▁ஓசை▁உடையது.\n(அ)▁செப்பல்▁(ஆ)▁அகவல்\n(இ)▁துள்ளல்▁(ஈ)▁தூங்கல்"},
        {"order": 11, "type": "PageNumber", "label": "Folio", "text": "[▁திருப்புக"},
        {"order": 12, "type": "Footnote", "label": "Footnote", "text": "Kindly▁Send▁Me▁Your▁Study▁Materials▁To▁Us"},
    ]},
    {"blocks": [
        {"order": 0, "type": "PageNumber", "label": "Page-number", "text": "2"},
        {"order": 1, "type": "SectionHeader", "label": "Section-title", "text": "பகுதி▁-▁V"},
        {"order": 2, "type": "SectionHeader", "label": "Sub-section-title", "text": "(மதிப்பெண்கள்▁:▁5)"},
        {"order": 3, "type": "Text", "label": "Infobox", "text": "1x5=5"},
        {"order": 4, "type": "Text", "label": "Question", "text": "2.▁(அ)▁இன்சொற்களைப்▁பேசுவதனால்▁ஏற்படும்▁நன்மைகளை▁எழுதுக.▁அல்லது\n"
                                                                "(ஆ)▁மொழிபெயர்க்க.\n(i)▁Education▁is▁what▁remains.\n(ii)▁Tomorrow▁is▁busy."},
    ]},
]


def test_real_indicocr_output():
    s = _parse(REAL_PAGES)
    got = [(q.display_number, q.max_marks, q.question_type, q.section, q.choice_group) for q in s.questions]
    assert s.exam_max_marks == 6 and s.exam_duration_minutes == 180
    assert got == [("1", 1.0, "mcq", "பகுதி - I", None),                # notes, header, register box, footers dropped
                   ("2(அ)", 5.0, "descriptive", "பகுதி - V", "2"),       # inline "அல்லது" splits the choice
                   ("2(ஆ)", 5.0, "descriptive", "பகுதி - V", "2")]
    assert s.questions[0].question_text.startswith("வெண்பா ______ ஓசை")     # "▁" read as spaces
    assert "(ii) Tomorrow is busy." in s.questions[2].question_text           # sub-parts stay inside the alternative


def test_glide_before_case_ending_shares_the_stem():
    # "தாய்மொழியின்" / "தாய்மொழி", "இயற்கையை" / "இயற்கை": the answer's words are the question's words
    q = tamil_format.indic_tokens("அ) தாய்மொழியின் முக்கியத்துவம் என்ன?\nஆ) இயற்கையை நாம் ஏன் பாதுகாக்க வேண்டும்?")
    a = tamil_format.indic_tokens("தாய்மொழி நமது எண்ணங்களை வெளிப்படுத்த உதவுகிறது. இயற்கை நமக்குக் காற்று வழங்குகிறது.")
    assert len(q & a) >= 2
    assert tamil_format.indic_tokens("உணவு தாழ்வு பறவை") == {"உணவ", "தாழ்வ", "பறவ"}  # a real வ is kept


def test_answer_labelled_5_stays_on_question_5():
    from types import SimpleNamespace
    from app.cbse.common.mapping import MAPPED, map_label
    qs = [SimpleNamespace(id=f"q{n}", normalized_number=str(n), section=None, question_text=t) for n, t in (
        (5, "கீழ்க்கண்ட வினாக்களுக்கு விடையளிக்கவும். (3)\nஅ) தாய்மொழியின் முக்கியத்துவம் என்ன? (1)\n"
            "ஆ) இயற்கையை நாம் ஏன் பாதுகாக்க வேண்டும்? (2)"),
        (6, "இலக்கணம்\nகீழ்க்கண்ட வாக்கியங்களில் உள்ள பிழைகளைக் கண்டறிந்து சரியான சொற்களை எழுதுக. (3)\n"
            "அ) அவன் பள்ளிக்குச் சென்றாள்.\nஆ) மரங்கள் நமக்கு நிழல் தருகிறான்."))]
    answer = ("அ) தாய்மொழி நமது எண்ணங்களையும் உணர்வுகளையும் தெளிவாக வெளிப்படுத்த உதவுகிறது.\n"
              "(b) இயற்கை நமக்குக் காற்று, நீர், உணவு ஆகியவற்றை வழங்குகிறது.")
    res = map_label("5", qs, 0.9, 0.5, answer_text=answer, answer_position=1, total_answers=2)
    assert res.status == MAPPED and res.normalized_number == "5"
