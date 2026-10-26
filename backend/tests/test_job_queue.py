"""GPU job queue: jobs grouped by engine, up to N at once on the loaded engine, never two engines at once."""
import threading
import time

from app.config import get_settings
from app.services import job_queue as jq


def _setup(monkeypatch, engines, internvl_slots=1, indic_slots=1):
    s = get_settings()
    monkeypatch.setattr(s, "job_queue_inline", False)
    monkeypatch.setattr(s, "indic_text_model", "tamil-llm")
    monkeypatch.setattr(s, "internvl_parallel_jobs", internvl_slots)
    monkeypatch.setattr(s, "indic_parallel_jobs", indic_slots)
    monkeypatch.setattr(jq, "_current_engine", "internvl")
    monkeypatch.setattr(jq, "engine_for", lambda exam_id: engines[exam_id])
    events = []
    monkeypatch.setattr(jq, "unload_model", lambda m: events.append(f"unload {m}"))
    monkeypatch.setattr(jq, "release_indic", lambda: events.append("release indic"))
    return events


def test_one_slot_groups_engines_and_survives_a_crash(monkeypatch):
    events = _setup(monkeypatch, {"eng-1": "internvl", "tam-1": "indic", "eng-2": "internvl", "bad": "internvl"})
    running, overlap = [], []

    def job(name):
        if running:
            overlap.append(name)
        running.append(name)
        time.sleep(0.05)                       # long enough that parallel runs would overlap
        events.append(f"run {name} on {jq._current_engine}")
        running.remove(name)

    def crash():
        raise RuntimeError("page could not be read")

    for exam_id, fn, args in (("eng-1", job, ("eng-1",)), ("tam-1", job, ("tam-1",)), ("bad", crash, ()),
                              ("eng-2", job, ("eng-2",))):
        jq.submit(exam_id, fn, *args)
    assert jq.wait_idle(5)

    assert overlap == []                                   # one slot: never two jobs at once
    assert events == [
        "run eng-1 on internvl",
        "run eng-2 on internvl",                           # English jobs go ahead of the Tamil one; the crash did not stop the queue
        "unload blaifa/InternVL3_5:4B",                    # one switch: InternVL leaves the GPU
        "run tam-1 on indic",
    ]


def test_eng_tam_eng_tam_runs_pairs_in_parallel_with_one_switch(monkeypatch):
    events = _setup(monkeypatch, {"E1": "internvl", "T1": "indic", "E2": "internvl", "T2": "indic"},
                    internvl_slots=2, indic_slots=2)
    lock, running, peak = threading.Lock(), [], {}

    def job(name):
        with lock:
            running.append(name)
            engines = {jq._current_engine}
            peak[jq._current_engine] = max(peak.get(jq._current_engine, 0), len(running))
        time.sleep(0.1)
        with lock:
            assert engines == {jq._current_engine}         # the engine never changes under a running job
            running.remove(name)
            events.append(f"done {name}")

    for name in ("E1", "T1", "E2", "T2"):
        jq.submit(name, job, name)
    assert jq.wait_idle(5)

    assert peak == {"internvl": 2, "indic": 2}
    assert sorted(events[:2]) == ["done E1", "done E2"]
    assert events[2] == "unload blaifa/InternVL3_5:4B"     # a single switch, after both English jobs
    assert sorted(events[3:]) == ["done T1", "done T2"]


def test_waiting_job_is_passed_over_at_most_max_skips_times(monkeypatch):
    names = ["E0", "T", "E1", "E2", "E3", "E4", "E5"]
    events = _setup(monkeypatch, {n: "indic" if n == "T" else "internvl" for n in names})
    gate = threading.Event()

    def job(name):
        if name == "E0":
            gate.wait(5)                                   # hold the GPU until everything is queued
        events.append(name)

    for n in names:
        jq.submit(n, job, n)
    gate.set()
    assert jq.wait_idle(5)

    assert jq.MAX_SKIPS == 4
    assert events == ["E0", "E1", "E2", "E3", "E4", "unload blaifa/InternVL3_5:4B", "T",
                      "unload tamil-llm", "release indic", "E5"]
