import json
from time import time
from urllib.parse import parse_qs, urlsplit

from authlib.integrations.starlette_client import OAuth
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
import httpx
import jwt
import pytest

from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.models import AuditLog, Teacher
from app.routes import google_auth
from app.security import create_token


def test_existing_teacher_migration_preserves_credentials(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, inspect, text
    from app import database
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE teachers (id VARCHAR(36) PRIMARY KEY, name TEXT, email TEXT, password_hash TEXT, created_at DATETIME)"))
        conn.execute(text("INSERT INTO teachers (id,name,email,password_hash) VALUES ('old','Existing','old@example.com','preserved-hash')"))
    monkeypatch.setattr(database, "engine", engine)
    database._add_missing_columns()
    database._add_missing_columns()
    assert {"is_active", "google_sub", "session_version", "last_login_at"} <= {c["name"] for c in inspect(engine).get_columns("teachers")}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT password_hash,is_active,session_version,approval_status,registration_source FROM teachers")).one() == ("preserved-hash", 1, 0, "APPROVED", "ADMIN")


@pytest.fixture
def owner_headers(client):
    with SessionLocal() as db:
        owner = db.query(Teacher).filter_by(email=get_settings().admin_email).one()
        return {"Authorization": f"Bearer {create_token(owner.id, owner.session_version)}"}


def test_teacher_cannot_manage_users(client, auth):
    assert client.get("/api/admin/users").status_code == 401
    assert client.get("/api/admin/users", headers=auth).status_code == 403
    assert client.post("/api/admin/users", headers=auth, json={"name": "X", "email": "x@example.com"}).status_code == 405


def test_owner_manages_teacher_and_revokes_sessions(client, owner_headers, auth):
    result = client.post("/api/management/teachers", headers=auth,
                         json={"name": "Managed Teacher", "email": "managed@example.com", "password": "initial-password-123"})
    assert result.status_code == 201, result.text
    user = result.json()
    assert "password_hash" not in user and "google_sub" not in user
    login = client.post("/api/auth/login", json={"email": user["email"], "password": "initial-password-123"}).json()
    old_headers = {"Authorization": f"Bearer {login['access_token']}"}
    assert client.patch(f"/api/admin/users/{user['id']}", headers=owner_headers, json={"is_active": False}).status_code == 200
    assert client.get("/api/auth/me", headers=old_headers).status_code == 401
    assert client.post("/api/auth/login", json={"email": user["email"], "password": "initial-password-123"}).status_code == 403
    client.patch(f"/api/admin/users/{user['id']}", headers=owner_headers, json={"is_active": True, "password": "reset-password-123"})
    assert client.get("/api/auth/me", headers=old_headers).status_code == 401
    assert client.post("/api/auth/login", json={"email": user["email"], "password": "reset-password-123"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": user["email"], "password": "initial-password-123"}).status_code == 401
    assert client.post("/api/management/teachers", headers=auth, json={"name": "Duplicate", "email": user["email"], "password":"initial-password-123"}).status_code == 409
    rows = client.get("/api/admin/users?q=managed@example.com", headers=owner_headers).json()
    assert rows["total"] == 1
    events = client.get(f"/api/admin/activity?user_id={user['id']}", headers=owner_headers).json()["events"]
    assert {"password_login"} <= {e["action"] for e in events}
    assert all("new_value" not in event for event in events)


def test_owner_is_protected_and_bulk_uploads_count_files(client, owner_headers):
    with SessionLocal() as db:
        owner = db.query(Teacher).filter_by(email=get_settings().admin_email).one()
        teacher = Teacher(name="Usage", email="usage@example.com", password_hash="!google-only")
        db.add(teacher)
        db.flush()
        teacher_id = teacher.id
        for action, value in [("answer_sheets_bulk_uploaded", ["a.pdf", "b.pdf", "c.pdf"]),
                              ("question_paper_uploaded", "paper.pdf"), ("ai_evaluation_started", None),
                              ("ai_grading_request", None), ("ai_grading_request", None)]:
            db.add(AuditLog(teacher_id=teacher_id, entity_type="exam", entity_id="usage-test", action=action, new_value=value))
        db.commit()
        owner_id = owner.id
    assert client.patch(f"/api/admin/users/{owner_id}", headers=owner_headers, json={"is_active": False}).status_code == 400
    user = client.get("/api/admin/users?q=usage@example.com", headers=owner_headers).json()["users"][0]
    assert user["uploads"] == 4
    assert user["ai_runs"] == 1 and user["ai_requests"] == 2


@pytest.fixture
def google_provider(monkeypatch, client):
    """A real signed ID token/JWKS exchange through Authlib, without contacting Google."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="test-key", alg="RS256", use="sig")
    values = {"email": get_settings().admin_email, "email_verified": True, "sub": "google-owner", "nonce": "", "tamper_nonce": False,
              "audience": "test-client", "issuer": "https://accounts.google.com", "expired": False, "bad_signature": False}
    def handle(request):
        if request.url.path.endswith("openid-configuration"):
            return httpx.Response(200, json={"issuer": "https://accounts.google.com", "authorization_endpoint": "https://provider.test/auth",
                "token_endpoint": "https://provider.test/token", "jwks_uri": "https://provider.test/jwks", "id_token_signing_alg_values_supported": ["RS256"]})
        if request.url.path == "/jwks":
            return httpx.Response(200, json={"keys": [jwk]})
        if request.url.path == "/token":
            assert "code_verifier=" in request.content.decode()
            claims = {"iss": values["issuer"], "aud": values["audience"], "iat": int(time()) - 2000, "exp": int(time()) - 1000 if values["expired"] else int(time()) + 300,
                      "nonce": "wrong-nonce" if values["tamper_nonce"] else values["nonce"], "sub": values["sub"],
                      "email": values["email"], "email_verified": values["email_verified"]}
            return httpx.Response(200, json={"access_token": "provider-access-token", "token_type": "Bearer",
                "id_token": jwt.encode(claims, rsa.generate_private_key(public_exponent=65537, key_size=2048) if values["bad_signature"] else key,
                                       algorithm="RS256", headers={"kid": "test-key"})})
        raise AssertionError(request.url)
    oauth = OAuth()
    provider = oauth.register("google", client_id="test-client", client_secret="test-secret",
        server_metadata_url="https://provider.test/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256", "transport": httpx.MockTransport(handle)})
    monkeypatch.setattr(google_auth, "google_client", lambda: provider)
    monkeypatch.setattr(get_settings(), "google_client_id", "test-client")
    monkeypatch.setattr(get_settings(), "google_client_secret", "test-secret")
    monkeypatch.setattr(get_settings(), "google_redirect_uri", "http://localhost:5173/api/auth/google/callback")
    return values


def start(browser, values):
    response = browser.get("/api/auth/google/start", follow_redirects=False)
    assert response.status_code == 302, response.headers
    params = parse_qs(urlsplit(response.headers["location"]).query)
    values["nonce"] = params["nonce"][0]
    assert params["code_challenge_method"] == ["S256"]
    return params["state"][0]


def test_google_owner_and_password_methods_coexist(google_provider):
    with TestClient(app, base_url="http://localhost:5173") as browser:
        state = start(browser, google_provider)
        response = browser.get("/api/auth/google/callback", params={"code": "one-use-code", "state": state}, follow_redirects=False)
        assert response.headers["location"] == "http://localhost:5173/admin"
        me = browser.get("/api/auth/me").json()
        assert me["is_admin"] is True
        assert "httponly" in response.headers["set-cookie"].lower()
        headers = {"X-Requested-With": "EvalAI"}
        reset = browser.patch(f"/api/admin/users/{me['id']}", json={"password": "owner-new-password-123"}, headers=headers)
        assert reset.status_code == 200
        assert browser.get("/api/auth/me").status_code == 200  # own session is renewed
        assert browser.post("/api/auth/logout", headers=headers).status_code == 204
        password_login = browser.post("/api/auth/login", json={"email": me["email"], "password": "owner-new-password-123", "browser_session": True}, headers=headers)
        assert password_login.status_code == 200
        assert password_login.json()["teacher"]["is_admin"] is True


@pytest.mark.parametrize("failure", ["state", "nonce", "unverified_email", "audience", "issuer", "expired", "bad_signature"])
def test_google_rejects_invalid_identity(google_provider, failure):
    with TestClient(app, base_url="http://localhost:5173") as browser:
        state = start(browser, google_provider)
        if failure == "state":
            state = "forged-state"
        elif failure == "nonce":
            google_provider["tamper_nonce"] = True
        elif failure == "unverified_email":
            google_provider["email_verified"] = False
        elif failure == "audience":
            google_provider["audience"] = "someone-elses-client"
        elif failure == "issuer":
            google_provider["issuer"] = "https://attacker.example"
        else:
            google_provider[failure] = True
        response = browser.get("/api/auth/google/callback", params={"code": "code", "state": state}, follow_redirects=False)
        assert "oauth_error=" in response.headers["location"]
        assert browser.get("/api/auth/me").status_code == 401


def test_new_google_user_must_complete_profile_without_approval(google_provider):
    google_provider.update(email="public-google@example.com", sub="public-google-sub")
    with TestClient(app, base_url="http://localhost:5173") as browser:
        state = start(browser, google_provider)
        response = browser.get("/api/auth/google/callback", params={"code": "new-user-code", "state": state}, follow_redirects=False)
        assert response.headers["location"] == "http://localhost:5173/onboarding"
        assert browser.get("/api/auth/me").json()["role"] == "UNASSIGNED"
        assert browser.get("/api/dashboard").status_code == 403


def test_google_disabled_user_and_changed_subject_are_rejected(client):
    with SessionLocal() as db:
        teacher = Teacher(name="Google Bound", email="bound@example.com", password_hash="!google-only", google_sub="original-sub", is_active=False)
        db.add(teacher)
        db.commit()
        claims = {"email": teacher.email, "email_verified": True, "sub": "original-sub"}
        assert google_auth.teacher_for_google(db, claims) is None
        teacher.is_active = True
        db.commit()
        assert google_auth.teacher_for_google(db, {**claims, "sub": "different-sub"}) is None
        assert google_auth.teacher_for_google(db, claims).id == teacher.id


def test_password_account_links_google_only_from_authenticated_flow(google_provider, auth):
    google_provider.update(email="rao@school.org", sub="linked-school-owner")
    with TestClient(app, base_url="http://localhost:5173") as browser:
        state = start(browser, google_provider)
        response = browser.get("/api/auth/google/callback", params={"code":"unlinked", "state":state}, follow_redirects=False)
        assert "oauth_error=" in response.headers["location"]
        assert browser.get("/api/auth/me").status_code == 401
        response = browser.get("/api/auth/google/link", headers=auth, follow_redirects=False)
        params = parse_qs(urlsplit(response.headers["location"]).query)
        google_provider["nonce"] = params["nonce"][0]
        response = browser.get("/api/auth/google/callback", params={"code":"linked", "state":params["state"][0]}, follow_redirects=False)
        assert response.headers["location"].endswith("/dashboard")
        assert browser.get("/api/auth/me").json()["email_verified"]


def test_google_start_behind_vercel_proxy_does_not_redirect_in_a_loop(google_provider, monkeypatch):
    monkeypatch.setattr(get_settings(), "public_web_url", "http://localhost:5173")
    with TestClient(app, base_url="https://backend.onrender.com") as browser:
        response = browser.get("/api/auth/google/start", follow_redirects=False)
        assert response.status_code == 302
        assert urlsplit(response.headers["location"]).hostname == "provider.test"
