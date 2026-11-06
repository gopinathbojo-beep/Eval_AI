"""Parallel AI jobs share one SQLite file. A job that meets "database is locked" is run again by itself (reading keeps
the pages already read; grading resumes with the questions still unmarked) and the SQL error never reaches the
teacher."""
import sqlite3

from sqlalchemy.exc import OperationalError

from app.database import is_locked
from app.services import evaluation_service, pipeline


def _locked():
    return OperationalError("UPDATE answer_sheet_documents SET pages=?", {}, sqlite3.OperationalError("database is locked"))


def test_lock_error_is_recognised():
    assert is_locked(_locked()) and not is_locked(ValueError("bad value"))


def test_reading_is_run_again_after_a_busy_database(monkeypatch):
    calls = []

    def run(db, kind, doc_id, only_failed):
        calls.append(only_failed)
        if len(calls) == 1:
            raise _locked()

    monkeypatch.setattr(pipeline, "_run", run)
    monkeypatch.setattr(pipeline.time, "sleep", lambda s: None)
    pipeline.process_document("answer-sheet", "doc-1")
    assert calls == [False, True]   # the retry keeps the pages already read


def test_reading_that_stays_busy_shows_a_plain_message(monkeypatch):
    def run(db, kind, doc_id, only_failed):
        raise _locked()

    saved = {}

    class Doc:
        status = "OCR_PROCESSING"

        def __setattr__(self, k, v):
            saved[k] = v

    class DB:
        def rollback(self): pass
        def commit(self): pass
        def close(self): pass
        def get(self, model, id): return Doc()

    monkeypatch.setattr(pipeline, "_run", run)
    monkeypatch.setattr(pipeline, "SessionLocal", DB)
    monkeypatch.setattr(pipeline.time, "sleep", lambda s: None)
    pipeline.process_document("answer-sheet", "doc-1")
    assert saved["status"] == "FAILED" and "locked" not in saved["error_message"]
    assert "SQL" not in saved["error_message"] and "busy" in saved["error_message"]


def test_grading_resumes_with_only_the_unmarked_questions(monkeypatch):
    runs = []

    def run(ev_id, todo, last=True):
        runs.append(todo)
        return len(runs) > 1

    monkeypatch.setattr(evaluation_service, "_run_evaluation", run)
    monkeypatch.setattr(evaluation_service, "_still_to_grade", lambda ev_id: ["q7", "q8"])
    monkeypatch.setattr(evaluation_service.time, "sleep", lambda s: None)
    from app.services import autopilot
    monkeypatch.setattr(autopilot, "after_grading", lambda ev_id: None)
    evaluation_service.run_evaluation("ev-1")
    assert runs == [None, ["q7", "q8"]]
