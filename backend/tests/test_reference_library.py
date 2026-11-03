"""Reference library: NCERT names, text cleanup, passage splitting, loading and class/subject-scoped search."""
import io, zipfile
from types import SimpleNamespace

import fitz
import pytest

from app.database import SessionLocal, init_db
from app.models import ReferenceChunk, ReferenceSource
from app.reference import ncert
from app.reference.ingest import clean_text, ingest, split_passages, subject_key
from app.reference.search import search, subject_of


def _pdf(*pages: str) -> bytes:
    doc = fitz.open()
    for text in pages:
        doc.new_page().insert_textbox(fitz.Rect(50, 50, 550, 800), text, fontsize=10)
    return doc.tobytes()


ACIDS = ("CHAPTER 2\nACIDS, BASES AND SALTS\nAcids are sour in taste and change the colour of blue litmus to red. "
         "Bases are bitter and soapy to touch and turn red litmus blue. Indicators such as litmus tell us whether "
         "a substance is acidic or basic.")
RANCID = ("When fats and oils are oxidised, they become rancid and their smell and taste change. Antioxidants are "
          "added to foods containing fats and oil to prevent rancidity. Keeping food in air tight containers helps.")
HCF = "CHAPTER 1\nREAL NUMBERS\nThe HCF of two positive integers is found by prime factorisation of each integer."


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    root = tmp_path_factory.mktemp("cbse")
    sci = root / "Text Books" / "Class 10" / "Science"
    sci.mkdir(parents=True)
    (sci / "jesc102.pdf").write_bytes(_pdf(ACIDS))
    (sci / "jesc101.pdf").write_bytes(_pdf("CHAPTER 1\nCHEMICAL REACTIONS AND EQUATIONS\n" + RANCID))
    (sci / "jesc1ps.pdf").write_bytes(_pdf("Foreword"))
    maths = root / "Text Books" / "Class 10" / "Mathematics"
    maths.mkdir(parents=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("jemh101.pdf", _pdf(HCF))
        z.writestr("jemh1an.pdf", _pdf("ANSWERS 1. HCF (96, 404) = 4 and LCM = 9696, found by prime factorisation."))
    (maths / "jemh1dd.zip").write_bytes(buf.getvalue())
    hindi = root / "Text Books" / "Class 10" / "Hindi Course A" / "Main Textbook"
    hindi.mkdir(parents=True)
    (hindi / "jhks101.pdf").write_bytes(_pdf("lu~ 1857 osQ ckxh lSfudksa dk dkSeh xhr ge gSa blosQ ekfyd gekjk " * 5))
    ms = root / "Sample Question paper" / "Class 10"
    ms.mkdir(parents=True)
    (ms / "Science-MS.pdf").write_bytes(_pdf(
        "SCIENCE MARKING SCHEME\n1 B. Displacement reaction 1\n2 C. R 1\n3 A. Glucose and salts 1\n"
        "4 D. A is false but R is true 1\n5 To prevent rancidity, the oxidation of fats and oils. 2"))
    (ms / "Science-SQP.pdf").write_bytes(_pdf(
        "SCIENCE SAMPLE PAPER\n1 Which type of reaction is iron and copper sulphate? 1\n2 Choose R. 1\n"
        "3 What is reabsorbed in the nephron? 1\n4 Assertion and reason. 1\n"
        "5 Why are antioxidants added to foods containing fats and oils? 2"))
    init_db()
    with SessionLocal() as db:
        report = ingest(db, root)
    return root, report


def test_ncert_names():
    assert ncert.parse("jemh101.pdf") == ncert.NcertName(10, "mh", 1, "chapter", 1)
    assert ncert.parse("leph1an.pdf") == ncert.NcertName(12, "ph", 1, "answers")
    assert ncert.parse("jhks112.pdf").chapter == 12
    assert ncert.parse("jemh1a2.pdf").kind == "appendix"
    assert ncert.parse("jesc1ps.pdf").kind == "front"
    assert ncert.parse("X-SQP.pdf") is None


def test_subject_keys_match_textbook_subjects():
    assert subject_key(10, "Hindi Course B") == "10-hindi"
    assert subject_key(12, "Business Studies") == subject_key(12, "BusinessStudies") == "12-business-studies"
    assert subject_key(10, "MathsStandard") == "10-mathematics"
    assert subject_key(12, "PolSci") == "12-political-science"


def test_symbol_font_characters_are_restored():
    assert clean_text("p/q (q  0), 3  2  5,   , �") == "p/q (q ≠ 0), 3 + 2 = 5, α × β,"
    assert clean_text("x =    y") == "x = y"


def test_passages_overlap_and_keep_pages():
    lines = "\n".join(f"line {i} " + "x" * 90 for i in range(30))
    parts = split_passages([(1, lines), (2, "last line on page two")], size=1000, overlap=150)
    assert len(parts) >= 3 and parts[0][0] == 1 and parts[-1][1] == 2
    assert all(len(t) < 1300 for *_, t in parts)
    assert parts[1][2].splitlines()[0] in parts[0][2]  # overlap carries the tail of the previous passage
    assert "last line on page two" in parts[-1][2]


def test_loading_reports_and_skips(library):
    _, report = library
    assert not report.failed
    reasons = dict(report.skipped)
    assert any(p.endswith("jesc1ps.pdf") for p in reasons)
    assert "legacy Hindi font" in next(why for p, why in report.skipped if p.endswith("jhks101.pdf"))
    assert any(p.endswith("jemh1dd.zip::jemh101.pdf") for p in report.loaded)
    with SessionLocal() as db:
        kinds = {s.path.rsplit("/", 1)[-1]: (s.kind, s.subject) for s in db.query(ReferenceSource)}
        assert kinds["jemh1dd.zip::jemh1an.pdf"] == ("TEXTBOOK_ANSWERS", "10-mathematics")
        assert kinds["Science-MS.pdf"] == ("MARKING_SCHEME", "10-science")
        title = db.query(ReferenceSource).filter(ReferenceSource.path.like("%jesc102.pdf")).one().title
        assert "Chapter 2: Acids, Bases And Salts" in title


def test_unchanged_files_are_not_reread(library):
    root, _ = library
    with SessionLocal() as db:
        before = db.query(ReferenceChunk).count()
        again = ingest(db, root)
        assert again.loaded == [] and again.unchanged >= 5
        assert db.query(ReferenceChunk).count() == before


def test_search_is_scoped_and_thresholded(library):
    with SessionLocal() as db:
        hits = search(db, "Why are antioxidants added to food containing fats?", 10, "10-science")
        assert hits and "antioxidant" in hits[0].text.lower()
        assert {h.kind for h in hits} <= {"TEXTBOOK", "MARKING_SCHEME"}
        only_ms = search(db, "antioxidants rancidity", 10, "10-science", kinds=["MARKING_SCHEME"])
        assert [h.kind for h in only_ms] == ["MARKING_SCHEME"]
        assert search(db, "antioxidants rancidity", 10, "10-mathematics") == []   # other subject
        assert search(db, "antioxidants rancidity", 12, "10-science") == []        # other class
        assert search(db, "photosynthesis chlorophyll stomata", 10, "10-science") == []  # weak match
        hcf = search(db, "Find the HCF by prime factorisation", 10, "10-mathematics")
        assert hcf and hcf[0].page_start == 1 and "HCF" in hcf[0].text


def test_subject_of_exam_profile():
    assert subject_of(SimpleNamespace(standard_profile_id="cbse-10-086")) == (10, "10-science")
    assert subject_of(SimpleNamespace(standard_profile_id=None)) is None


# --- marking schemes paired with their question papers, and answer verification ---

from app.reference.ingest import split_marking_scheme  # noqa: E402
from app.reference import verify as verify_mod  # noqa: E402
from app.reference.verify import verify_answer  # noqa: E402


def test_marking_scheme_rows_split_per_question():
    page = ("SCIENCE MARKING SCHEME\nSection - A\n1 A. Carbon dioxide gains hydrogen. 1\n2 C. R 1\n"
            "For visually impaired students\n3 Bile makes the food alkaline 2\n1. first point of the answer\n"
            "2. second point\n7B OR choice stays with question 3\n^4.(C) a garbled row 1\n6 jump with marks 3\n")
    rows = split_marking_scheme([(1, page)])
    assert [(q, m) for _, _, q, m, _ in rows] == [("1", 1.0), ("2", 1.0), ("3", 2.0), ("4", 1.0), ("6", 3.0)]
    q3 = rows[2][4]
    assert "second point" in q3 and "OR choice" in q3   # numbered points and the OR choice stay with Q3


def test_board_answers_carry_their_question(library):
    with SessionLocal() as db:
        ms = db.query(ReferenceChunk).filter_by(kind="MARKING_SCHEME").all()
        assert ms and all(c.question_number for c in ms)
        q5 = next(c for c in ms if c.question_number == "5")
        assert q5.text.startswith("QUESTION 5: 5 Why are antioxidants") and "MARKING SCHEME: 5 To prevent rancidity" in q5.text
        assert q5.marks == 2.0


def test_verify_answer_statuses(library):
    with SessionLocal() as db:
        q = "Why are antioxidants added to foods containing fats and oils?"
        good = verify_answer(db, 10, "10-science", q, "Antioxidants are added to prevent rancidity, the oxidation "
                             "of fats and oils that changes their smell and taste.")
        assert good.status == "ON_TOPIC" and good.sources and good.support >= 0.6
        assert good.board_match and good.board_match["question_number"] == "5"
        wrong = verify_answer(db, 10, "10-science", q, "Antioxidants make bread rise faster in hot ovens during baking.")
        assert wrong.status in {"UNSUPPORTED", "PARTIAL"} and wrong.support < good.support
        numbers = verify_answer(db, 10, "10-science", q, "Antioxidants prevent rancidity of fats and oils in 1857 "
                                "at 42 degrees.")
        assert numbers.status == "PARTIAL" and any("1857" in n for n in numbers.notes)
        uncited = verify_answer(db, 10, "10-science", q, good_text := "Antioxidants prevent rancidity of fats and oils.",
                                cited=[])
        assert uncited.status == "PARTIAL" and "cites no source" in " ".join(uncited.notes)
        made_up = verify_answer(db, 10, "10-science", q, good_text, cited=["S9"])
        assert any("not given" in n for n in made_up.notes)
        assert verify_answer(db, 10, "10-science", q, "(B)").status == "NOT_CHECKED"
        assert verify_answer(db, 10, "10-science", "Explain photosynthesis in leaves", "Chlorophyll absorbs "
                             "sunlight").status == "NO_REFERENCE"


def test_generated_key_comes_from_the_library_only(client, auth, library, monkeypatch):
    c, h = client, auth
    cls = c.post("/api/classes", json={"name": "10"}, headers=h).json()
    sub = c.post("/api/subjects", json={"name": "Science"}, headers=h).json()
    eid = c.post("/api/_test/legacy-exams", headers=h, json={
        "name": "Science Unit Test", "academic_year": "2026-27", "class_id": cls["id"], "subject_id": sub["id"],
        "exam_type": "Unit Test", "total_marks": 7.0}).json()["id"]
    from .conftest import make_pdf
    c.post(f"/api/exams/{eid}/question-paper", headers=h, files={"file": ("sci.pdf", make_pdf(2), "application/pdf")})
    c.post(f"/api/exams/{eid}/questions/accept-valid", headers=h)
    assert c.post(f"/api/exams/{eid}/questions/verify", headers=h).status_code == 200
    import app.ocr.internvl as ai

    def no_model(*a, **k):
        raise AssertionError("answer keys must not come from the model")
    monkeypatch.setattr(ai, "chat_structured", no_model)
    gen = c.post(f"/api/exams/{eid}/answer-keys/generate-ai", headers=h).json()
    assert gen["reference_subject"] == "10-science" and gen["source"] == "REFERENCE_LIBRARY"
    assert all(a["origin"] in {"BOARD_MARKING_SCHEME", "NONE"} and a["note"] for a in gen["answers"])
    assert all(a["answer_text"] == "" for a in gen["answers"] if a["origin"] == "NONE")
    checked = c.post(f"/api/exams/{eid}/answer-keys/check-references", headers=h)
    assert checked.status_code == 200 and checked.json()["reference_subject"] == "10-science"


# --- no AI in verification: the book text is shown as printed ---

Q_ANTI = "Why are antioxidants added to foods containing fats and oils?"


def test_verification_shows_book_text_and_never_calls_the_model(library, monkeypatch):
    import app.ocr.internvl as ai

    def no_model(*a, **k):
        raise AssertionError("verification must not call the model")
    monkeypatch.setattr(ai, "chat_structured", no_model)
    with SessionLocal() as db:
        [v] = verify_mod.verify_answers(db, 10, "10-science", [{"question": Q_ANTI, "answer": "Antioxidants prevent rancidity."}])
        stored = {c.text for c in db.query(ReferenceChunk)}
    assert v.sources and all(s["text"] in stored for s in v.sources)   # exactly the passage as loaded
    assert any("Antioxidants are added to" in s["text"] for s in v.sources)


def test_board_question_gets_the_marking_scheme_answer_as_printed(library):
    from app.reference.verify import board_answer, find_references
    with SessionLocal() as db:
        refs = find_references(db, 10, "10-science", Q_ANTI)
        b = board_answer(refs, Q_ANTI)
        assert b and b["question_number"] == "5" and b["marks"] == 2.0
        assert b["answer"] == "To prevent rancidity, the oxidation of fats and oils. 2"   # the row exactly as printed
        other = "Why does food kept in air tight containers stay fresh longer than food in open plates?"
        assert board_answer(find_references(db, 10, "10-science", other), other) is None  # same topic, other question
