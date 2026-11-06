"""Test harness. The stub below imitates OpenRouter so the real client code runs end-to-end.
It lives only in tests; the application itself has no mock mode."""
import json, os, re, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

_tmp = tempfile.mkdtemp(prefix="adem-test-")
os.environ["DATA_DIR"] = _tmp
os.environ["DATABASE_URL"] = ""
os.environ["OPENROUTER_API_KEY"] = "test-openrouter-key"
os.environ["OPENROUTER_MODEL"] = "deepseek/deepseek-v4.1-flash-1017"
os.environ["AI_MEDIUM_MODEL"] = ""  # tests use the single OPENROUTER_MODEL
os.environ["AI_SMALL_MODEL"] = ""
os.environ["AUTOPILOT"] = "false"  # existing tests drive the manual steps; autopilot tests switch it on
os.environ["AI_PARALLEL_JOBS"] = "1"
os.environ["AI_JOIN_ANSWERS"] = "false"  # existing tests drive the rule segmenter; the joiner's tests switch it on
os.environ["STORAGE_PROVIDER"] = "local"
os.environ["DURABLE_JOBS"] = "false"
os.environ["AUTO_MIGRATE"] = "false"
os.environ["SECRET_KEY"] = "test-secret-at-least-32-bytes-long-for-jwt-security"
os.environ["PDF_RENDER_DPI"] = "72"
os.environ["AI_MAX_RETRIES"] = "1"
os.environ["JOB_QUEUE_INLINE"] = "true"  # queued GPU jobs finish before the request returns
os.environ["GOOGLE_CLIENT_ID"] = ""  # tests must not read real OAuth credentials
os.environ["GOOGLE_CLIENT_SECRET"] = ""

import fitz  # noqa: E402  (pymupdf)
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

MODEL = "deepseek/deepseek-v4.1-flash-1017"
BEHAVIOUR = {"garbage_pages": set(), "sheet": "main", "identities": []}   # tweakable per test


def _page(prompt: str) -> int:
    m = re.search(r"is page (\d+) of", prompt)
    return int(m.group(1)) if m else 1


def _reply(system: str, user: str) -> str:
    if "ANSWERS TO MATCH" in user:  # autopilot: settle the answers a sheet's mapping left open
        rows = []
        for line in user.split("ANSWERS TO MATCH", 1)[1].splitlines():
            m = re.match(r"id=(\S+) .*written number=(\S+): (.*)", line)
            if m:
                written = m[2].lstrip("Qq")
                rows.append({"id": m[1], "question": None if written == "-" else ("3(a)" if written == "3" else written)})
        return json.dumps({"rows": rows})
    if system.startswith("You read the student details box"):   # answer-sheet header; one queued reply per call
        return json.dumps(BEHAVIOUR["identities"].pop(0) if BEHAVIOUR["identities"] else {})
    if "Generating reference answer key" in user or "generate suggested answers" in user:
        q_matches = re.findall(r"QUESTION ([\w\(\)\.\-]+) \(ID: ([^,\)]+), max marks: ([\d\.]+)\)", user)
        answers = []
        for q_num, q_id, q_marks in q_matches:
            answers.append({
                "exam_question_id": q_id,
                "question_number": q_num,
                "answer_text": f"Model answer for {q_num}.",
                "marks": float(q_marks),
                "criteria": [f"1 mark for core explanation of {q_num}", f"1 mark for detail of {q_num}"],
                "keywords": [f"keyword_{q_num}", "concept"],
                "accepted_answers": [f"Alternative answer for {q_num}."]
            })
        return json.dumps({"answers": answers})
    if "QUESTION " in user and "OFFICIAL ANSWER KEY" in user:        # evaluation
        mx = float(re.search(r"maximum marks: ([\d.]+)", user).group(1))
        ans = user.split("STUDENT ANSWER (verbatim transcription)")[1]
        if "OVERSHOOT" in ans:
            return json.dumps({"marks_awarded": mx + 3, "max_marks": mx, "decision": "CORRECT", "feedback": "x"})
        if "UNSURE" in ans:
            return json.dumps({"marks_awarded": 1, "max_marks": mx, "decision": "PARTIAL", "feedback": "Hard to tell",
                               "matched_points": [], "missing_points": [], "confidence": 0.3})
        if "WRONG" in ans:
            return json.dumps({"marks_awarded": 0, "max_marks": mx, "decision": "INCORRECT", "feedback": "No match",
                               "matched_points": [], "missing_points": ["all"], "confidence": 0.8})
        return json.dumps({"marks_awarded": mx, "max_marks": mx, "decision": "CORRECT", "feedback": "Good",
                           "matched_points": ["p"], "missing_points": [], "confidence": 0.9})
    p = _page(user)
    if "printed question paper" in user:
        if p in BEHAVIOUR["garbage_pages"]:
            return "Sorry, I cannot read this page."
        data = {1: [("Q1", "Define osmosis.", 2), ("2.", "Explain diffusion.", 5)],
                2: [("3 (a)", "Describe photosynthesis.", 3), ("3-b", "Draw a labelled leaf.", 5)]}[p]
        return json.dumps({"page_number": p, "questions": [
            {"raw_question_number": n, "question_text": t, "marks": m, "confidence": 0.95,
             "bbox": {"x": 10, "y": 10 + 40 * i, "width": 100, "height": 30}} for i, (n, t, m) in enumerate(data)]})
    if "answer key" in user:
        rows = [("Q1", "Movement of water across a membrane", 2), ("2", "Movement from high to low concentration", 4),
                ("3 (a)", "Plants make glucose using light", 3), ("3b", "Labelled diagram of leaf", 5)]
        return "```json\n" + json.dumps({"page_number": 1, "answers": [
            {"question_number": n, "answer_text": t, "marks": m, "criteria": ["c1"], "confidence": 0.9} for n, t, m in rows]}) + "\n```"
    if "answer sheet" in user:
        if BEHAVIOUR["sheet"] == "dup":
            rows = [("1", "Osmosis is water movement"), ("Q1", "Another try at one"), ("2", "Diffusion text"),
                    ("3(a)", "Photosynthesis"), ("3(b)", "Leaf diagram")]
        elif BEHAVIOUR["sheet"] in ("clean", "unsure"):
            rows = [("Q1", "Osmosis is movement of water"), ("2", "Diffusion text"), ("3(a)", "Photosynthesis"),
                    ("3(b)", "UNSURE leaf sketch" if BEHAVIOUR["sheet"] == "unsure" else "Leaf diagram")]
        else:
            rows = [("Q1", "Osmosis is movement of water"), ("Q2", "WRONG diffusion answer"), ("3", "Photosynthesis makes food"),
                    ("3(b)", "OVERSHOOT leaf drawing"), (None, "stray text continued from earlier")]
        return json.dumps({"page_number": 1, "answers": [
            {"question_number": n, "answer_text": t, "ocr_confidence": 0.9} for n, t in rows]})
    return "{}"


class _H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        if self.path == "/api/tags":  # InternVL (Ollama)
            body = json.dumps({"models": [{"name": MODEL, "model": MODEL}]}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)
            return
        body = json.dumps({"data": [{"id": MODEL, "architecture": {"input_modalities": ["text", "image"]}}]}).encode()
        if self.path.endswith("/key"):
            body = json.dumps({"data": {"label": "test"}}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert req["model"] == MODEL and req["stream"] is False
        msgs = req["messages"]
        user = msgs[1]["content"]
        if self.path == "/api/chat":  # InternVL (Ollama)
            assert all(isinstance(i, str) for i in msgs[1].get("images", []))
            out = _reply(msgs[0]["content"], user)
            body = json.dumps({"message": {"role": "assistant", "content": out}, "done": True, "done_reason": "stop",
                               "logprobs": [{"token": out, "bytes": list(out.encode("utf-8")), "logprob": 0.0}]}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)
            return
        if isinstance(user, list):
            assert user[1]["image_url"]["url"].startswith("data:image/")
            user = user[0]["text"]
        out = _reply(msgs[0]["content"], user)
        body = json.dumps({"choices": [{"message": {"role": "assistant", "content": out}, "finish_reason": "stop",
                                        "logprobs": {"content": [{"bytes": list(out.encode("utf-8")), "logprob": 0.0}]}}]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)


@pytest.fixture(scope="session", autouse=True)
def openrouter_stub():
    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    from app.ocr import remote
    from app.config import get_settings
    get_settings().openrouter_base_url = f"http://127.0.0.1:{srv.server_port}"
    yield srv
    srv.shutdown()


@pytest.fixture(scope="session")
def client(openrouter_stub):
    from app.main import app
    from app.database import SessionLocal
    from app.models import Teacher, Workspace
    from datetime import datetime, timezone
    from app.security import hash_password
    with TestClient(app) as c:
        db = SessionLocal()
        if not db.query(Teacher).filter_by(email="rao@school.org").first():
            teacher = Teacher(name="Ms Rao", email="rao@school.org", role="MANAGEMENT", profile_completed_at=datetime.now(timezone.utc), password_hash=hash_password("Password@123"))
            db.add(teacher)
            db.flush()
            ws = Workspace(name="Test school", kind="SCHOOL", owner_id=teacher.id)
            db.add(ws)
            db.flush()
            teacher.workspace_id = ws.id
            db.commit()
        db.close()
        yield c


@pytest.fixture(scope="session", autouse=True)
def legacy_exam_seed_route(openrouter_stub):
    """Seed pre-standard records for regression tests through a TEST-ONLY authenticated route.

    Production /api/exams always enforces CBSE. Legacy workflow tests deliberately create
    historical records without weakening or monkeypatching the production creation gate.
    """
    from fastapi import Depends
    from app.main import app
    from app.database import get_db
    from app.routes.core import ExamIn, exam_view
    from app.models import Exam, SchoolClass, Subject
    from app.security import current_teacher
    from app.workspaces import owner_id, assigned
    from app.deps import err
    from app.services.audit import audit
    from datetime import datetime

    @app.post("/api/_test/legacy-exams",status_code=201)
    def seed(body: ExamIn, db=Depends(get_db), user=Depends(current_teacher)):
        c,s=db.get(SchoolClass,body.class_id),db.get(Subject,body.subject_id)
        if not c or not s or c.teacher_id!=owner_id(db,user) or s.teacher_id!=owner_id(db,user) or not assigned(db,user,c.id,s.id):
            raise err(404,"NOT_FOUND","Class or subject not found in your assignments.")
        data=body.model_dump(exclude={"standard_profile_id","standard_options"})
        if not data.get("academic_year"):
            data["academic_year"]=f"{datetime.now().year}-{str(datetime.now().year+1)[-2:]}"
        row=Exam(teacher_id=user.id,workspace_id=user.workspace_id,status="DRAFT",**data)
        db.add(row);db.flush()
        audit(db,exam_id=row.id,teacher_id=user.id,entity_type="exam",entity_id=row.id,action="exam_created")
        db.commit()
        return exam_view(row)


@pytest.fixture(scope="session")
def auth(client):
    r = client.post("/api/auth/login", json={"email": "rao@school.org", "password": "Password@123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def make_pdf(pages: int = 1) -> bytes:
    d = fitz.open()
    for i in range(pages):
        pg = d.new_page(); pg.insert_text((72, 100), f"Test page {i + 1}")
    return d.tobytes()


def make_png() -> bytes:
    from io import BytesIO
    from PIL import Image
    b = BytesIO(); Image.new("RGB", (400, 300), "white").save(b, "PNG"); return b.getvalue()
