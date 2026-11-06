"""The whole sheet is joined and matched by one text-only AI call that sees every page: an answer running onto the
next page stays one answer, a piece holding the end of one answer and the start of the next is cut where the next
starts, rough work is set aside. A reply that does not hold together leaves the sheet to the rules."""
from types import SimpleNamespace as NS

import pytest

from app.config import get_settings
from app.ocr.schemas import StudentPageResult
from app.services import ai_joiner
from app.services.ai_joiner import JoinResult

QS = [NS(id=f"q{n}", display_number=str(n), normalized_number=str(n), question_text=f"Question {n}", max_marks=3)
      for n in (23, 24, 25, 26)]


def _pages(*pages):
    return [({"page_number": n}, StudentPageResult.model_validate({"page_number": n, "answers": [
        {"question_number": lbl, "answer_text": text, "bbox": [0, 10 * i, 100, 10 * i + 8], "ocr_confidence": 0.9}
        for i, (lbl, text) in enumerate(blocks)]})) for n, blocks in enumerate(pages, 1)]


SHEET = _pages(
    [(None, "rough work 12 x 3 = 36 , 36 - 4 = 32"), ("23", "Let f(x) = x^2. f'(x) = 2x"), ("24", "Given |a| = sqrt 6, a.b = 1")],
    [(None, "so |b| = sqrt(35/6). Hence proved.\n25) Area = integral 0 to 2 of sqrt(4-x^2) dx = pi"),
     ("26(iii)", "The probability is 3/8")],
)


@pytest.fixture(autouse=True)
def on(monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_join_answers", True)


def _ask(reply):
    calls = []

    def ask(system, prompt):
        calls.append(prompt)
        return JoinResult.model_validate(reply)
    return ask, calls


GOOD = {"answers": [
    {"question": "23", "parts": ["p1.b2"]},
    {"question": "Q24", "parts": [{"block": "p1.b3"}, {"block": "p2.b1"}]},
    {"question": "25", "parts": [{"block": "p2.b1", "start": "25) Area"}]},
    {"question": "26(iii)", "parts": ["p2.b2"]}],
    "ignored": ["p1.b1"]}


def test_answers_are_joined_across_pages_and_cut_where_the_next_starts():
    ask, calls = _ask(GOOD)
    joined = ai_joiner.join(SHEET, QS, ask=ask)
    assert len(calls) == 1 and "[p2.b1] page 2, number written: -" in calls[0]
    got = {j.question.normalized_number: j.answer for j in joined if j.question is not None}
    assert got["24"].answer_text == "Given |a| = sqrt 6, a.b = 1\nso |b| = sqrt(35/6). Hence proved."
    assert got["24"].page_number == 1 and got["24"].raw_question_number == "24"
    assert got["25"].answer_text.startswith("25) Area") and got["25"].page_number == 2
    assert got["26"].answer_text == "The probability is 3/8"          # a part of a question scored as a whole
    ignored = [j for j in joined if j.ignored]
    assert len(ignored) == 1 and "rough work" in ignored[0].answer.answer_text
    assert [j.answer.position for j in joined] == [1, 2, 3, 4, 5]


def test_a_piece_the_reply_forgot_continues_the_answer_before_it():
    reply = {"answers": [{"question": "23", "parts": ["p1.b2"]}, {"question": "24", "parts": ["p1.b3"]},
                         {"question": "26", "parts": ["p2.b2"]}], "ignored": ["p1.b1"]}
    joined = ai_joiner.join(SHEET, QS, ask=_ask(reply)[0])
    q24 = next(j for j in joined if j.question is not None and j.question.id == "q24")
    assert "Hence proved" in q24.answer.answer_text and "25) Area" in q24.answer.answer_text


@pytest.mark.parametrize("reply", [
    {"answers": [{"question": "23", "parts": ["p9.b9"]}]},                                    # a piece that is not there
    {"answers": [{"question": "23", "parts": ["p1.b2"]}]},                                    # most of the sheet left out
    {"answers": [{"question": "99", "parts": ["p1.b2", "p1.b3", "p2.b1", "p2.b2"]}]},          # nothing matched
])
def test_a_reply_that_does_not_hold_together_leaves_the_sheet_to_the_rules(reply):
    assert ai_joiner.join(SHEET, QS, ask=_ask(reply)[0]) is None


def test_switched_off_or_failing_call_leaves_the_sheet_to_the_rules(monkeypatch):
    def boom(system, prompt):
        raise RuntimeError("network")
    assert ai_joiner.join(SHEET, QS, ask=boom) is None
    monkeypatch.setattr(get_settings(), "ai_join_answers", False)
    assert ai_joiner.join(SHEET, QS, ask=_ask(GOOD)[0]) is None


def test_ai_placed_answers_stay_placed_by_the_mapping_rules(client, auth, monkeypatch):
    """End to end on the pipeline: rows the joiner placed are MAPPED and confirmed, rough work is IGNORED."""
    from app.database import SessionLocal
    from app.models import AnswerSheetDocument, Evaluation, Exam, ExamQuestion, Student, StudentAnswer
    from app.services import pipeline
    from app.services.mapping_service import apply_student_mapping

    exam = client.post("/api/exams/simple", headers=auth, json={
        "name": "Joiner", "grade": "10", "section": "J", "subject_key": "10-science"}).json()
    db = SessionLocal()
    try:
        for n in (23, 24, 25, 26):
            db.add(ExamQuestion(exam_id=exam["id"], display_number=str(n), normalized_number=str(n),
                                question_text=f"Question {n}", max_marks=3, position=n))
        student = Student(class_id=db.get(Exam, exam["id"]).class_id, roll_number="J1", name="J One")
        sheet = AnswerSheetDocument(exam_id=exam["id"], original_filename="s.pdf", original_file="s.pdf",
                                    mime_type="application/pdf", file_size=1, status="READY", pages=[])
        db.add_all([student, sheet])
        db.flush()
        ev = Evaluation(exam_id=exam["id"], student_id=student.id, answer_sheet_id=sheet.id, status="DRAFT")
        db.add(ev)
        db.commit()
        doc = NS(id=sheet.id)
        monkeypatch.setattr(ai_joiner, "chat_structured", lambda system, user, schema, model=None: NS(
            parsed=JoinResult.model_validate(GOOD)))
        monkeypatch.setattr(pipeline, "_bbox_and_crop", lambda p, bb, wd, name: (bb, None))
        pipeline._build_student_answers(db, doc, db.get(Exam, exam["id"]), None, SHEET)
        rows = db.query(StudentAnswer).filter_by(evaluation_id=ev.id).order_by(StudentAnswer.position).all()
        assert [r.status for r in rows] == ["IGNORED", "MAPPED", "MAPPED", "MAPPED", "MAPPED"]
        assert all(r.mapping_confirmed for r in rows[1:])
        apply_student_mapping(db, ev)   # a later re-mapping keeps what the AI placed
        assert [r.normalized_number for r in rows[1:]] == ["23", "24", "25", "26"]
        assert all(r.status == "MAPPED" for r in rows[1:])
    finally:
        db.close()


@pytest.mark.parametrize("shape", [lambda a: a, lambda a: {"items": a}])
def test_the_answers_alone_or_under_another_name_are_read(shape):
    reply = JoinResult.model_validate(shape(GOOD["answers"]))
    assert [a.question for a in reply.answers] == ["23", "Q24", "25", "26(iii)"]


def test_a_piece_given_to_two_answers_without_a_cut_stays_with_the_number_written_on_it():
    reply = {"answers": [{"question": "23", "parts": ["p1.b2", "p1.b3"]}, {"question": "24", "parts": ["p1.b3"]},
                         {"question": "25", "parts": ["p2.b1"]}, {"question": "26", "parts": ["p2.b2"]}]}
    joined = ai_joiner.join(SHEET, QS, ask=_ask(reply)[0])
    by_q = {j.question.id: j.answer.answer_text for j in joined if j.question is not None}
    assert by_q["q24"].startswith("Given |a|") and "Given" not in by_q["q23"]


def test_a_piece_set_aside_that_looks_like_answer_text_goes_to_the_rules_instead():
    sheet = _pages([("23", "Let f(x) = x^2"), (None, "i) C2H6O + CH2 = C3H8O"), (None, "12 x 3 = 36")])
    reply = {"answers": [{"question": "23", "parts": ["p1.b1"]}], "ignored": ["p1.b2", "p1.b3"]}
    joined = ai_joiner.join(sheet, QS, ask=_ask(reply)[0])
    kinds = {j.blocks[0]: ("ignored" if j.ignored else j.question) for j in joined}
    assert kinds["p1.b3"] == "ignored"        # plain rough work is set aside
    assert kinds["p1.b2"] is None             # a sub-part is left for the rules to place, never dropped
