import re
import pymupdf
import pytest
from app.database import SessionLocal
from app.models import (
    AnswerKey,
    AnswerSheetDocument,
    AuditLog,
    Evaluation,
    EvaluationItem,
    ExamQuestion,
    Student,
    StudentAnswer,
    Teacher,
)
from app.security import hash_password
from app.services.report_generator import format_math_text


def test_format_math_text():
    # Test superscripts and fractions
    t1 = format_math_text(r"Solve (k + 1)^2 and \frac{a}{b}")
    assert "<sup>2</sup>" in t1
    assert "(a / b)" in t1

    # Test math symbols
    t2 = format_math_text(r"\sqrt{16} \pm \pi \times 2 \leq 10")
    assert "√(16)" in t2
    assert "±" in t2
    assert "π" in t2
    assert "×" in t2
    assert "≤" in t2

    # Test empty
    assert format_math_text(None) == "&ndash;"

    # Test stripping LaTeX math wrappers \left, \right, \(, \)
    t3 = format_math_text(r"\(\left(\frac{a}{b}\right)^{-n} = \left(\frac{b}{a}\right)^{n}\)")
    assert r"\(" not in t3
    assert r"\)" not in t3
    assert r"\left" not in t3
    assert "(a / b)" in t3
    assert "(b / a)" in t3


def test_download_evaluation_report_pdf_e2e(client, auth):
    c, h = client, auth

    # Setup class, subject, exam
    cls = c.post("/api/classes", json={"name": "10-B"}, headers=h).json()
    sub = c.post("/api/subjects", json={"name": "Mathematics"}, headers=h).json()
    exam = c.post(
        "/api/exams",
        headers=h,
        json={
            "name": "Math Term 1",
            "academic_year": "2026-27",
            "class_id": cls["id"],
            "subject_id": sub["id"],
            "exam_type": "Term Exam",
            "total_marks": 20,
        },
    ).json()
    eid = exam["id"]

    # Student
    stu = c.post(
        "/api/students",
        headers=h,
        json={"class_id": cls["id"], "name": "Alice Smith", "roll_number": "101"},
    ).json()

    ev_id = None
    db = SessionLocal()
    try:
        q1 = ExamQuestion(
            exam_id=eid,
            display_number="1",
            question_text=r"Evaluate 101^3 using identity (a + b)^3 = a^3 + 3a^2b + 3ab^2 + b^3",
            max_marks=10.0,
            position=1,
        )
        q2 = ExamQuestion(
            exam_id=eid,
            display_number="2",
            question_text=r"Find the value of \sqrt{144} + \frac{10}{2}",
            max_marks=10.0,
            position=2,
        )
        db.add_all([q1, q2])
        db.flush()

        k1 = AnswerKey(
            exam_id=eid,
            exam_question_id=q1.id,
            answer_text="1000000 + 30000 + 300 + 1 = 1030301",
            marks=10.0,
            mapping_status="MAPPED",
            keywords=["1030301", "identity"],
        )
        k2 = AnswerKey(
            exam_id=eid,
            exam_question_id=q2.id,
            answer_text="12 + 5 = 17",
            marks=10.0,
            mapping_status="MAPPED",
        )
        db.add_all([k1, k2])
        db.flush()

        doc = AnswerSheetDocument(
            exam_id=eid,
            student_id=stu["id"],
            original_filename="alice_math.pdf",
            original_file="mock/path.pdf",
            mime_type="application/pdf",
            file_size=1024,
            status="READY",
        )
        db.add(doc)
        db.flush()

        ev = Evaluation(
            exam_id=eid,
            student_id=stu["id"],
            answer_sheet_id=doc.id,
            status="FINALIZED",
            total_marks=18.5,
            maximum_marks=20.0,
            percentage=92.5,
        )
        db.add(ev)
        db.flush()

        a1 = StudentAnswer(
            evaluation_id=ev.id,
            exam_question_id=q1.id,
            answer_text="101^3 = 1000000 + 30000 + 300 + 1 = 1030301",
            status="APPROVED",
        )
        a2 = StudentAnswer(
            evaluation_id=ev.id,
            exam_question_id=q2.id,
            answer_text="sqrt(144) + 5 = 12 + 5 = 17",
            status="APPROVED",
        )
        db.add_all([a1, a2])
        db.flush()

        it1 = EvaluationItem(
            evaluation_id=ev.id,
            exam_question_id=q1.id,
            student_answer_id=a1.id,
            status="APPROVED",
            ai_marks=10.0,
            final_marks=10.0,
            ai_decision="FULL_MARKS",
            ai_feedback="Correct calculation using identity.",
            teacher_overridden=False,
        )
        it2 = EvaluationItem(
            evaluation_id=ev.id,
            exam_question_id=q2.id,
            student_answer_id=a2.id,
            status="APPROVED",
            ai_marks=8.0,
            final_marks=8.5,
            ai_decision="PARTIAL_MARKS",
            ai_feedback="Minor notation variation.",
            teacher_overridden=True,
            teacher_feedback="Accepted correct final simplification.",
        )
        db.add_all([it1, it2])
        db.flush()

        audit_log = AuditLog(
            exam_id=eid,
            entity_type="evaluation_item",
            entity_id=it2.id,
            action="marks_changed",
            old_value={"ai": 8.0, "was": 8.0},
            new_value=8.5,
            reason="Awarded half mark for clear intermediate step.",
        )
        db.add(audit_log)
        db.commit()
        ev_id = ev.id
    finally:
        db.close()

    # 1. Download via /evaluations/{ev_id}/report.pdf
    res = c.get(f"/api/evaluations/{ev_id}/report.pdf", headers=h)
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert "attachment" in res.headers["content-disposition"]
    assert "Alice_Smith" in res.headers["content-disposition"]
    assert len(res.content) > 1000

    # 2. Download via /evaluations/{ev_id}/report
    res_alt = c.get(f"/api/evaluations/{ev_id}/report", headers=h)
    assert res_alt.status_code == 200
    assert len(res_alt.content) == len(res.content)

    # 3. Parse PDF with PyMuPDF to verify content integrity
    doc_pdf = pymupdf.open(stream=res.content, filetype="pdf")
    assert doc_pdf.page_count >= 1

    raw_text = "".join(page.get_text() for page in doc_pdf)
    clean_text = re.sub(r"\s+", " ", raw_text)
    assert "Alice Smith" in clean_text
    assert "101" in clean_text
    assert "Math Term 1" in clean_text
    assert "Mathematics" in clean_text
    assert "18.5" in clean_text
    assert "92.5%" in clean_text
    assert "A1" in clean_text                                                   # CBSE grade for 92.5%
    assert "Adjusted by teacher: Awarded half mark for clear intermediate step" in clean_text
    assert "Accepted correct final simplification" in clean_text
    assert "Page 1 of" in clean_text


def test_download_evaluation_report_unfinalized_rejected(client, auth):
    c, h = client, auth
    cls = c.post("/api/classes", json={"name": "9-B"}, headers=h).json()
    sub = c.post("/api/subjects", json={"name": "Physics"}, headers=h).json()
    exam = c.post(
        "/api/exams",
        headers=h,
        json={
            "name": "Physics Quiz",
            "academic_year": "2026-27",
            "class_id": cls["id"],
            "subject_id": sub["id"],
            "exam_type": "Quiz",
            "total_marks": 10,
        },
    ).json()

    stu = c.post(
        "/api/students",
        headers=h,
        json={"class_id": cls["id"], "name": "Bob Jones", "roll_number": "102"},
    ).json()

    ev_id = None
    db = SessionLocal()
    try:
        doc = AnswerSheetDocument(
            exam_id=exam["id"],
            student_id=stu["id"],
            original_filename="bob.pdf",
            original_file="mock.pdf",
            mime_type="application/pdf",
            file_size=500,
            status="READY",
        )
        db.add(doc)
        db.flush()

        ev = Evaluation(
            exam_id=exam["id"],
            student_id=stu["id"],
            answer_sheet_id=doc.id,
            status="AI_EVALUATED",  # Not finalized
        )
        db.add(ev)
        db.commit()
        ev_id = ev.id
    finally:
        db.close()

    res = c.get(f"/api/evaluations/{ev_id}/report.pdf", headers=h)
    assert res.status_code == 400
    data = res.json()
    assert data["code"] == "EVALUATION_NOT_FINALIZED"


def test_download_evaluation_report_auth_and_isolation(client, auth):
    c, h = client, auth

    # Unauthenticated -> 401
    res_unauth = c.get("/api/evaluations/nonexistent-id/report.pdf")
    assert res_unauth.status_code == 401

    # Another teacher trying to access Teacher A's evaluation
    db = SessionLocal()
    try:
        other_teacher = db.query(Teacher).filter_by(email="other@school.org").first()
        if not other_teacher:
            other_teacher = Teacher(
                name="Other Teacher",
                email="other@school.org",
                password_hash=hash_password("password123"),
            )
            db.add(other_teacher)
            db.commit()
    finally:
        db.close()

    login_b = c.post("/api/auth/login", json={"email": "other@school.org", "password": "password123"}).json()
    h_b = {"Authorization": f"Bearer {login_b['access_token']}"}

    # Request with Teacher B's credentials -> 404
    res_iso = c.get("/api/evaluations/nonexistent-id/report.pdf", headers=h_b)
    assert res_iso.status_code == 404
