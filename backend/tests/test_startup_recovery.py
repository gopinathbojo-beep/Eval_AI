from app.database import SessionLocal
from app.models import Exam, QuestionPaperDocument, SchoolClass, Subject, Teacher
from app.services import job_queue
from app.services.recovery import INTERRUPTED, recover_interrupted_jobs


def _exam_with_doc(name: str, **doc_fields):
    db = SessionLocal()
    t = db.query(Teacher).filter_by(email="rao@school.org").one()
    cls, subj = SchoolClass(teacher_id=t.id, name=f"{name} 8A"), Subject(teacher_id=t.id, name=f"{name} Science")
    db.add_all([cls, subj]); db.flush()
    exam = Exam(teacher_id=t.id, name=name, academic_year="2026", class_id=cls.id, subject_id=subj.id,
                exam_type="Unit", total_marks=10, status="EVALUATING")
    db.add(exam); db.flush()
    doc = QuestionPaperDocument(exam_id=exam.id, original_filename="qp.pdf", original_file="x/original.pdf",
                                mime_type="application/pdf", file_size=1, status="OCR_PROCESSING", **doc_fields)
    db.add(doc); db.commit()
    ids = exam.id, doc.id
    db.close()
    return ids


def test_restart_resumes_a_document_stuck_mid_processing(client, monkeypatch):
    """A restart (uvicorn --reload on a code change) carries on reading the document, keeping the pages read."""
    queued = []
    monkeypatch.setattr(job_queue, "submit", lambda exam_id, fn, *args, **kw: queued.append((exam_id, fn.__name__, args)))
    exam_id, doc_id = _exam_with_doc("Recovery test", pages=[{"page_number": 1, "ocr_status": "OK"}, {"page_number": 2}])

    recover_interrupted_jobs()

    db = SessionLocal()
    doc = db.get(QuestionPaperDocument, doc_id)
    assert doc.status == "UPLOADED" and doc.error_message is None
    assert (exam_id, "process_document", ("question-paper", doc_id, True)) in queued  # only the pages not read yet
    assert db.get(Exam, exam_id).status == "REVIEW_REQUIRED"
    db.close()


def test_restart_fails_a_replaced_document_instead_of_resuming_it(client, monkeypatch):
    queued = []
    monkeypatch.setattr(job_queue, "submit", lambda *a, **kw: queued.append(a))
    _, doc_id = _exam_with_doc("Recovery replaced", is_active=False)

    recover_interrupted_jobs()

    db = SessionLocal()
    doc = db.get(QuestionPaperDocument, doc_id)
    assert doc.status == "FAILED" and doc.error_message == INTERRUPTED
    assert not any(doc_id in str(a) for a in queued)
    db.close()
