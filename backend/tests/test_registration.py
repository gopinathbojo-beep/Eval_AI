from uuid import uuid4

from app.database import SessionLocal
from app.main import app
from app.models import Teacher
from app.routes.google_auth import teacher_for_google
from fastapi.testclient import TestClient

HEADERS = {"X-Requested-With": "EvalAI"}
PROFILE = {
    "name": "School Owner",
    "phone": "9876543210",
    "school_name": "CBSE School",
    "address": "School Road",
    "city": "Chennai",
    "state": "Tamil Nadu",
    "postcode": "600001",
}


def signup(browser, role="MANAGEMENT"):
    email = f"user-{uuid4().hex}@example.com"
    result = browser.post(
        "/api/auth/register",
        headers=HEADERS,
        json={
            "name": "Owner",
            "email": email,
            "password": "initial-password-123",
            "role": role,
        },
    )
    assert result.status_code == 201, result.text
    return result.json()["teacher"]


def test_school_self_service_no_approval(client):
    with TestClient(app) as browser:
        user = signup(browser)
        assert not user["profile_complete"] and not user["is_admin"]
        assert browser.get("/api/dashboard").status_code == 403
        result = browser.put("/api/auth/profile", headers=HEADERS, json=PROFILE)
        assert result.status_code == 200, result.text
        assert result.json()["teacher"]["workspace_id"]
        assert browser.get("/api/dashboard").status_code == 200
        assert browser.get("/api/admin/users").status_code == 403
        assert (
            browser.put(
                "/api/auth/profile",
                headers=HEADERS,
                json={
                    **PROFILE,
                    "role": "PARENT",
                    "child_name": "Child",
                    "child_class": "10",
                },
            ).status_code
            == 409
        )


def test_parent_has_exactly_one_child(client):
    with TestClient(app) as browser:
        signup(browser, "PARENT")
        profile = {
            "name": "Parent",
            "phone": "1234567890",
            "child_name": "Child",
            "child_class": "10",
        }
        assert (
            browser.put("/api/auth/profile", headers=HEADERS, json=profile).status_code
            == 200
        )
        assert (
            browser.put(
                "/api/auth/profile",
                headers=HEADERS,
                json={**profile, "child_name": "Updated child"},
            ).status_code
            == 200
        )
        students = browser.get("/api/students").json()
        assert len(students) == 1 and students[0]["name"] == "Updated child"
        assert (
            browser.post(
                "/api/students",
                headers=HEADERS,
                json={
                    "name": "Second",
                    "roll_number": "2",
                    "class_id": students[0]["class_id"],
                },
            ).status_code
            == 403
        )
        assert (
            browser.put(
                "/api/auth/profile",
                headers=HEADERS,
                json={**profile, "child_class": "11"},
            ).status_code
            == 422
        )


def test_registration_roles_csrf_and_google_link_protection(client):
    with TestClient(app) as browser:
        body = {
            "name": "Account",
            "email": f"{uuid4().hex}@example.com",
            "password": "initial-password-123",
            "role": "ADMIN",
        }
        assert (
            browser.post("/api/auth/register", headers=HEADERS, json=body).status_code
            == 422
        )
        body["role"] = "TEACHER"
        assert (
            browser.post("/api/auth/register", headers=HEADERS, json=body).status_code
            == 422
        )
        body["role"] = "PARENT"
        assert browser.post("/api/auth/register", json=body).status_code == 403
        assert (
            browser.post("/api/auth/register", headers=HEADERS, json=body).status_code
            == 201
        )
        assert (
            browser.post("/api/auth/register", headers=HEADERS, json=body).status_code
            == 409
        )
        with SessionLocal() as db:
            user = db.query(Teacher).filter_by(email=body["email"]).one()
            original = user.password_hash
            assert (
                teacher_for_google(
                    db,
                    {
                        "email_verified": True,
                        "email": body["email"],
                        "sub": "unauthenticated-link",
                    },
                )
                is None
            )
            assert user.password_hash == original and user.google_sub is None
