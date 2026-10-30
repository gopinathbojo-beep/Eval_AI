from datetime import datetime, timezone
from uuid import uuid4

from app.database import SessionLocal
from app.models import (
    AuditLog,
    Exam,
    QuestionPaperDocument,
    SchoolClass,
    Subject,
    Teacher,
)
from app.services import job_queue
from app.services.audit import audit


def test_jobs_keep_actor_attribution_and_recheck_access(client):
    with SessionLocal() as db:
        manager = db.query(Teacher).filter_by(email="rao@school.org").one()
        teacher = Teacher(
            name="Job teacher",
            email=f"{uuid4().hex}@example.com",
            role="TEACHER",
            workspace_id=manager.workspace_id,
            password_hash="!unused",
            is_active=False,
            profile_completed_at=datetime.now(timezone.utc),
        )
        db.add(teacher)
        cls = SchoolClass(teacher_id=manager.id, name="10-Queue")
        subject = Subject(teacher_id=manager.id, name="Queue English")
        db.add_all([cls, subject])
        db.flush()
        exam = Exam(
            teacher_id=teacher.id,
            workspace_id=manager.workspace_id,
            class_id=cls.id,
            subject_id=subject.id,
            name="Queue test",
            academic_year="2026-27",
            exam_type="Unit",
            total_marks=2,
        )
        db.add(exam)
        db.flush()
        document = QuestionPaperDocument(
            exam_id=exam.id,
            original_filename="paper.pdf",
            original_file="paper.pdf",
            mime_type="application/pdf",
            file_size=1,
        )
        db.add(document)
        db.commit()
        eid, did, tid, mid, version = (
            exam.id,
            document.id,
            teacher.id,
            manager.id,
            manager.session_version,
        )
    called = []

    def run():
        called.append(True)
        with SessionLocal() as db:
            audit(
                db,
                exam_id=eid,
                teacher_id=tid,
                entity_type="exam",
                entity_id=eid,
                action="ai_grading_request",
            )
            db.commit()

    job_queue._call(
        job_queue._Job(
            "internvl", run, (), exam_id=eid, actor_id=mid, session_version=version
        )
    )
    assert called == [True]
    with SessionLocal() as db:
        event = (
            db.query(AuditLog).filter_by(exam_id=eid, action="ai_grading_request").one()
        )
        assert event.teacher_id == mid and event.workspace_id == manager.workspace_id
    called.clear()
    job_queue._call(
        job_queue._Job(
            "internvl", run, (), exam_id=eid, actor_id=tid, session_version=0
        )
    )
    assert not called
    with SessionLocal() as db:
        assert db.get(QuestionPaperDocument, did).status == "NEEDS_ATTENTION"
