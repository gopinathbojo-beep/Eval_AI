"""Accounts: portal-scoped sign-in, lockout, sessions, password reset, invitations and public signup."""
import uuid
import pytest
from app.database import SessionLocal
from app.models import School, User, Wallet
from app.security import hash_password
from app.services import accounts, mailer


@pytest.fixture
def outbox(monkeypatch):
    """Captures emails instead of writing them; each entry is (to, subject, link)."""
    sent = []
    monkeypatch.setattr(mailer, "send", lambda to, subject, heading, lines, button=None: sent.append((to, subject, button[1] if button else None)))
    return sent


@pytest.fixture(autouse=True)
def _no_rate_limits():
    accounts._hits.clear()


def _email() -> str:
    return f"u{uuid.uuid4().hex[:10]}@example.org"


def _user(role="parent", password="password123", **kw) -> User:
    db = SessionLocal()
    u = User(name="Test", email=kw.pop("email", _email()), role=role, password_hash=hash_password(password), **kw)
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u


def _login(client, email, password="password123", portal="parent"):
    return client.post("/api/auth/login", json={"email": email, "password": password, "portal": portal})


def test_login_is_scoped_to_the_portal(client):
    u = _user("parent")
    r = _login(client, u.email, portal="parent")
    assert r.status_code == 200 and r.json()["user"]["role"] == "parent"
    wrong = _login(client, u.email, portal="admin")
    assert wrong.status_code == 403 and wrong.json()["code"] == "WRONG_PORTAL"
    # a parent token cannot call teacher routes
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/exams", headers=h).status_code == 403


def test_wrong_password_and_unknown_email_look_the_same(client):
    u = _user()
    a = _login(client, u.email, password="nope12345")
    b = _login(client, _email())
    assert a.status_code == b.status_code == 401
    assert a.json()["message"] == b.json()["message"]


def test_lockout_after_repeated_failures(client):
    u = _user()
    for _ in range(5):
        _login(client, u.email, password="wrongpass1")
    r = _login(client, u.email)  # right password, but locked
    assert r.status_code == 423 and r.json()["code"] == "ACCOUNT_LOCKED"


def test_logout_everywhere_ends_old_sessions(client):
    u = _user()
    t = _login(client, u.email).json()["access_token"]
    h = {"Authorization": f"Bearer {t}"}
    assert client.get("/api/auth/me", headers=h).status_code == 200
    assert client.post("/api/auth/logout-all", headers=h).status_code == 200
    r = client.get("/api/auth/me", headers=h)
    assert r.status_code == 401 and r.json()["code"] == "SESSION_ENDED"


def test_suspended_account_is_refused_on_the_next_request(client):
    u = _user()
    h = {"Authorization": f"Bearer {_login(client, u.email).json()['access_token']}"}
    db = SessionLocal()
    db.get(User, u.id).status = "suspended"
    db.commit()
    db.close()
    assert client.get("/api/auth/me", headers=h).status_code == 401


def test_forced_password_change_blocks_other_routes(client):
    u = _user("teacher", must_change_password=True)
    s = _login(client, u.email, portal="teacher").json()
    h = {"Authorization": f"Bearer {s['access_token']}"}
    blocked = client.get("/api/exams", headers=h)
    assert blocked.status_code == 403 and blocked.json()["code"] == "PASSWORD_CHANGE_REQUIRED"
    weak = client.post("/api/auth/change-password", headers=h, json={"current_password": "password123", "new_password": "short"})
    assert weak.status_code == 422
    ok = client.post("/api/auth/change-password", headers=h, json={"current_password": "password123", "new_password": "newpass123"})
    assert ok.status_code == 200
    h2 = {"Authorization": f"Bearer {ok.json()['access_token']}"}
    assert client.get("/api/exams", headers=h2).status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 401  # the old token ended


def test_forgot_and_reset_password(client, outbox):
    u = _user()
    r = client.post("/api/auth/forgot-password", json={"email": u.email, "portal": "parent"})
    assert r.status_code == 200
    unknown = client.post("/api/auth/forgot-password", json={"email": _email(), "portal": "parent"})
    assert unknown.json()["message"] == r.json()["message"]  # same answer for an unknown email
    link = outbox[-1][2]
    token = link.split("token=")[1]
    assert client.post("/api/auth/reset-password", json={"token": token, "new_password": "fresh1234"}).status_code == 200
    again = client.post("/api/auth/reset-password", json={"token": token, "new_password": "other1234"})
    assert again.status_code == 400  # single use
    assert _login(client, u.email, password="fresh1234").status_code == 200


def test_teacher_invite_into_an_active_school(client):
    db = SessionLocal()
    school = School(name="Green Valley", status="ACTIVE")
    db.add(school)
    db.flush()
    t = User(name="New Teacher", email=_email(), role="teacher", school_id=school.id, status="invited")
    db.add(t)
    db.flush()
    raw = accounts.issue_link(db, "invite", user_id=t.id)
    db.commit()
    db.close()
    info = client.get(f"/api/auth/invite?token={raw}").json()
    assert info["school"] == "Green Valley"
    assert _login(client, t.email, portal="teacher").status_code == 401  # no password yet
    s = client.post("/api/auth/invite/accept", json={"token": raw, "password": "teach1234"})
    assert s.status_code == 200 and s.json()["user"]["school"]["name"] == "Green Valley"
    assert _login(client, t.email, password="teach1234", portal="teacher").status_code == 200


def test_teacher_of_a_pending_school_cannot_sign_in(client):
    db = SessionLocal()
    school = School(name="Pending School", status="PENDING")
    db.add(school)
    db.flush()
    email = _email()
    db.add(User(name="T", email=email, role="teacher", school_id=school.id, password_hash=hash_password("password123")))
    db.commit()
    db.close()
    r = _login(client, email, portal="teacher")
    assert r.status_code == 403 and r.json()["code"] == "SCHOOL_NOT_ACTIVE"


def test_parent_signup_confirms_email_and_grants_free_credits(client, outbox):
    email = _email()
    body = {"name": "Priya", "email": email, "phone": "+91 98765 43210", "password": "parent123",
            "accept_terms": True, "accept_privacy": True, "accept_child_data": True}
    r = client.post("/api/public/signup/parent", json=body)
    assert r.status_code == 200
    assert _login(client, email, password="parent123").status_code == 401  # nothing exists before the email check
    token = outbox[-1][2].split("token=")[1]
    s = client.post("/api/public/signup/verify-email", json={"token": token})
    assert s.status_code == 200 and s.json()["user"]["role"] == "parent"
    db = SessionLocal()
    w = db.query(Wallet).filter_by(owner_type="parent", owner_id=s.json()["user"]["id"]).one()
    assert w.balance == 10
    db.close()
    # a second account with the same phone number gets no second free tier
    email2 = _email()
    client.post("/api/public/signup/parent", json={**body, "email": email2, "phone": "9876543210"})
    s2 = client.post("/api/public/signup/verify-email", json={"token": outbox[-1][2].split("token=")[1]})
    db = SessionLocal()
    w2 = db.query(Wallet).filter_by(owner_type="parent", owner_id=s2.json()["user"]["id"]).first()
    assert w2 is None or w2.balance == 0
    db.close()


def test_signup_answer_is_the_same_for_an_existing_email(client, outbox):
    u = _user()
    body = {"name": "Someone", "email": u.email, "phone": "9000000001", "password": "parent123",
            "accept_terms": True, "accept_privacy": True, "accept_child_data": True}
    r = client.post("/api/public/signup/parent", json=body)
    assert r.status_code == 200 and "Check" in r.json()["message"]
    assert outbox[-1][1] == "You already have an ADEM account"


def test_signup_requires_consent(client):
    body = {"name": "Priya", "email": _email(), "phone": "9000000002", "password": "parent123",
            "accept_terms": True, "accept_privacy": True, "accept_child_data": False}
    assert client.post("/api/public/signup/parent", json=body).status_code == 422


def test_school_signup_waits_for_approval(client, outbox):
    email = _email()
    body = {"school_name": "Sunrise School", "phone": "9000000003", "manager_name": "Mrs Iyer", "email": email,
            "password": "school123", "accept_terms": True, "accept_privacy": True}
    assert client.post("/api/public/signup/school", json=body).status_code == 200
    s = client.post("/api/public/signup/verify-email", json={"token": outbox[-1][2].split("token=")[1]})
    assert s.status_code == 200
    me = s.json()["user"]
    assert me["role"] == "school_manager" and me["school"]["status"] == "PENDING"
    h = {"Authorization": f"Bearer {s.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=h).status_code == 200  # can see the pending status


def test_google_is_off_until_configured(client, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "google_client_id", "")  # whatever the local .env says
    r = client.post("/api/auth/google", json={"id_token": "x", "portal": "parent"})
    assert r.status_code == 503 and r.json()["code"] == "GOOGLE_DISABLED"
    assert client.get("/api/public/config").json()["google_client_id"] is None


# ---------- web app: one sign-in for school management and their invited teachers ----------
def _school(status="ACTIVE") -> str:
    db = SessionLocal()
    s = School(name="Green Valley School", status=status)
    db.add(s)
    db.commit()
    sid = s.id
    db.close()
    return sid


def _manager_headers(client, school_id):
    m = _user("school_manager", school_id=school_id)
    return {"Authorization": f"Bearer {_login(client, m.email, portal='web').json()['access_token']}"}


def test_web_sign_in_takes_managers_and_teachers_only(client):
    sid = _school()
    m = _user("school_manager", school_id=sid)
    t = _user("teacher", school_id=sid)
    assert _login(client, m.email, portal="web").json()["user"]["role"] == "school_manager"
    assert _login(client, t.email, portal="web").json()["user"]["role"] == "teacher"
    r = _login(client, _user("parent").email, portal="web")
    assert r.status_code == 403 and r.json()["code"] == "WRONG_PORTAL"
    # a manager's session is the school scope, not the teacher one
    h = {"Authorization": f"Bearer {_login(client, m.email, portal='web').json()['access_token']}"}
    assert client.get("/api/exams", headers=h).status_code == 403
    assert client.get("/api/school/teachers", headers=h).status_code == 200


def test_manager_of_a_pending_school_signs_in_but_cannot_manage_yet(client):
    sid = _school("PENDING")
    m = _user("school_manager", school_id=sid)
    r = _login(client, m.email, portal="web")
    assert r.status_code == 200 and r.json()["user"]["school"]["status"] == "PENDING"
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/school/teachers", headers=h).json()["code"] == "SCHOOL_NOT_ACTIVE"


def test_manager_invites_a_teacher_who_joins_and_signs_in_on_the_web(client, outbox):
    sid = _school()
    h = _manager_headers(client, sid)
    email = _email()
    r = client.post("/api/school/teachers", headers=h, json={"name": "Priya", "email": email.upper()})
    assert r.status_code == 201 and r.json()["status"] == "invited"
    to, _, link = outbox[-1]
    assert to == email and "/accept-invite?token=" in link
    # an invited teacher cannot sign in until they accept
    token = link.split("token=")[1]
    acc = client.post("/api/auth/invite/accept", json={"token": token, "password": "newpass123"})
    assert acc.status_code == 200 and acc.json()["user"]["role"] == "teacher"
    assert _login(client, email, "newpass123", portal="web").status_code == 200
    rows = client.get("/api/school/teachers", headers=h).json()
    assert [x["status"] for x in rows if x["email"] == email] == ["active"]


def test_invite_refuses_an_email_that_has_an_account(client, outbox):
    h = _manager_headers(client, _school())
    r = client.post("/api/school/teachers", headers=h, json={"name": "Dup", "email": _user("parent").email})
    assert r.status_code == 409 and r.json()["code"] == "EMAIL_TAKEN"


def test_cancelled_invite_link_stops_working_and_frees_the_email(client, outbox):
    h = _manager_headers(client, _school())
    email = _email()
    tid = client.post("/api/school/teachers", headers=h, json={"name": "Ravi", "email": email}).json()["id"]
    token = outbox[-1][2].split("token=")[1]
    assert client.delete(f"/api/school/teachers/{tid}/invite", headers=h).status_code == 200
    assert client.post("/api/auth/invite/accept", json={"token": token, "password": "newpass123"}).status_code == 400
    assert client.post("/api/school/teachers", headers=h, json={"name": "Ravi", "email": email}).status_code == 201


def test_manager_sees_and_manages_only_their_own_school(client, outbox):
    h = _manager_headers(client, _school())
    other = _user("teacher", school_id=_school())
    assert other.id not in [x["id"] for x in client.get("/api/school/teachers", headers=h).json()]
    r = client.put(f"/api/school/teachers/{other.id}/status", headers=h, json={"status": "suspended"})
    assert r.status_code == 404


def test_suspended_teacher_is_signed_out_and_can_be_reactivated(client):
    sid = _school()
    h = _manager_headers(client, sid)
    t = _user("teacher", school_id=sid)
    th = {"Authorization": f"Bearer {_login(client, t.email, portal='web').json()['access_token']}"}
    assert client.put(f"/api/school/teachers/{t.id}/status", headers=h, json={"status": "suspended"}).status_code == 200
    assert client.get("/api/auth/me", headers=th).status_code == 401
    assert client.put(f"/api/school/teachers/{t.id}/status", headers=h, json={"status": "active"}).json()["status"] == "active"
    assert _login(client, t.email, portal="web").status_code == 200
