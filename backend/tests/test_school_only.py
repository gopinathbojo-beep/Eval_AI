"""School-only accounts (2026-11-02): no teachers, the Create Exam subject list, one Finalize step, uploader codes,
and students added by roll number."""
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from .conftest import BEHAVIOUR, make_pdf
from .test_bulk_sheets_and_early_key import _exam_ready_for_sheets, j

BROWSER = {"X-Requested-With": "EvalAI"}


def test_teacher_accounts_are_refused(client):
    from app.database import SessionLocal
    from app.models import Teacher
    from app.security import hash_password
    with SessionLocal() as db:
        db.add(Teacher(name="Old Teacher", email="old-teacher@school.org", role="TEACHER",
                       profile_completed_at=datetime.now(timezone.utc), password_hash=hash_password("Password@123")))
        db.commit()
    r = client.post("/api/auth/login", json={"email": "old-teacher@school.org", "password": "Password@123"})
    assert r.status_code == 403 and r.json()["code"] == "TEACHER_RETIRED"
    assert client.post("/api/management/teachers", json={}).status_code == 404


def test_subject_catalog_joins_textbook_subjects(client, auth):
    ten = {s["name"]: s for s in j(client.get("/api/subjects/catalog?grade=10", headers=auth), 200)["10"]}
    assert {"English", "Hindi", "Mathematics", "Science", "Social Science", "Tamil"} <= set(ten)
    assert "Hindi Course A" not in ten
    assert ten["Hindi"]["profiles"] == ["cbse-10-002", "cbse-10-085"]          # usual variant first
    assert ten["Mathematics"]["profiles"][0] == "cbse-10-041"
    twelve = {s["name"]: s for s in j(client.get("/api/subjects/catalog?grade=12", headers=auth), 200)["12"]}
    assert twelve["Fine Arts"]["profiles"] == [] and twelve["Mathematics"]["profiles"] == ["cbse-12-041", "cbse-12-241"] and twelve["Tamil"]["profiles"] == ["cbse-12-106"]


def test_simple_exam_creates_class_and_subject(client, auth):
    e = j(client.post("/api/exams/simple", headers=auth, json={"name": "Term 1", "grade": "10", "section": "b",
                                                            "subject_key": "10-hindi"}), 201)
    assert e["standard_profile_id"] == "cbse-10-002"
    classes = {c["name"] for c in j(client.get("/api/classes", headers=auth), 200)}
    assert "10-B" in classes
    generic = j(client.post("/api/exams/simple", headers=auth, json={"name": "Unit", "grade": "12", "section": "A",
                                                                  "subject_key": "12-fine-arts"}), 201)
    assert generic["standard_profile_id"] is None and generic["total_marks"] == 80
    assert client.post("/api/exams/simple", headers=auth, json={"name": "X", "grade": "10",
                                                               "subject_key": "10-biology"}).status_code == 400


def test_question_paper_names_its_variant():
    from app.cbse.variant import pick_variant
    exam = SimpleNamespace(standard_profile_id="cbse-10-002", subject=SimpleNamespace(name="Hindi", code=None),
                           school_class=SimpleNamespace(name="10-A"), total_marks=80, duration_minutes=180,
                           standard_validation={"x": 1})
    assert pick_variant(exam, [{"page_text": "हिंदी Hindi Course B  Code No. 085  Set 1"}]) == "cbse-10-085"
    assert exam.standard_profile_id == "cbse-10-085" and exam.standard_validation is None
    assert pick_variant(exam, [{"page_text": ""}]) is None                      # scanned paper: keep the variant


def test_uploader_code_uploads_only_to_its_exam(client, auth):
    cls, eid = _exam_ready_for_sheets(client, auth, "10-Codes")
    assert client.post(f"/api/exams/{eid}/uploader-codes", headers=auth, json={"count": 1}).status_code == 409
    assert j(client.post(f"/api/exams/{eid}/finalize-setup", headers=auth), 200)["status"] == "READY_FOR_EVALUATION"
    codes = j(client.post(f"/api/exams/{eid}/uploader-codes", headers=auth, json={"labels": ["Room 4", "Hall"]}), 201)
    assert len(codes) == 2 and all(len(c["code"]) == 6 and c["code"].isalnum() for c in codes)
    assert not set("01IO") & set("".join(c["code"] for c in codes))
    from app.database import SessionLocal
    from app.routes.uploader import _new_code
    with SessionLocal() as db:  # every code mixes letters and digits
        assert all(any(ch.isdigit() for ch in x) and any(ch.isalpha() for ch in x) for x in (_new_code(db) for _ in range(300)))

    with TestClient(client.app) as up:
        assert up.post("/api/auth/code-login", headers=BROWSER, json={"code": "ZZZZZZ"}).status_code == 401
        me = j(up.post("/api/auth/code-login", headers=BROWSER, json={"code": codes[0]["code"].lower()}), 200)
        assert me["exam"]["id"] == eid
        # upload only: no school pages, no results
        assert up.get("/api/dashboard").status_code == 401
        assert up.get(f"/api/exams/{eid}/results").status_code == 401
        BEHAVIOUR["sheet"] = "main"
        # nobody has roll 77 yet; the typed roll decides the student, the sheet is not read for it
        # a roll number is optional for uploaded files (read from the sheet); when typed, it decides
        r = j(up.post("/api/uploader/answer-sheets", headers=BROWSER, data={"roll_number": "77"},
                      files=[("files", ("s.pdf", make_pdf(1), "application/pdf"))]), 202)
        assert r["uploaded"] == 1
        mine = j(up.get("/api/uploader/me"), 200)
        assert len(mine["uploads"]) == 1 and "total_marks" not in mine["uploads"][0]
        # phone: three photographed pages of one student's sheet arrive as one 3-page answer sheet
        from .conftest import make_png
        j(up.post("/api/uploader/answer-sheets", headers=BROWSER, data={"one_sheet": "true", "roll_number": "78"},
                  files=[("files", (f"p{i}.png", make_png(), "image/png")) for i in range(3)]), 202)
        mine = j(up.get("/api/uploader/me"), 200)
        assert len(mine["uploads"]) == 2 and mine["uploads"][0]["original_filename"] == "answer-sheet.pdf"
        assert mine["uploads"][0]["pages"] == 3
        # the uploader gives their name once, and may type the roll number instead of it being read
        assert up.put("/api/uploader/name", headers=BROWSER, json={"name": "R2D2"}).status_code == 400
        j(up.put("/api/uploader/name", headers=BROWSER, json={"name": "Kumar Swamy"}), 200)
        j(up.post("/api/uploader/answer-sheets", headers=BROWSER, data={"one_sheet": "true", "roll_number": "91"},
                  files=[("files", ("p.png", make_png(), "image/png"))]), 202)
        dup = up.post("/api/uploader/answer-sheets", headers=BROWSER, data={"one_sheet": "true", "roll_number": "91"},
                      files=[("files", ("p.png", make_png(), "image/png"))])
        assert dup.status_code == 409  # one sheet per student per exam
        assert any(s["roll_number"] == "91" for s in j(client.get(f"/api/students?class_id={cls['id']}", headers=auth), 200))
        # a PDF saved under a typed roll number goes to that student and is read, then graded
        j(up.post("/api/uploader/answer-sheets", headers=BROWSER, data={"roll_number": "92"},
                  files=[("files", ("roll92.pdf", make_pdf(2), "application/pdf"))]), 202)
        ev = next(e for e in j(client.get(f"/api/exams/{eid}/results", headers=auth), 200) if e["student"]["roll_number"] == "92")
        # read straight away under roll 92; grading follows on its own once every answer maps to a question
        # (this dummy sheet's answers don't, so it waits for the school's review and shows in the bell)
        assert ev["status"] in ("MAPPING_REVIEW", "AI_EVALUATED", "TEACHER_REVIEW", "FINALIZABLE")
        listed = {x["id"]: x for x in j(client.get(f"/api/exams/{eid}/uploader-codes", headers=auth), 200)}
        assert listed[codes[0]["id"]]["uploader_name"] == "Kumar Swamy" and listed[codes[0]["id"]]["uploads"] == 4

        # the student was added by roll number, with the class's section
        students = j(client.get(f"/api/students?class_id={cls['id']}", headers=auth), 200)
        kid = next(s for s in students if s["roll_number"] == "77")
        assert kid["name"] == "Roll 77"  # named by its roll until the school renames it; the sheet is not read for it
        assert j(client.get(f"/api/students/{kid['id']}/evaluations", headers=auth), 200)[0]["exam_id"] == eid

        # regenerating the code ends the old session at once
        new = j(client.post(f"/api/uploader-codes/{codes[0]['id']}/regenerate", headers=auth), 200)
        assert new["code"] != codes[0]["code"] and new["uploads"] == 4
        assert up.get("/api/uploader/me").status_code == 401

    with TestClient(client.app) as up2:
        j(up2.post("/api/auth/code-login", headers=BROWSER, json={"code": codes[1]["code"]}), 200)
        assert client.delete(f"/api/uploader-codes/{codes[1]['id']}", headers=auth).status_code == 204
        assert up2.get("/api/uploader/me").status_code == 401
    assert [c["label"] for c in j(client.get(f"/api/exams/{eid}/uploader-codes", headers=auth), 200)] == ["Room 4"]


def test_dashboard_reports_school_cards(client, auth):
    d = j(client.get("/api/dashboard", headers=auth), 200)
    assert d["credits"] is None  # unlimited until a payment gateway exists
    assert {"total_exams", "pending_review", "evaluated_sheets"} <= set(d)


def test_school_registration_structured_address_and_safe_retry(client):
    from app.routes.registration import register_limiter
    register_limiter._attempts.clear()  # this file signs up more than 10 accounts a minute
    from app.database import SessionLocal
    from app.models import SchoolProfile, Teacher, Workspace
    with TestClient(client.app) as browser:
        email = f"school-{datetime.now().timestamp()}@example.com"
        j(browser.post("/api/auth/register", headers=BROWSER, json={"name": "Dr. Meena", "email": email,
                                                                     "password": "School-password-1", "role": "MANAGEMENT"}), 201)
        profile = {"name": "Dr. Meena", "role": "MANAGEMENT", "phone": "9876543210", "school_name": "Green Valley School",
                   "principal_name": "Dr. Meena", "building": "Green Valley Campus", "locality": "Anna Nagar",
                   "city": "Chennai", "state": "Tamil Nadu", "postcode": "600040", "total_students": 850}
        first = j(browser.put("/api/auth/profile", headers=BROWSER, json=profile), 200)
        # a retry (lost response, double click) updates the same workspace instead of creating another
        j(browser.put("/api/auth/profile", headers=BROWSER, json={**profile, "locality": "Kilpauk"}), 200)
        assert browser.post("/api/auth/register", headers=BROWSER, json={"name": "Xavier", "email": email,
               "password": "School-password-1", "role": "MANAGEMENT"}).status_code == 409
        # teachers can never self-register
        assert browser.post("/api/auth/register", headers=BROWSER, json={"name": "Xavier", "email": "t" + email,
               "password": "School-password-1", "role": "TEACHER"}).status_code == 422
    with SessionLocal() as db:
        user = db.query(Teacher).filter_by(email=email).one()
        assert db.query(Workspace).filter_by(owner_id=user.id).count() == 1
        assert user.workspace_id == first["teacher"]["workspace_id"]
        p = user.profile
        assert (p["building"], p["locality"], p["city"], p["state"], p["postcode"], p["total_students"]) == \
            ("Green Valley Campus", "Kilpauk", "Chennai", "Tamil Nadu", "600040", 850)
        assert p["address"] == "Green Valley Campus, Kilpauk, Chennai, Tamil Nadu - 600040"
        assert db.query(SchoolProfile).filter_by(teacher_id=user.id).one().address == p["address"]


def test_registration_and_login_formats(client):
    from app.routes.registration import register_limiter
    register_limiter._attempts.clear()  # this file signs up more than 10 accounts a minute
    from app import validation as valid
    import pytest
    assert valid.phone("+91 98765-43210") == "9876543210" and valid.phone("044 2345 6789") == "4423456789"
    assert valid.person_name("  Dr.  K.  Meena ") == "Dr. K. Meena" and valid.person_name("மீனா") == "மீனா"
    for bad, fn in (("98765", valid.phone), ("abc@", valid.email), ("R2D2", valid.person_name), ("012345", valid.pin_code),
                    ("6000400", valid.pin_code)):
        with pytest.raises(ValueError):
            fn(bad)
    with TestClient(client.app) as browser:
        r = browser.post("/api/auth/register", headers=BROWSER, json={"name": "Asha", "email": "not-an-email",
                                                                     "password": "School-password-1", "role": "PARENT"})
        assert r.status_code == 422 and r.json()["message"].startswith("Enter a valid email address")
        r = browser.post("/api/auth/login", json={"email": "nope", "password": "x"})
        assert r.status_code == 400 and r.json()["code"] == "INVALID_EMAIL"
        email = f"fmt-{datetime.now().timestamp()}@example.com"
        j(browser.post("/api/auth/register", headers=BROWSER, json={"name": "Asha Rani", "email": email.upper(),
                                                                     "password": "School-password-1", "role": "MANAGEMENT"}), 201)
        bad = {"name": "Asha Rani", "role": "MANAGEMENT", "phone": "12345", "school_name": "Green Valley", "principal_name": "Asha Rani",
               "building": "Campus", "locality": "Anna Nagar", "city": "Chennai", "state": "Tamil Nadu", "postcode": "600040"}
        r = browser.put("/api/auth/profile", headers=BROWSER, json=bad)
        assert r.status_code == 422 and r.json()["message"] == "Enter a valid 10-digit phone number."
        r = browser.put("/api/auth/profile", headers=BROWSER, json={**bad, "phone": "9876543210", "postcode": "60004"})
        assert r.json()["message"] == "Enter a valid 6-digit PIN code."
        j(browser.post("/api/auth/login", json={"email": email.upper(), "password": "School-password-1"}), 200)
