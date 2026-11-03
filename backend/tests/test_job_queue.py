"""The hosted OpenRouter queue uses one engine for every subject and task."""
from app.config import get_settings
from app.services import job_queue as jq


def test_parallelism_is_one_setting(monkeypatch):
    monkeypatch.setattr(get_settings(), "internvl_parallel_jobs", 3)
    assert jq.slots() == 3


def test_every_queued_job_can_be_saved_as_a_durable_job():
    """Production runs DURABLE_JOBS=true, where submit() refuses functions missing from HANDLERS (tests run without)."""
    import ast
    from pathlib import Path
    from app.services.persistent_queue import HANDLERS

    registered = {h.split(":")[1] for h in HANDLERS}
    queued = set()
    app_dir = Path("app") if Path("app").exists() else (Path(__file__).resolve().parent.parent / "app")
    for path in app_dir.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            args = node.args
            if name == "add_task" and args and getattr(args[0], "id", None) == "submit":
                args = args[1:]  # bg.add_task(submit, exam_id, fn, ...)
            elif name != "submit":
                continue
            if len(args) > 1 and isinstance(args[1], ast.Name):
                queued.add(args[1].id)
    assert queued and queued <= registered, f"not in HANDLERS: {queued - registered}"
