"""Autopilot: the school uploads the question paper, the answer key and an answer sheet, and nothing else. The
questions are accepted and verified, the key's mark mismatch is settled by the paper, the sheet's unclear answers
are matched by the AI, every question is graded, and the result is finalized; a teacher can reopen it."""
import pytest

from app.config import get_settings
from app.models import AuditLog
from app.database import SessionLocal
from .conftest import BEHAVIOUR, make_pdf, make_png


def j(r, code=None):
    if code is not None:
        assert r.status_code == code, f"{r.status_code}: {r.text}"
    return r.json()


@pytest.fixture
def autopilot(monkeypatch):
    monkeypatch.setattr(get_settings(), "autopilot", True)
    yield
    BEHAVIOUR["sheet"] = "main"


def test_upload_only_workflow_ends_with_a_finalized_result(client, auth, autopilot):
    c, h = client, auth
    cls = j(c.post("/api/classes", json={"name": "10-C"}, headers=h), 201)
    sub = j(c.post("/api/subjects", json={"name": "Botany"}, headers=h), 201)
    eid = j(c.post("/api/_test/legacy-exams", headers=h, json={
        "name": "Autopilot term", "academic_year": "2026-27", "class_id": cls["id"], "subject_id": sub["id"],
        "exam_type": "Unit", "total_marks": 15}), 201)["id"]

    BEHAVIOUR["garbage_pages"] = set()
    j(c.post(f"/api/exams/{eid}/question-paper", headers=h, files={"file": ("p.pdf", make_pdf(2), "application/pdf")}), 202)
    assert j(c.get(f"/api/exams/{eid}", headers=h))["status"] == "QUESTIONS_VERIFIED"   # no teacher step
    qs = j(c.get(f"/api/exams/{eid}/questions", headers=h))["questions"]
    assert all(q["verification_status"] == "VERIFIED" for q in qs)
    qid = {q["display_number"]: q["id"] for q in qs}

    j(c.post(f"/api/exams/{eid}/answer-key", headers=h, files={"file": ("k.png", make_png(), "image/png")}), 202)
    assert j(c.get(f"/api/exams/{eid}", headers=h))["status"] == "ANSWER_KEY_VERIFIED"  # the 4-vs-5 mismatch settled
    keys = j(c.get(f"/api/exams/{eid}/answer-keys", headers=h))["keys"]
    assert {k["exam_question_id"]: k["marks"] for k in keys}[qid["2"]] == 5               # the paper's marks stand
    assert [q["max_marks"] for q in j(c.get(f"/api/exams/{eid}/questions", headers=h))["questions"]] == [2, 5, 3, 5]

    BEHAVIOUR["sheet"] = "main"   # "3" is ambiguous and a stray line has no number: the AI settles both
    ev = j(c.post(f"/api/exams/{eid}/answer-sheets", headers=h, data={"student_name": "Ravi", "roll_number": "21"},
                  files={"file": ("s.pdf", make_pdf(1), "application/pdf")}), 202)
    d = j(c.get(f"/api/evaluations/{ev['id']}", headers=h))
    by_label = {a["raw_question_number"]: a for a in d["answers"]}
    assert by_label["3"]["exam_question_id"] == qid["3(a)"] and by_label["3"]["status"] in ("MAPPED", "EVALUATED", "APPROVED")
    assert by_label[None]["status"] == "IGNORED"
    # strict marking: 3(b) was given 8 of 5 on every try, so no mark is made up for it; that one sheet waits for the
    # teacher while everything else on it is approved
    items = {i["exam_question_id"]: i for i in d["items"]}
    assert d["evaluation"]["status"] != "FINALIZED"
    assert items[qid["3(b)"]]["status"] == "EVALUATION_ERROR" and items[qid["3(b)"]]["final_marks"] is None
    assert all(i["status"] == "APPROVED" for q, i in items.items() if q != qid["3(b)"])
    j(c.patch(f"/api/evaluations/{ev['id']}/items/{items[qid['3(b)']]['id']}",
              json={"final_marks": 4, "approve": True, "reason": "checked the sheet"}, headers=h), 200)
    j(c.post(f"/api/evaluations/{ev['id']}/finalize", headers=h), 200)
    assert j(c.get(f"/api/evaluations/{ev['id']}", headers=h))["evaluation"]["status"] == "FINALIZED"

    # a teacher can still change a mark: reopen, and the autopilot leaves the reopened result alone
    reopened = j(c.post(f"/api/evaluations/{ev['id']}/reopen", headers=h), 200)
    assert reopened["status"] != "FINALIZED"
    j(c.post(f"/api/evaluations/{ev['id']}/run", headers=h), 202)
    assert j(c.get(f"/api/evaluations/{ev['id']}", headers=h))["evaluation"]["status"] != "FINALIZED"
    db = SessionLocal()
    try:
        actions = {a.action for a in db.query(AuditLog).filter_by(exam_id=eid)}
    finally:
        db.close()
    assert {"autopilot_questions_verified", "autopilot_answer_key_verified", "autopilot_answers_mapped",
            "evaluation_reopened"} <= actions


def test_autopilot_off_keeps_the_manual_steps(client, auth):
    assert get_settings().autopilot is False   # the test settings: the other workflow tests drive each step
