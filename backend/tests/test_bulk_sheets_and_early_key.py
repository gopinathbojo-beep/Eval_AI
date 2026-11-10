from io import BytesIO
from openpyxl import Workbook, load_workbook
from .conftest import BEHAVIOUR, make_pdf, make_png


def j(r, code=None):
    if code is not None:
        assert r.status_code == code, f"{r.status_code}: {r.text}"
    return r.json()


def _xlsx(rows) -> bytes:
    wb = Workbook()
    for r in rows:
        wb.active.append(r)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _exam_ready_for_sheets(c, h, class_name):
    """Question paper + answer key uploaded together; one by one: the key waits unread until the questions are
    extracted (not verified), then is read and built."""
    cls = j(c.post("/api/classes", json={"name": class_name}, headers=h), 201)
    sub = j(c.post("/api/subjects", json={"name": f"Biology {class_name}"}, headers=h), 201)
    eid = j(c.post("/api/_test/legacy-exams", headers=h, json={"name": "Bulk", "academic_year": "2026-27", "class_id": cls["id"],
                                                   "subject_id": sub["id"], "exam_type": "Unit", "total_marks": 15}), 201)["id"]
    key = j(c.post(f"/api/exams/{eid}/answer-key", headers=h, files={"file": ("key.png", make_png(), "image/png")}), 202)
    assert key["status"] == "WAITING"                                                    # unread, no questions yet
    j(c.post(f"/api/exams/{eid}/question-paper", headers=h, files={"file": ("paper.pdf", make_pdf(2), "application/pdf")}), 202)
    assert j(c.get(f"/api/exams/{eid}/answer-key", headers=h))["status"] == "READY"     # built before any verification
    j(c.post(f"/api/exams/{eid}/questions/accept-valid", headers=h), 200)
    j(c.post(f"/api/exams/{eid}/questions/verify", headers=h), 200)
    ks = j(c.get(f"/api/exams/{eid}/answer-keys", headers=h))["keys"]
    assert len(ks) == 4 and all(k["exam_question_id"] for k in ks)          # mapped onto the verified questions
    k2 = next(k for k in ks if k["raw_question_number"] == "2")
    j(c.patch(f"/api/answer-keys/{k2['id']}", json={"mismatch_resolution": "keep_question_marks"}, headers=h), 200)
    j(c.post(f"/api/exams/{eid}/answer-keys/verify", headers=h), 200)
    return cls, eid


def test_bulk_sheets_use_the_roll_number_and_name_read_from_the_sheet(client, auth):
    """No student list is matched: the roll number and name written on the sheet are used as they are."""
    c, h = client, auth
    cls, eid = _exam_ready_for_sheets(c, h, "10-BulkA")
    BEHAVIOUR["sheet"] = "main"
    BEHAVIOUR["identities"] = [
        {"name": "Asha", "roll_number": "01", "registration_number": "reg 001"},     # roll used as written
        {"name": "Ravi Kumar", "registration_number": "R-77"},                       # no roll: registration number
        {"name": "Priya", "roll_number": "01"},                                     # same roll again -> hold
        {}, {},                                                                     # nothing legible -> hold
    ]
    files = [("files", (f"s{i}.pdf", make_pdf(1), "application/pdf")) for i in range(4)]
    up = j(c.post(f"/api/exams/{eid}/answer-sheets/bulk", headers=h, files=files), 202)
    assert up["uploaded"] == 4

    sheets = j(c.get(f"/api/exams/{eid}/answer-sheets", headers=h))
    assert {(s["student"]["roll_number"], s["student"]["name"]) for s in sheets} == {("01", "Asha"), ("R-77", "Ravi Kumar")}
    assert all(s["detected_answers"] > 0 for s in sheets)
    held = j(c.get(f"/api/exams/{eid}/answer-sheets/unassigned", headers=h))
    assert [d["status"] for d in held] == ["NEEDS_STUDENT", "NEEDS_STUDENT"]
    notes = sorted(d["identity"]["note"] for d in held)
    assert "No roll number or registration number" in notes[0]
    assert "Roll number 01 already has an answer sheet" in notes[1]
    for d in held:
        j(c.delete(f"/api/answer-sheets/{d['id']}", headers=h), None)

    # an unreadable upload in a batch rejects the batch before anything is stored
    bad = [("files", ("ok.pdf", make_pdf(1), "application/pdf")), ("files", ("bad.pdf", b"nope", "application/pdf"))]
    r = c.post(f"/api/exams/{eid}/answer-sheets/bulk", headers=h, files=bad)
    assert r.status_code == 400 and "bad.pdf" in r.json()["message"]
    assert j(c.get(f"/api/exams/{eid}/answer-sheets/unassigned", headers=h)) == []


def test_bulk_sheets_are_graded_in_turn_and_finalized_together(client, auth):
    c, h = client, auth
    cls, eid = _exam_ready_for_sheets(c, h, "10-BulkB")
    mk = lambda name, roll: j(c.post("/api/students", headers=h, json={  # noqa: E731
        "name": name, "roll_number": roll, "class_id": cls["id"]}), 201)
    clean, messy, unsure = mk("Clean Kid", "1"), mk("Messy Kid", "2"), mk("Unsure Kid", "3")

    for sheet, roll in (("clean", "1"), ("main", "2"), ("unsure", "3")):
        BEHAVIOUR["sheet"], BEHAVIOUR["identities"] = sheet, [{"roll_number": roll}]
        j(c.post(f"/api/exams/{eid}/answer-sheets/bulk", headers=h,
                 files=[("files", (f"{sheet}.pdf", make_pdf(1), "application/pdf"))]), 202)
    BEHAVIOUR["sheet"] = "main"

    # every sheet was read and the clean ones graded without the teacher starting anything
    sheets = {s["student"]["id"]: s for s in j(c.get(f"/api/exams/{eid}/answer-sheets", headers=h))}
    assert sheets[clean["id"]]["run_status"] == "DONE" and sheets[unsure["id"]]["run_status"] == "DONE"
    assert sheets[messy["id"]]["run_status"] == "IDLE"                          # unmapped answer: left for the teacher

    summ = j(c.get(f"/api/exams/{eid}/review-summary", headers=h), 200)
    assert summ["processing"] == 0 and summ["total"] == 3 and summ["unassigned"] == 0
    # an unsure AI mark is not a review (only unmapped answers and marks mismatches are): that sheet is ready too
    assert sorted(r["student"]["id"] for r in summ["ready"]) == sorted([clean["id"], unsure["id"]])
    review = {r["student"]["id"]: r["reasons"] for r in summ["needs_review"]}
    assert set(review) == {messy["id"]}
    assert any("Fix the answer mapping" in x["reason"] for x in review[messy["id"]])
    assert not any(x["reason"] == "Not evaluated yet" for x in review[messy["id"]])

    done = j(c.post(f"/api/exams/{eid}/finalize-ready", headers=h), 200)
    assert done["finalized_now"] == 2 and done["finalized"] == 2 and done["ready"] == [] and len(done["needs_review"]) == 1
    res = j(c.get(f"/api/evaluations/{sheets[clean['id']]['id']}/result", headers=h))
    assert res["finalized"] and res["total_marks"] == res["maximum_marks"]
    r = c.post(f"/api/exams/{eid}/finalize-ready", headers=h)
    assert r.status_code == 400 and r.json()["code"] == "NOTHING_READY"


def test_student_import_export(client, auth):
    c, h = client, auth
    data = _xlsx([["Class list"], ["Student Name", "Roll No", "Reg No", "Class", "Sec"],
                  ["Lakshmi", 1, "IMP-1", "12", "ImportA"], ["Arun", 2, "IMP-2", "12", "ImportB"], ["Bala", 3, "IMP-3", "12", "ImportA"],
                  ["Dup Roll", 1, None, "12", "ImportA"], ["", "", "", "", ""], ["No Roll", None, None, "12", None]])
    r = j(c.post("/api/students/import", headers=h, files={"file": ("s.xlsx", data, "application/octet-stream")}), 200)
    assert r["created"] == 3 and r["updated"] == 0 and [e["row"] for e in r["errors"]] == [6, 8]
    assert not r["committed"]
    data = _xlsx([["Name", "Roll Number", "Registration Number", "Class", "Section"],
                  ["Lakshmi", 1, "IMP-1", "12", "ImportA"], ["Arun", 2, "IMP-2", "12", "ImportB"], ["Bala", 3, "IMP-3", "12", "ImportA"]])
    assert j(c.post("/api/students/import", headers=h, files={"file": ("s.xlsx", data)}, data={"confirm":"true"}), 200)["committed"]
    names = {x["name"] for x in j(c.get("/api/classes", headers=h))}
    assert {"12-ImportA", "12-ImportB"} <= names
    # re-import updates by registration number instead of duplicating
    data = _xlsx([["Name", "Roll Number", "Registration Number", "Class", "Section"], ["Lakshmi", 1, "IMP-1", "12", "ImportA"]])
    assert j(c.post("/api/students/import", headers=h, files={"file": ("s.xlsx", data, "x")}), 200)["updated"] == 1
    assert c.post("/api/students/import", headers=h, files={"file": ("s.csv", b"a,b", "text/csv")}).status_code == 400

    cls = next(x for x in j(c.get("/api/classes", headers=h)) if x["name"] == "12-ImportA")
    st = j(c.get(f"/api/students?class_id={cls['id']}", headers=h))
    assert {(s["name"], s["registration_number"], s["section"]) for s in st} == {("Lakshmi", "IMP-1", "ImportA"), ("Bala", "IMP-3", "ImportA")}
    r = c.post("/api/students", headers=h, json={"name": "X", "roll_number": "9", "class_id": cls["id"], "registration_number": "imp 1"})
    assert r.status_code == 409 and r.json()["code"] == "DUPLICATE_REG"

    x = c.get(f"/api/students/export?format=xlsx&class_id={cls['id']}", headers=h)
    assert x.status_code == 200
    rows = list(load_workbook(BytesIO(x.content)).active.iter_rows(values_only=True))
    assert rows[0] == ("Name", "Roll Number", "Registration Number", "Class", "Section") and len(rows) == 3
    assert rows[1][3] == "12-ImportA"
    p = c.get("/api/students/export?format=pdf", headers=h)
    assert p.status_code == 200 and p.content.startswith(b"%PDF")




def test_bulk_upload_refuses_photos(client, auth):
    c, h = client, auth
    _, eid = _exam_ready_for_sheets(c, h, "10-BulkPhotos")
    files = [("files", ("ok.pdf", make_pdf(1), "application/pdf")), ("files", ("page.png", make_png(), "image/png"))]
    r = c.post(f"/api/exams/{eid}/answer-sheets/bulk", headers=h, files=files)
    assert r.status_code == 400 and "page.png" in r.json()["message"]
    assert j(c.get(f"/api/exams/{eid}/answer-sheets/unassigned", headers=h)) == []   # nothing stored
