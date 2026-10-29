import pytest
from app.ocr.schemas import QuestionPageResult, QuestionItem
from app.services import paper_format
from app.formatter.common.paper import parse_question_paper_structure


def _page(n, items):
    return ({"page_number": n}, QuestionPageResult(page_number=n, questions=[QuestionItem(**i) for i in items]))


def test_questions_inside_one_ocr_block_are_split():
    """Class 8 Tamil via IndicOCR: Q1 came back holding வினா 2-4, and Section B's marks rule holding வினா 5-6.
    Each must be its own question, not one 36-mark question 1."""
    pages = [
        _page(1, [
            {"question_text": "எட்டாம் வகுப்பு – தமிழ் வினாத்தாள்\nமொத்த மதிப்பெண்கள்: 30"},
            {"question_text": "பகுதி - அ: குறுவினாக்கள்"},
            {"question_text": "(4 வினாக்கள் × 2 மதிப்பெண்கள் = 8 மதிப்பெண்கள்)"},
            {"raw_question_number": "1", "question_text": "கீழ்க்கண்ட வினாக்களுக்கு விடையளிக்கவும்.\nஅ) கல்வியின் சிறப்புகள் யாவை? (2)\n\n"
             "வினா 2. இலக்கணம்:\nஅ) எதிர்ச்சொற்களை எழுதுக. (1)\nஆ) பன்மை வடிவங்களை எழுதுக. (1)\n\n"
             "வினா 3. செய்யுளைப் படித்து விடையளிக்கவும்.\nஅ) நாம் எதைக் கற்க வேண்டும்? (1)\nஆ) மனதில் எவற்றைக் கொண்டிருக்க வேண்டும்? (1)\n\n"
             "வினா 4. கோடிட்ட இடங்களை நிரப்புக. (2)\nஅ) திருக்குறளை இயற்றியவர் ____."},
            {"question_text": "பகுதி – ஆ: நடுத்தர வினாக்கள்"},
            {"question_text": "(4 வினாக்கள் × 3 மதிப்பெண்கள் = 12 மதிப்பெண்கள்)\n\nவினா 5. விடையளிக்கவும். (3)\nஅ) தாய்மொழியின் முக்கியத்துவம் என்ன? (1)\n\n"
             "வினா 6. இலக்கணம்\nபிழைகளைக் கண்டறிந்து சரியான சொற்களை எழுதுக. (3)\nஅ) அவன் பள்ளிக்குச் சென்றாள்."},
        ]),
        _page(2, [
            {"raw_question_number": "(c)", "question_text": "மாணவர்கள் பாடம் படித்தான்."},
            {"raw_question_number": "7", "question_text": "படித்துப் புரிந்து விடையளித்தல் (3)"},
            {"raw_question_number": "8", "question_text": "தலைப்பில் மூன்று அல்லது நான்கு வாக்கியங்களில் எழுதுக. (3)"},
            {"question_text": "பகுதி - இ: விரிவான விடைகள்"},
            {"question_text": "(2 வினாக்கள் × 5 மதிப்பெண்கள் = 10 மதிப்பெண்கள்)"},
            {"raw_question_number": "9", "question_text": "கடிதம் எழுதுதல் (5)"},
            {"raw_question_number": "10", "question_text": "கட்டுரை எழுதுதல் (5)"},
        ]),
    ]
    with paper_format.use(paper_format.TAMIL):
        doc = parse_question_paper_structure(pages)
    assert [q.normalized_number for q in doc.questions] == [str(n) for n in range(1, 11)]
    assert [q.max_marks for q in doc.questions] == [2, 2, 2, 2, 3, 3, 3, 3, 5, 5]
    assert "வினா 2" not in doc.questions[0].question_text
    assert doc.questions[5].question_text.endswith("(இ) மாணவர்கள் பாடம் படித்தான்.")


def test_key_answers_inside_one_ocr_block_are_split():
    """Class 8 Tamil key via IndicOCR: Q1's answer block held வினா 2's key, and a பகுதி heading held வினா 5's."""
    from app.ocr.schemas import AnswerKeyPageResult, AnswerKeyItem
    from app.formatter.tamil import paper as tamil_paper

    def page(n, items):
        return ({"page_number": n}, AnswerKeyPageResult(page_number=n, answers=[AnswerKeyItem(**i) for i in items]))
    key = [
        page(1, [
            {"answer_text": "விடைக்குறிப்பு மற்றும் மதிப்பீட்டுத் திட்டம்"},
            {"question_number": "1", "answer_text": "கல்வியின் சிறப்புகள் (2 மதிப்பெண்கள்)"},
            {"answer_text": "விடை: கல்வி அறிவை அளிக்கிறது.\nமதிப்பீட்டுத் திட்டம்:\n1 மதிப்பெண் - அறிவு பெறுதல்.\n"
             "1 மதிப்பெண் - ஒழுக்கம்.\nவினா 2. இலக்கணம் (2 மதிப்பெண்கள்)\nவிடைகள்:\nஅ) உயர்வு - தாழ்வு\n"
             "மதிப்பீட்டுத் திட்டம்:\nஒவ்வொரு சரியான விடைக்கும் 1 மதிப்பெண்."},
        ]),
        page(2, [
            {"answer_text": "பகுதி - ஆ: நடுத்தர வினாக்கள் (12 மதிப்பெண்கள்)\nவினா 3. குறுவிடைகள் (3 மதிப்பெண்கள்)"},
            {"answer_text": "• விடை: தாய்மொழி உணர்வுகளை வெளிப்படுத்த உதவுகிறது."},
        ]),
    ]
    qs = [type("Q", (), {"normalized_number": str(n), "id": f"q{n}"})() for n in (1, 2, 3)]
    with paper_format.use(paper_format.TAMIL):
        keys = tamil_paper.segment_keys(key, qs)
    assert [(k.normalized_number, k.marks) for k in keys] == [("1", 2), ("2", 2), ("3", 3)]
    assert not any("வினா 2" in c for c in keys[0].criteria)
    assert "தாய்மொழி" in keys[2].answer_text


def test_student_answers_rebuilt_from_tamil_question_numbers():
    """Handwritten Tamil sheet via IndicOCR: headings inside other blocks ("வினா 4." under Q3, "அனா 7." / "வானா 8." /
    "வினா 9." misread or buried), parts as (a)/(b)/(c), continuation blocks across pages, a title before Q1."""
    from app.ocr.schemas import StudentPageResult, StudentAnswerItem
    from app.formatter.common.answers import segment_student_answers

    def page(n, items):
        return ({"page_number": n}, StudentPageResult(page_number=n, answers=[StudentAnswerItem(**i) for i in items]))
    sheet = [
        page(1, [
            {"answer_text": "எட்டாம் வகுப்பு - தமிழ் வினாத்தாள்"},
            {"question_number": "6", "answer_text": "இலக்கணம் (3 மதிப்பெண்கள்)"},
            {"question_number": "(a)", "answer_text": "அவன் பள்ளிக்குச் சென்றான்.\nஅனா 7. படித்துப் புரிந்து விடையளித்தல்"},
            {"question_number": "(a)", "answer_text": "மரங்கள் ஆக்சிஜனை வழங்குகின்றன."},
        ]),
        page(2, [
            {"question_number": "(c)", "answer_text": "மண்ணரிப்பைத் தடுக்க வேண்டும்.\nவானா 8. ஒழுக்கம் பற்றி எழுதுக\nவிடை: ஒழுக்கம் முக்கியமானது.\n"
             "பகுதி-இ: விரிவான விடைகள் (10 மதிப்பெண்கள்)\nவினா 9. கடிதம் எழுதுக.\nஅன்புள்ள நண்பா ரவி,"},
        ]),
        page(3, [
            {"answer_text": "உன் அன்பு நண்பன்,\nகுமார்."},
            {"answer_text": "அணா 10. கட்டுரை எழுதுக."},
            {"question_number": "(a)", "answer_text": "சுற்றுச்சூழல் பாதுகாப்பு"},
        ]),
    ]
    qs = [type("Q", (), {"normalized_number": str(n), "id": f"q{n}", "question_text": ""})() for n in (6, 7, 8, 9, 10)]
    with paper_format.use(paper_format.TAMIL):
        res = segment_student_answers(sheet, qs)
    assert [a.normalized_number for a in res] == ["6", "7", "8", "9", "10"]
    assert res[0].answer_text.endswith("அ) அவன் பள்ளிக்குச் சென்றான்.")
    assert "இ) மண்ணரிப்பைத்" in res[1].answer_text
    assert "பகுதி" not in res[2].answer_text and "வினா 9" not in res[2].answer_text
    assert res[3].answer_text.endswith("குமார்.")
    assert res[4].answer_text == "கட்டுரை எழுதுக.\nஅ) சுற்றுச்சூழல் பாதுகாப்பு"


Q10 = ("கட்டுரை எழுதுதல் (5)\nகீழ்க்கண்ட தலைப்புகளில் ஏதேனும் ஒன்றைப் பற்றி 100–120 சொற்களில் கட்டுரை எழுதுக.\n"
       "அ) சுற்றுச்சூழல் பாதுகாப்பு\nஆ) கல்வியின் முக்கியத்துவம்\nஇ) எனக்குப் பிடித்த திருவிழா")
Q10_ANSWER = ("கீழ்க்கண்ட தலைப்புகளில் ஏதேனும் ஒன்றைப் பற்றி கட்டுரை எழுதுக.\nஅ) சுற்றுச்சூழல் பாதுகாப்பு\n"
              "சுற்றுச்சூழல் என்பது நம்மைச் சுற்றியுள்ள காற்று, நீர், நிலம்.\nஆ) கல்வியின் முக்கியத்துவம்\n"
              "கல்வி மனிதனின் வாழ்க்கையில் மிகவும் முக்கியமானது.\nஇ) எனக்குப் பிடித்த திருவிழா\nபொங்கல் திருவிழா.")


def test_any_one_topic_answered_on_several_splits_per_topic():
    from app.formatter.tamil.answers import one_of_attempts
    got = one_of_attempts(Q10, Q10_ANSWER)
    assert [t for t, _ in got] == ["அ) சுற்றுச்சூழல் பாதுகாப்பு", "ஆ) கல்வியின் முக்கியத்துவம்", "இ) எனக்குப் பிடித்த திருவிழா"]
    assert got[1][1] == "ஆ) கல்வியின் முக்கியத்துவம்\nகல்வி மனிதனின் வாழ்க்கையில் மிகவும் முக்கியமானது."
    assert one_of_attempts(Q10, "அ) சுற்றுச்சூழல் பாதுகாப்பு\nஒரு கட்டுரை மட்டும்.") == []  # one topic: graded as is
    assert one_of_attempts("வினா 3. அ) நாம் எதைக் கற்க வேண்டும்? ஆ) ...", Q10_ANSWER) == []  # parts, not a choice


def test_any_one_topic_answered_on_several_counts_the_best(monkeypatch):
    from types import SimpleNamespace as NS
    from app.ocr.internvl import AICall
    from app.ocr.schemas import EvaluationResult
    from app.services import evaluation_service as es

    answer = NS(id="a10", status="MAPPED")
    monkeypatch.setattr(es, "resolve_student_answer", lambda db, ev, q: es.ResolvedAnswer(
        status=es.STUDENT_ANSWER_FOUND, combined_text=Q10_ANSWER, primary_answer=answer, constituent_answers=[answer]))
    monkeypatch.setattr(es, "active_key_for", lambda db, exam_id, qid: NS(answer_text="மாதிரி விடை", criteria=[],
                                                                           accepted_answers=[], keywords=[]))
    scores = {"சுற்றுச்சூழல்": 3.0, "கல்வியின்": 4.5, "திருவிழா": 2.0}
    prompts_seen = []

    def fake(system, prompt, schema, model=None):
        prompts_seen.append(prompt)
        marks = next(v for k, v in scores.items() if k in prompt.rsplit("அ) சுற்றுச்சூழல் பாதுகாப்பு\nஆ)", 1)[-1])
        return AICall(EvaluationResult(marks_awarded=marks, decision="PARTIAL", feedback="ok", confidence=0.8), "raw", 1)
    monkeypatch.setattr(es, "chat_structured", fake)

    item = NS(status=None, error=None, student_answer_id=None)
    q = NS(id="q10", display_number="10", question_text=Q10, max_marks=5.0)
    with paper_format.use(paper_format.TAMIL):
        es.evaluate_item(NS(commit=lambda: None), NS(exam_id="e"), q, item)
    assert len(prompts_seen) == 3
    assert item.status == "EVALUATED" and item.ai_marks == 4.5 and item.final_marks == 4.5
    assert "ஆ) கல்வியின் முக்கியத்துவம்" in item.ai_feedback.splitlines()[0]


def test_student_headings_misread_or_without_full_stop_and_ocr_noise():
    """"வினா 1. படித்துப் புரிந்து ..." after Q6 is Q7 (7 read as 1, its title says so); "வினா 9 கடிதம்" has no full stop;
    a line in Bengali script is OCR noise; a wrapped பகுதி heading leaves no line behind."""
    from app.ocr.schemas import StudentPageResult, StudentAnswerItem
    from app.formatter.common.answers import segment_student_answers

    sheet = [({"page_number": 1}, StudentPageResult(page_number=1, answers=[StudentAnswerItem(**i) for i in [
        {"question_number": "6", "answer_text": "இலக்கணம் - பிழை திருத்துதல்"},
        {"answer_text": "(প্রকৌশলপ্রযোজ্য) : পশ্যতি।\nசென்றாள் - சென்றான்\nவினா 1. படித்துப் புரிந்து விடையளித்தல் (3 மதிப்பெண்கள்)\nஅ) ஆக்சிஜனை வழங்குகின்றன."},
        {"question_number": "8", "answer_text": "ஒழுக்கத்தின் முக்கியத்துவம்\nஒழுக்கம் முக்கியமானது.\nபகுதி - இ : விரிவான விடைகள் மற்றும்\n"
         "எருதும் திறன் (10 மதிப்பெண்கள்)\nவினா 9 கடிதம் எழுதுதல் (5 மதிப்பெண்கள்,\nஅன்புள்ள நண்பா ரவி,"},
    ]]))]
    qs = [type("Q", (), {"normalized_number": str(n), "id": f"q{n}", "question_text": t})() for n, t in
          [(6, "இலக்கணம்"), (7, "படித்துப் புரிந்து விடையளித்தல் (3)"), (8, "ஒழுக்கம்"), (9, "கடிதம் எழுதுதல் (5)")]]
    with paper_format.use(paper_format.TAMIL):
        res = segment_student_answers(sheet, qs)
    assert [(a.raw_question_number, a.normalized_number) for a in res] == [("6", "6"), ("7", "7"), ("8", "8"), ("9", "9")]
    assert res[0].answer_text == "இலக்கணம் - பிழை திருத்துதல்\nசென்றாள் - சென்றான்"
    assert res[2].answer_text == "ஒழுக்கத்தின் முக்கியத்துவம்\nஒழுக்கம் முக்கியமானது."


def _graded(marks, missing, feedback="x"):
    from types import SimpleNamespace as NS
    return NS(marks_awarded=marks, decision="PARTIALLY_CORRECT", missing_points=missing, feedback=feedback)


Q1_KEY = ("கல்வியின் சிறப்புகள் (2 மதிப்பெண்கள்)\nவிடை: கல்வி மனிதனுக்கு அறிவையும் ஒழுக்கத்தையும் அளிக்கிறது. நல்ல\n"
          "சிந்தனையையும் தன்னம்பிக்கையையும் வளர்த்து, வாழ்க்கையில் முன்னேற\nஉதவுகிறது.")
Q1_STUDENT = ("கல்வியின் சிறப்புகள் (2 மதிப்பெண்கள்)\nவிடை: கல்வி மனிதனுக்கு\nஅறிவையும் ஒழுக்கத்தையும் அளிக்கிறது. நல்ல\n"
              "சிந்தனையையும் தன்னம்பிக்கையையும் வளர்த்து,\nவாழ்க்கையில் முன்னேற உதவுகிறது.\n• மதிப்பீட்டுத் திட்டம்")
Q1_MISSING = ["1 மதிப்பெண் - ஒழுக்கம் அல்லது வாழ்கை முன்னேற்றத்தைக் குறிப்பிடுதல்"]


def test_deduction_contradicted_by_the_answer_is_undone():
    """Answer word-for-word the key, graded 1.5/2 for a "missing" point it contains: full marks."""
    from app.formatter.tamil.answers import check_deductions
    assert check_deductions(_graded(1.5, Q1_MISSING), Q1_STUDENT, Q1_KEY, 2.0).marks_awarded == 2.0
    # without the key the named point alone is checked (reworded and misspelled by the grader)
    r = check_deductions(_graded(1.5, Q1_MISSING), Q1_STUDENT, None, 2.0)
    assert r.marks_awarded == 2.0 and r.missing_points == [] and "restored" in r.feedback


def test_real_deductions_stand():
    from app.formatter.tamil.answers import check_deductions
    key6 = "| அ) அவன் பள்ளிக்குச் சென்றாள். | சென்றாள் | சென்றான் |"
    assert check_deductions(_graded(2, ["சென்றான்"]), "அ) சென்றாள் சென்றாள்", key6, 3.0).marks_awarded == 2  # wrong ending
    key4 = "அ) திருக்குறளை இயற்றியவர் - திருவள்ளுவர்.\nஆ) தமிழின் பழமையான இலக்கண நூல் - தொல்காப்பியம்."
    student4 = "அ) திருக்குறளை இயற்றியவர் - திருவள்ளுவர்.\nஆ) தமிழன் பழமையான இலக்கண நூல் - தொல்காப்பியம்"
    assert check_deductions(_graded(1, [], "missed"), student4, key4, 2.0).marks_awarded == 1  # not every key word
    assert check_deductions(_graded(1, ["கல்வியின் மூலம் அறிவு பெறுதல்"]), "ஒழுக்கம் முக்கியம்.", Q1_KEY, 2.0).marks_awarded == 1


@pytest.mark.parametrize("question,kind", [
    ("கடிதம் எழுதுதல் (5)\nஉங்கள் பள்ளியில் நடைபெற்ற விழாவைப் பற்றி உங்கள் நண்பருக்குக் கடிதம் எழுதுக.", "letter"),
    ("கட்டுரை எழுதுதல் (5)\nகீழ்க்கண்ட தலைப்புகளில் ஏதேனும் ஒன்றைப் பற்றி கட்டுரை எழுதுக.", "essay"),
    ("கீழ்க்கண்ட தலைப்பில் மூன்று அல்லது நான்கு வாக்கியங்களில் எழுதுக. (3)\nதலைப்பு: ஒழுக்கத்தின் முக்கியத்துவம்", "paragraph"),
    ("கீழ்க்கண்ட வினாக்களுக்கு விடையளிக்கவும்.\nஅ) கல்வியின் சிறப்புகள் யாவை? (2)", "points"),
    ("இலக்கணம்:\nஅ) கீழ்க்கண்ட சொற்களின் எதிர்ச்சொற்களை எழுதுக. (1)", "points"),
])
def test_tamil_question_kind(question, kind):
    from app.formatter.tamil.rubric import question_kind
    assert question_kind(question) == kind


def test_open_question_rubric_keeps_criteria_and_notes_apart():
    from app.formatter.tamil.rubric import build_rubric
    key = ("கட்டுரை எழுதுதல் (5 மதிப்பெண்கள்)\n• மாதிரி விடை: சுற்றுச்சூழல் பாதுகாப்பு\nசுற்றுச்சூழல் என்பது ...\n"
           "குறிப்பு: வினா 10-இல் மாணவர்கள் தேர்ந்தெடுக்கும் தலைப்புக்கு ஏற்ற சரியான,")
    crit = ["தலைப்புக்குப் பொருத்தமான கருத்துகள் – 2 மதிப்பெண்கள்.", "கருத்துகளின் தொடர்ச்சி மற்றும் அமைப்பு – 1 மதிப்பெண்.",
            "மொழிநடை மற்றும் இலக்கணத் துல்லியம் – 2 மதிப்பெண்கள்.", "பொருத்தமான கட்டுரைக்கும் இதே மதிப்பீட்டுத் திட்டத்தைப் பயன்படுத்தலாம்."]
    r = build_rubric("கட்டுரை எழுதுதல் (5)", key, crit, 5.0)
    assert r.kind == "essay" and [c.marks for c in r.criteria] == [2, 1, 2] and not r.problems
    assert r.notes == ["குறிப்பு: வினா 10-இல் மாணவர்கள் தேர்ந்தெடுக்கும் தலைப்புக்கு ஏற்ற சரியான, "
                       "பொருத்தமான கட்டுரைக்கும் இதே மதிப்பீட்டுத் திட்டத்தைப் பயன்படுத்தலாம்."]
    bad = build_rubric("கடிதம் எழுதுதல் (5)", "கடிதம் எழுதுதல் (5 மதிப்பெண்கள்)\n• மாதிரி விடை:\nகுமார்.",
                       ["கடித வடிவம் – 1 மதிப்பெண்.", "பொருத்தமான உள்ளடக்கம் – 2 மதிப்பெண்கள்."], 5.0)
    assert bad.kind == "letter" and any("add up to 3" in p for p in bad.problems) and any("model letter" in p for p in bad.problems)


def test_point_question_rubric_from_the_keys_parts():
    from app.formatter.tamil.rubric import build_rubric
    pairs = build_rubric("இலக்கணம் (2)", "இலக்கணம் (2 மதிப்பெண்கள்)\nவிடைகள்:\nஅ) எதிர்ச்சொற்கள்: உயர்வு - தாழ்வு; நன்மை - தீமை\n"
                         "ஆ) பன்மை வடிவங்கள்: மரம் - மரங்கள்; மாணவன் - மாணவர்கள்", ["ஒவ்வொரு சரியான விடைக்கும் ½ மதிப்பெண்."], 2.0)
    assert [(c.part, c.kind, c.expected, c.marks) for c in pairs.criteria] == [
        ("அ", "exact", ["தாழ்வு"], 0.5), ("அ", "exact", ["தீமை"], 0.5),
        ("ஆ", "exact", ["மரங்கள்"], 0.5), ("ஆ", "exact", ["மாணவர்கள்"], 0.5)] and not pairs.problems
    table = build_rubric("பிழை திருத்துதல் (3)", "இலக்கணம் - பிழை திருத்துதல் (3 மதிப்பெண்கள்)\n• விடை:\n"
                         "| வாக்கியம் | பிழையான சொல் | சரியான சொல் |\n| --- | --- | --- |\n"
                         "| அ) அவன் பள்ளிக்குச் சென்றாள். | சென்றாள் | சென்றான் |\n"
                         "| ஆ) மரங்கள் நமக்கு நிழல் தருகிறான். | தருகிறான் | தருகின்றன |\n"
                         "| இ) மாணவர்கள் பாடம் படித்தான். | படித்தான் | படித்தார்கள் |",
                         ["ஒவ்வொரு சரியான பிழைத் திருத்தத்திற்கும் 1 மதிப்பெண்."], 3.0)
    assert [c.expected for c in table.criteria] == [["சென்றான்"], ["தருகின்றன"], ["படித்தார்கள்"]] and table.total == 3
    asked = build_rubric("குறுவிடைகள் (3)", "குறுவிடைகள் (3 மதிப்பெண்கள்)\n• விடைகள்:\n• அ) தாய்மொழியின் முக்கியத்துவம் என்ன? (1)\n"
                         "• விடை: தாய்மொழி நமது எண்ணங்களை வெளிப்படுத்த உதவுகிறது.\n• ஆ) இயற்கையை நாம் ஏன் பாதுகாக்க வேண்டும்? (2)\n"
                         "• விடை: இயற்கை நமக்குக் காற்று, நீர், உணவு ஆகியவற்றை வழங்குகிறது.",
                         ["தாய்மொழியின் முக்கியத்துவம் – 1 மதிப்பெண்.", "இயற்கையின் பயன்கள் மற்றும் பாதுகாப்பின் அவசியம் – 2 மதிப்பெண்கள்."], 3.0)
    assert [(c.part, c.kind, c.marks) for c in asked.criteria] == [("அ", "meaning", 1), ("ஆ", "meaning", 2)] and not asked.problems
    assert "எண்ணங்களை" in asked.criteria[0].text and "என்ன?" not in asked.criteria[0].text
    whole = build_rubric("கல்வியின் சிறப்புகள் (2)", Q1_KEY, ["1 மதிப்பெண் - கல்வியின் மூலம் அறிவு பெறுதல்.",
                         "1 மதிப்பெண் - ஒழுக்கம் அல்லது வாழ்க்கை முன்னேற்றத்தைக் குறிப்பிடுதல்."], 2.0)
    assert [c.marks for c in whole.criteria] == [1, 1] and whole.criteria[0].kind == "meaning"


def test_key_note_keeps_its_continuation_line():
    from app.formatter.tamil import format as tamil_format
    with paper_format.use(paper_format.TAMIL):
        answer, criteria = tamil_format.extract_criteria_from_block(
            "கட்டுரை எழுதுதல் (5 மதிப்பெண்கள்)\n• மாதிரி விடை: ...\n• மதிப்பீட்டுத் திட்டம்:\n"
            "• கருத்துகள் – 2 மதிப்பெண்கள்.\nகுறிப்பு: வினா 10-இல் மாணவர்கள் தேர்ந்தெடுக்கும் தலைப்புக்கு ஏற்ற சரியான,\n"
            "பொருத்தமான கட்டுரைக்கும் இதே மதிப்பீட்டுத் திட்டத்தைப் பயன்படுத்தலாம்.")
    assert criteria == ["கருத்துகள் – 2 மதிப்பெண்கள்."]
    assert answer.endswith("ஏற்ற சரியான, பொருத்தமான கட்டுரைக்கும் இதே மதிப்பீட்டுத் திட்டத்தைப் பயன்படுத்தலாம்.")
