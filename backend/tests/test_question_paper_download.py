import pytest
from app.database import SessionLocal
from app.models import Teacher
from app.security import hash_password
from .conftest import make_pdf, make_png


def test_download_question_paper_pdf(client, auth):
    c, h = client, auth
    # Setup class, subject, exam
    cls = c.post("/api/classes", json={"name": "11-A"}, headers=h).json()
    sub = c.post("/api/subjects", json={"name": "Chemistry"}, headers=h).json()
    exam = c.post("/api/exams", headers=h, json={
        "name": "Chemistry Midterm", "academic_year": "2026-27",
        "class_id": cls["id"], "subject_id": sub["id"],
        "exam_type": "Midterm", "total_marks": 25
    }).json()
    eid = exam["id"]

    # Before upload -> 404
    r_empty = c.get(f"/api/exams/{eid}/question-paper/pdf", headers=h)
    assert r_empty.status_code == 404

    # Upload PDF
    pdf_bytes = make_pdf(2)
    upload_res = c.post(
        f"/api/exams/{eid}/question-paper",
        headers=h,
        files={"file": ("chem_paper.pdf", pdf_bytes, "application/pdf")}
    )
    assert upload_res.status_code == 202
    doc_id = upload_res.json()["id"]

    # Download via /exams/{eid}/question-paper/pdf
    r_pdf = c.get(f"/api/exams/{eid}/question-paper/pdf", headers=h)
    assert r_pdf.status_code == 200
    assert r_pdf.headers["content-type"] == "application/pdf"
    assert "attachment" in r_pdf.headers["content-disposition"]
    assert "chem_paper.pdf" in r_pdf.headers["content-disposition"]
    assert r_pdf.content == pdf_bytes

    # Download via /exams/{eid}/question-paper/download
    r_dl = c.get(f"/api/exams/{eid}/question-paper/download", headers=h)
    assert r_dl.status_code == 200
    assert r_dl.content == pdf_bytes

    # Download via generic document endpoint /documents/question-paper/{doc_id}/pdf
    r_doc = c.get(f"/api/documents/question-paper/{doc_id}/pdf", headers=h)
    assert r_doc.status_code == 200
    assert r_doc.content == pdf_bytes


def test_download_with_token_query_param(client):
    c = client
    login = c.post("/api/auth/login", json={"email": "rao@school.org", "password": "password123"}).json()
    token = login["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    cls = c.post("/api/classes", json={"name": "12-A"}, headers=h).json()
    sub = c.post("/api/subjects", json={"name": "Math"}, headers=h).json()
    exam = c.post("/api/exams", headers=h, json={
        "name": "Math Final", "academic_year": "2026-27",
        "class_id": cls["id"], "subject_id": sub["id"],
        "exam_type": "Final", "total_marks": 50
    }).json()
    eid = exam["id"]

    pdf_bytes = make_pdf(1)
    c.post(
        f"/api/exams/{eid}/question-paper",
        headers=h,
        files={"file": ("math_final.pdf", pdf_bytes, "application/pdf")}
    )

    # Use query param token without Bearer header
    r = c.get(f"/api/exams/{eid}/question-paper/pdf?token={token}")
    assert r.status_code == 200
    assert r.content == pdf_bytes


def test_download_security_and_isolation(client, auth):
    c, h = client, auth
    cls = c.post("/api/classes", json={"name": "9-B"}, headers=h).json()
    sub = c.post("/api/subjects", json={"name": "History"}, headers=h).json()
    exam = c.post("/api/exams", headers=h, json={
        "name": "History Exam", "academic_year": "2026-27",
        "class_id": cls["id"], "subject_id": sub["id"],
        "exam_type": "Unit", "total_marks": 20
    }).json()
    eid = exam["id"]

    pdf_bytes = make_pdf(1)
    c.post(
        f"/api/exams/{eid}/question-paper",
        headers=h,
        files={"file": ("history.pdf", pdf_bytes, "application/pdf")}
    )

    # Unauthenticated
    assert c.get(f"/api/exams/{eid}/question-paper/pdf").status_code == 401

    # Non-existent exam
    assert c.get("/api/exams/non-existent-id/question-paper/pdf", headers=h).status_code == 404

    # Other teacher isolation
    db = SessionLocal()
    other_teacher = Teacher(name="Mr Sharma", email="sharma@school.org", password_hash=hash_password("pw123"))
    db.add(other_teacher)
    db.commit()
    db.close()

    other_login = c.post("/api/auth/login", json={"email": "sharma@school.org", "password": "pw123"}).json()
    other_h = {"Authorization": f"Bearer {other_login['access_token']}"}

    # Other teacher cannot download Teacher Rao's question paper
    r_other = c.get(f"/api/exams/{eid}/question-paper/pdf", headers=other_h)
    assert r_other.status_code == 404


def test_download_image_as_pdf(client, auth):
    c, h = client, auth
    cls = c.post("/api/classes", json={"name": "8-A"}, headers=h).json()
    sub = c.post("/api/subjects", json={"name": "Art"}, headers=h).json()
    exam = c.post("/api/exams", headers=h, json={
        "name": "Art Test", "academic_year": "2026-27",
        "class_id": cls["id"], "subject_id": sub["id"],
        "exam_type": "Unit", "total_marks": 10
    }).json()
    eid = exam["id"]

    png_bytes = make_png()
    c.post(
        f"/api/exams/{eid}/question-paper",
        headers=h,
        files={"file": ("sketch.png", png_bytes, "image/png")}
    )

    r = c.get(f"/api/exams/{eid}/question-paper/pdf", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert "sketch.pdf" in r.headers["content-disposition"]
    # PDF magic bytes
    assert r.content.startswith(b"%PDF")
