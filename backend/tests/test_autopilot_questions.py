"""Autopilot on a CBSE question paper: a flagged question is checked against its page by the AI, a question the
board pattern has but the reading missed is read from the page, marks follow the pattern, and the paper is
verified without the school."""
from types import SimpleNamespace as NS

import pytest
from PIL import Image

from app.cbse.catalog import get_profile
from app.config import get_settings
from app.database import SessionLocal
from app.documents.storage import data_root, rel
from app.models import Exam, ExamQuestion, QuestionPaperDocument
from app.services import autopilot


@pytest.fixture
def cbse_exam(client, auth):
    exam = client.post("/api/exams/simple", headers=auth, json={
        "name": "Maths autopilot", "grade": "12", "section": "Z", "subject_key": "12-mathematics"}).json()
    assert exam["standard_profile_id"] == "cbse-12-041"
    page = data_root() / "autopilot-test" / "page-001.png"
    page.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (200, 280), "white").save(page)
    db = SessionLocal()
    try:
        doc = QuestionPaperDocument(exam_id=exam["id"], original_filename="p.pdf", original_file=rel(page),
                                    mime_type="application/pdf", file_size=1, status="READY",
                                    pages=[{"page_number": 1, "ocr_status": "OK", "processed_file": rel(page)}])
        db.add(doc)
        marks = get_profile("cbse-12-041")["parent_marks"]
        for root, m in enumerate(marks, 1):
            if root == 30:
                continue  # the reading missed Q30
            issues = ["Text is missing: part of the question could not be read."] if root == 12 else []
            db.add(ExamQuestion(exam_id=exam["id"], display_number=str(root), normalized_number=str(root),
                                question_text=f"Question {root} text", max_marks=m, position=root,
                                page_start=1, page_end=1, structure={"root": root, "issues": issues},
                                verification_status="NEEDS_REVIEW" if issues else "UNVERIFIED"))
        db.get(Exam, exam["id"]).status = "QUESTIONS_EXTRACTED"
        db.commit()
    finally:
        db.close()
    return exam["id"]


def test_flagged_and_missing_questions_are_settled_and_the_paper_verified(cbse_exam, monkeypatch):
    monkeypatch.setattr(get_settings(), "autopilot", True)
    asked = []

    def fake(system, user, schema, image=None, model=None):
        asked.append(user)
        number = 30 if "question 30 " in user else 12
        return NS(parsed=schema(found=True, text=f"Full printed text of question {number}", marks=9), raw="{}")

    monkeypatch.setattr(autopilot, "chat_structured", fake)
    autopilot.settle_questions(cbse_exam)
    db = SessionLocal()
    try:
        exam = db.get(Exam, cbse_exam)
        qs = {q.normalized_number: q for q in db.query(ExamQuestion).filter_by(exam_id=cbse_exam)}
        assert exam.status == "QUESTIONS_VERIFIED"
        assert len(qs) == 38 and all(q.verification_status == "VERIFIED" for q in qs.values())
        assert qs["12"].question_text == "Full printed text of question 12" and qs["12"].structure["issues"] == []
        assert any("Checked by AI" in n for n in qs["12"].structure["notes"])
        assert qs["30"].question_text == "Full printed text of question 30" and qs["30"].max_marks == 3  # the pattern's marks
        assert qs["12"].max_marks == 1
        assert len(asked) == 2   # only the two problems cost an AI call
    finally:
        db.close()
