"""The parent exam (spec 07): a child, a sample paper chosen for a fixed charge, a server-held timer, pages only while
the exam runs, a quality-checked upload within the hour, MISSED when nothing comes, and delete-my-data."""
import io
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image

from app.database import SessionLocal
from app.models import AnswerKey, CreditSetting, Exam, ExamQuestion, ParentExam, SchoolClass, Subject, Teacher, Workspace
from app.security import create_token
from app.services import credits


def _parent(balance: int = 0) -> tuple[dict, str]:
    db = SessionLocal()
    p = Teacher(name="Parent", email=f"parent-{uuid.uuid4().hex[:6]}@x.org", role="PARENT", password_hash="!x",
                profile_completed_at=datetime.now(timezone.utc))
    db.add(p)
    db.flush()
    ws = Workspace(kind="FAMILY", name="Family", owner_id=p.id)
    db.add(ws)
    db.flush()
    p.workspace_id = ws.id
    if balance:
        credits.post(db, credits.wallet_for(db, "parent", p.id), "ADMIN_GRANT", balance, f"g-{p.id}")
    db.commit()
    h = {"Authorization": f"Bearer {create_token(p, portal='parent')}"}
    pid = p.id
    db.close()
    return h, pid


def _bank_paper(client) -> str:
    """A verified Class 10 Science exam turned into a sample paper by the console."""
    db = SessionLocal()
    owner = db.query(Teacher).filter_by(email="rao@school.org").one()
    cls = SchoolClass(teacher_id=owner.id, name="10-Bank")
    sub = Subject(teacher_id=owner.id, name="Science bank")
    db.add_all([cls, sub])
    db.flush()
    exam = Exam(teacher_id=owner.id, class_id=cls.id, subject_id=sub.id, name="Bank", academic_year="2026-27",
                exam_type="Sample", total_marks=5, duration_minutes=30, status="ANSWER_KEY_VERIFIED")
    db.add(exam)
    db.flush()
    q = ExamQuestion(exam_id=exam.id, display_number="1", normalized_number="1", question_text="Define force.", max_marks=5,
                     position=1)
    db.add(q)
    db.flush()
    db.add(AnswerKey(exam_id=exam.id, exam_question_id=q.id, answer_text="A push or a pull.", marks=5,
                     mapping_status="MAPPED", is_active=True))
    admin = Teacher(name="A", email=f"a-{uuid.uuid4().hex[:6]}@adem.test", role="ADMIN", admin_role="admin", password_hash="!x")
    db.add(admin)
    db.commit()
    ah = {"Authorization": f"Bearer {create_token(admin, portal='admin')}"}
    eid = exam.id
    db.close()
    r = client.post("/api/admin/papers", headers=ah, json={"exam_id": eid, "standard": 10, "subject": "Science"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _png(blurred: bool) -> bytes:
    img = Image.new("L", (900, 1200), 255)
    if not blurred:
        from PIL import ImageDraw
        d = ImageDraw.Draw(img)
        for y in range(40, 1160, 30):
            d.text((40, y), "The answer is a push or a pull " * 3, fill=0)
    b = io.BytesIO()
    img.save(b, "PNG")
    return b.getvalue()


def test_timed_exam_lifecycle(client):
    h, pid = _parent()
    paper = _bank_paper(client)
    child = client.post("/api/parent/children", headers=h, json={"name": "Asha", "standard": 10, "subjects": ["Science"]}).json()
    assert client.post("/api/parent/children", headers=h, json={"name": "X", "standard": 9}).status_code == 422
    assert any(p["id"] == paper for p in client.get("/api/parent/papers?standard=10", headers=h).json()["papers"])
    pe = client.post("/api/parent/exams", headers=h, json={"child_id": child["id"], "paper_id": paper}).json()
    assert pe["status"] == "PAPER_SELECTED" and pe["duration_minutes"] == 30
    assert client.get(f"/api/parent/exams/{pe['id']}/pages/1", headers=h).status_code == 403  # not started
    started = client.post(f"/api/parent/exams/{pe['id']}/start", headers=h).json()
    assert started["status"] == "IN_PROGRESS" and started["ends_at"] and started["upload_closes_at"]
    assert client.post(f"/api/parent/exams/{pe['id']}/start", headers=h).status_code == 409  # no restart
    bad = client.post(f"/api/parent/exams/{pe['id']}/upload", headers=h, files=[("files", ("s.png", _png(True), "image/png"))])
    assert bad.status_code == 422 and bad.json()["code"] == "QUALITY_CHECK_FAILED"
    assert client.get(f"/api/parent/exams/{pe['id']}/report", headers=h).status_code == 409
    with SessionLocal() as db:  # the clock moves past the end of the exam and of the upload window
        row = db.get(ParentExam, pe["id"])
        row.ends_at = datetime.now(timezone.utc) - timedelta(hours=2)
        row.upload_closes_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
    assert client.get(f"/api/parent/exams/{pe['id']}", headers=h).json()["status"] == "MISSED"
    late = client.post(f"/api/parent/exams/{pe['id']}/upload", headers=h, files=[("files", ("s.png", _png(False), "image/png"))])
    assert late.status_code == 409 and late.json()["code"] == "UPLOAD_CLOSED"


def test_paper_needs_credits_when_it_has_a_charge(client):
    h, _ = _parent(0)
    paper = _bank_paper(client)
    child = client.post("/api/parent/children", headers=h, json={"name": "Ravi", "standard": 10}).json()
    with SessionLocal() as db:
        db.merge(CreditSetting(key="paper_fixed", value=5))
        db.commit()
    try:
        r = client.post("/api/parent/exams", headers=h, json={"child_id": child["id"], "paper_id": paper})
        assert r.status_code == 402 and r.json()["code"] == "INSUFFICIENT_CREDITS"
    finally:
        with SessionLocal() as db:
            db.merge(CreditSetting(key="paper_fixed", value=0))
            db.commit()


def test_a_parent_sees_only_their_own_children(client):
    h1, _ = _parent()
    h2, _ = _parent()
    child = client.post("/api/parent/children", headers=h1, json={"name": "Mine", "standard": 12}).json()
    assert client.patch(f"/api/parent/children/{child['id']}", headers=h2, json={"name": "x", "standard": 12}).status_code == 404
    assert client.get("/api/parent/children", headers=h2).json() == []


def test_delete_my_data_closes_the_account(client):
    h, pid = _parent()
    client.post("/api/parent/children", headers=h, json={"name": "Gone", "standard": 10})
    assert client.post("/api/parent/delete-my-data", headers=h).status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 401
    with SessionLocal() as db:
        assert db.get(Teacher, pid).email.endswith("@deleted.invalid")
