from io import BytesIO
import sqlite3
import tarfile

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from app.config import Settings, get_settings
from app.login_limiter import LoginLimiter
from app.main import app, create_app
from scripts.backup_data import backup, restore


def test_browser_session_and_csrf(client):
    # A separate client prevents cookies leaking into the bearer API regression tests.
    with TestClient(app) as browser:
        credentials = {"email": "rao@school.org", "password": "password123", "browser_session": True}
        headers = {"X-Requested-With": "EvalAI", "Origin": "http://localhost:5173"}
        assert browser.post("/api/auth/login", json=credentials).status_code == 403
        evil = {**headers, "Origin": "https://attacker.example"}
        assert browser.post("/api/auth/login", json=credentials, headers=evil).status_code == 403
        response = browser.post("/api/auth/login", json=credentials, headers=headers)
        assert response.status_code == 200
        assert "access_token" not in response.json()
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api" in cookie
        assert browser.get("/api/auth/me").status_code == 200
        assert browser.post("/api/classes", json={"name": "Forged class"}).status_code == 403
        assert browser.post("/api/classes", json={"name": "Forged class"}, headers=evil).status_code == 403
        assert browser.post("/api/auth/logout", headers=headers).status_code == 204
        assert browser.get("/api/auth/me").status_code == 401


def test_cookie_secure_flag(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "cookie_secure", True)
    with TestClient(app, base_url="https://testserver") as browser:
        response = browser.post("/api/auth/login", json={"email": "rao@school.org", "password": "password123", "browser_session": True},
                                headers={"X-Requested-With": "EvalAI"})
        assert "; Secure" in response.headers["set-cookie"]
        assert browser.get("/api/auth/me").status_code == 200


def test_login_limiter(monkeypatch):
    import app.login_limiter as module
    clock = [100.0]
    monkeypatch.setattr(module, "monotonic", lambda: clock[0])
    limiter = LoginLimiter()
    limiter.check("address-1", 2)
    limiter.check("address-1", 2)
    with pytest.raises(HTTPException) as exc:
        limiter.check("address-1", 2)
    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "60"
    limiter.check("address-2", 2)
    clock[0] += 61
    limiter.check("address-1", 2)


def test_production_configuration():
    common = dict(_env_file=None, environment="production", secret_key="s" * 48,
                  cookie_secure=True, cors_origins="https://eval.example.com", allowed_hosts="eval.example.com")
    assert Settings(**common).cookie_secure
    for invalid in ({"secret_key": "short"}, {"cookie_secure": False}, {"cors_origins": "*"}, {"allowed_hosts": "*"}):
        with pytest.raises(ValueError):
            Settings(**{**common, **invalid})


def test_readiness_and_private_response(client, auth):
    assert client.get("/api/ready").json() == {"ok": True}
    assert client.get("/api/auth/me", headers=auth).headers["cache-control"] == "no-store"


def test_production_host_docs_and_query_tokens(client, auth, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "allowed_hosts", "eval.example.test")
    with TestClient(create_app(), base_url="https://eval.example.test") as production:
        assert production.get("/docs").status_code == 404
        assert production.get("/openapi.json").status_code == 404
        assert production.get("/api/ready").status_code == 200
        assert production.get("/api/ready", headers={"Host": "attacker.example"}).status_code == 400
        token = auth["Authorization"].removeprefix("Bearer ")
        assert production.get("/api/auth/me", params={"token": token}).status_code == 401
        assert production.get("/api/auth/me", headers=auth).status_code == 200


def test_offline_backup_and_restore(tmp_path):
    data = tmp_path / "source"
    data.mkdir()
    with sqlite3.connect(data / "adem.db") as db:
        db.execute("CREATE TABLE sample (name TEXT)")
        db.execute("INSERT INTO sample VALUES ('retained')")
    (data / "exams").mkdir()
    (data / "exams" / "paper.pdf").write_bytes(b"paper-content")
    archive = backup(data, tmp_path / "backups")
    restored = tmp_path / "restored"
    restore(archive, restored)
    assert (restored / "exams" / "paper.pdf").read_bytes() == b"paper-content"
    with sqlite3.connect(restored / "adem.db") as db:
        assert db.execute("SELECT name FROM sample").fetchone() == ("retained",)
    with pytest.raises(ValueError, match="empty"):
        restore(archive, restored)


def test_restore_rejects_traversal(tmp_path):
    archive = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        entry = tarfile.TarInfo("../escaped")
        entry.size = 4
        tar.addfile(entry, BytesIO(b"evil"))
    with pytest.raises(ValueError, match="Unsafe"):
        restore(archive, tmp_path / "restored")
    assert not (tmp_path / "escaped").exists()
