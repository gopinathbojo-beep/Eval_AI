from app.services.school_reports import relative_grades
from app.services.report_templates import normalize
from app.database import SessionLocal
from app.models import AnswerSheetDocument, Evaluation, Exam, SchoolClass, Student, Subject, Teacher
from app.services.school_reports import card_data, RELATIVE_GRADES


def test_ties_share_higher_band_without_splitting_or_input_order_effects():
    scores = {str(i): 100 - i * 2 for i in range(16)}
    scores["2"] = scores["1"]
    assigned = relative_grades(scores)
    assert assigned["1"] == assigned["2"] == "A-1"
    assert relative_grades(dict(reversed(list(scores.items())))) == assigned
    assert set(relative_grades({"x": 0, "y": 32.999}).values()) == {"E"}
    assert relative_grades({}) == {}


def test_legacy_templates_drop_k_level_and_outcomes():
    template = normalize("report", {"columns": ["qno", "k_level", "max", "obtained"], "sections": ["header", "outcomes", "marks_table"]})
    assert "k_level" not in [c["id"] for c in template["columns"]]
    assert "outcomes" not in [s["id"] for s in template["sections"]]


def test_term_grades_use_whole_class_and_require_all_subjects_to_pass(client):
    with SessionLocal() as db:
        teacher = db.query(Teacher).filter_by(email="rao@school.org").one()
        cls = SchoolClass(teacher_id=teacher.id, name="Relative grade cohort")
        db.add(cls)
        db.flush()
        students = [Student(class_id=cls.id, name=f"Candidate {i}", roll_number=str(i)) for i in range(10)]
        db.add_all(students)
        db.flush()
        for subject_index in range(2):
            subject = Subject(teacher_id=teacher.id, name=f"Relative Subject {subject_index}")
            db.add(subject)
            db.flush()
            exam = Exam(teacher_id=teacher.id, class_id=cls.id, subject_id=subject.id, name=subject.name,
                        academic_year="2026-27", exam_type="Relative Term", total_marks=100, status="FINALIZED")
            db.add(exam)
            db.flush()
            for i, student in enumerate(students):
                if subject_index == 1 and i == 9:
                    continue
                marks = 100 - i * 8 if i < 8 else 0 if subject_index == 1 else 100
                document = AnswerSheetDocument(exam_id=exam.id, student_id=student.id, original_filename="test.pdf",
                                              original_file="test.pdf", mime_type="application/pdf", file_size=1, status="READY")
                db.add(document)
                db.flush()
                db.add(Evaluation(exam_id=exam.id, student_id=student.id, answer_sheet_id=document.id,
                                  status="FINALIZED", total_marks=marks, maximum_marks=100, percentage=marks))
        db.commit()
        cards, _ = card_data(db, teacher, cls.id, "2026-27", "Relative Term")
        assert [c["overall_grade"] for c in cards[:8]] == list(RELATIVE_GRADES)
        assert cards[8]["overall_grade"] == "E"  # 50% overall, but failed one subject
        assert cards[9]["overall_grade"] == "–" and cards[9]["rank"] is None
        single, _ = card_data(db, teacher, cls.id, "2026-27", "Relative Term", students[5].id)
        assert single[0]["overall_grade"] == cards[5]["overall_grade"]
        assert single[0]["subjects"] == cards[5]["subjects"]
