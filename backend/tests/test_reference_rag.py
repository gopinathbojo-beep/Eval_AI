"""Reference RAG: local embeddings, hybrid retrieval, textbook passages in the grading prompt, choice shapes."""
from types import SimpleNamespace

import fitz
import numpy as np
import pytest

from app.cbse import grading
from app.cbse.build import shape_choices
from app.database import SessionLocal, init_db
from app.models import ReferenceChunk
from app.reference import embed
from app.reference.ingest import ingest
from app.reference.search import Hit, retrieve

RANCID = ("When fats and oils are oxidised, they become rancid and their smell and taste change. Antioxidants are "
          "added to foods containing fats and oil to prevent rancidity.")
ACIDS = "Acids are sour in taste and change the colour of blue litmus to red. Bases turn red litmus blue."

# a stand-in for the local model: one axis per topic, so "spoilt butter" sits next to "rancid"
_TOPICS = [("rancid", "spoil", "fat", "oil", "butter", "smell"), ("acid", "litmus", "sour", "base")]


def _fake_embed(texts):
    rows = []
    for text in texts:
        low = text.lower()
        rows.append([sum(w in low for w in words) for words in _TOPICS] + [0.01])
    v = np.asarray(rows, dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def _pdf(text):
    doc = fitz.open()
    doc.new_page().insert_textbox(fitz.Rect(50, 50, 550, 800), text, fontsize=10)
    return doc.tobytes()


@pytest.fixture(scope="module")
def rag_library(tmp_path_factory):
    root = tmp_path_factory.mktemp("rag")
    sci = root / "Text Books" / "Class 9" / "Science"
    sci.mkdir(parents=True)
    (sci / "iesc101.pdf").write_bytes(_pdf("CHAPTER 1\nFOOD\n" + RANCID))
    (sci / "iesc102.pdf").write_bytes(_pdf("CHAPTER 2\nACIDS\n" + ACIDS))
    init_db()
    with SessionLocal() as db:
        ingest(db, root)
    return root


def _scope(db):
    chunk = db.query(ReferenceChunk).filter(ReferenceChunk.text.contains("rancid")).first()
    return chunk.standard, chunk.subject


def test_keyword_only_without_a_model(rag_library, monkeypatch):
    monkeypatch.setattr(embed, "available", lambda: False)
    with SessionLocal() as db:
        hits = retrieve(db, "why do fats and oils become rancid", *_scope(db), k=2)
    assert hits and "rancid" in hits[0].text and hits[0].similarity is None


def test_meaning_finds_what_keywords_miss(rag_library, monkeypatch):
    monkeypatch.setattr(embed, "available", lambda: True)
    monkeypatch.setattr(embed, "model_name", lambda: "fake-topic-model")
    monkeypatch.setattr(embed, "embed", _fake_embed)
    with SessionLocal() as db:
        assert embed.embed_missing(db) > 0
        assert embed.embed_missing(db) == 0  # nothing left to embed
        scope = _scope(db)
        assert retrieve(db, "spoilt butter", *scope, k=2, kinds=["TEXTBOOK"])[0].text.count("rancid")
        hits = retrieve(db, "spoilt butter", *scope, k=2)
    assert "rancid" in hits[0].text and hits[0].similarity > 0.9
    assert all("litmus" not in h.text for h in hits)  # an unrelated passage is never returned


def test_grading_prompt_quotes_textbook_as_reference_only():
    hit = Hit(1, 1.0, RANCID, "TEXTBOOK", "Food", 3, 3, "Science Class 9 - Food", "x.pdf")
    q = SimpleNamespace(display_number="5", max_marks=2.0, question_text="Why are antioxidants added?",
                        structure={})
    key = SimpleNamespace(answer_text="To prevent rancidity.", rubric={}, accepted_answers=[],
                          criteria=[], marks=2.0)
    text = grading.prompt(q, key, "so food does not go bad", {"accessibility": "standard"}, [], [hit])
    assert "NCERT TEXTBOOK REFERENCE" in text and RANCID in text and "p.3-3" in text
    assert "never replaces the marking scheme" in text and "background" in text
    assert "NCERT TEXTBOOK REFERENCE" not in grading.prompt(q, key, "x", {"accessibility": "standard"}, [])


def _point(id, marks, audience=None, text=""):
    return {"id": id, "kind": "point", "marks": marks, "audience": audience, "text": text, "children": []}


def test_visually_impaired_part_becomes_an_alternative():
    tree = {"id": "q24", "kind": "all", "marks": 2, "text": "", "children": [
        _point("q24.s", 2), {"id": "q24.vi", "kind": "point", "marks": 2, "audience": "accessible",
                             "text": "", "children": [_point("q24.vi.1", 1), _point("q24.vi.2", 1)]}]}
    shaped = shape_choices(tree)
    assert shaped["kind"] == "choose" and shaped["limit"] == 1
    assert [c["audience"] for c in shaped["children"]] == ["standard", "accessible"]


def test_nested_one_of_choices_are_flattened():
    tree = {"id": "q27", "kind": "choose", "limit": 1, "marks": 3, "children": [
        {"id": "q27.A", "kind": "all", "marks": 3, "text": "", "children": [
            _point("q27.A.1", 3), {"id": "q27.A.vi", "kind": "all", "marks": 3, "audience": "accessible",
                                   "text": "", "children": [_point("q27.A.vi.1", 3)]}]},
        _point("q27.B", 3)]}
    shaped = shape_choices(tree)
    assert [c["id"] for c in shaped["children"]] == ["q27.A.1", "q27.A.vi", "q27.B"]


@pytest.mark.parametrize("subject, kind", [("English", "LANGUAGE"), ("Tamil", "LANGUAGE"), ("Hindi Course A", "LANGUAGE"),
                                           ("Science", "UNDERSTANDING"), ("Social Science", "UNDERSTANDING"),
                                           ("Physics", "UNDERSTANDING"), ("Maths", None)])
def test_understanding_rules_per_subject(subject, kind):
    from app import formatter
    rules = formatter.get(formatter.for_subject(subject)).grading_rules("Explain why.", "Because ...")
    assert (kind in rules) if kind else rules == ""


def test_hindi_reads_papers_exactly_like_common():
    """Hindi got a formatter only for grading: every reading hook is the shared one."""
    from app.formatter import common, hindi
    for hook in ("parse_paper", "segment_keys", "segment_answers", "grading_attempts", "check_deductions",
                 "uses_pdf_text", "build_rubric"):
        assert getattr(hindi, hook) is getattr(common, hook)


def test_one_mark_answer_with_explanation_stays_on_its_question():
    from app.services.mapping_service import _chooses_option
    q = SimpleNamespace(question_text="Which complex is tetrahedral? A. [Ni(CN)4]2- B. [Cu(NH3)4]2+ C. [NiCl4]2- D. [Ni(CO)4]")
    assert _chooses_option(q, "C. [NiCl4]2- is tetrahedral because Cl- is a weak field ligand ...")
    assert _chooses_option(q, "The answer is [NiCl4]2- since chloride is a weak field ligand")
    assert not _chooses_option(q, "2. Chromium has more unpaired electrons than titanium ...")


def test_half_mark_steps_and_unnumbered_continuation():
    from app.cbse.grading import _to_scheme_step
    from app.services.mapping_service import _continues
    assert [_to_scheme_step(v, 1) for v in (0.8, 0.3, 0.2, 1)] == [1, 0.5, 0, 1]
    before = SimpleNamespace(question_type="", max_marks=2)
    prev = SimpleNamespace(page_number=10, answer_text="17(A) 1. 2MnO4- + ...")
    assert _continues(prev, SimpleNamespace(page_number=10, answer_text="2. Chromium has more unpaired"), before)
    assert not _continues(prev, SimpleNamespace(page_number=9, answer_text="2. Chromium"), before)
    assert not _continues(prev, SimpleNamespace(page_number=10, answer_text="B. 32 min"), before)


def test_explanation_stays_with_the_numbered_answer_above_it():
    from app.services.mapping_service import _repair_misread_labels
    q6 = SimpleNamespace(id="6", normalized_number="6", question_type="mcq", max_marks=1, question_text="Order?")
    q11 = SimpleNamespace(id="11", normalized_number="11", question_type="mcq", max_marks=1, question_text="Half-life?")
    def answer(position, qid, number, text):
        return SimpleNamespace(position=position, page_number=3, exam_question_id=qid, normalized_number=number,
                               raw_question_number="Q" + number, answer_text=text, status="MAPPED",
                               mapping_note=None, mapping_candidates=[])
    first = answer(1, "6", "6", "6. (i) Second order (ii) First order")
    second = answer(2, "11", "11", "The reaction will depend on reactants, called pseudounimolecular reactions")
    second.raw_question_number = None
    later = answer(3, "11", "11", "B. 32 min")
    _repair_misread_labels([first, second, later], [q6, q11])
    assert second.exam_question_id == "6" and second.status == "MAPPED"
