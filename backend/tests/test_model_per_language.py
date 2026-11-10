"""English-script subjects use OPENROUTER_MODEL (DeepSeek); Tamil, Hindi and Sanskrit exams use AI_INDIC_MODEL."""
from types import SimpleNamespace
from app import formatter
from app.config import get_settings
from app.ocr import remote


def _sent_model(monkeypatch, subject, model=None):
    sent = {}

    def post(url, json, **_):
        sent.update(json)
        return SimpleNamespace(is_success=True, json=lambda: {"choices": [{"message": {"content": "{}"},
                                                                            "finish_reason": "stop"}]})
    monkeypatch.setattr(remote.httpx, "post", post)
    with formatter.use(subject):
        remote.call("s", "u", None, True, model)
    return sent["model"]


def test_each_subject_gets_its_model(monkeypatch):
    s = get_settings()
    for subject in ("tamil", "hindi", "sanskrit"):
        assert _sent_model(monkeypatch, subject) == s.ai_indic_model
        assert _sent_model(monkeypatch, subject, s.small_model) == s.ai_indic_model  # every tier
    for subject in ("english", "maths", "accountancy", "common", None):
        assert _sent_model(monkeypatch, subject) == s.medium_model


def test_sanskrit_subject_names_pick_sanskrit():
    assert formatter.for_subject("Sanskrit") == formatter.for_subject("संस्कृतम्") == "sanskrit"


def test_page_reads_never_ask_gemini_to_turn_reasoning_off(monkeypatch, tmp_path):
    """Gemini answers HTTP 400 to reasoning {"enabled": false}; it gets effort "minimal", DeepSeek keeps "off"."""
    image = tmp_path / "page.png"
    image.write_bytes(b"png")
    sent = {}

    def post(url, json, **_):
        sent.update(json)
        return SimpleNamespace(is_success=True, json=lambda: {"choices": [{"message": {"content": "{}"},
                                                                            "finish_reason": "stop"}]})
    monkeypatch.setattr(remote.httpx, "post", post)
    with formatter.use("hindi"):
        remote.call("s", "u", image, True)
    assert sent["reasoning"] == {"effort": "minimal", "exclude": True}
    with formatter.use("english"):
        remote.call("s", "u", image, True)
    assert sent["reasoning"] == {"enabled": False}


def test_a_page_object_wrapped_in_a_list_is_unwrapped():
    from app.ocr.parser import extract_json_object
    assert extract_json_object('[{"page_number": 1, "elements": []}]')["page_number"] == 1
    assert "items" in extract_json_object('[{"a": 1}, {"b": 2}]')  # a real list stays a list
