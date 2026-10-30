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
    monkeypatch.setattr(jq, "engine_for", lambda exam_id, grading=False: engines[exam_id])
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


def test_uploads_are_not_held_up_while_the_engine_switches(monkeypatch):
    events = _setup(monkeypatch, {"E1": "internvl", "T1": "indic", "T2": "indic"})
    unloading, release = threading.Event(), threading.Event()

    def slow_unload(model):
        unloading.set()
        release.wait(5)                                    # Ollama on the GPU machine takes its time
        events.append(f"unload {model}")

    monkeypatch.setattr(jq, "unload_model", slow_unload)
    monkeypatch.setattr(jq, "_current_engine", "internvl")
    jq.submit("T1", lambda: events.append("run T1"))
    assert unloading.wait(5)
    started = time.monotonic()
    jq.submit("E1", lambda: events.append("run E1"))     # an upload arriving mid-switch
    assert time.monotonic() - started < 0.5                # queued at once, not after the unload
    jq.submit("T2", lambda: events.append("run T2"))
    assert jq.pending() == 2 and "run T1" not in events     # nothing starts until the switch is done
    release.set()
    assert jq.wait_idle(5)
    assert events[:3] == ["unload blaifa/InternVL3_5:4B", "run T1", "run T2"]


def test_a_failed_switch_does_not_stop_the_queue(monkeypatch):
    events = _setup(monkeypatch, {"T1": "indic", "T2": "indic"})

    def unreachable(model):
        raise ConnectionError("Ollama is not reachable")

    monkeypatch.setattr(jq, "unload_model", unreachable)
    jq.submit("T1", lambda: events.append("run T1"))
    jq.submit("T2", lambda: events.append("run T2"))
    assert jq.wait_idle(5)
    assert events == ["run T1", "run T2"]                   # the jobs ran and record the engine error themselves


def test_tamil_reading_has_the_gpu_to_itself(monkeypatch):
    events = _setup(monkeypatch, {})
    monkeypatch.setattr(get_settings(), "indic_text_model", "")
    jq.switch_engine("indic")                              # InternVL leaves: IndicOCR reads alone
    assert events == ["unload blaifa/InternVL3_5:4B"]
    events.clear()
    jq.switch_engine("internvl")                           # back for English and for grading the Tamil sheets
    assert events == ["release indic"]


def test_tamil_papers_go_one_after_another(monkeypatch):
    # paper A: two sheets; its grading is queued after the first, ahead of paper B's reading jobs
    jobs = [("A-sheet1", "A", False), ("A-grade1", "A", True), ("A-sheet2", "A", False), ("B-paper", "B", False),
            ("B-key", "B", False), ("B-sheet1", "B", False)]
    events = _setup(monkeypatch, {})
    monkeypatch.setattr(jq, "engine_for", lambda exam_id, grading=False: "internvl" if grading else "indic")
    monkeypatch.setattr(get_settings(), "indic_text_model", "")
    monkeypatch.setattr(jq, "_current_engine", "indic")
    gate = threading.Event()

    def job(name):
        if name == "A-sheet1":
            gate.wait(5)                                   # hold the GPU until everything is queued
        events.append(name)

    for name, exam, grading in jobs:
        jq.submit(exam, job, name, grading=grading)
    gate.set()
    assert jq.wait_idle(5)
    # paper A's other sheet is read first, then InternVL grades A, then paper B is read with IndicOCR
    assert events == ["A-sheet1", "A-sheet2", "release indic", "A-grade1", "unload blaifa/InternVL3_5:4B",
                      "B-paper", "B-key", "B-sheet1"]


def test_english_grading_does_not_cut_a_tamil_paper_short(monkeypatch):
    events = _setup(monkeypatch, {})
    monkeypatch.setattr(jq, "engine_for", lambda exam_id, grading=False: "internvl" if exam_id == "E" or grading else "indic")
    monkeypatch.setattr(get_settings(), "indic_text_model", "")
    monkeypatch.setattr(jq, "_current_engine", "indic")
    gate = threading.Event()

    def job(name):
        if name == "T-sheet1":
            gate.wait(5)
        events.append(name)

    for name, exam, grading in (("T-sheet1", "T", False), ("E-grade", "E", True), ("T-sheet2", "T", False)):
        jq.submit(exam, job, name, grading=grading)
    gate.set()
    assert jq.wait_idle(5)
    assert events == ["T-sheet1", "T-sheet2", "release indic", "E-grade"]  # English follows the MAX_SKIPS rule
