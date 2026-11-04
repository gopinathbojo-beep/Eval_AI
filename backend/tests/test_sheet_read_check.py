"""The second look at a student's sheet page: a later read never overwrites the first, disagreements lower the
reading confidence and are kept for the teacher."""
from types import SimpleNamespace
from PIL import Image
from app.ocr.check import AGREED, DIFFERS, DOUBTFUL, check_page, compare_zoom
from app.ocr.schemas import PageLineStarts, StudentPageCheck, StudentPageResult


def _page(*answers):
    return StudentPageResult.model_validate({"answers": [
        {"question_number": n, "answer_text": t} for n, t in answers]})


def _model(checks, rows=None):
    def call(system, prompt, schema, image):
        if schema is PageLineStarts:
            return SimpleNamespace(parsed=PageLineStarts.model_validate({"rows": rows or []}), raw="{}")
        assert schema is StudentPageCheck and "FIRST READING" in prompt
        return SimpleNamespace(parsed=StudentPageCheck.model_validate({"checks": checks}), raw="{}")
    return call


def test_a_differing_second_reading_is_kept_as_a_suggestion_not_applied():
    page = _page(("Q2", "c) R."), ("Q3", "a) The implantation"), ("Q4", "a) salt [unclear]"), ("Q5", "d) R"))
    record = check_page(page, 1, None, "sys", _model([
        {"answer_id": "ans_001", "status": "CORRECTED", "answer_text": "d) R.", "changes": ["c) -> d)"]},
        {"answer_id": "ans_002", "status": "CORRECTED", "answer_text": "a) the implantation."},
        {"answer_id": "ans_003", "status": "OK"},
    ]), measured=False)
    assert [a.answer_text for a in page.answers] == ["c) R.", "a) The implantation", "a) salt [unclear]", "d) R"]
    assert [a.ocr_confidence for a in page.answers] == [DIFFERS, AGREED, DIFFERS, DOUBTFUL]
    assert record["applied"][0]["second_reading"] == "d) R." and record["applied"][0]["doubts"] == ["c) -> d)"]
    assert record["applied"][3]["doubts"] == ["not checked"]


def test_a_lower_measured_confidence_is_kept():
    page = _page(("Q1", "c) R."))
    page.answers[0].ocr_confidence = 0.62
    check_page(page, 1, None, "sys", _model([{"answer_id": "ans_001", "status": "OK"}]), measured=True)
    assert page.answers[0].ocr_confidence == 0.62


def test_zoom_disagreements_are_doubts_and_only_a_lone_q_is_repaired():
    assert compare_zoom("c) R.", "c) R.", []) == ("c) R.", [])
    assert compare_zoom("a) Physical change", "D) Physical change", []) == (
        "a) Physical change", ["option letter: reading a), zoomed read D)"])
    assert compare_zoom("I, iii & iv", "c) i, iii & iv", [])[1] == ["option letter missing from the reading; zoomed read: c)"]
    assert compare_zoom("a) cat one b) soap", "B) soap", ["A) cat one"])[1][0] == "may include struck-out words: A) cat one"
    assert compare_zoom("Q II and IV.", "c) II and IV.", [])[0] == "c) II and IV."
    assert compare_zoom("Bile juice is basic", "a) The liver", []) == ("Bile juice is basic", [])


def test_zoom_compares_the_first_answer_of_each_question(tmp_path):
    src = tmp_path / "page.png"
    Image.new("RGB", (100, 100), "white").save(src)
    page = _page(("18", "Q II and IV."), ("19", "a) soap is acidic"), ("19", "a) continued"), ("20", "c) I"))
    rows = [{"question_number": "Q18", "start": "c) II and IV", "struck": []},
            {"question_number": "19", "start": "B) soap is acidic", "struck": []},
            {"question_number": "20", "start": "c) I", "struck": []}]
    check_page(page, 6, None, "sys", _model([{"answer_id": f"ans_00{i}", "status": "OK"} for i in (1, 2, 3, 4)], rows),
               measured=False, zoom_source=src, zoom_dir=tmp_path)
    assert [a.answer_text for a in page.answers] == ["c) II and IV.", "a) soap is acidic", "a) continued", "c) I"]
    assert [a.ocr_confidence for a in page.answers] == [DOUBTFUL, DOUBTFUL, AGREED, AGREED]
    assert (tmp_path / "page-006-zoom1.png").exists() and (tmp_path / "page-006-zoom2.png").exists()
