"""Tests for ADEM's Document Structure Parser, Segmentation, and OCR Recovery."""
import pytest
from app.ocr.schemas import QuestionPageResult, QuestionItem, StudentPageResult, StudentAnswerItem, AnswerKeyPageResult, AnswerKeyItem
from app.services.doc_structure import (
    parse_question_paper_structure,
    extract_section_marks_rule,
    extract_exam_total_marks,
    is_heading_or_title,
    is_instruction,
    is_table_block,
)
from app.services.student_segmentation import segment_student_answers
from app.services.key_segmentation import segment_answer_keys
from app.services.ocr_recovery import find_recovery_candidates
from app.services.mapping import map_label, MAPPED, NEEDS_REVIEW, UNMAPPED
from app.services.numbering import normalize_question_number


class DummyQuestion:
    def __init__(self, qid: str, norm: str, pos: int = 1, text: str = ""):
        self.id = qid
        self.normalized_number = norm
        self.position = pos
        self.question_text = text
        self.display_number = norm


def test_section_marks_rule_extraction():
    assert extract_section_marks_rule("4 questions × 2 marks = 8 marks") == 2.0
    assert extract_section_marks_rule("4 x 2 = 8 marks") == 2.0
    assert extract_section_marks_rule("Each question carries 3 marks") == 3.0
    assert extract_section_marks_rule("Answer all questions (2 marks each)") == 2.0
    assert extract_exam_total_marks("Maximum Marks: 30") == 30.0
    assert extract_exam_total_marks("Total: 45 Marks") == 45.0


def test_headings_and_instructions_identified():
    assert is_heading_or_title("SECTION A")
    assert is_heading_or_title("Reading Comprehension")
    assert is_heading_or_title("Part I - Grammar")
    assert not is_heading_or_title("What is the process of photosynthesis?")

    assert is_instruction("Read the short passage and answer the questions that follow:")
    assert is_instruction("Fill in the blanks with suitable prepositions:")
    assert is_instruction("Answer any four of the following questions:")


def test_table_block_detected():
    table = "Line | Incorrect Word | Correct Word\n1 | was | were\n2 | has | have"
    assert is_table_block(table)


def test_doc_structure_parser_headings_and_section_marks():
    """Verify headings/instructions do not become questions and section marks are inherited."""
    page_res = QuestionPageResult(
        page_number=1,
        questions=[
            QuestionItem(raw_question_number=None, question_text="SECTION A\n4 questions × 2 marks = 8 marks"),
            QuestionItem(raw_question_number=None, question_text="Read the short passage and answer the questions that follow:"),
            QuestionItem(raw_question_number="Q1", question_text="Define osmosis.", marks=None),
            QuestionItem(raw_question_number="Q2", question_text="Explain diffusion.", marks=None),
            QuestionItem(raw_question_number="Q3", question_text="Fill in the blanks:\n(a) since\n(b) otherwise", marks=None),
            QuestionItem(raw_question_number="Q6", question_text="Error correction:\nLine | Incorrect Word | Correct Word\n1 | go | went", marks=None),
        ]
    )
    p_info = {"page_number": 1, "ocr_width": 1000, "ocr_height": 1400, "width": 1000, "height": 1400}
    doc = parse_question_paper_structure([(p_info, page_res)])

    # Only Q1, Q2, Q3, Q6 should be questions (headings/instructions are discarded from question list)
    nums = [q.display_number for q in doc.questions]
    assert nums == ["1", "2", "3", "6"]

    # All questions inherited 2 marks each from SECTION A rule
    for q in doc.questions:
        assert q.max_marks == 2.0

    # Q3 did NOT invent Q3(a) or Q3(b)
    q3 = next(q for q in doc.questions if q.display_number == "3")
    assert "(a) since" in q3.question_text
    assert q3.normalized_number == "3"

    # Q6 table preserved
    q6 = next(q for q in doc.questions if q.display_number == "6")
    assert "Line | Incorrect Word" in q6.question_text


def test_student_answer_segmentation_bullets():
    """Verify Q7 with content bullets 1) and 2) is grouped into a single answer to question 7."""
    page_res = StudentPageResult(
        page_number=1,
        answers=[
            StudentAnswerItem(question_number="Q7(a)", answer_text="Two environmental benefits:"),
            StudentAnswerItem(question_number="1)", answer_text="They absorb carbon dioxide from atmosphere."),
            StudentAnswerItem(question_number="2)", answer_text="They prevent soil erosion during heavy rains."),
        ]
    )
    p_info = {"page_number": 1, "ocr_width": 1000, "ocr_height": 1400, "width": 1000, "height": 1400}
    res = segment_student_answers([(p_info, page_res)])

    # Should produce exactly ONE answer record, for question 7 (part (a) kept in its text)
    assert len(res) == 1
    a = res[0]
    assert a.normalized_number == "7" and a.answer_text.startswith("Q7(a)")
    assert "Two environmental benefits" in a.answer_text
    assert "1) They absorb carbon dioxide" in a.answer_text
    assert "2) They prevent soil erosion" in a.answer_text


def test_ocr_recovery_q17_and_q27():
    """Verify Q17 is recovered as candidate Q1 and Q27 as candidate Q2."""
    exam_qs = [
        DummyQuestion("id-1", "1", pos=1, text="Define osmosis"),
        DummyQuestion("id-2", "2", pos=2, text="Explain diffusion"),
        DummyQuestion("id-3", "3", pos=3, text="Photosynthesis process"),
    ]

    # For handwritten "Q17" at answer position 1
    cands17 = find_recovery_candidates("Q17", "Osmosis is the passage of water", exam_qs, answer_index=1, total_answers=3)
    assert len(cands17) >= 1
    assert cands17[0].normalized_number == "1"
    assert cands17[0].score >= 0.80

    # For handwritten "Q27" at answer position 2
    cands27 = find_recovery_candidates("Q27", "Diffusion occurs down concentration gradient", exam_qs, answer_index=2, total_answers=3)
    assert len(cands27) >= 1
    assert cands27[0].normalized_number == "2"
    assert cands27[0].score >= 0.80

    # Mapping with recovery
    r17 = map_label("Q17", exam_qs, answer_text="Osmosis passage of water", answer_position=1)
    assert r17.status == NEEDS_REVIEW
    assert "id-1" in r17.candidates


def test_answer_key_multipage_continuation():
    """Verify answer key spanning page 1 and page 2 is merged."""
    p1 = AnswerKeyPageResult(
        page_number=1,
        answers=[AnswerKeyItem(question_number="Q5", answer_text="First part of photosynthesis explanation.")]
    )
    p2 = AnswerKeyPageResult(
        page_number=2,
        answers=[AnswerKeyItem(question_number=None, answer_text="Second part continues on next page.")]
    )
    p1_info = {"page_number": 1, "ocr_width": 1000, "ocr_height": 1400}
    p2_info = {"page_number": 2, "ocr_width": 1000, "ocr_height": 1400}

    keys = segment_answer_keys([(p1_info, p1), (p2_info, p2)])
    assert len(keys) == 1
    assert keys[0].normalized_number == "5"
    assert "First part" in keys[0].answer_text
    assert "Second part continues" in keys[0].answer_text


def test_answer_key_split_and_merge_api(client, auth):
    """Test splitting and merging answer keys via the API."""
    c, h = client, auth
    from app.database import SessionLocal
    from app.models import AnswerKey, Exam, ExamQuestion, SchoolClass, Subject, Teacher
    db = SessionLocal()
    try:
        t = db.query(Teacher).filter_by(email="rao@school.org").one()
        cls = SchoolClass(teacher_id=t.id, name="Class SplitKey")
        sub = Subject(teacher_id=t.id, name="Subject SplitKey")
        db.add_all([cls, sub])
        db.commit()

        exam = Exam(
            teacher_id=t.id, class_id=cls.id, subject_id=sub.id,
            name="Exam SplitKey", academic_year="2026-27", exam_type="Unit",
            total_marks=20, status="ANSWER_KEY_UPLOADED"
        )
        db.add(exam)
        db.commit()

        q1 = ExamQuestion(exam_id=exam.id, display_number="1", normalized_number="1",
                          question_text="Q1 text", max_marks=5.0, position=1)
        q2 = ExamQuestion(exam_id=exam.id, display_number="2", normalized_number="2",
                          question_text="Q2 text", max_marks=5.0, position=2)
        db.add_all([q1, q2])
        db.commit()

        k1 = AnswerKey(
            exam_id=exam.id, raw_question_number="1", normalized_number="1",
            exam_question_id=q1.id, answer_text="Part A text\nPart B text",
            raw_ocr_text="Part A text\nPart B text", marks=5.0, mapping_status="MAPPED"
        )
        db.add(k1)
        db.commit()
        k1_id = k1.id
        eid = exam.id
    finally:
        db.close()

    # Split k1 at split index
    at_char = len("Part A text\n")
    r_split = c.post(f"/api/answer-keys/{k1_id}/split", headers=h, json={
        "at_char": at_char, "new_label": "2", "new_marks": 5.0
    })
    assert r_split.status_code == 200, r_split.text
    split_data = r_split.json()
    assert "Part A text" in split_data["original"]["answer_text"]
    assert "Part B text" in split_data["new"]["answer_text"]
    assert split_data["new"]["raw_question_number"] == "2"

    # Merge them back
    k_orig_id = split_data["original"]["id"]
    k_new_id = split_data["new"]["id"]
    r_merge = c.post(f"/api/answer-keys/{k_orig_id}/merge", headers=h, json={
        "other_id": k_new_id
    })
    assert r_merge.status_code == 200, r_merge.text
    merged = r_merge.json()
    assert "Part A text" in merged["answer_text"]
    assert "Part B text" in merged["answer_text"]


def test_student_answer_split_merge_and_suggestion_api(client, auth):
    """Test splitting, merging, and accepting suggestions on student answers via API."""
    c, h = client, auth
    from app.database import SessionLocal
    from app.models import AnswerSheetDocument, Evaluation, Exam, ExamQuestion, SchoolClass, Student, StudentAnswer, Subject, Teacher
    db = SessionLocal()
    try:
        t = db.query(Teacher).filter_by(email="rao@school.org").one()
        cls = SchoolClass(teacher_id=t.id, name="Class EvalSplit")
        sub = Subject(teacher_id=t.id, name="Subject EvalSplit")
        db.add_all([cls, sub])
        db.commit()

        exam = Exam(
            teacher_id=t.id, class_id=cls.id, subject_id=sub.id,
            name="Exam EvalSplit", academic_year="2026-27", exam_type="Unit",
            total_marks=20, status="READY_FOR_EVALUATION"
        )
        db.add(exam)
        db.commit()

        q1 = ExamQuestion(exam_id=exam.id, display_number="1", normalized_number="1",
                          question_text="Q1 text", max_marks=5.0, position=1, verification_status="VERIFIED")
        q2 = ExamQuestion(exam_id=exam.id, display_number="2", normalized_number="2",
                          question_text="Q2 text", max_marks=5.0, position=2, verification_status="VERIFIED")
        db.add_all([q1, q2])
        db.commit()

        stu = Student(class_id=cls.id, name="Student Test", roll_number="101")
        db.add(stu)
        db.commit()

        ans_doc = AnswerSheetDocument(
            exam_id=exam.id, student_id=stu.id,
            original_filename="sheet.pdf", original_file="sheet.pdf",
            mime_type="application/pdf", file_size=1024, status="READY"
        )
        db.add(ans_doc)
        db.commit()

        ev = Evaluation(exam_id=exam.id, student_id=stu.id, answer_sheet_id=ans_doc.id, status="MAPPING_REVIEW")
        db.add(ev)
        db.commit()

        ans1 = StudentAnswer(
            evaluation_id=ev.id,
            raw_question_number="17",
            normalized_number="17",
            answer_text="First answer text\nSecond answer text",
            raw_ocr_text="First answer text\nSecond answer text",
            status="NEEDS_REVIEW",
            mapping_candidates=[q1.id],
            position=1,
        )
        db.add(ans1)
        db.commit()
        ans1_id = ans1.id
        ev_id = ev.id
        q1_id = q1.id
    finally:
        db.close()

    # 1. Accept suggestion
    r_acc = c.patch(f"/api/evaluations/{ev_id}/mapping/{ans1_id}", headers=h, json={
        "accept_suggestion": True
    })
    assert r_acc.status_code == 200, r_acc.text
    ans_updated = r_acc.json()
    assert ans_updated["status"] == "MAPPED"
    assert ans_updated["exam_question_id"] == q1_id

    # 2. Split answer
    at_char = len("First answer text\n")
    r_split = c.post(f"/api/evaluations/{ev_id}/answers/{ans1_id}/split", headers=h, json={
        "at_char": at_char,
        "new_label": "2"
    })
    assert r_split.status_code == 200, r_split.text
    split_data = r_split.json()
    assert "First answer text" in split_data["original"]["answer_text"]
    assert "Second answer text" in split_data["new"]["answer_text"]

    # 3. Merge answers
    a_orig_id = split_data["original"]["id"]
    a_new_id = split_data["new"]["id"]
    r_merge = c.post(f"/api/evaluations/{ev_id}/answers/{a_orig_id}/merge", headers=h, json={
        "other_id": a_new_id
    })
    assert r_merge.status_code == 200, r_merge.text
    merged = r_merge.json()
    assert "First answer text" in merged["answer_text"]
    assert "Second answer text" in merged["answer_text"]


def test_doc_structure_preserves_short_and_unnumbered_questions():
    """Verify short items like '01/02 is missing' or unnumbered questions are never dropped."""
    page_res = QuestionPageResult(
        page_number=1,
        questions=[
            QuestionItem(raw_question_number=None, question_text="01/02 is missing", marks=None),
            QuestionItem(raw_question_number=None, question_text="Define Newton's first law of motion.", marks=2),
        ]
    )
    p_info = {"page_number": 1, "ocr_width": 1000, "ocr_height": 1400, "width": 1000, "height": 1400}
    doc = parse_question_paper_structure([(p_info, page_res)])

    assert len(doc.questions) == 2
    # First question extracted '01/02' -> normalized to '1(2)'
    assert doc.questions[0].display_number in ("1(2)", "01/02")
    assert "missing" in doc.questions[0].question_text

    # Second question was unnumbered -> inferred sequential number 2
    assert doc.questions[1].display_number == "2"
    assert "Newton" in doc.questions[1].question_text
    assert doc.questions[1].max_marks == 2.0
    assert doc.questions[1].verification_status == "NEEDS_REVIEW"


def test_doc_structure_question_continuation_unnumbered():
    """Verify unnumbered blocks continuing an abrupt or dangling sentence are merged properly."""
    page_res = QuestionPageResult(
        page_number=1,
        questions=[
            QuestionItem(raw_question_number="1", question_text="A particle moves along a straight line with constant speed and", marks=None),
            QuestionItem(raw_question_number=None, question_text="experiences zero net external force.", marks=None),
        ]
    )
    p_info = {"page_number": 1, "ocr_width": 1000, "ocr_height": 1400, "width": 1000, "height": 1400}
    doc = parse_question_paper_structure([(p_info, page_res)])

    assert len(doc.questions) == 1
    assert doc.questions[0].display_number == "1"
    assert "constant speed and experiences zero net external force." in doc.questions[0].question_text



