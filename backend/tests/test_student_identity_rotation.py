"""Sheet identity: labels copied as values are cleaned, and sideways photos are retried turned."""
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from app.ocr.schemas import StudentIdentityResult
from app.services import student_identity as si


def test_label_copied_as_value_is_cleaned():
    assert si.clean_id("Rollinco") is None   # handwritten "Roll no:" read as the value
    assert si.clean_id("Roll no") is None
    assert si.clean_id("Roll No. 69") == "69"
    assert si.clean_id("reg 001", strip_label=False) == "reg 001"   # letters can be part of a registration no.
    assert si.clean_id("Reg. No", strip_label=False) is None
    assert si.clean_id("069") == "069"


def test_sideways_photo_is_identified_after_turning(tmp_path, monkeypatch):
    page = tmp_path / "page-001.png"
    Image.new("RGB", (400, 600), "white").save(page)  # portrait scan of a page photographed sideways
    doc = SimpleNamespace(pages=[{"processed_file": str(page)}])
    monkeypatch.setattr(si, "abs_path", lambda p: Path(p))

    def fake_model(system, user, schema, image_path=None):
        upright = Path(image_path).name.startswith("identity-r90-")  # only the page turned back upright reads well
        read = {"name": "A. Alan", "roll_number": "69"} if upright else {"name": "Rajne", "roll_number": "Rollinco"}
        return SimpleNamespace(parsed=StudentIdentityResult(**read))

    monkeypatch.setattr(si, "chat_structured", fake_model)
    monkeypatch.setattr(si, "match_student", lambda db, exam, read: (
        {"match": "AUTO", "student_id": "alan", "note": "Matched by roll number.", "read": read, "candidates": []}
        if read.get("roll_number") == "69" else
        {"match": "HOLD", "student_id": None, "note": si.NOTE_NO_ID, "read": read, "candidates": []}))

    res = si.identify_with_rotation(None, None, doc)
    assert res["match"] == "AUTO" and res["student_id"] == "alan" and "rotated" in res["note"]
    assert not list(tmp_path.glob("identity-*"))  # temporary crops/turns are cleaned up


def test_upright_match_makes_no_extra_calls(tmp_path, monkeypatch):
    page = tmp_path / "page-001.png"
    Image.new("RGB", (400, 600), "white").save(page)
    doc = SimpleNamespace(pages=[{"processed_file": str(page)}])
    monkeypatch.setattr(si, "abs_path", lambda p: Path(p))
    calls = []

    def fake_model(system, user, schema, image_path=None):
        calls.append(image_path)
        return SimpleNamespace(parsed=StudentIdentityResult(name="Alan", roll_number="69"))

    monkeypatch.setattr(si, "chat_structured", fake_model)
    monkeypatch.setattr(si, "match_student", lambda db, exam, read: {"match": "AUTO", "student_id": "alan",
                                                                     "note": "ok", "read": read, "candidates": []})
    assert si.identify_with_rotation(None, None, doc)["match"] == "AUTO"
    assert len(calls) == 1


def test_clear_read_that_conflicts_is_not_retried(tmp_path, monkeypatch):
    page = tmp_path / "page-001.png"
    Image.new("RGB", (400, 600), "white").save(page)
    doc = SimpleNamespace(pages=[{"processed_file": str(page)}])
    monkeypatch.setattr(si, "abs_path", lambda p: Path(p))
    calls = []
    monkeypatch.setattr(si, "chat_structured", lambda *a, **k: calls.append(1) or SimpleNamespace(
        parsed=StudentIdentityResult(name="Priya", roll_number="3")))
    monkeypatch.setattr(si, "match_student", lambda db, exam, read: {
        "match": "HOLD", "student_id": None, "note": "Roll number 3 is Meena, but the name on the sheet reads 'Priya'.",
        "read": read, "candidates": []})
    assert si.identify_with_rotation(None, None, doc)["match"] == "HOLD"
    assert len(calls) == 1


class _FakeQuery(list):
    def filter_by(self, **_):
        return self

    def all(self):
        return list(self)


def _students_db(students):
    return SimpleNamespace(query=lambda what: _FakeQuery(students if what is si.Student else []))


def test_roll_number_written_under_reg_label_still_matches():
    gopi = SimpleNamespace(id="g", name="Gopinath", roll_number="23CS17", registration_number="538573873874", section="A")
    other = SimpleNamespace(id="o", name="Priya", roll_number="23CS18", registration_number="538573873875", section="A")
    db, exam = _students_db([gopi, other]), SimpleNamespace(id="e", class_id="c")
    res = si.match_student(db, exam, {"name": "GOPINATH.R", "registration_number": "23CS17"})  # "Reg.NO: 23CS17"
    assert res["match"] == "AUTO" and res["student_id"] == "g" and "other label" in res["note"]
    res = si.match_student(db, exam, {"name": "Priya", "roll_number": "538573873875"})
    assert res["match"] == "AUTO" and res["student_id"] == "o"
    assert si.match_student(db, exam, {"registration_number": "99XX99"})["match"] == "HOLD"


def test_legible_page_without_details_is_not_turned(tmp_path, monkeypatch):
    """An answer key or a sheet with no name/roll no.: IndicOCR reads it upright, so the rotations are skipped."""
    page = tmp_path / "page-001.png"
    Image.new("RGB", (400, 600), "white").save(page)
    doc = SimpleNamespace(pages=[{"processed_file": str(page)}])
    monkeypatch.setattr(si, "abs_path", lambda p: Path(p))
    calls = []

    def fake_indic(image_path, legible=True):
        calls.append(Path(image_path).name)
        return {"name": None, "roll_number": None, "registration_number": None, "legible": legible}

    monkeypatch.setattr(si, "_reader", lambda exam: fake_indic)
    monkeypatch.setattr(si, "match_student", lambda db, exam, read: (
        {"match": "HOLD", "student_id": None, "note": si.NOTE_NO_ID, "read": read, "candidates": []}))
    res = si.identify_with_rotation(None, None, doc)
    assert res["match"] == "HOLD" and "legible" not in res["read"]
    assert not any(c.startswith("identity-r") for c in calls)

    calls.clear()
    monkeypatch.setattr(si, "_reader", lambda exam: lambda p: fake_indic(p, legible=False))
    si.identify_with_rotation(None, None, doc)
    assert sum(c.startswith("identity-r") for c in calls) == 3  # an unreadable page is still tried turned
