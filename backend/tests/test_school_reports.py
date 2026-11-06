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
        ex = Exam(teacher_id=t.id, name="Term 1", academic_year="2026-27", class_id=cls.id, subject_id=sub.id,
                  exam_type="Board pattern", total_marks=80, status="FINALIZED")
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
    assert terms == [{"term": "Term 1", "academic_year": "2026-27", "exam_type": "Term 1",
                      "subjects": ["RC English", "RC Hindi"]}]
    # CBSE card: English 72/80 = 90% (A2), Hindi 50/80 = 62.5% (B2), overall 122/160 = 76.25% (B1)
    r = c.get(f"/api/students/{asha_id}/report-card?term=Term 1", headers=h)
    assert r.status_code == 200 and "Asha" in r.headers["content-disposition"]
    text, pages = _text(r.content)
    assert pages == 1 and "Green Valley School" in text and "REPORT CARD" in text and "Term 1" in text
    assert "Scholastic Areas" in text and "122" in text and "76.25%" in text and "Dr. R. Iyer" in text
    assert "A2" in text and "B2" in text and "B1" in text and "PASS" in text and "1 of 1" in text
    assert "K Level" not in text and "Knowledge Level" not in text
    whole = c.get(f"/api/classes/{cls_id}/report-cards?term=Term 1", headers=h)
    text, pages = _text(whole.content)
    assert pages == 2 and "Awaited" in text and "RESULT AWAITED" in text      # Ravi's missing Hindi result
    assert c.get(f"/api/classes/{cls_id}/report-cards?term=Final", headers=h).status_code == 404


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
    q1 = ExamQuestion(exam_id=ex.id, display_number="1", max_marks=10, position=0)
    q2 = ExamQuestion(exam_id=ex.id, display_number="2", max_marks=10, position=1)
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
    assert "Exam Result Analysis" in text and "Maths Unit Test" in text and "2 evaluated" in text and "pending" not in text and "Not evaluated" not in text
    assert "Meena" in text and "Arjun" in text and "Kavya" not in text
    assert "55%" in text and "1 / 2" in text and "50%" in text                  # average, passed, pass %
    assert "Question-wise Analysis" in text and "Knowledge Level" not in text and "K Level" not in text


def test_all_student_reports_in_one_zip(client, auth):
    import io
    import zipfile
    c, h = client, auth
    db = SessionLocal()
    t = db.query(Teacher).filter_by(email="rao@school.org").one()
    cls = SchoolClass(teacher_id=t.id, name="ZIP-9C")
    sub = Subject(teacher_id=t.id, name="ZIP Science")
    db.add_all([cls, sub])
    db.flush()
    kids = [Student(class_id=cls.id, name=n, roll_number=r) for n, r in (("Meena", "1"), ("Arjun", "2"), ("Kavya", "3"))]
    db.add_all(kids)
    ex = Exam(teacher_id=t.id, name="Science Term 1", academic_year="2026-27", class_id=cls.id, subject_id=sub.id,
              exam_type="Term", total_marks=10, status="REVIEW_REQUIRED")
    db.add(ex)
    db.flush()
    q1 = ExamQuestion(exam_id=ex.id, display_number="1", max_marks=10, position=0)
    db.add(q1)
    db.commit()
    assert c.get(f"/api/exams/{ex.id}/student-reports.zip", headers=h).status_code == 400   # nobody finalized yet
    for st, marks, status in ((kids[0], 9, "FINALIZED"), (kids[1], 4, "FINALIZED"), (kids[2], 6, "DRAFT")):
        doc = AnswerSheetDocument(exam_id=ex.id, student_id=st.id, original_filename="s.pdf", original_file="x",
                                  mime_type="application/pdf", file_size=1, status="READY")
        db.add(doc)
        db.flush()
        ev = Evaluation(exam_id=ex.id, student_id=st.id, answer_sheet_id=doc.id, status=status, total_marks=marks,
                        maximum_marks=10, percentage=10.0 * marks,
                        finalized_at=datetime.now(timezone.utc) if status == "FINALIZED" else None)
        db.add(ev)
        db.flush()
        db.add(EvaluationItem(evaluation_id=ev.id, exam_question_id=q1.id, final_marks=marks))
    db.commit()
    ex_id = ex.id
    db.close()

    r = c.get(f"/api/exams/{ex_id}/student-reports.zip", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert "StudentReports_Science_Term_1.zip" in r.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    assert len(names) == 2 and all(n.endswith(".pdf") for n in names)        # the draft student is left out
    texts = " ".join(_text(z.read(n))[0] for n in names)
    assert "Meena" in texts and "Arjun" in texts and "Kavya" not in texts


def test_report_details_change_the_reports_and_nothing_else(client, auth):
    c, h = client, auth
    db = SessionLocal()
    t = db.query(Teacher).filter_by(email="rao@school.org").one()
    cls = SchoolClass(teacher_id=t.id, name="RD-10A")
    sub = Subject(teacher_id=t.id, name="RD Maths")
    db.add_all([cls, sub])
    db.flush()
    kid = Student(class_id=cls.id, name="Meena", roll_number="1")
    db.add(kid)
    ex = Exam(teacher_id=t.id, name="Unit 1", academic_year="2026-27", class_id=cls.id, subject_id=sub.id,
              exam_type="Board pattern", total_marks=10, status="FINALIZED", standard_profile_id="cbse-12-041")
    db.add(ex)
    db.flush()
    q = ExamQuestion(exam_id=ex.id, display_number="1", max_marks=10, position=0)
    doc = AnswerSheetDocument(exam_id=ex.id, student_id=kid.id, original_filename="s.pdf", original_file="x",
                              mime_type="application/pdf", file_size=1, status="READY")
    db.add_all([q, doc])
    db.flush()
    ev = Evaluation(exam_id=ex.id, student_id=kid.id, answer_sheet_id=doc.id, status="FINALIZED", total_marks=7,
                    maximum_marks=10, percentage=70.0, finalized_at=datetime.now(timezone.utc))
    db.add(ev)
    db.flush()
    db.add(EvaluationItem(evaluation_id=ev.id, exam_question_id=q.id, final_marks=7))
    db.commit()
    ex_id, ev_id = ex.id, ev.id
    db.close()

    r = c.put(f"/api/exams/{ex_id}/report-details", headers=h, json={
        "name": "Half Yearly", "class_name": "Class XII - A", "subject": "Applied Maths", "exam_type": "Term Exam",
        "academic_year": "2027-28", "exam_date": "05 Nov 2026"})
    assert r.status_code == 200, r.text                                   # open on a finalized board-pattern exam
    body = r.json()
    assert body["report_details"]["name"] == "Half Yearly"
    assert body["name"] == "Unit 1" and body["subject_name"] == "RD Maths" and body["exam_type"] == "Board pattern"

    text, _ = _text(c.get(f"/api/evaluations/{ev_id}/report.pdf", headers=h).content)
    for shown in ("Half Yearly", "Class XII - A", "Applied Maths", "Term Exam", "2027-28", "05 Nov 2026", "7 / 10"):
        assert shown in text, shown
    assert "Unit 1" not in text and "RD Maths" not in text
    text, _ = _text(c.get(f"/api/exams/{ex_id}/report.pdf", headers=h).content)
    assert "Half Yearly" in text and "Applied Maths" in text and "Unit 1" not in text

    r = c.put(f"/api/exams/{ex_id}/report-details", headers=h, json={"name": "  ", "subject": "Applied Maths"})
    assert r.json()["report_details"] == {"subject": "Applied Maths"}     # blank goes back to the exam's own value
    text, _ = _text(c.get(f"/api/evaluations/{ev_id}/report.pdf", headers=h).content)
    assert "Unit 1" in text and "Applied Maths" in text


def test_report_file_name_is_roll_section_subject():
    from types import SimpleNamespace as NS
    from app.services.school_reports import report_filename

    def ev(section=None, class_name="10-C", subject="Science", details=None, roll="10C04"):
        cls, sub = NS(name=class_name), NS(name=subject)
        return NS(student=NS(roll_number=roll, section=section),
                  exam=NS(report_details=details, school_class=cls, subject=sub, name="T", exam_type="B",
                          academic_year="2026-27", exam_date=None))

    assert report_filename(ev()) == "10C04-C-Science.pdf"                       # the section from the class name
    assert report_filename(ev(section="D")) == "10C04-D-Science.pdf"            # the student's own section first
    assert report_filename(ev(class_name="Grade 10")) == "10C04-Science.pdf"    # no section at all
    assert report_filename(ev(subject="Social Science")) == "10C04-C-Social_Science.pdf"
    assert report_filename(ev(roll="10/C 04")) == "10_C_04-C-Science.pdf"       # safe in a file name
    edited = {"subject": "Physics", "class_name": "10-E"}
    assert report_filename(ev(details=edited)) == "10C04-E-Physics.pdf"         # follows what the report prints
