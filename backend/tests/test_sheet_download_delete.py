"""The review page's downloads (one PDF per tab, the marks one before finalizing) and deleting a student's answer
sheet, where a finalized one needs an explicit confirmation."""
import pymupdf

from app.database import SessionLocal
from app.models import AnswerSheetDocument, Evaluation, EvaluationItem, ExamQuestion, StudentAnswer


def _sheet(c, h, roll, status):
    cls = c.post("/api/classes", json={"name": f"10-{roll}"}, headers=h).json()
    sub = c.post("/api/subjects", json={"name": f"Science {roll}"}, headers=h).json()
    exam = c.post("/api/_test/legacy-exams", headers=h, json={
        "name": f"Unit test {roll}", "academic_year": "2026-27", "class_id": cls["id"], "subject_id": sub["id"],
        "exam_type": "Term Exam", "total_marks": 3}).json()
    stu = c.post("/api/students", headers=h, json={"class_id": cls["id"], "name": "Test Pupil", "roll_number": roll}).json()
    db = SessionLocal()
    try:
        qs = [ExamQuestion(exam_id=exam["id"], display_number=str(n), normalized_number=str(n),
                           question_text=f"Question {n} text", max_marks=m, position=n) for n, m in ((1, 1.0), (2, 2.0))]
        db.add_all(qs)
        db.flush()
        doc = AnswerSheetDocument(exam_id=exam["id"], student_id=stu["id"], original_filename="sheet.pdf",
                                  original_file="mock/sheet.pdf", mime_type="application/pdf", file_size=10, status="READY")
        db.add(doc)
        db.flush()
        ev = Evaluation(exam_id=exam["id"], student_id=stu["id"], answer_sheet_id=doc.id, status=status,
                        total_marks=2.5 if status == "FINALIZED" else None, maximum_marks=3.0 if status == "FINALIZED" else None)
        db.add(ev)
        db.flush()
        a = StudentAnswer(evaluation_id=ev.id, exam_question_id=qs[1].id, raw_question_number="Q2", page_number=1,
                          raw_ocr_text="Photosynthesis makes glucose", answer_text="Photosynthesis makes glucose",
                          status="EVALUATED")
        db.add(a)
        db.flush()
        db.add_all([EvaluationItem(evaluation_id=ev.id, exam_question_id=qs[0].id, status="MISSING", final_marks=0.0),
                    EvaluationItem(evaluation_id=ev.id, exam_question_id=qs[1].id, student_answer_id=a.id,
                                   status="EVALUATED", ai_marks=1.5, final_marks=1.5, ai_feedback="Partly correct.")])
        db.commit()
        return ev.id, doc.id
    finally:
        db.close()


def _text(pdf: bytes) -> str:
    return "".join(page.get_text() for page in pymupdf.open(stream=pdf, filetype="pdf"))


def test_each_review_tab_downloads_its_own_pdf_before_finalizing(client, auth):
    ev_id, _ = _sheet(client, auth, "D1", "TEACHER_REVIEW")
    mapping = client.get(f"/api/evaluations/{ev_id}/extraction-report.pdf?part=mapping", headers=auth)
    assert mapping.status_code == 200 and "Mapping_Review.pdf" in mapping.headers["content-disposition"]
    text = _text(mapping.content)
    assert "Answers as read" in text and "Photosynthesis makes glucose" in text and "Grading" not in text

    marks = client.get(f"/api/evaluations/{ev_id}/extraction-report.pdf?part=marks", headers=auth)
    assert marks.status_code == 200 and "Marks_Review.pdf" in marks.headers["content-disposition"]
    text = _text(marks.content)
    assert "total 1.5 / 3" in text and "Partly correct." in text and "Answers as read" not in text

    assert client.get(f"/api/evaluations/{ev_id}/extraction-report.pdf?part=other", headers=auth).status_code == 400


def test_a_finalized_sheet_is_deleted_only_when_confirmed(client, auth):
    ev_id, doc_id = _sheet(client, auth, "D2", "FINALIZED")
    refused = client.delete(f"/api/evaluations/{ev_id}", headers=auth)
    assert refused.status_code == 409 and refused.json()["code"] == "EVALUATION_FINALIZED"

    assert client.delete(f"/api/evaluations/{ev_id}?confirm_finalized=true", headers=auth).status_code == 200
    db = SessionLocal()
    try:
        assert db.get(Evaluation, ev_id) is None
        assert not db.query(EvaluationItem).filter_by(evaluation_id=ev_id).count()
        assert db.get(AnswerSheetDocument, doc_id).is_active is False
    finally:
        db.close()


def test_a_sheet_in_review_is_deleted_directly(client, auth):
    ev_id, _ = _sheet(client, auth, "D3", "TEACHER_REVIEW")
    assert client.delete(f"/api/evaluations/{ev_id}", headers=auth).status_code == 200
