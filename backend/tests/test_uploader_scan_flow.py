"""Page-by-page scanning by an uploader: the typed roll number decides the student, pages added (retries replace)."""
import uuid

from fastapi.testclient import TestClient

from .conftest import BEHAVIOUR, make_png
from .test_bulk_sheets_and_early_key import _exam_ready_for_sheets, j

BROWSER = {"X-Requested-With": "EvalAI"}


def _uploader(client, auth):
    cls, eid = _exam_ready_for_sheets(client, auth, f"10-Scan{uuid.uuid4().hex[:4]}")
    j(client.post(f"/api/exams/{eid}/finalize-setup", headers=auth), 200)
    code = j(client.post(f"/api/exams/{eid}/uploader-codes", headers=auth, json={"labels": ["Hall"]}), 201)[0]["code"]
    up = TestClient(client.app)
    j(up.post("/api/auth/code-login", headers=BROWSER, json={"code": code}), 200)
    return up, cls, eid


def _page(name="p.png"):
    return {"page": (name, make_png(), "image/png")}


def _start(up, roll, cover=None):
    # cover: what the details page says; never read, the typed roll number alone decides the student
    BEHAVIOUR["identities"] = [cover or {}]
    return up.post("/api/uploader/sheets", headers=BROWSER, data={"roll_number": roll}, files=_page())


def _sheet(eid, sid):
    from app.database import SessionLocal
    from app.models import AnswerSheetDocument
    with SessionLocal() as db:
        return db.get(AnswerSheetDocument, sid)


def test_scan_flow_uses_the_typed_roll_and_grades(client, auth):
    up, cls, eid = _uploader(client, auth)
    BEHAVIOUR["sheet"] = "main"
    sheet = j(_start(up, "31", {"name": "Lakshmi", "roll_number": "031", "pages_written": 3}), 201)
    assert sheet["pages"] == 1 and sheet["status"] == "CAPTURING"
    assert "cover" not in _sheet(eid, sheet["id"]).identity  # the details page is not read to identify the student
    # still scanning: not offered to the school as an unassigned sheet yet
    assert all(d["id"] != sheet["id"] for d in j(client.get(f"/api/exams/{eid}/answer-sheets/unassigned", headers=auth), 200))
    assert j(up.post(f"/api/uploader/sheets/{sheet['id']}/pages", headers=BROWSER, data={"index": 2}, files=_page()), 200)["pages"] == 2
    # a retry of page 2 replaces it instead of adding a page
    assert j(up.post(f"/api/uploader/sheets/{sheet['id']}/pages", headers=BROWSER, data={"index": 2}, files=_page()), 200)["pages"] == 2
    assert j(up.post(f"/api/uploader/sheets/{sheet['id']}/pages", headers=BROWSER, data={"index": 3}, files=_page()), 200)["pages"] == 3
    mine = {u["id"]: u for u in j(up.get("/api/uploader/me"), 200)["uploads"]}
    assert mine[sheet["id"]]["status"] == "CAPTURING" and mine[sheet["id"]]["pages"] == 3 and mine[sheet["id"]]["roll_number"] == "31"
    done = j(up.post(f"/api/uploader/sheets/{sheet['id']}/finish", headers=BROWSER), 202)
    assert done["pages"] == 3
    doc = _sheet(eid, sheet["id"])
    assert doc.student_id and len(doc.pages) == 3          # one PDF of three pages, read by the regular pipeline
    assert doc.identity["match"] == "AUTO"
    results = j(client.get(f"/api/exams/{eid}/results", headers=auth), 200)
    ev = next(e for e in results if e["student"]["roll_number"] == "31")
    assert ev["status"] != "DRAFT"
    # page uploads after finishing are refused; the same roll cannot start again
    assert up.post(f"/api/uploader/sheets/{sheet['id']}/pages", headers=BROWSER, data={"index": 4}, files=_page()).status_code == 409
    assert _start(up, "31").status_code == 409


def test_typed_roll_wins_over_what_the_sheet_says(client, auth, monkeypatch):
    from app.services import student_identity
    up, cls, eid = _uploader(client, auth)
    read = []
    monkeypatch.setattr(student_identity, "_read_page", lambda *a, **k: read.append(a) or {})
    # the details page would say roll 42 and 6 pages; neither is checked
    sheet = j(_start(up, "41", {"roll_number": "42", "pages_written": 6}), 201)
    j(up.post(f"/api/uploader/sheets/{sheet['id']}/finish", headers=BROWSER), 202)
    doc = _sheet(eid, sheet["id"])
    assert doc.student_id and doc.status != "NEEDS_STUDENT" and not read
    results = j(client.get(f"/api/exams/{eid}/results", headers=auth), 200)
    assert any(e["student"]["roll_number"] == "41" for e in results)


def test_page_gaps_duplicates_and_discard(client, auth):
    up, cls, eid = _uploader(client, auth)
    sheet = j(_start(up, "61", {"roll_number": "61"}), 201)
    assert _start(up, "61", {}).status_code == 409                   # already being scanned
    assert up.post("/api/uploader/sheets", headers=BROWSER, data={"roll_number": "6 1"}, files=_page()).status_code == 400
    assert up.post(f"/api/uploader/sheets/{sheet['id']}/pages", headers=BROWSER, data={"index": 1}, files=_page()).status_code == 422
    j(up.post(f"/api/uploader/sheets/{sheet['id']}/pages", headers=BROWSER, data={"index": 3}, files=_page()), 200)
    r = up.post(f"/api/uploader/sheets/{sheet['id']}/finish", headers=BROWSER)
    assert r.status_code == 400 and r.json()["message"] == "Page 2 is missing. Scan it again before finishing."
    folder = __import__("app.documents.storage", fromlist=["abs_path"]).abs_path(_sheet(eid, sheet["id"]).original_file).parent
    assert up.delete(f"/api/uploader/sheets/{sheet['id']}", headers=BROWSER).status_code == 204
    assert _sheet(eid, sheet["id"]) is None and not folder.exists()
    # another uploader code cannot touch this exam's sheets
    other, _, _ = _uploader(client, auth)
    mine = j(_start(up, "62", {"roll_number": "62"}), 201)
    assert other.post(f"/api/uploader/sheets/{mine['id']}/finish", headers=BROWSER).status_code == 404


def test_papers_tab_lists_every_sheet_of_the_exam(client, auth):
    """The uploader's Papers tab shows all sheets of the exam by roll number, with who sent them; no marks."""
    from .test_school_only import BROWSER
    from .test_bulk_sheets_and_early_key import _exam_ready_for_sheets, j
    from .conftest import BEHAVIOUR, make_png
    from fastapi.testclient import TestClient
    cls, eid = _exam_ready_for_sheets(client, auth, "10-Papers")
    j(client.post(f"/api/exams/{eid}/finalize-setup", headers=auth), 200)
    a, b = j(client.post(f"/api/exams/{eid}/uploader-codes", headers=auth, json={"labels": ["A", "B"]}), 201)
    BEHAVIOUR["sheet"] = "main"
    with TestClient(client.app) as up_a, TestClient(client.app) as up_b:
        j(up_a.post("/api/auth/code-login", headers=BROWSER, json={"code": a["code"]}), 200)
        j(up_b.post("/api/auth/code-login", headers=BROWSER, json={"code": b["code"]}), 200)
        j(up_b.put("/api/uploader/name", headers=BROWSER, json={"name": "Priya Devi"}), 200)
        for up, roll in ((up_a, "7"), (up_b, "3")):
            j(up.post("/api/uploader/answer-sheets", headers=BROWSER, data={"one_sheet": "true", "roll_number": roll},
                      files=[("files", ("p.png", make_png(), "image/png"))]), 202)
        papers = j(up_a.get("/api/uploader/papers"), 200)["papers"]
    assert [p["roll_number"] for p in papers] == ["3", "7"]
    assert [p["mine"] for p in papers] == [False, True] and papers[0]["uploaded_by"] == "Priya Devi"
    assert all("total_marks" not in p and "percentage" not in p for p in papers)


def test_bell_lists_sheets_needing_a_person(client, auth):
    """A held sheet (its roll number got another sheet meanwhile) shows in the bell with a link to fix it."""
    from .test_school_only import BROWSER
    from .test_bulk_sheets_and_early_key import _exam_ready_for_sheets, j
    from .conftest import make_png
    from fastapi.testclient import TestClient
    cls, eid = _exam_ready_for_sheets(client, auth, "10-Bell")
    j(client.post(f"/api/exams/{eid}/finalize-setup", headers=auth), 200)
    code = j(client.post(f"/api/exams/{eid}/uploader-codes", headers=auth, json={"count": 1}), 201)[0]
    with TestClient(client.app) as up:
        j(up.post("/api/auth/code-login", headers=BROWSER, json={"code": code["code"]}), 200)
        sheet = j(up.post("/api/uploader/sheets", headers=BROWSER, data={"roll_number": "25"},
                          files=[("page", ("p.png", make_png(), "image/png"))]), 201)
        # while it is being scanned, a PDF for the same roll number is sent and graded
        j(up.post("/api/uploader/answer-sheets", headers=BROWSER, data={"one_sheet": "true", "roll_number": "25"},
                  files=[("files", ("p.png", make_png(), "image/png"))]), 202)
        j(up.post(f"/api/uploader/sheets/{sheet['id']}/finish", headers=BROWSER), 202)
    bell = j(client.get("/api/notifications", headers=auth), 200)
    [held] = [i for i in bell["items"] if i["kind"] == "sheet_held" and i["exam_id"] == eid]
    assert held["title"].startswith("Roll 25") and "already has an answer sheet" in held["detail"]
    assert held["link"] == f"/exams/{eid}/submissions"
    # the exam cannot be finalized while that sheet has no student: it could never be graded or assigned afterwards
    r = client.post(f"/api/exams/{eid}/finalize", headers=auth)
    assert r.status_code == 400
    assert {"question": "Roll 25", "reason": "Answer sheet is not linked to a student yet"} in r.json()["issues"]
