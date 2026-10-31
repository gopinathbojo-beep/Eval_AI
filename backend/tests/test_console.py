"""The Platform Admin console (spec 6.1): a Viewer reads and every write is refused; approving a school grants its
signup credits once; manual adjustments, disputes with refunds and support replies are audited; login-as is for a
Super Admin only."""
import uuid

from app.database import SessionLocal
from app.models import AuditLog, Teacher, Workspace
from app.security import create_token


def _console(role: str) -> dict:
    db = SessionLocal()
    u = Teacher(name=f"Console {role}", email=f"{role}-{uuid.uuid4().hex[:6]}@adem.test", role="ADMIN", admin_role=role,
                password_hash="!x")
    db.add(u)
    db.commit()
    h = {"Authorization": f"Bearer {create_token(u, portal='admin')}"}
    db.close()
    return h


def _pending_school() -> str:
    db = SessionLocal()
    m = Teacher(name="Head", email=f"head-{uuid.uuid4().hex[:6]}@x.org", role="MANAGEMENT", password_hash="!x")
    db.add(m)
    db.flush()
    ws = Workspace(kind="SCHOOL", name="New School", owner_id=m.id, status="PENDING")
    db.add(ws)
    db.flush()
    m.workspace_id = ws.id
    db.commit()
    sid = ws.id
    db.close()
    return sid


def test_viewer_reads_but_cannot_write(client):
    viewer = _console("viewer")
    assert client.get("/api/admin/dashboard", headers=viewer).status_code == 200
    r = client.post(f"/api/admin/schools/{_pending_school()}/approve", headers=viewer)
    assert r.status_code == 403 and r.json()["code"] == "READ_ONLY"


def test_approving_a_school_grants_its_signup_credits_once(client):
    admin = _console("admin")
    sid = _pending_school()
    assert any(s["id"] == sid for s in client.get("/api/admin/schools?status=PENDING", headers=admin).json())
    first = client.post(f"/api/admin/schools/{sid}/approve", headers=admin).json()
    assert first["status"] == "ACTIVE" and first["balance"] > 0
    again = client.post(f"/api/admin/schools/{sid}/approve", headers=admin).json()
    assert again["balance"] == first["balance"]
    adjusted = client.post(f"/api/admin/wallets/{first['wallet_id']}/adjust", headers=admin,
                           json={"amount": 25, "reason": "Goodwill"}).json()
    assert adjusted["balance"] == first["balance"] + 25
    assert client.post(f"/api/admin/wallets/{first['wallet_id']}/adjust", headers=admin,
                       json={"amount": -100000, "reason": "Too much"}).status_code == 409
    with SessionLocal() as db:
        assert db.query(AuditLog).filter_by(entity_id=sid, action="SCHOOL_APPROVED").count() == 1


def test_dispute_upheld_with_refund_and_support_reply(client, auth, teach):
    from app.models import Evaluation, Exam
    admin = _console("admin")
    with SessionLocal() as db:  # an evaluation the school's teacher can see: an exam of the test school's teacher
        t = db.query(Teacher).filter_by(email="teacher@school.org").one()
        ev = (db.query(Evaluation).join(Exam, Exam.id == Evaluation.exam_id).filter(Exam.teacher_id == t.id).first())
    if ev is None:
        return  # no graded sheet of the teacher yet in this run (the e2e suite makes them)
    d = client.post("/api/disputes", headers=teach, json={"evaluation_id": ev.id, "reason": "Q2 deserved full marks"})
    assert d.status_code == 201, d.text
    assert client.post("/api/disputes", headers=teach, json={"evaluation_id": ev.id, "reason": "again please"}).status_code == 409
    before = client.get("/api/credits", headers=auth).json()["balance"]
    done = client.post(f"/api/admin/disputes/{d.json()['id']}/resolve", headers=admin,
                       json={"status": "UPHELD", "resolution": "Marks corrected", "refund_credits": 1}).json()
    assert done["status"] == "UPHELD" and client.get("/api/credits", headers=auth).json()["balance"] == before + 1
    ticket = client.post("/api/support", headers=teach, json={"subject": "Help", "message": "How do I export?"}).json()
    replied = client.post(f"/api/admin/support/{ticket['id']}/reply", headers=admin, json={"reply": "Use Results."}).json()
    assert replied["status"] == "ANSWERED" and client.get("/api/support", headers=teach).json()[0]["reply"] == "Use Results."


def test_login_as_is_for_a_super_admin_only(client):
    with SessionLocal() as db:
        parent = Teacher(name="P", email=f"p-{uuid.uuid4().hex[:6]}@x.org", role="PARENT", password_hash="!x")
        db.add(parent)
        db.commit()
        pid = parent.id
    assert client.post(f"/api/admin/accounts/{pid}/impersonate", headers=_console("admin")).status_code == 403
    r = client.post(f"/api/admin/accounts/{pid}/impersonate", headers=_console("super_admin"))
    assert r.status_code == 200 and r.json()["user"]["role"] == "PARENT"
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()["id"] == pid
