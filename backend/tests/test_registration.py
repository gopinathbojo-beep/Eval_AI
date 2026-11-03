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
    "principal_name": "Dr. Lakshmi",
}


def signup(browser, role="MANAGEMENT"):
    email = f"user-{uuid4().hex}@example.com"
    result = browser.post(
        "/api/auth/register",
        headers=HEADERS,
        json={
            "name": "Owner",
            "email": email,
            "password": "Initial-password-123",
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
            "password": "Initial-password-123",
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


# trimmed from the real SARAS page for affiliation 1930001
SARAS_PAGE = """<html><body><table>
<tr><td width="433"><b>Name of Institution</b></td><td width="494">
    THE LAWRENCE SCHOOL </td></tr>
<tr><td><b>Affiliation Number</b></td><td> 1930001 </td></tr>
<tr><td><b>State</b></td><td> TAMILNADU </td></tr>
<tr><td><b>District</b></td><td> NILGIRIS </td></tr>
<tr><td><b>Postal Address</b></td><td> LOVEDALE OOTACAMUND THE NILGIRIS TAMIL NADU 643003 </td></tr>
<tr><td><b>Pin Code</b></td><td> 643003 </td></tr>
<tr><td><b>Website</b></td><td> www.thelawrenceschool.org </td></tr>
<tr><td><b>Name of Principal/ Head of Institution</b></td><td> Dhavala Venkata Someswara Rao </td></tr>
<tr><td><b>Status of The School</b></td><td> Senior Secondary Level </td></tr>
<tr><td><b>School Type</b></td><td> INDEPENDENT </td></tr>
<tr><td><b>Affiliation Period </b></td><td><p><b>From :</b>&nbsp;01/04/2024&nbsp;<b> To :</b>&nbsp;31/03/2029&nbsp;</p></td></tr>
<tr><td><b>Name of Trust/ Society/ Managing Committee</b></td><td> MINISTRY OF HUMAN RESOURCE DEV DEPT </td></tr>
</table></body></html>"""


def test_saras_page_parsed():
    from app.services.cbse_affiliation import parse

    school = parse(SARAS_PAGE)
    assert school["school_name"] == "The Lawrence School"
    assert school["affiliation_number"] == "1930001"
    assert school["address"] == "Lovedale Ootacamund The Nilgiris Tamil Nadu"  # the PIN has its own field
    assert (school["district"], school["state"], school["postcode"]) == ("Nilgiris", "Tamilnadu", "643003")
    assert school["principal_name"] == "Dhavala Venkata Someswara Rao"
    assert school["school_level"] == "Senior Secondary Level"
    assert school["affiliation_to"] == "31/03/2029"
    # capitals tidied without "Mary'S"
    assert parse(SARAS_PAGE.replace("THE LAWRENCE SCHOOL", "ST. MARY'S SR. SEC. SCHOOL"))["school_name"] == "St. Mary's Sr. Sec. School"
    # an unknown number gets the page frame with no school rows
    assert parse("<html><body><h1>Details OF SCHOOL AFFILIATED TO</h1></body></html>") is None


def test_affiliation_lookup_endpoint(client, monkeypatch):
    from app.services import cbse_affiliation

    pages = {"1930001": SARAS_PAGE}

    def fake_lookup(number):
        if number == "1111111":
            raise cbse_affiliation.LookupFailed("timed out")
        page = pages.get(number)
        return cbse_affiliation.parse(page) if page else None

    monkeypatch.setattr(cbse_affiliation, "lookup", fake_lookup)
    with TestClient(app) as browser:
        assert browser.get("/api/auth/affiliation/1930001").status_code == 401  # signed-in accounts only
        signup(browser)
        found = browser.get("/api/auth/affiliation/1930001")
        assert found.status_code == 200, found.text
        assert found.json()["principal_name"] == "Dhavala Venkata Someswara Rao"
        assert browser.get("/api/auth/affiliation/2222222").json()["code"] == "AFFILIATION_NOT_FOUND"
        assert browser.get("/api/auth/affiliation/1111111").status_code == 502
        assert browser.get("/api/auth/affiliation/12ab").status_code == 400
