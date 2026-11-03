"""CBSE term report card: subjects of one exam name, 8-point grades, section and class ranks, result."""
import uuid

from .test_bulk_sheets_and_early_key import j


def _seed(client, auth):
    """Two sections of Class 10, 'Term 1' in Science and Tamil, finalized marks out of 80."""
    from app.database import SessionLocal
    from app.models import AnswerSheetDocument, Evaluation, Exam, Student
    term = f"Term {uuid.uuid4().hex[:6]}"
    ids = {}
    for sec in ("A", "B"):
        for subject in ("10-science", "10-tamil"):
            e = j(client.post("/api/exams/simple", headers=auth,
                              json={"name": term, "grade": "10", "section": sec, "subject_key": subject}), 201)
            ids[(sec, subject)] = e["id"]
    marks = {("A", "1"): (76, 70), ("A", "2"): (40, 20), ("B", "1"): (78, 76), ("B", "2"): (20, 10)}
    with SessionLocal() as db:
        students = {}
        for (sec, roll), (sci, tam) in marks.items():
            exam = db.get(Exam, ids[(sec, "10-science")])
            st = Student(class_id=exam.class_id, name=f"Student {sec}{roll}", roll_number=f"{term[-6:]}{roll}")
            db.add(st)
            db.flush()
            students[(sec, roll)] = st.id
            for subject, got in (("10-science", sci), ("10-tamil", tam)):
                eid = ids[(sec, subject)]
                doc = AnswerSheetDocument(exam_id=eid, student_id=st.id, original_filename="s.pdf", original_file="x",
                                          mime_type="application/pdf", file_size=1, status="READY")
                db.add(doc)
                db.flush()
                db.add(Evaluation(exam_id=eid, student_id=st.id, answer_sheet_id=doc.id, status="FINALIZED",
                                  total_marks=got, maximum_marks=80, percentage=round(100 * got / 80, 2)))
        db.commit()
    return term, students


def test_term_card_grades_ranks_and_result(client, auth):
    from app.database import SessionLocal
    from app.models import Teacher
    from app.services.cbse_report_card import card_data, grade_for
    term, students = _seed(client, auth)
    assert [grade_for(p) for p in (100, 90.5, 90.4, 33, 32.4, None)] == ["A1", "A1", "A2", "D", "E", "–"]
    with SessionLocal() as db:
        t = db.query(Teacher).filter_by(email="rao@school.org").one()
        top_a = card_data(db, t, students[("A", "1")], term)
        weak_b = card_data(db, t, students[("B", "2")], term)
    # A1: 146/160 = 91.25% -> A1; section rank 1 of 2, class rank 2 of 4 (B1 has 154)
    assert top_a["overall"] == 91.25 and top_a["overall_grade"] == "A1" and top_a["result"] == "PASS"
    assert (top_a["section_rank"], top_a["section_ranked"], top_a["class_rank"], top_a["class_ranked"]) == (1, 2, 2, 4)
    assert [r["subject"] for r in top_a["rows"]] == ["Science", "Tamil"]
    assert top_a["rows"][0]["grade"] == "A1" and top_a["rows"][1]["grade"] == "A2"   # 95%, 87.5%
    assert top_a["remark"].startswith("Student has shown outstanding")
    # B2 fails both subjects -> compartment, last in class
    assert weak_b["result"] == "COMPARTMENT" and weak_b["failed"] == ["Science", "Tamil"]
    assert (weak_b["section_rank"], weak_b["class_rank"]) == (2, 4)

    terms = j(client.get(f"/api/students/{students[('A', '1')]}/terms", headers=auth), 200)
    assert any(x["term"] == term and x["finalized"] == 2 for x in terms)
    pdf = client.get(f"/api/students/{students[('A', '1')]}/term-card", params={"term": term}, headers=auth)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert client.get(f"/api/students/{uuid.uuid4()}/term-card", params={"term": term}, headers=auth).status_code == 404


def test_question_summary_replaces_k_levels(client, auth):
    term, students = _seed(client, auth)
    exams = [e for e in j(client.get("/api/exams", headers=auth), 200) if e["name"] == term]
    s = j(client.get(f"/api/exams/{exams[0]['id']}/question-summary", headers=auth), 200)
    assert s["finalized_students"] == 2 and s["questions"] == []  # no questions were extracted in this seed
    assert client.get(f"/api/exams/{exams[0]['id']}/outcome-summary", headers=auth).status_code == 404
