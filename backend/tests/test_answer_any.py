""""Answer any N" sections: compulsory questions count, then the best of the rest up to N."""
from types import SimpleNamespace

from app.ocr.indic import blocks_to_result
from app.ocr.schemas import QuestionItem, QuestionPageResult
from app.cbse.common import choices
from app.cbse.common.paper import parse_question_paper_structure


def _q(label, text, marks=None):
    return QuestionItem(raw_question_number=label, question_text=text, marks=marks)


def _parse(*items):
    return parse_question_paper_structure([({"page_number": 1}, QuestionPageResult(page_number=1, questions=list(items)))])


def test_english_answer_any_with_a_compulsory_question():
    doc = _parse(_q(None, "Maximum Marks : 6"), _q(None, "SECTION B"),
                 _q(None, "Answer any three of the following. Question 5 is compulsory."),
                 *[_q(str(n), f"Explain topic {n}.", 2) for n in range(1, 6)])
    got = {q.display_number: (q.answer_any, q.compulsory) for q in doc.questions}
    assert got == {"1": (3, False), "2": (3, False), "3": (3, False), "4": (3, False), "5": (3, True)}
    assert choices.max_total(doc.questions) == 6                     # not 10: three questions count


def test_mark_rule_count_means_answer_any_only_when_the_section_has_more():
    doc = _parse(_q(None, "Maximum Marks : 4"), _q(None, "SECTION A"), _q(None, "2 x 2 = 4"),
                 *[_q(str(n), f"Define term {n}.", 2) for n in range(1, 4)])
    assert {q.answer_any for q in doc.questions} == {2}
    doc = _parse(_q(None, "Maximum Marks : 6"), _q(None, "SECTION A"), _q(None, "3 x 2 = 6"),
                 *[_q(str(n), f"Define term {n}.", 2) for n in range(1, 4)])
    assert {q.answer_any for q in doc.questions} == {None}           # 3 of 3: everything is answered


def test_note_about_one_questions_parts_is_not_a_section_rule():
    doc = _parse(_q(None, "Maximum Marks : 4"), _q(None, "SECTION A"), _q("1", "Define force.", 2),
                 _q(None, "Answer any two of the following parts:"), _q("2", "Explain inertia.", 2))
    assert {q.answer_any for q in doc.questions} == {None}


def test_tamil_section_as_on_the_sslc_paper():
    page = {"blocks": [
        {"order": 0, "type": "PageNumber", "label": "Folio", "text": "[▁மொத்த▁மதிப்பெண்கள்▁:▁6"},
        {"order": 1, "type": "SectionHeader", "label": "Section-title", "text": "பகுதி▁-▁II\n(மதிப்பெண்கள்▁:▁6)"},
        {"order": 2, "type": "SectionHeader", "label": "Sub-section-title", "text": "பிரிவு▁-▁1"},
        {"order": 3, "type": "Text", "label": "Paragraph",
         "text": "குறிப்பு▁:▁எவையேனும்▁மூன்று▁வினாக்களுக்கு▁மட்டும்▁விடையளிக்கவும்.▁4▁-வது\nவினாவிற்குக்▁கட்டாயமாக▁விடையளிக்கவும்.▁▁▁▁3x2=6"},
        *[{"order": 3 + n, "type": "Text", "label": "Question", "text": f"{n}.▁வினா▁{n}▁எழுதுக."} for n in range(1, 6)],
    ]}
    doc = parse_question_paper_structure([({"page_number": 1}, blocks_to_result(page, QuestionPageResult, 1))])
    got = {q.display_number: (q.max_marks, q.answer_any, q.compulsory) for q in doc.questions}
    assert got == {"1": (2, 3, False), "2": (2, 3, False), "3": (2, 3, False), "4": (2, 3, True), "5": (2, 3, False)}
    assert choices.max_total(doc.questions) == 6


def test_student_total_counts_compulsory_then_best_answers():
    q = lambda i, c=False: SimpleNamespace(id=i, section="B", answer_any=3, compulsory=c, choice_group=None, max_marks=2)  # noqa: E731
    qs = [q("q1"), q("q2"), q("q3"), q("q4"), q("q5", True)]
    marks = {"q1": 2, "q2": 0.5, "q3": 1.5, "q4": 2, "q5": 0}         # answered all five, did badly on the compulsory one
    assert [x.id for x in choices.counted(qs, marks)] == ["q1", "q4", "q5"]
    assert [x.id for x in choices.counted(qs, {"q2": 2, "q5": 1})] == ["q1", "q2", "q5"]   # answered two: both count


def test_either_or_inside_an_answer_any_section_is_one_question():
    q = lambda i, g=None, c=False: SimpleNamespace(id=i, section="B", answer_any=2, compulsory=c, choice_group=g, max_marks=3)  # noqa: E731
    qs = [q("q32"), q("q33"), q("q34a", "34", True), q("q34b", "34", True)]
    assert len(choices.units(qs)) == 3
    assert choices.max_total(qs) == 6                                # 34 (either alternative) + the better of 32/33
