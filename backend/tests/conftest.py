"""Test harness. The stub below imitates the *Ollama HTTP server* so the real client code runs end-to-end.
It lives only in tests; the application itself has no mock mode."""
import json, os, re, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

_tmp = tempfile.mkdtemp(prefix="adem-test-")
os.environ["DATA_DIR"] = _tmp
os.environ["DB_MODE"] = "local"   # overrides .env so tests never touch Supabase
os.environ["SECRET_KEY"] = "test-secret-at-least-32-bytes-long-for-jwt-security"
os.environ["PDF_RENDER_DPI"] = "72"
os.environ["INTERNVL_MAX_RETRIES"] = "1"

import fitz  # noqa: E402  (pymupdf)
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

MODEL = "blaifa/InternVL3_5:4B"
BEHAVIOUR = {"garbage_pages": set(), "sheet": "main", "identities": []}   # tweakable per test


def _page(prompt: str) -> int:
    m = re.search(r"is page (\d+) of", prompt)
    return int(m.group(1)) if m else 1


def _reply(system: str, user: str) -> str:
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
        else:
            rows = [("Q1", "Osmosis is movement of water"), ("Q2", "WRONG diffusion answer"), ("3", "Photosynthesis makes food"),
                    ("3(b)", "OVERSHOOT leaf drawing"), (None, "stray text continued from earlier")]
        return json.dumps({"page_number": 1, "answers": [
            {"question_number": n, "answer_text": t, "ocr_confidence": 0.9} for n, t in rows]})
    return "{}"


class _H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        body = json.dumps({"models": [{"name": MODEL, "model": MODEL}]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert req["model"] == MODEL and req["stream"] is False and req.get("format") in ("json", None)
        msgs = req["messages"]
        if "images" in msgs[1]:
            assert len(msgs[1]["images"][0]) > 100          # real base64 image was sent
        out = _reply(msgs[0]["content"], msgs[1]["content"])
        body = json.dumps({"message": {"role": "assistant", "content": out}}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)


@pytest.fixture(scope="session", autouse=True)
def ollama_stub():
    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    from app.config import get_settings
    get_settings().internvl_api_url = f"http://127.0.0.1:{srv.server_port}"
    yield srv
    srv.shutdown()


@pytest.fixture(scope="session")
def client(ollama_stub):
    from app.main import app
    from app.database import SessionLocal
    from app.models import Teacher
    from app.security import hash_password
    with TestClient(app) as c:
        db = SessionLocal()
        if not db.query(Teacher).filter_by(email="rao@school.org").first():
            db.add(Teacher(name="Ms Rao", email="rao@school.org", password_hash=hash_password("password123")))
            db.commit()
        db.close()
        yield c


@pytest.fixture(scope="session")
def auth(client):
    r = client.post("/api/auth/login", json={"email": "rao@school.org", "password": "password123"})
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
