"""Cancelling OCR: the endpoint, the pipeline stopping (including mid-call), and continuing afterwards."""
import threading
import time

from app.database import SessionLocal
from app.models import QuestionPaperDocument
from app.services.pipeline import process_document
from .conftest import BEHAVIOUR
from .test_mapping_and_marks import _exam_with_questions, j


def _set(doc_id, **vals):
    db = SessionLocal()
    doc = db.get(QuestionPaperDocument, doc_id)
    for k, v in vals.items():
        setattr(doc, k, v)
    db.commit()
    db.close()


def _paper(c, h):
    eid, qids = _exam_with_questions(c, h)
    return eid, j(c.get(f"/api/exams/{eid}/question-paper", headers=h), 200)["id"], qids


def test_cancel_endpoint_states(client, auth):
    c, h = client, auth
    _, doc_id, _ = _paper(c, h)
    url = f"/api/documents/question-paper/{doc_id}/cancel"
    r = c.post(url, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "NOT_PROCESSING"
    _set(doc_id, status="EXTRACTING")
    r = c.post(url, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "ALMOST_DONE"
    _set(doc_id, status="OCR_PROCESSING")
    assert j(c.post(url, headers=h), 200)["status"] == "CANCELLING"
    assert j(c.post(url, headers=h), 200)["status"] == "CANCELLING"      # repeat click is harmless
    # Still busy until the pipeline confirms, so a second run cannot start alongside the first.
    r = c.post(f"/api/documents/question-paper/{doc_id}/reprocess", headers=h)
    assert r.status_code == 409


def test_pipeline_stops_on_cancel_and_keeps_existing_questions(client, auth):
    c, h = client, auth
    eid, doc_id, qids = _paper(c, h)
    _set(doc_id, status="CANCELLING")
    BEHAVIOUR["page_calls"] = []
    process_document("question-paper", doc_id)
    doc = j(c.get(f"/api/exams/{eid}/question-paper", headers=h), 200)
    assert doc["status"] == "CANCELLED" and "cancelled" in doc["error_message"]
    assert BEHAVIOUR["page_calls"] == []
    qs = j(c.get(f"/api/exams/{eid}/questions", headers=h), 200)["questions"]
    assert {q["id"] for q in qs} == set(qids.values())


def test_cancel_aborts_page_in_flight_then_continue_reads_only_the_rest(client, auth):
    c, h = client, auth
    eid, doc_id, _ = _paper(c, h)
    db = SessionLocal()
    doc = db.get(QuestionPaperDocument, doc_id)
    pages = [dict(p) for p in doc.pages]
    pages[1].pop("ocr_status", None)     # page 1 already read, page 2 not yet
    doc.pages, doc.status = pages, "UPLOADED"
    db.commit()
    db.close()

    BEHAVIOUR.update(page_delay=30.0, page_calls=[])
    try:
        t = threading.Thread(target=process_document, args=("question-paper", doc_id, True))
        t.start()
        deadline = time.time() + 10
        while not BEHAVIOUR["page_calls"] and time.time() < deadline:
            time.sleep(0.05)
        assert BEHAVIOUR["page_calls"] == [2]
        started = time.time()
        assert j(c.post(f"/api/documents/question-paper/{doc_id}/cancel", headers=h), 200)["status"] == "CANCELLING"
        t.join(10)
        assert not t.is_alive() and time.time() - started < 5     # did not wait for the 30 s page
    finally:
        BEHAVIOUR["page_delay"] = 0.0
    doc = j(c.get(f"/api/exams/{eid}/question-paper", headers=h), 200)
    assert doc["status"] == "CANCELLED"
    assert [p.get("ocr_status") for p in doc["pages"]] == ["OK", None]

    BEHAVIOUR["page_calls"] = []
    j(c.post(f"/api/documents/question-paper/{doc_id}/reprocess", headers=h), 202)
    assert BEHAVIOUR["page_calls"] == [2]                      # page 1 was not read again
    doc = j(c.get(f"/api/exams/{eid}/question-paper", headers=h), 200)
    assert doc["status"] == "READY"
    assert [q["display_number"] for q in j(c.get(f"/api/exams/{eid}/questions", headers=h), 200)["questions"]] \
        == ["1", "2", "3"]


def test_recovery_finishes_a_pending_cancel(client, auth):
    from app.services.pipeline import recover_interrupted_jobs
    c, h = client, auth
    eid, doc_id, _ = _paper(c, h)
    _set(doc_id, status="CANCELLING")
    recover_interrupted_jobs()
    assert j(c.get(f"/api/exams/{eid}/question-paper", headers=h), 200)["status"] == "CANCELLED"
