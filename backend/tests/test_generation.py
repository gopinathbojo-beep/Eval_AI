"""Question paper / answer key generation from the reference library (app/generation)."""
import json, re

import fitz
import pytest

from app.database import SessionLocal, init_db
from app.generation import retrieve
from app.generation.blueprint import board, custom
from app.generation.generate import generate
from app.generation.render import key_pdf, paper_pdf
from app.models import AnswerKey, ExamQuestion
from app.ocr import remote
from app.reference.ingest import ingest

ACIDS = ("CHAPTER 2\nACIDS, BASES AND SALTS\nAcids are sour in taste and change the colour of blue litmus to red. "
         "Bases are bitter and soapy to touch and turn red litmus blue. Indicators such as litmus tell us whether "
         "a substance is acidic or basic. When an acid reacts with a base, salt and water are formed; this reaction "
         "is called neutralisation. The pH scale measures the strength of acids and bases from 0 to 14. ") * 2
METALS = ("CHAPTER 3\nMETALS AND NON-METALS\nMetals are lustrous, malleable and ductile and are good conductors of "
          "heat and electricity. Non-metals are brittle and poor conductors. Reactive metals such as sodium are "
          "stored in kerosene because they react vigorously with oxygen and water. ") * 2


def _pdf(*pages: str) -> bytes:
    doc = fitz.open()
    for text in pages:
        doc.new_page().insert_textbox(fitz.Rect(50, 50, 550, 800), text, fontsize=10)
    return doc.tobytes()


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    root = tmp_path_factory.mktemp("cbse-gen")
    sci = root / "Text Books" / "Class 10" / "Science"
    sci.mkdir(parents=True)
    (sci / "jesc102.pdf").write_bytes(_pdf(ACIDS))
    (sci / "jesc103.pdf").write_bytes(_pdf(METALS))
    init_db()
    with SessionLocal() as db:
        ingest(db, root)
    return root


def fake_ai(calls: list):
    """Answers each requested question from the first passage in the prompt; cites one real and one invented id."""
    def call(system, user, image, structured, model=None):
        calls.append(user)
        ids = [int(i) for i in re.findall(r"^\[(\d+)\]", user, flags=re.M)]
        wanted = re.findall(r"- number (\d+): section (\w+), ([\d.]+) mark\(s\), type: .*?, with_choice: (true|false)", user)
        qs = []
        for n, _, marks, choice in wanted:
            item = {"number": int(n), "type": "Short answer", "text": f"Q{n}: Why are acids sour and what is neutralisation?",
                    "options": ["a", "b", "c", "d"] if marks == "1" else [],
                    "answer": "Acids are sour in taste; an acid reacts with a base to form salt and water (neutralisation).",
                    "marking_points": [{"point": "salt and water", "marks": float(marks)}],
                    "source_ids": [ids[0], 999999], "difficulty": "medium"}
            if choice == "true":
                item["or"] = {**item, "text": f"Q{n} OR: Why is sodium stored in kerosene?", "source_ids": []}
            qs.append(item)
        return json.dumps({"questions": qs}), None
    return call


def test_blueprints_add_up():
    b = board("cbse-10-041", "Mathematics", 10)
    assert b.total_marks == 80 and sum(s.marks for s in b.slots()) == 80 and len(b.slots()) == 38
    assert any(s.with_choice for s in b.slots())
    c = custom({"1": 5, "3": 2, "5": 1}, "Science", 10, 60)
    assert [s["key"] for s in c.sections] == ["A", "B", "C"] and c.total_marks == 16
    assert "1 hour" in c.instructions[1]
    assert board("cbse-12-106", "Tamil", 12) is None  # upload-driven: no fixed pattern


def test_generate_grounds_answers_and_drops_invented_citations(library, monkeypatch):
    calls = []
    monkeypatch.setattr(remote, "call", fake_ai(calls))
    with SessionLocal() as db:
        chapters = retrieve.chapters(db, 10, "10-science")
        assert {c["chapter"] for c in chapters} >= {"Chapter 2: Acids, Bases And Salts"}
        acids = next(c["id"] for c in chapters if "Acids" in c["chapter"])
        bp = custom({"1": 3, "3": 2}, "Science", 10, 60)
        paper = generate(db, bp, 10, "10-science", "Science", [acids])
    assert [q["number"] for q in paper["questions"]] == [1, 2, 3, 4, 5]
    assert [q["marks"] for q in paper["questions"]] == [1, 1, 1, 3, 3]
    q = paper["questions"][0]
    assert len(q["sources"]) == 1 and "Acids" in q["sources"][0]["chapter"]  # 999999 was never supplied: dropped
    assert q["grounding"] == "GROUNDED" and q["support"] >= 0.5
    alt = paper["questions"][-1]["or"]
    assert alt and alt["grounding"] == "UNSUPPORTED" and alt["notes"]
    assert paper["flagged"] >= 1
    # only the chosen chapter's passages were offered to the AI
    assert all("Metals" not in c and "METALS" not in c for c in calls)
    assert "Acids" in calls[0] or "ACIDS" in calls[0]
    for data in (paper_pdf(paper), key_pdf(paper)):
        text = "".join(p.get_text() for p in fitz.open(stream=data, filetype="pdf"))
        assert "SECTION A" in text and "Q1:" in text
    assert "Answer:" in "".join(p.get_text() for p in fitz.open(stream=key_pdf(paper), filetype="pdf"))


def test_generation_api(library, client, auth, monkeypatch):
    monkeypatch.setattr(remote, "call", fake_ai([]))
    subjects = client.get("/api/generation/subjects", headers=auth).json()
    sci = next(s for s in subjects["10"] if s["key"] == "10-science")
    assert sci["chapters"] >= 2 and sci["patterns"]
    r = client.post("/api/generation/papers", headers=auth, json={
        "grade": "10", "subject_key": "10-science", "pattern": "custom", "mix": {"1": 2, "2": 1}, "duration_minutes": 30})
    assert r.status_code == 202, r.text
    pid = r.json()["id"]
    gp = client.get(f"/api/generation/papers/{pid}", headers=auth).json()  # the background task ran after the response
    assert gp["status"] == "READY", gp
    assert gp["paper"]["total_marks"] == 4 and len(gp["paper"]["questions"]) == 3
    r = client.patch(f"/api/generation/papers/{pid}/questions/1", headers=auth, json={"answer": "(a) edited"})
    assert r.json()["paper"]["questions"][0]["answer"] == "(a) edited"
    pdf = client.get(f"/api/generation/papers/{pid}/answer-key.pdf", headers=auth)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert any(p["id"] == pid for p in client.get("/api/generation/papers", headers=auth).json())
    # a subject with no textbook loaded cannot be generated
    r = client.post("/api/generation/papers", headers=auth, json={"grade": "12", "subject_key": "12-psychology"})
    assert r.status_code == 409
    assert client.delete(f"/api/generation/papers/{pid}", headers=auth).json() == {"ok": True}


def _exam(client, auth, name):
    return client.post("/api/exams/simple", headers=auth, json={"name": name, "grade": "10", "subject_key": "10-science"}).json()


def test_generated_custom_paper_goes_straight_into_the_exam(library, client, auth, monkeypatch):
    calls = []
    monkeypatch.setattr(remote, "call", fake_ai(calls))
    exam = _exam(client, auth, "Gen custom")
    r = client.post(f"/api/exams/{exam['id']}/generate-paper", headers=auth,
                    json={"pattern": "custom", "mix": {"1": 2, "3": 3}, "duration_minutes": 45})
    assert r.status_code == 202, r.text
    info = client.get(f"/api/exams/{exam['id']}/generated-paper", headers=auth).json()
    assert info["subject"] == {"grade": "10", "key": "10-science"} and info["paper"]["status"] == "READY"
    assert len(calls) == 2  # one AI call per section; the PDFs are never read back
    detail = client.get(f"/api/exams/{exam['id']}", headers=auth).json()
    assert detail["status"] == "READY_FOR_EVALUATION" and detail["total_marks"] == 11
    assert detail["generation"]["status"] == "READY" and detail["generation"]["question_count"] == 5
    assert detail["question_paper"]["status"] == "READY" and detail["answer_key_document"]["status"] == "READY"
    with SessionLocal() as db:
        qs = db.query(ExamQuestion).filter_by(exam_id=exam["id"]).order_by(ExamQuestion.position).all()
        keys = db.query(AnswerKey).filter_by(exam_id=exam["id"], is_active=True).all()
        # Q5 has an OR alternative: two questions in one choice group, the school-exam convention
        assert [q.display_number for q in qs] == ["1", "2", "3", "4", "5(a)", "5(b)"]
        assert [q.choice_group for q in qs][-2:] == ["5", "5"]
        assert all(q.verification_status == "VERIFIED" and not q.review_reason for q in qs)
        assert len(keys) == len(qs) and all(k.mapping_status == "MAPPED" and k.verification_status == "VERIFIED"
                                             and k.rubric_status == "CONFIRMED" and not (k.rubric or {}).get("problems")
                                             for k in keys)
        assert all(abs(sum(p["marks"] for p in k.rubric["points"]) - k.marks) < 1e-9 for k in keys)


def test_generated_board_paper_passes_cbse_validation(library, client, auth, monkeypatch):
    monkeypatch.setattr(remote, "call", fake_ai([]))
    exam = _exam(client, auth, "Gen board")
    r = client.post(f"/api/exams/{exam['id']}/generate-paper", headers=auth, json={"pattern": "board"})
    assert r.status_code == 202, r.text
    detail = client.get(f"/api/exams/{exam['id']}", headers=auth).json()
    assert detail["status"] == "READY_FOR_EVALUATION" and detail["standard_profile_id"] == "cbse-10-086"
    assert detail["question_count"] == 39 and detail["verified_question_count"] == 39
    v = client.get(f"/api/exams/{exam['id']}/standard-validation?phase=paper", headers=auth).json()
    assert v["valid"], [(i["code"], i.get("question"), i["message"], i.get("expected"), i.get("detected")) for i in v["issues"]]
    v = client.get(f"/api/exams/{exam['id']}/standard-validation?phase=evaluation", headers=auth).json()
    assert v["valid"], [(i["code"], i.get("question"), i["message"]) for i in v["issues"]]


def test_generated_paper_replaces_a_paper_read_by_ocr(library, client, auth, monkeypatch):
    """An exam already past question verification (OCR route) can take the generated paper until sheets arrive."""
    monkeypatch.setattr(remote, "call", fake_ai([]))
    exam = _exam(client, auth, "Gen replace")
    with SessionLocal() as db:
        from app.models import Exam
        db.get(Exam, exam["id"]).status = "ANSWER_KEY_UPLOADED"
        db.commit()
    pid = client.post("/api/generation/papers", headers=auth, json={
        "grade": "10", "subject_key": "10-science", "pattern": "custom", "mix": {"2": 2}}).json()["id"]
    r = client.post(f"/api/generation/papers/{pid}/use/{exam['id']}", headers=auth)
    assert r.status_code == 202, r.text
    detail = client.get(f"/api/exams/{exam['id']}", headers=auth).json()
    assert detail["status"] == "READY_FOR_EVALUATION" and detail["verified_question_count"] == detail["question_count"] == 3
