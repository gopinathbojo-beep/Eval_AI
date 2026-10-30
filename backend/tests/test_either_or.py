"""Either/or questions ("(a) ... OR (b) ...", "(அ) ... அல்லது (ஆ) ..."): one question per alternative, counted once."""
from types import SimpleNamespace

from sqlalchemy import create_engine, inspect, text

from app.ocr.indic import blocks_to_result
from app.ocr.schemas import AnswerKeyItem, AnswerKeyPageResult, QuestionItem, QuestionPageResult
from app.cbse.formatter.common import choices
from app.cbse.formatter.common.paper import parse_question_paper_structure
from app.cbse.formatter.common.keys import segment_answer_keys


def _paper(*items, total=None):
    qs = ([QuestionItem(raw_question_number=None, question_text=f"Maximum Marks : {total}")] if total else []) + list(items)
    return parse_question_paper_structure([({"page_number": 1}, QuestionPageResult(page_number=1, questions=qs))])


def test_english_or_inside_one_question():
    doc = _paper(QuestionItem(raw_question_number="1", question_text="Define force.", marks=2),
                 QuestionItem(raw_question_number="2", question_text="(a) Explain Newton's first law.\nOR\n(b) Describe inertia.",
                              marks=5), total=7)
    got = {q.display_number: (q.max_marks, q.choice_group) for q in doc.questions}
    assert got == {"1": (2, None), "2(a)": (5, "2"), "2(b)": (5, "2")}
    assert [q.normalized_number for q in doc.questions] == ["1", "2(a)", "2(b)"]
    assert choices.max_total(doc.questions) == 7


def test_english_parts_already_apart():
    doc = _paper(QuestionItem(raw_question_number="3(a)", question_text="Explain osmosis.\nOR", marks=3),
                 QuestionItem(raw_question_number="3(b)", question_text="Explain diffusion.", marks=3), total=3)
    assert [(q.normalized_number, q.choice_group, q.question_text) for q in doc.questions] == [
        ("3(a)", "3", "Explain osmosis."), ("3(b)", "3", "Explain diffusion.")]


def test_tamil_allathu_as_on_the_sslc_paper():
    page = {"blocks": [
        {"order": 0, "type": "Text", "text": "[ மொத்த மதிப்பெண்கள் : 5"},
        {"order": 1, "type": "Text", "text": "பகுதி - IV\n(மதிப்பெண்கள் : 5)"},
        {"order": 2, "type": "Text", "text": "குறிப்பு : அனைத்து வினாக்களுக்கும் விடையளிக்கவும். 1x5=5"},
        {"order": 3, "type": "Text", "text": "1. (அ) கூத்தனைக் கூத்தன் ஆற்றுப்படுத்தலைக் கூத்தராற்றுப்படை எவ்வாறு காட்டுகிறது ?"},
        {"order": 4, "type": "Text", "text": "அல்லது"},
        {"order": 5, "type": "Text", "text": "(ஆ) வள்ளுவம், சிறந்த அமைச்சருக்குக் கூறிய இலக்கணங்கள் நமக்கும் பொருந்துவதைக் குறள்வழி விளக்குக."},
    ]}
    doc = parse_question_paper_structure([({"page_number": 1}, blocks_to_result(page, QuestionPageResult, 1))])
    got = [(q.display_number, q.normalized_number, q.max_marks, q.choice_group) for q in doc.questions]
    assert got == [("1(அ)", "1(a)", 5, "1"), ("1(ஆ)", "1(b)", 5, "1")]
    assert "அல்லது" not in doc.questions[0].question_text + doc.questions[1].question_text


def test_one_alternative_counts_and_the_higher_mark_wins():
    q = lambda i, g=None: SimpleNamespace(id=i, choice_group=g, max_marks=5)  # noqa: E731
    qs = [q("q1"), q("q2a", "2"), q("q2b", "2")]
    assert [x.id for x in choices.counted(qs, {"q1": 4, "q2a": None, "q2b": 3})] == ["q1", "q2b"]   # answered one
    assert [x.id for x in choices.counted(qs, {"q1": 4, "q2a": 2, "q2b": 3.5})] == ["q1", "q2b"]    # answered both
    assert [x.id for x in choices.counted(qs, {})] == ["q1", "q2a"]
    assert choices.max_total(qs) == 10


def test_answer_key_for_the_choice_is_split_per_alternative():
    exam_qs = [SimpleNamespace(display_number="2(a)", normalized_number="2(a)", choice_group="2", max_marks=5),
               SimpleNamespace(display_number="2(b)", normalized_number="2(b)", choice_group="2", max_marks=5)]
    page = AnswerKeyPageResult(page_number=1, answers=[AnswerKeyItem(
        question_number="2", answer_text="(a) A body stays at rest unless a force acts.\nOR\n(b) Inertia resists change.", marks=5)])
    keys = segment_answer_keys([({"page_number": 1}, page)], exam_qs)
    assert [(k.normalized_number, k.answer_text, k.marks) for k in keys] == [
        ("2(a)", "(a) A body stays at rest unless a force acts.", 5), ("2(b)", "(b) Inertia resists change.", 5)]


def test_startup_adds_the_column_to_an_existing_database(tmp_path, monkeypatch):
    from app import database
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE exam_questions (id VARCHAR(36) PRIMARY KEY, max_marks FLOAT)"))
    monkeypatch.setattr(database, "engine", eng)
    database._add_missing_columns()
    database._add_missing_columns()                                  # a second start changes nothing
    assert "choice_group" in {c["name"] for c in inspect(eng).get_columns("exam_questions")}


def test_or_as_its_own_item():
    doc = _paper(QuestionItem(raw_question_number="1", question_text="Define force.", marks=2),
                 QuestionItem(raw_question_number="2", question_text="(a) Explain Newton's first law.", marks=5),
                 QuestionItem(raw_question_number=None, question_text="OR"),
                 QuestionItem(raw_question_number="(b)", question_text="Describe inertia with an example.", marks=5),
                 total=7)
    assert [(q.display_number, q.choice_group, q.question_text) for q in doc.questions] == [
        ("1", None, "Define force."), ("2(a)", "2", "(a) Explain Newton's first law."),
        ("2(b)", "2", "(b) Describe inertia with an example.")]


def test_or_between_parts_numbered_apart():
    doc = _paper(QuestionItem(raw_question_number="3(a)", question_text="Explain osmosis.", marks=5),
                 QuestionItem(raw_question_number=None, question_text="OR"),
                 QuestionItem(raw_question_number="3(b)", question_text="Explain diffusion.", marks=5), total=5)
    assert [(q.normalized_number, q.choice_group, q.question_text) for q in doc.questions] == [
        ("3(a)", "3", "Explain osmosis."), ("3(b)", "3", "Explain diffusion.")]


def test_finalized_total_counts_the_better_alternative(monkeypatch):
    from app.services import evaluation_service

    class Rows:
        def __init__(self, rows):
            self.rows = rows

        def filter_by(self, **_):
            return self

        def all(self):
            return self.rows

    items = [SimpleNamespace(exam_question_id=i, final_marks=m) for i, m in (("q1", 2), ("q2a", 3), ("q2b", 4.5))]
    db = SimpleNamespace(query=lambda _model: Rows(items), commit=lambda: None)
    qs = [SimpleNamespace(id="q1", choice_group=None, max_marks=2),
          SimpleNamespace(id="q2a", choice_group="2", max_marks=5), SimpleNamespace(id="q2b", choice_group="2", max_marks=5)]
    monkeypatch.setattr(evaluation_service, "exam_questions", lambda _db, _exam_id: qs)
    ev = SimpleNamespace(id="ev", exam_id="ex")
    evaluation_service.finalize(db, ev)                              # the student answered both: the 4.5 counts
    assert (ev.total_marks, ev.maximum_marks, ev.percentage) == (6.5, 7, 92.86)
