from app.database import SessionLocal
from app.models import Exam, QuestionPaperDocument, SchoolClass, Subject, Teacher
from app.services.recovery import INTERRUPTED, recover_interrupted_jobs


def test_restart_releases_documents_stuck_mid_processing(client):
    db = SessionLocal()
    t = db.query(Teacher).filter_by(email="rao@school.org").one()
    cls, subj = SchoolClass(teacher_id=t.id, name="Recovery 8A"), Subject(teacher_id=t.id, name="Recovery Science")
    db.add_all([cls, subj]); db.flush()
    exam = Exam(teacher_id=t.id, name="Recovery test", academic_year="2026", class_id=cls.id, subject_id=subj.id,
                exam_type="Unit", total_marks=10, status="EVALUATING")
    db.add(exam); db.flush()
    doc = QuestionPaperDocument(exam_id=exam.id, original_filename="qp.pdf", original_file="x/original.pdf",
                                mime_type="application/pdf", file_size=1, status="OCR_PROCESSING")
    db.add(doc); db.commit()
    exam_id, doc_id = exam.id, doc.id
    db.close()

    recover_interrupted_jobs()

    db = SessionLocal()
    doc = db.get(QuestionPaperDocument, doc_id)
    assert doc.status == "FAILED" and doc.error_message == INTERRUPTED
    assert db.get(Exam, exam_id).status == "REVIEW_REQUIRED"
    db.close()
