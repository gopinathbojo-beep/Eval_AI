import re
from datetime import datetime, timezone
import pymupdf
from app.database import SessionLocal
from app.models import (AnswerSheetDocument, Evaluation, EvaluationItem, Exam, ExamQuestion, SchoolClass, Student, Subject,
                        Teacher)
from app.services.report_templates import normalize
from app.services.school_reports import relative_grades
from .conftest import make_png


def j(r, code=None):
    if code is not None:
        assert r.status_code == code, f"{r.status_code}: {r.text}"
    return r.json()


def _text(pdf: bytes) -> str:
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    return re.sub(r"\s+", " ", "".join(p.get_text() for p in doc)), doc.page_count


def test_relative_grades():
    scores = {str(i): 100 - i * 8 for i in range(8)}
    scores.update(failed=32.9, missing=None)
    grades = relative_grades(scores)
    assert [grades[str(i)] for i in range(8)] == ["A-1", "A-2", "B-1", "B-2", "C-1", "C-2", "D-1", "D-2"]
    assert grades["failed"] == "E" and grades["missing"] == "–"
    assert relative_grades({"a": 80, "b": 80, "c": 50})["a"] == relative_grades({"a": 80, "b": 80, "c": 50})["b"]
    assert relative_grades({"only": 33}) == {"only": "A-1"}
    assert relative_grades({"failed_subject": 90}, {"failed_subject"}) == {"failed_subject": "E"}


def test_template_normalize_keeps_known_keys_only():
    cfg = normalize("report_card", {
        "sections": [{"id": "summary", "visible": False}, {"id": "bogus"}, "header"],
        "labels": {"title": "Progress Report", "nope": "x"},
        "style": {"accent": "red", "font_size": 99, "borders": "lines"},
        "signers": ["Form Tutor", "", "Principal"],
    })
    ids = [s["id"] for s in cfg["sections"]]
    assert ids[:2] == ["summary", "header"] and "bogus" not in ids and len(ids) == 9
    assert cfg["sections"][0]["visible"] is False
    assert cfg["labels"]["title"] == "Progress Report" and "nope" not in cfg["labels"]
    assert cfg["style"]["accent"] == "#1E3A5F" and cfg["style"]["font_size"] == 12.0 and cfg["style"]["borders"] == "lines"
    assert cfg["signers"] == ["Form Tutor", "Principal"]


def test_school_profile_templates_and_report_cards(client, auth):
    c, h = client, auth
    # school details + logo
    p = j(c.put("/api/school-profile", headers=h, json={"name": "Green Valley School", "address": "12 Lake Rd, Chennai",
                                                        "principal_name": "Dr. R. Iyer"}), 200)
    assert p["name"] == "Green Valley School" and not p["has_logo"]
    assert j(c.post("/api/school-profile/logo", headers=h, files={"file": ("logo.png", make_png(), "image/png")}), 200)["has_logo"]
    assert c.get("/api/school-profile/logo", headers=h).status_code == 200

    # presets + a custom template that renames the title and hides the rank
    lst = j(c.get("/api/report-templates?kind=report_card", headers=h), 200)
    assert lst["active_id"] == "preset:classic" and [t["name"] for t in lst["templates"]][:3] == ["Classic", "Modern", "Minimal"]
    cfg = lst["templates"][1]["config"]
    cfg["labels"]["title"] = "Progress Report"
    cfg["summary"] = [s if s["id"] != "rank" else {"id": "rank", "visible": False} for s in cfg["summary"]]
    tpl = j(c.post("/api/report-templates", headers=h, json={"kind": "report_card", "name": "Our card", "config": cfg}), 201)
    prev = c.post("/api/report-templates/preview", headers=h, json={"kind": "report_card", "config": tpl["config"]})
    assert prev.status_code == 200 and "Progress Report" in _text(prev.content)[0]
    assert c.get(f"/api/report-templates/{tpl['id']}/preview?kind=report_card", headers=h).status_code == 200
    assert c.post("/api/report-templates/activate", headers=h, json={"kind": "report", "id": tpl["id"]}).status_code == 400
    j(c.post("/api/report-templates/activate", headers=h, json={"kind": "report_card", "id": tpl["id"]}), 200)

    # two students, two subjects of "Term 1"; Ravi has no Hindi result yet
    db = SessionLocal()
    t = db.query(Teacher).filter_by(email="rao@school.org").one()
    cls = SchoolClass(teacher_id=t.id, name="RC-8A")
    db.add(cls)
    db.flush()
    asha = Student(class_id=cls.id, name="Asha", roll_number="1", registration_number="RC001", section="A")
    ravi = Student(class_id=cls.id, name="Ravi", roll_number="2")
    db.add_all([asha, ravi])
    db.flush()
    for subj, marks in (("English", {asha: 72, ravi: 60}), ("Hindi", {asha: 50})):
        sub = Subject(teacher_id=t.id, name=f"RC {subj}")
        db.add(sub)
        db.flush()
        ex = Exam(teacher_id=t.id, name=f"{subj} T1", academic_year="2026-27", class_id=cls.id, subject_id=sub.id,
                  exam_type="Term 1", total_marks=80, status="FINALIZED")
        db.add(ex)
        db.flush()
        for st, got in marks.items():
            doc = AnswerSheetDocument(exam_id=ex.id, student_id=st.id, original_filename="s.pdf", original_file="x",
                                      mime_type="application/pdf", file_size=1, status="READY")
            db.add(doc)
            db.flush()
            db.add(Evaluation(exam_id=ex.id, student_id=st.id, answer_sheet_id=doc.id, status="FINALIZED",
                              total_marks=got, maximum_marks=80, percentage=round(100 * got / 80, 2),
                              finalized_at=datetime.now(timezone.utc)))
    db.commit()
    cls_id, asha_id = cls.id, asha.id
    db.close()

    terms = j(c.get(f"/api/classes/{cls_id}/report-card-terms", headers=h), 200)
    assert terms == [{"academic_year": "2026-27", "exam_type": "Term 1", "subjects": ["RC English", "RC Hindi"]}]
    r = c.get(f"/api/students/{asha_id}/report-card?academic_year=2026-27&exam_type=Term 1", headers=h)
    assert r.status_code == 200 and "Asha" in r.headers["content-disposition"]
    text, pages = _text(r.content)
    assert pages == 1 and "Green Valley School" in text and "Progress Report · Term 1 · 2026-27" in text
    assert "122 / 160" in text and "76.25%" in text and "A-1" in text and "Dr. R. Iyer" in text
    assert "K Level" not in text and "Knowledge Level" not in text
    assert "Class Rank" not in text                                             # hidden by the template
    whole = c.get(f"/api/classes/{cls_id}/report-cards?academic_year=2026-27&exam_type=Term 1", headers=h)
    text, pages = _text(whole.content)
    assert pages == 2 and "Not evaluated" in text                               # Ravi's missing Hindi result

    # deleting the active template falls back to Classic, which shows the rank
    j(c.delete(f"/api/report-templates/{tpl['id']}", headers=h), 200)
    assert j(c.get("/api/report-templates?kind=report_card", headers=h))["active_id"] == "preset:classic"
    text, _ = _text(c.get(f"/api/students/{asha_id}/report-card?academic_year=2026-27&exam_type=Term 1", headers=h).content)
    assert "Report Card · Term 1" in text and "1 of 1" in text
    assert c.get(f"/api/classes/{cls_id}/report-cards?academic_year=2026-27&exam_type=Final", headers=h).status_code == 404


def test_exam_wise_report(client, auth):
    c, h = client, auth
    db = SessionLocal()
    t = db.query(Teacher).filter_by(email="rao@school.org").one()
    cls = SchoolClass(teacher_id=t.id, name="EX-9B")
    sub = Subject(teacher_id=t.id, name="EX Maths")
    db.add_all([cls, sub])
    db.flush()
    kids = [Student(class_id=cls.id, name=n, roll_number=r) for n, r in (("Meena", "1"), ("Arjun", "2"), ("Kavya", "3"))]
    db.add_all(kids)
    ex = Exam(teacher_id=t.id, name="Maths Unit Test", academic_year="2026-27", class_id=cls.id, subject_id=sub.id,
              exam_type="Unit Test", total_marks=20, status="FINALIZED")
    db.add(ex)
    db.flush()
    q1 = ExamQuestion(exam_id=ex.id, display_number="1", max_marks=10, position=0, k_level="K1")
    q2 = ExamQuestion(exam_id=ex.id, display_number="2", max_marks=10, position=1, k_level="K3")
    db.add_all([q1, q2])
    db.commit()
    empty = c.get(f"/api/exams/{ex.id}/report.pdf", headers=h)
    assert empty.status_code == 400, empty.text                                 # nothing finalized yet
    for st, (a, b) in ((kids[0], (10, 8)), (kids[1], (4, 0))):                  # Kavya is not evaluated
        doc = AnswerSheetDocument(exam_id=ex.id, student_id=st.id, original_filename="s.pdf", original_file="x",
                                  mime_type="application/pdf", file_size=1, status="READY")
        db.add(doc)
        db.flush()
        ev = Evaluation(exam_id=ex.id, student_id=st.id, answer_sheet_id=doc.id, status="FINALIZED", total_marks=a + b,
                        maximum_marks=20, percentage=5.0 * (a + b), finalized_at=datetime.now(timezone.utc))
        db.add(ev)
        db.flush()
        db.add_all([EvaluationItem(evaluation_id=ev.id, exam_question_id=q1.id, final_marks=a),
                    EvaluationItem(evaluation_id=ev.id, exam_question_id=q2.id, final_marks=b)])
    db.commit()
    ex_id = ex.id
    db.close()

    r = c.get(f"/api/exams/{ex_id}/report.pdf", headers=h)
    assert r.status_code == 200 and "ExamReport_Maths_Unit_Test_EX-9B" in r.headers["content-disposition"]
    text, _ = _text(r.content)
    assert "Exam Result Analysis" in text and "Maths Unit Test" in text and "2 evaluated, 1 pending" in text
    assert "Meena" in text and "Arjun" in text and "Kavya" in text and "Not evaluated" in text
    assert "55%" in text and "1 / 2" in text and "50%" in text                  # average, passed, pass %
    assert "Question-wise Analysis" in text and "Knowledge Level" not in text and "K Level" not in text
