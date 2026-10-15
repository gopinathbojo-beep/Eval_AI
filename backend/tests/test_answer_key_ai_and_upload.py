import json
import pytest
from app.database import SessionLocal
from app.models import Teacher
from app.security import hash_password
from .conftest import make_pdf, make_png


def test_ai_generate_and_save_answer_key(client, auth):
    c, h = client, auth

    # 1. Setup exam
    cls = c.post("/api/classes", json={"name": "Grade 10"}, headers=h).json()
    sub = c.post("/api/subjects", json={"name": "Physics"}, headers=h).json()
    exam = c.post("/api/exams", headers=h, json={
        "name": "Physics Midterm", "academic_year": "2026-27",
        "class_id": cls["id"], "subject_id": sub["id"],
        "exam_type": "Midterm", "total_marks": 7.0
    }).json()
    eid = exam["id"]

    # Trying to generate AI answer key before questions are verified -> 409
    r_early = c.post(f"/api/exams/{eid}/answer-keys/generate-ai", headers=h)
    assert r_early.status_code == 409
    assert r_early.json()["code"] == "QUESTIONS_NOT_VERIFIED"

    # 2. Upload question paper (2 pages) and verify questions
    c.post(f"/api/exams/{eid}/question-paper", headers=h, files={"file": ("physics.pdf", make_pdf(2), "application/pdf")})
    # Accept all questions and verify
    c.post(f"/api/exams/{eid}/questions/accept-valid", headers=h)
    r_ver = c.post(f"/api/exams/{eid}/questions/verify", headers=h, json={"confirm_marks_mismatch": True})
    assert r_ver.status_code == 200

    qs_res = c.get(f"/api/exams/{eid}/questions", headers=h).json()
    qs = qs_res["questions"]
    assert len(qs) >= 2
    q1 = qs[0]
    q2 = qs[1]

    # 3. Generate Answer Key with AI (Option 2)
    r_gen = c.post(f"/api/exams/{eid}/answer-keys/generate-ai", headers=h)
    assert r_gen.status_code == 200
    gen_data = r_gen.json()
    assert "answers" in gen_data
    answers = gen_data["answers"]
    assert len(answers) == len(qs)

    # Check question numbers & deterministic question IDs are preserved
    for item in answers:
        matching_q = next((q for q in qs if q["id"] == item["exam_question_id"]), None)
        assert matching_q is not None
        assert item["question_number"] == matching_q["display_number"]
        assert item["question_text"] == matching_q["question_text"]
        assert item["marks"] == matching_q["max_marks"]
        assert len(item["answer_text"]) > 0

    # 4. Teacher reviews and edits AI answers before saving
    answers[0]["answer_text"] = "Teacher edited model answer for Q1."
    answers[0]["criteria"] = ["1 mark for edited point A", "1 mark for edited point B"]
    answers[0]["keywords"] = ["edited_keyword"]

    # 5. Save reviewed answers
    r_save = c.post(f"/api/exams/{eid}/answer-keys/save-ai", headers=h, json={"answers": answers})
    assert r_save.status_code == 201
    saved_data = r_save.json()
    assert len(saved_data["keys"]) == len(qs)

    saved_q1 = next(k for k in saved_data["keys"] if k["exam_question_id"] == q1["id"])
    assert saved_q1["answer_text"] == "Teacher edited model answer for Q1."
    assert saved_q1["criteria"] == ["1 mark for edited point A", "1 mark for edited point B"]
    assert saved_q1["mapping_status"] == "MAPPED"
    assert saved_q1["verification_status"] == "UNVERIFIED"

    # Exam status should now be ANSWER_KEY_UPLOADED
    exam_detail = c.get(f"/api/exams/{eid}", headers=h).json()
    assert exam_detail["status"] == "ANSWER_KEY_UPLOADED"

    # 6. Verify answer key (Teacher approval required before evaluation)
    r_verify_keys = c.post(f"/api/exams/{eid}/answer-keys/verify", headers=h)
    assert r_verify_keys.status_code == 200
    assert r_verify_keys.json()["verified"] == len(qs)

    exam_verified = c.get(f"/api/exams/{eid}", headers=h).json()
    assert exam_verified["status"] == "ANSWER_KEY_VERIFIED"


def test_upload_answer_key_sheet_option(client, auth):
    c, h = client, auth

    # 1. Setup exam with verified questions
    cls = c.post("/api/classes", json={"name": "Grade 9"}, headers=h).json()
    sub = c.post("/api/subjects", json={"name": "Chemistry"}, headers=h).json()
    exam = c.post("/api/exams", headers=h, json={
        "name": "Chemistry Unit 1", "academic_year": "2026-27",
        "class_id": cls["id"], "subject_id": sub["id"],
        "exam_type": "Unit", "total_marks": 7.0
    }).json()
    eid = exam["id"]

    # Upload and verify questions
    c.post(f"/api/exams/{eid}/question-paper", headers=h, files={"file": ("chem_q.pdf", make_pdf(2), "application/pdf")})
    c.post(f"/api/exams/{eid}/questions/accept-valid", headers=h)
    c.post(f"/api/exams/{eid}/questions/verify", headers=h, json={"confirm_marks_mismatch": True})

    # 2. Upload Answer Key Sheet (Option 1)
    r_up = c.post(f"/api/exams/{eid}/answer-key", headers=h, files={"file": ("chem_key.png", make_png(), "image/png")})
    assert r_up.status_code == 202

    doc_info = c.get(f"/api/exams/{eid}/answer-key", headers=h).json()
    assert doc_info["original_filename"] == "chem_key.png"
    assert doc_info["status"] in ("READY", "NEEDS_ATTENTION", "UPLOADED")


def test_ai_generation_security_and_errors(client, auth):
    c, h = client, auth

    # Non-existent exam -> 404
    assert c.post("/api/exams/non-existent-id/answer-keys/generate-ai", headers=h).status_code == 404
    assert c.post("/api/exams/non-existent-id/answer-keys/save-ai", headers=h, json={"answers": []}).status_code == 404

    # Unauthenticated -> 401
    assert c.post("/api/exams/any-id/answer-keys/generate-ai").status_code == 401
    assert c.post("/api/exams/any-id/answer-keys/save-ai", json={"answers": []}).status_code == 401


def test_create_exam_without_academic_year(client, auth):
    c, h = client, auth
    cls = c.post("/api/classes", json={"name": "Grade 11"}, headers=h).json()
    sub = c.post("/api/subjects", json={"name": "Biology"}, headers=h).json()
    res = c.post(
        "/api/exams",
        headers=h,
        json={
            "name": "Biology Quiz",
            "class_id": cls["id"],
            "subject_id": sub["id"],
            "exam_type": "Quiz",
            "total_marks": 25.0,
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Biology Quiz"
    assert data["academic_year"] != ""
    assert "-" in data["academic_year"]


def test_answer_key_not_locked_in_questions_verified(client, auth):
    c, h = client, auth
    cls = c.post("/api/classes", json={"name": "Grade 12"}, headers=h).json()
    sub = c.post("/api/subjects", json={"name": "Maths"}, headers=h).json()
    exam_res = c.post(
        "/api/exams",
        headers=h,
        json={
            "name": "Maths Unit Test",
            "class_id": cls["id"],
            "subject_id": sub["id"],
            "exam_type": "Unit test",
            "total_marks": 10.0,
        },
    )
    exam_id = exam_res.json()["id"]

    # Upload question paper and verify questions
    c.post(f"/api/exams/{exam_id}/question-paper", headers=h, files={"file": ("maths.pdf", make_pdf(1), "application/pdf")})
    c.post(f"/api/exams/{exam_id}/questions/accept-valid", headers=h)
    v_res = c.post(f"/api/exams/{exam_id}/questions/verify", headers=h, json={"confirm_marks_mismatch": True})
    assert v_res.status_code == 200

    exam_detail = c.get(f"/api/exams/{exam_id}", headers=h).json()
    assert exam_detail["status"] == "QUESTIONS_VERIFIED"

    # Now verify that answer keys endpoint reports locked == False
    keys_res = c.get(f"/api/exams/{exam_id}/answer-keys", headers=h)
    assert keys_res.status_code == 200
    keys_data = keys_res.json()
    assert keys_data["locked"] is False
    assert len(keys_data["keys"]) == 0

