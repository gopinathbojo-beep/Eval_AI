"""Unreadable sheet pages and AI outages are retried automatically before the teacher is asked."""
from types import SimpleNamespace as NS

from app.services import pipeline


def test_unreadable_page_is_queued_again_until_tries_run_out(monkeypatch):
    started = []
    monkeypatch.setattr(pipeline, "get_settings", lambda: NS(job_queue_inline=False), raising=False)
    import app.config
    monkeypatch.setattr(app.config, "get_settings", lambda: NS(job_queue_inline=False))

    class FakeTimer:
        def __init__(self, delay, fn, args):
            started.append(delay)
            self.daemon = False

        def start(self):
            pass

    import threading
    monkeypatch.setattr(threading, "Timer", FakeTimer)
    doc = NS(id="d1", exam_id="e1", status="NEEDS_ATTENTION", stage="", error_message="x",
             pages=[{"page_number": 1, "ocr_status": "OK"}, {"page_number": 2, "ocr_status": "FAILED_PARSE"}])
    db = NS(commit=lambda: None)
    for n in range(len(pipeline.PAGE_RETRY_DELAYS)):
        assert pipeline.schedule_page_retry(db, doc, [2]) is True
        assert doc.status == "UPLOADED" and doc.stage.startswith(pipeline.AUTO_RETRY_STAGE)
        assert doc.pages[1]["auto_retries"] == n + 1 and "auto_retries" not in doc.pages[0]
    assert started == list(pipeline.PAGE_RETRY_DELAYS)
    assert pipeline.schedule_page_retry(db, doc, [2]) is False  # tries used up: the teacher is asked


def test_a_page_read_as_empty_answers_is_not_a_good_read():
    from app.services.pipeline import _blank_answers
    from app.ocr.schemas import StudentPageResult
    assert _blank_answers(StudentPageResult(answers=[{"answer_text": ""}, {"answer_text": "  "}]))
    assert not _blank_answers(StudentPageResult(answers=[{"answer_text": ""}, {"answer_text": "1. (c) 27000"}]))
    assert not _blank_answers(StudentPageResult(answers=[]))  # a blank page with no answers is just blank
