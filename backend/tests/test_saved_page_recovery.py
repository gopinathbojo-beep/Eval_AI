import json
from pathlib import Path

import pytest

from app.cbse.extraction import Page
from app.services import pipeline


def stored_page(tmp_path, monkeypatch, obj):
    path = tmp_path / "failed-response.json"
    path.write_text(json.dumps({"status": "FAILED_PARSE", "parsed": None, "raw": json.dumps(obj)}), encoding="utf-8")
    monkeypatch.setattr(pipeline, "abs_path", Path)
    monkeypatch.setattr(pipeline, "rel", str)
    return {"page_number": 4, "ocr_status": "FAILED_PARSE", "ocr_file": str(path)}, path


def test_saved_page_recovers_after_parser_update_without_changing_original(tmp_path, monkeypatch):
    page, path = stored_page(tmp_path, monkeypatch, {"page_number": 4, "fragments": [
        {"root": 9, "text": "Printed answer", "marks": 2}, "issues_found_in_source_text",
    ]})
    original = path.read_bytes()
    recovered = pipeline.recover_failed_page(page, Page)
    assert recovered["status"] == "OK" and recovered["attempts"] == 0
    assert recovered["parsed"]["fragments"][0]["root"] == 9
    assert path.read_bytes() == original


@pytest.mark.parametrize("obj", [
    {"page_number": 5, "fragments": [{"root": 9, "text": "Wrong page"}]},
    {"page_number": 4, "answers": [{"question_number": "9", "answer_text": "Wrong format"}]},
    {"page_number": 4, "fragments": [{"root": 9, "text": "Answer"}, "unknown source text"]},
    {"page_number": 4, "fragments": []},
])
def test_unusable_cached_response_requires_a_fresh_read(tmp_path, monkeypatch, obj):
    page, _ = stored_page(tmp_path, monkeypatch, obj)
    assert pipeline.recover_failed_page(page, Page) is None
