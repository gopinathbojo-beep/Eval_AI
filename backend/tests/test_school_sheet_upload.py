"""The exam's Upload tab: the school sends sheets itself, by typed roll number or letting the sheet say whose it is."""
import uuid

from .conftest import BEHAVIOUR, make_pdf, make_png
from .test_bulk_sheets_and_early_key import _exam_ready_for_sheets, j
from .test_uploader_scan_flow import _grading_calls, _roll


def _exam(client, auth):
    cls, eid = _exam_ready_for_sheets(client, auth, f"10-Up{uuid.uuid4().hex[:4]}")
    j(client.post(f"/api/exams/{eid}/finalize-setup", headers=auth), 200)
    return cls, eid


def _send(client, auth, eid, roll=None, written=None):
    BEHAVIOUR["identities"] = [written or {}]
    data = {"roll_number": roll} if roll is not None else {}
    return client.post(f"/api/exams/{eid}/answer-sheets", headers=auth, data=data,
                       files={"file": ("sheet.pdf", make_pdf(1), "application/pdf")})


def _doc(doc_id):
    from app.database import SessionLocal
    from app.models import AnswerSheetDocument
    with SessionLocal() as db:
        return db.get(AnswerSheetDocument, doc_id)


def test_a_typed_roll_decides_the_student_and_the_sheet_is_graded(client, auth, monkeypatch):
    graded = _grading_calls(monkeypatch)
    _, eid = _exam(client, auth)
    sheet = j(_send(client, auth, eid, " 61a ", {"roll_number": "61A"}), 202)
    doc_id = sheet["document"]["id"]
    assert _roll(doc_id) == "61A" and doc_id in graded        # upper-cased, like the uploader app
    assert sheet["student"]["name"] == "Roll 61A"
    assert _doc(doc_id).identity["roll_check"]["status"] == "MATCH"


def test_a_typed_roll_that_differs_from_the_sheet_waits_for_the_school(client, auth, monkeypatch):
    graded = _grading_calls(monkeypatch)
    _, eid = _exam(client, auth)
    doc_id = j(_send(client, auth, eid, "62", {"roll_number": "26"}), 202)["document"]["id"]
    assert _doc(doc_id).identity["roll_check"] == {"typed": "62", "written": "26", "status": "MISMATCH"}
    assert doc_id not in graded
    j(client.post(f"/api/answer-sheets/{doc_id}/roll-check", headers=auth, json={"use": "typed"}), 202)
    assert doc_id in graded


def test_no_roll_reads_the_student_from_the_sheet(client, auth):
    _, eid = _exam(client, auth)
    BEHAVIOUR["sheet"] = "main"
    doc = j(_send(client, auth, eid, "  "), 202)                 # nothing written either: held for the school
    assert doc["id"] in {d["id"] for d in j(client.get(f"/api/exams/{eid}/answer-sheets/unassigned", headers=auth), 200)}


def test_one_answer_sheet_per_roll_and_only_real_rolls(client, auth):
    _, eid = _exam(client, auth)
    j(_send(client, auth, eid, "63"), 202)
    assert _send(client, auth, eid, "63").status_code == 409
    assert _send(client, auth, eid, "6 3!").status_code == 400


def test_a_name_without_a_roll_is_still_refused(client, auth):
    _, eid = _exam(client, auth)
    r = client.post(f"/api/exams/{eid}/answer-sheets", headers=auth, data={"student_name": "Asha"},
                    files={"file": ("sheet.pdf", make_pdf(1), "application/pdf")})
    assert r.status_code == 400


def test_photos_of_a_student_become_one_sheet(client, auth, monkeypatch):
    graded = _grading_calls(monkeypatch)
    _, eid = _exam(client, auth)
    BEHAVIOUR["identities"] = [{}]
    photos = [("files", (f"p{i}.png", make_png(), "image/png")) for i in range(1, 4)]
    r = client.post(f"/api/exams/{eid}/answer-sheets/photos", headers=auth, data={"roll_number": "64"}, files=photos)
    doc_id = j(r, 202)["document"]["id"]
    assert len(_doc(doc_id).pages) == 3 and doc_id in graded and _roll(doc_id) == "64"


def test_photos_without_a_roll_are_one_sheet_read_for_the_student(client, auth):
    _, eid = _exam(client, auth)
    BEHAVIOUR["identities"] = [{}]
    photos = [("files", (f"p{i}.png", make_png(), "image/png")) for i in range(1, 3)]
    doc = j(client.post(f"/api/exams/{eid}/answer-sheets/photos", headers=auth, files=photos), 202)
    assert len(_doc(doc["id"]).pages) == 2 and _doc(doc["id"]).student_id is None


def test_sheets_are_refused_before_the_key_is_verified(client, auth):
    cls = j(client.post("/api/classes", json={"name": f"10-Up{uuid.uuid4().hex[:4]}"}, headers=auth), 201)
    sub = j(client.post("/api/subjects", json={"name": f"Bio {uuid.uuid4().hex[:4]}"}, headers=auth), 201)
    eid = j(client.post("/api/_test/legacy-exams", headers=auth, json={
        "name": "Early", "academic_year": "2026-27", "class_id": cls["id"], "subject_id": sub["id"],
        "exam_type": "Unit", "total_marks": 15}), 201)["id"]
    assert _send(client, auth, eid, "65").status_code == 409
    r = client.post(f"/api/exams/{eid}/answer-sheets/photos", headers=auth, data={"roll_number": "65"},
                    files=[("files", ("p.png", make_png(), "image/png"))])
    assert r.status_code == 409
