"""The hosted OpenRouter queue uses one engine for every subject and task."""
from app.config import get_settings
from app.services import job_queue as jq


def test_every_exam_uses_openrouter():
    assert jq.engine_for(None) == "openrouter"
    assert jq.engine_for("missing", grading=True) == "openrouter"


def test_openrouter_parallelism_is_single_setting(monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_parallel_jobs", 3)
    assert jq.slots("openrouter") == 3
    assert jq.slots("any-legacy-name") == 3


def test_switch_engine_has_no_local_model_side_effects():
    jq.switch_engine("openrouter")
    assert jq._current_engine == "openrouter"
