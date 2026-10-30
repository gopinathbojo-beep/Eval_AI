"""Opt-in live-model smoke test in an isolated temporary database (no production data).

Run from the project root: backend/.venv/Scripts/python.exe backend/scripts/workspace_smoke.py
Reads local model configuration; never prints credentials. Writes reports under ignored .e2e-data.
"""

import os
import sys
import tempfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="eval-live-workspaces-")
os.environ["ENVIRONMENT"] = "development"
os.environ["COOKIE_SECURE"] = "false"
os.environ["JOB_QUEUE_INLINE"] = "true"
os.environ["PDF_RENDER_DPI"] = "96"
os.environ["GOOGLE_CLIENT_ID"] = ""
os.environ["GOOGLE_CLIENT_SECRET"] = ""

from app.main import app
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

HEADERS = {"X-Requested-With": "EvalAI"}


def pdf(lines):
    stream = BytesIO()
    doc = canvas.Canvas(stream)
    for i, line in enumerate(lines):
        doc.drawString(60, 780 - i * 30, line)
    doc.save()
    return stream.getvalue()


def checked(response, status=200):
    if response.status_code != status:
        raise RuntimeError(
            f"{response.request.url.path}: HTTP {response.status_code}: {response.text[:1000]}"
        )
    return response.json()


def exercise(role):
    with TestClient(app) as browser:
        checked(
            browser.post(
                "/api/auth/register",
                headers=HEADERS,
                json={
                    "name": "Live test",
                    "email": f"live-{role.lower()}@example.com",
                    "password": "live-test-password-123",
                    "role": role,
                },
            ),
            201,
        )
        profile = {
            "name": "Live test",
            "phone": "9876543210",
            "school_name": "Live CBSE School",
            "address": "School Road",
            "city": "Chennai",
            "state": "Tamil Nadu",
            "postcode": "600001",
            "child_name": "Aditi",
            "child_class": "10",
        }
        checked(browser.put("/api/auth/profile", headers=HEADERS, json=profile))
        if role == "MANAGEMENT":
            cls = checked(
                browser.post(
                    "/api/classes", headers=HEADERS, json={"std": "10", "section": "A"}
                ),
                201,
            )
            student = checked(
                browser.post(
                    "/api/students",
                    headers=HEADERS,
                    json={"name": "Aditi", "roll_number": "1", "class_id": cls["id"]},
                ),
                201,
            )
        else:
            cls = checked(browser.get("/api/classes"))[0]
            student = checked(browser.get("/api/students"))[0]
        subject = checked(
            browser.post("/api/subjects", headers=HEADERS, json={"name": "English"}),
            201,
        )
        exam = checked(
            browser.post(
                "/api/exams",
                headers=HEADERS,
                json={
                    "name": "Live model smoke",
                    "class_id": cls["id"],
                    "subject_id": subject["id"],
                    "exam_type": "Unit",
                    "total_marks": 2,
                },
            ),
            201,
        )
        eid = exam["id"]
        for kind, lines in (
            (
                "question-paper",
                [
                    "CBSE Class 10 - English - Total marks: 2",
                    "1. Write the plural of cat. (2 marks)",
                ],
            ),
            (
                "answer-key",
                [
                    "Answer key and marking scheme",
                    "1. cats",
                    "Award 2 marks for the correct plural: cats.",
                    "Maximum marks: 2",
                ],
            ),
        ):
            print(role, "upload", kind, flush=True)
            checked(
                browser.post(
                    f"/api/exams/{eid}/{kind}",
                    headers=HEADERS,
                    files={"file": (f"{kind}.pdf", pdf(lines), "application/pdf")},
                ),
                202,
            )
            if kind == "question-paper":
                checked(
                    browser.post(
                        f"/api/exams/{eid}/questions/accept-valid", headers=HEADERS
                    )
                )
                checked(
                    browser.post(f"/api/exams/{eid}/questions/verify", headers=HEADERS)
                )
            else:
                checked(
                    browser.post(
                        f"/api/exams/{eid}/answer-keys/verify", headers=HEADERS
                    )
                )
        print(role, "upload answer sheet", flush=True)
        data = {"student_id": student["id"]} if role == "MANAGEMENT" else {}
        ev = checked(
            browser.post(
                f"/api/exams/{eid}/answer-sheets",
                headers=HEADERS,
                data=data,
                files={
                    "file": (
                        "sheet.pdf",
                        pdf(
                            ["Student: Aditi - Roll number: 1", "Class: 10", "1. cats"]
                        ),
                        "application/pdf",
                    )
                },
            ),
            202,
        )
        print(role, "evaluate", flush=True)
        checked(browser.post(f"/api/evaluations/{ev['id']}/run", headers=HEADERS), 202)
        details = checked(browser.get(f"/api/evaluations/{ev['id']}"))
        assert details["evaluation"]["run_status"] == "DONE", details["evaluation"]
        for item in details["items"]:
            if item["ai_marks"] is None:
                raise RuntimeError("The model did not return marks")
            checked(
                browser.patch(
                    f"/api/evaluations/{ev['id']}/items/{item['id']}",
                    headers=HEADERS,
                    json={"approve": True, "reason": "Live smoke test review"},
                )
            )
        checked(browser.post(f"/api/evaluations/{ev['id']}/finalize", headers=HEADERS))
        report = browser.get(f"/api/evaluations/{ev['id']}/report.pdf")
        assert report.status_code == 200 and report.content.startswith(b"%PDF")
        output = ROOT / ".e2e-data" / "live-reports"
        output.mkdir(parents=True, exist_ok=True)
        (output / f"{role.lower()}.pdf").write_bytes(report.content)
        print(role, "PASS", flush=True)


if __name__ == "__main__":
    print(
        "Isolated live-model workflow; application data will not be modified.",
        flush=True,
    )
    for role in ("MANAGEMENT", "PARENT"):
        exercise(role)
