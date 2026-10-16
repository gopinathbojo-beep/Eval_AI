"""Tests for ADEM's Document Structure Parser, Segmentation, and OCR Recovery."""
import pytest
from dataclasses import dataclass
from typing import Any
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
    """Verify Q7 with content bullets 1) and 2) is grouped into a single Q7(a) answer."""
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

    # Should produce exactly ONE answer record for Q7(a)
    assert len(res) == 1
    a = res[0]
    assert a.normalized_number == "7(a)"
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
        t = db.query(Teacher).filter_by(email="rao@school.org").first() or db.query(Teacher).first()
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
        t = db.query(Teacher).filter_by(email="rao@school.org").first() or db.query(Teacher).first()
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


def test_duplicate_and_distinct_constant_redirection_q6_to_q10():
    """Verify an answer mislabelled as Q6 is redirected to Q10 when it contains Q10 constants and Q6 was already answered."""
    exam_qs = [
        DummyQuestion("id-6", "6", pos=6, text="Business equipment Rs. 1,25,000 depreciates at R1 = 8% first year and R2 = 10% second year."),
        DummyQuestion("id-10", "10", pos=10, text="Principal P = Rs. 80,000 invested for t = 1.5 years at annual rate R = 10% compounded annually and half-yearly."),
    ]
    page_res = StudentPageResult(
        page_number=2,
        answers=[
            StudentAnswerItem(
                question_number="Q6",
                answer_text="Given: principal = 1,25,000\nFirst year = 8%, Second year = 10%\nA = P(1 - R1/100)(1 - R2/100)",
            ),
        ]
    )
    page_res_p4 = StudentPageResult(
        page_number=4,
        answers=[
            StudentAnswerItem(
                question_number="Q6",
                answer_text="Principal = Rs 80,000\nTime = 1.5 years\nRate of Interest = 10% per annum\nA1 = P(1 + R/100)",
            ),
        ]
    )
    p_info_2 = {"page_number": 2, "ocr_width": 1000, "ocr_height": 1400, "width": 1000, "height": 1400}
    p_info_4 = {"page_number": 4, "ocr_width": 1000, "ocr_height": 1400, "width": 1000, "height": 1400}
    res = segment_student_answers([(p_info_2, page_res), (p_info_4, page_res_p4)], canonical_questions=exam_qs)

    assert len(res) == 2
    assert res[0].normalized_number == "6"
    assert "1,25,000" in res[0].answer_text
    assert res[1].normalized_number == "10"
    assert "80,000" in res[1].answer_text


def test_misread_digit_confusion_q8_to_q9_with_continuation():
    """Verify an answer mislabelled as Q8 is redirected to Q9 based on unique constants (15m, hemisphere), and continuation merges cleanly."""
    exam_qs = [
        DummyQuestion("id-8", "8", pos=8, text="Hollow pipe with outer radius R = 8 cm, inner radius r = 6 cm, height h = 14 cm, volume of metal."),
        DummyQuestion("id-9", "9", pos=9, text="Composite storage silo cylindrical tank connected to hemispherical top, r = 7 m, h = 15 m, painting rate Rs. 45 per m2."),
    ]
    page_res = StudentPageResult(
        page_number=3,
        answers=[
            StudentAnswerItem(
                question_number="8>",
                answer_text="Given: r = 7m, h = 15m, pi = 22/7\nCylinder volume + Hemisphere volume\nTotal Surface Area = 968m2",
            ),
            StudentAnswerItem(
                question_number="9>",
                answer_text="Rate = Rs 45 per m2\nCost = 968 x 45 = 44370",
            ),
        ]
    )
    p_info = {"page_number": 3, "ocr_width": 1000, "ocr_height": 1400, "width": 1000, "height": 1400}
    res = segment_student_answers([(p_info, page_res)], canonical_questions=exam_qs)

    assert len(res) == 1
    assert res[0].normalized_number == "9"
    assert "Hemisphere volume" in res[0].answer_text
    assert "Rate = Rs 45 per m2" in res[0].answer_text


def test_swallowed_subpart_split_q7_and_q8():
    """Verify that when a sub-part question (Q7 with a, b, c) swallows the next question (Q8)

    because the vision model misread handwritten '8)' as 'd)', the dynamic phrase extractor
    and boundary splitter cleanly divide them into distinct Q7 and Q8 answers.
    """
    exam_qs = [
        DummyQuestion(
            "id-7", "7", pos=7,
            text='Reading Comprehension:\n\nRead the short passage and answer the questions:\n\n"Trees are essential for maintaining life on Earth. They absorb harmful gases like carbon dioxide and release oxygen. Trees also prevent soil erosion."\n\n(a) Mention two environmental benefits of trees.\n(b) What is the consequence of cutting down trees indiscriminately?\n(c) Find a word that means "absolutely necessary".'
        ),
        DummyQuestion(
            "id-8", "8", pos=8,
            text="Literature:\n\nWhy did Jody want to bring the fawn home in This is Jody's Fawn? How did he persuade his father?"
        ),
    ]

    swallowed_text = (
        "7)\n"
        "(a) Two environmental benefits of trees are:\n"
        "1) They absorb carbon dioxide and release oxygen.\n"
        "2) They prevent soil erosion.\n"
        "(b) Cutting down trees indiscriminately causes environmental imbalance.\n"
        "c) The word meaning 'absolutely necessary' is essential.\n\n"
        "d) This is Jody's fawn\n"
        "Jody wanted to bring the fawn home because his mother had been killed after providing her milk to save Jody's father, "
        "Penny Baxter, from a snakebite. Jody felt that the young fawn would be helpless without its mother. "
        "He persuaded his father by explaining that it was their responsibility to care for the fawn since they had taken away its mother."
    )

    page_res = StudentPageResult(
        page_number=2,
        answers=[
            StudentAnswerItem(
                question_number="7)",
                raw_question_label="7)",
                answer_text=swallowed_text,
            ),
        ]
    )
    p_info = {"page_number": 2, "ocr_width": 1000, "ocr_height": 1400, "width": 1000, "height": 1400}
    res = segment_student_answers([(p_info, page_res)], canonical_questions=exam_qs)

    assert len(res) == 2, f"Expected 2 answers, got {len(res)}"
    assert res[0].normalized_number == "7"
    assert "Two environmental benefits of trees" in res[0].answer_text
    assert "essential" in res[0].answer_text
    assert "Jody" not in res[0].answer_text

    assert res[1].normalized_number == "8"
    assert "This is Jody's fawn" in res[1].answer_text
    assert "Penny Baxter" in res[1].answer_text


def test_doc_structure_subquestions_restart_creates_q10():
    """Verify that when subquestions restart with (a) after (c), they form Question 10 instead of being merged into Q9."""
    p1_res = QuestionPageResult(
        page_number=1,
        questions=[
            QuestionItem(
                raw_question_number="Q9",
                question_text="Corrosion & Chemical Properties:\n(a) What is rusting of iron? Write the chemical equation for the rusting process. (2 marks)",
                marks=5.0,
            ),
        ]
    )
    p2_res = QuestionPageResult(
        page_number=2,
        questions=[
            QuestionItem(
                raw_question_number="(b)",
                question_text="Explain why copper vessels develop a greenish coating when exposed to moist air over time.",
                marks=2.0,
            ),
            QuestionItem(
                raw_question_number="(c)",
                question_text="List two methods used to prevent the corrosion of metals.",
                marks=1.0,
            ),
            QuestionItem(
                raw_question_number="(a)",
                question_text="Why are plastics widely used in daily life despite their harmful impact on the environment?",
                marks=2.0,
            ),
            QuestionItem(
                raw_question_number="(b)",
                question_text="Differentiate between biodegradable and non-biodegradable substances with suitable examples.",
                marks=2.0,
            ),
            QuestionItem(
                raw_question_number="(c)",
                question_text="State the '5R Principle' recommended for reducing the environmental hazards caused by plastic waste.",
                marks=1.0,
            ),
        ]
    )
    p1_info = {"page_number": 1, "page_text": "SECTION C: LONG ANSWER (2 questions x 5 marks = 10 Marks)\nQ9. Corrosion & Chemical Properties:\n(a) What is rusting of iron?"}
    p2_info = {"page_number": 2, "page_text": "(b) Explain why copper vessels...\n(c) List two methods...\nQ10. Polymerization & Environmental Impact:\n(a) Why are plastics widely used...\n(b) Differentiate between...\n(c) State the '5R Principle'..."}

    doc = parse_question_paper_structure([(p1_info, p1_res), (p2_info, p2_res)])

    assert len(doc.questions) == 2, f"Expected 2 questions (Q9, Q10), got {len(doc.questions)}"
    q9 = doc.questions[0]
    q10 = doc.questions[1]

    assert q9.normalized_number == "9"
    assert "What is rusting of iron" in q9.question_text
    assert "Explain why copper vessels" in q9.question_text
    assert "List two methods" in q9.question_text
    assert "plastics" not in q9.question_text

    assert q10.normalized_number == "10"
    assert "Polymerization & Environmental Impact" in q10.question_text
    assert "Why are plastics widely used" in q10.question_text
    assert "biodegradable" in q10.question_text
    assert "5R Principle" in q10.question_text


def test_answer_key_numbered_step_not_duplicate_q1():
    """Verify that a calculation step labeled '1.' on page 4 does not produce a duplicate Question 1 answer key."""
    exam_qs = [
        DummyQuestion("q1", "1", pos=1, text="Force & Pressure: Define atmospheric pressure"),
        DummyQuestion("q9", "9", pos=9, text="Wave Motion: Calculate depth and frequency"),
        DummyQuestion("q10", "10", pos=10, text="Human Eye: Describe eye anatomy"),
    ]
    p1_res = AnswerKeyPageResult(
        page_number=1,
        answers=[
            AnswerKeyItem(
                question_number="Q1",
                answer_text="Atmospheric Pressure: The force per unit area exerted on a surface by the weight of air.",
                marks=2.0,
                criteria=["1 Mark: definition", "1 Mark: SI unit"],
            )
        ]
    )
    p3_res = AnswerKeyPageResult(
        page_number=3,
        answers=[
            AnswerKeyItem(
                question_number="Q9",
                answer_text="Sonar Seabed Depth Computation: d = 1800 meters.\nOscillation Parameters:",
                marks=2.0,
            )
        ]
    )
    p4_res = AnswerKeyPageResult(
        page_number=4,
        answers=[
            AnswerKeyItem(
                question_number="Q10",
                answer_text="Eye Components: Cornea & Lens, Iris & Pupil, Retina & Optic Nerve.",
                marks=5.0,
                criteria=["3 Marks: eye components", "2 Marks: vision defects"],
            ),
            AnswerKeyItem(
                question_number="1",
                answer_text="Frequency: f = 1200 / 15 = 80 Hz.\nTime Period: T = 1 / 80 = 0.0125 s.",
                marks=3.0,
                criteria=["2 Marks: echo depth", "1.5 Marks: frequency", "1.5 Marks: time period"],
            ),
        ]
    )

    page_results = [
        ({"page_number": 1, "page_text": "Q1. Atmospheric Pressure"}, p1_res),
        ({"page_number": 3, "page_text": "Q9. Wave Motion\nAnswer:\nSonar Seabed Depth Computation"}, p3_res),
        ({"page_number": 4, "page_text": "1. Frequency: 80 Hz\n2. Time Period: 0.0125 s\nQ10. Eye Components"}, p4_res),
    ]

    keys = segment_answer_keys(page_results, canonical_questions=exam_qs)

    norm_nums = [k.normalized_number for k in keys]
    assert norm_nums.count("1") == 1, f"Expected exactly one Q1 answer key, got: {norm_nums}"
    assert "9" in norm_nums
    assert "10" in norm_nums

    q9_key = next(k for k in keys if k.normalized_number == "9")
    assert "Frequency" in q9_key.answer_text
    assert q9_key.marks == 5.0


def test_physics_student_answers_with_cross_page_continuations():
    """Verify 4-page Physics student answer sheet with 'Q1, topic :' format and cross-page continuations."""
    from app.services.student_segmentation import segment_student_answers

    @dataclass
    class DummyOCRBlock:
        question_number: str | None
        answer_text: str
        bbox: Any = None
        ocr_confidence: float = 0.95

    @dataclass
    class DummyPage:
        answers: list[DummyOCRBlock]

    @dataclass
    class DummyCanonicalQ:
        id: str
        display_number: str
        normalized_number: str
        question_text: str

    canonical = [
        DummyCanonicalQ(f"q{i}", f"Q{i}", str(i), f"Question {i} topic") for i in range(1, 11)
    ]

    p1 = DummyPage([
        DummyOCRBlock("Q1, force & pressure :", "a) define atmospheric pressure... SI unit: Pascal(Pa)\nb, Explain why sharp cutting edge tools exert higher pressure"),
        DummyOCRBlock("Q2, Sound wave Terminology :", "a, Amplitude and its relationship... b, Frequency and its SI unit..."),
    ])
    p2 = DummyPage([
        DummyOCRBlock("Q3, Friction Types :", "Increasing order: Rolling friction < sliding < static\nInterlocking: ...\nLubricants: ..."),
        DummyOCRBlock("Q4, Chemical Effects of Electric current.", "Electroplating: The process... Electrodes: Conducting plates..."),
    ])
    p3 = DummyPage([
        DummyOCRBlock(None, "For coating iron with copper:\nElectrolyte : copper sulphate (CuSO4) solution.\ncathode : iron object\nAnode : copper plate"),
        DummyOCRBlock("Q5, optics & Reflection :", "a, state the two fundamental laws of reflection...\nb, If a ray of light strikes a plane mirror..."),
        DummyOCRBlock("Q6, Electrostatics & Natural phenomena :", "a, Differentiate btw a conductor and an insulator based on free electron mobility."),
    ])
    p4 = DummyPage([
        DummyOCRBlock(None, "conductor | insulator\nfree electrons can move easily | Electrons cannot move freely.\nExample: copper | Example: Rubber\nb, Explain the working mechanism of an electroscope..."),
        DummyOCRBlock("Q7, Acoustics & noise pollution :", "a, difference btw audible & infrasonic... 20 Hz to 20,000 Hz"),
    ])

    physics_pages = [
        ({"page_number": 1}, p1),
        ({"page_number": 2}, p2),
        ({"page_number": 3}, p3),
        ({"page_number": 4}, p4),
    ]

    answers = segment_student_answers(physics_pages, canonical)
    norm_nums = [a.normalized_number for a in answers]
    assert norm_nums == ["1", "2", "3", "4", "5", "6", "7"], f"Unexpected segmented numbers: {norm_nums}"

    # Q4 continued across page 2 and page 3
    q4 = next(a for a in answers if a.normalized_number == "4")
    assert "copper sulphate" in q4.answer_text
    assert "Electroplating" in q4.answer_text

    # Q6 continued across page 3 and page 4
    q6 = next(a for a in answers if a.normalized_number == "6")
    assert "conductor | insulator" in q6.answer_text
    assert "Differentiate" in q6.answer_text


def test_maths_student_answers_with_skipped_questions():
    """Verify 4-page Mathematics student answer sheet with angle-bracket format and non-consecutive questions."""
    from app.services.student_segmentation import segment_student_answers

    @dataclass
    class DummyOCRBlock:
        question_number: str | None
        answer_text: str
        bbox: Any = None
        ocr_confidence: float = 0.95

    @dataclass
    class DummyPage:
        answers: list[DummyOCRBlock]

    @dataclass
    class DummyCanonicalQ:
        id: str
        display_number: str
        normalized_number: str
        question_text: str

    canonical = [
        DummyCanonicalQ("q1", "Q1", "1", "Exponents & Powers ((2/3)^-2 * (3/4)^-3) / (8/9)^-2"),
        DummyCanonicalQ("q2", "Q2", "2", "Algebraic Identities x + 1/x = 6"),
        DummyCanonicalQ("q3", "Q3", "3", "Direct & Inverse Variations 12 workers, 20 days, 8 hours/day"),
        DummyCanonicalQ("q4", "Q4", "4", "Factorisation 16x^4 - 81y^4"),
        DummyCanonicalQ("q5", "Q5", "5", "Mensuration Trapezium a=12m, b=8m, h=4m, length=250m"),
        DummyCanonicalQ("q6", "Q6", "6", "Comparing Quantities Principal Rs 1,25,000, Rate 8%, 10% depreciation"),
        DummyCanonicalQ("q7", "Q7", "7", "Algebraic Expansion [(3x+4y)^2 - (3x-4y)^2] + (3x-4y)(3x+4y)"),
        DummyCanonicalQ("q8", "Q8", "8", "Solid Geometry Hollow Cylinder R=8cm, r=6cm, h=14cm"),
        DummyCanonicalQ("q9", "Q9", "9", "Multi-Shape Mensuration radius 7m, cylinder height 15m, cost Rs 45/m2"),
        DummyCanonicalQ("q10", "Q10", "10", "Advanced Financial Mathematics Compound Interest Rs 80,000, 10% p.a., 1.5 years"),
    ]

    m_p1 = DummyPage([
        DummyOCRBlock("1>", "[ (2/3)^-2 x (3/4)^-3 ] ÷ (8/9)^-2 = 1024/243"),
        DummyOCRBlock("2>", "given: x + 1/x = 6 ... x^2 + 1/x^2 = 34"),
    ])
    m_p2 = DummyPage([
        DummyOCRBlock("3>", "given: workers = 12, Days = 20... x = 20 days"),
        DummyOCRBlock("4>", "given 16x^4 - 81y^4 = (2x - 3y)(2x + 3y)(4x^2 + 9y^2)"),
        DummyOCRBlock("6>", "Given: principle = 1,25,000, first year = 8%, second year = 10%"),
    ])
    m_p3 = DummyPage([
        DummyOCRBlock("7>", "given: (3x+4y)^2 - (3x-4y)^2 + (3x-4y)(3x+4y) = 9x^2 + 48xy - 16y^2"),
        DummyOCRBlock("9>", "r = 7m, h = 15m\na> V = pi r^2 h + 2/3 pi r^3 = 3028.67 m^3\nb> Total Surface Area: 968 m^2\nc> Rate = Rs 45 per m2 -> Cost = 44370"),
    ])
    m_p4 = DummyPage([
        DummyOCRBlock("10>", "Principal = Rs 80,000, Time = 1.5 years\na> A1 = 92,400, CI1 = 12,400"),
    ])

    maths_pages = [
        ({"page_number": 1}, m_p1),
        ({"page_number": 2}, m_p2),
        ({"page_number": 3}, m_p3),
        ({"page_number": 4}, m_p4),
    ]

    answers = segment_student_answers(maths_pages, canonical)
    norm_nums = [a.normalized_number for a in answers]
    assert norm_nums == ["1", "2", "3", "4", "6", "7", "9", "10"], f"Unexpected segmented numbers: {norm_nums}"

    # Confirm Q9 includes all subparts a>, b>, c>
    q9 = next(a for a in answers if a.normalized_number == "9")
    assert "3028.67" in q9.answer_text
    assert "968" in q9.answer_text
    assert "44370" in q9.answer_text


def test_answer_key_subparts_consolidated_into_parent_question():
    """Verify that when the answer key contains subparts (e.g. Q8(a), Q8(b), Q9(a))
    but the question paper only defines parent questions (8, 9), the subparts are
    cleanly consolidated into parent questions with combined text, criteria, and marks,
    producing no orphan subpart rows.
    """
    canonical = [
        DummyQuestion("q-8", "8", pos=8, text="Solid Geometry hollow cylinder pipe."),
        DummyQuestion("q-9", "9", pos=9, text="Composite storage silo."),
    ]
    canonical[0].max_marks = 3.0
    canonical[1].max_marks = 5.0

    p_info = {"page_number": 5, "page_text": ""}
    page_res = AnswerKeyPageResult(
        page_number=5,
        answers=[
            AnswerKeyItem(
                question_number="Q8(a)",
                answer_text="Volume of Metal: V = 22/7 x 28 x 14 = 1232 cm3",
                marks=2.0,
                criteria=["Volume computation formula and exact value (1232 cm3)."],
            ),
            AnswerKeyItem(
                question_number="Q8(b)",
                answer_text="Total Surface Area (TSA): TSA = 704 + 528 + 176 = 1408 cm2",
                marks=1.0,
                criteria=["Total Surface Area calculation (1408 cm2)."],
            ),
            AnswerKeyItem(
                question_number="Q9(a)",
                answer_text="Total Volume: V = 2310 + 718.67 = 3028.67 m3",
                marks=5.0,
                criteria=["Individual volume computations and total volume."],
            ),
        ]
    )

    keys = segment_answer_keys([(p_info, page_res)], canonical_questions=canonical)
    assert len(keys) == 2, f"Expected 2 parent keys, got {len(keys)}: {[k.normalized_number for k in keys]}"

    k8 = next(k for k in keys if k.normalized_number == "8")
    assert k8.raw_question_number == "Q8"
    assert "1232 cm3" in k8.answer_text
    assert "1408 cm2" in k8.answer_text
    assert len(k8.criteria) == 2
    assert k8.marks == 3.0

    k9 = next(k for k in keys if k.normalized_number == "9")
    assert k9.raw_question_number == "Q9"
    assert "3028.67 m3" in k9.answer_text
    assert k9.marks == 5.0


def test_section_c_not_swallowed_in_q8():
    """Verify Section C heading and instructions appearing between Q8 and Q9 are not included in Q8."""
    raw_text = (
        "SECTION B: MEDIUM ANSWER QUESTIONS & EQUATIONS\n"
        "(4 questions x 3 marks = 12 Marks)\n"
        "Q8. Flame & Combustion:\n"
        "Draw a neat labeled diagram showing the three distinct zones of a candle flame. Identify which zone has the highest temperature and explain why.\n"
        "SECTION C: LONG ANSWER & DETAILED QUESTIONS\n"
        "(2 questions x 5 marks = 10 Marks)\n"
        "Q9. Corrosion & Chemical Properties:\n"
        "(a) What is rusting of iron? Write the chemical equation for the rusting process. (2 marks)"
    )
    page_res = QuestionPageResult(
        page_number=1,
        questions=[QuestionItem(raw_question_number=None, question_text=raw_text)],
    )
    p_info = {"page_number": 1, "ocr_width": 1000, "ocr_height": 1400, "width": 1000, "height": 1400}
    doc = parse_question_paper_structure([(p_info, page_res)])

    q8 = next(q for q in doc.questions if q.display_number == "8")
    assert "SECTION C" not in q8.question_text
    assert "10 Marks" not in q8.question_text
    assert "Draw a neat labeled diagram" in q8.question_text
    assert q8.max_marks == 3.0
    assert "SECTION B" in (q8.section or "")

    q9 = next(q for q in doc.questions if q.display_number in ("9", "9(a)"))
    assert "SECTION C" in (q9.section or "")
    assert q9.max_marks == 5.0


def test_redundant_full_page_dump_deduplication():
    """Verify unnumbered full-page raw dump does not duplicate questions when explicit questions exist."""
    mega_text = (
        "CLASS 8 CHEMISTRY\n"
        "Time Allowed: 1 Hour\n"
        "Maximum Marks: 30\n"
        "SECTION B: MEDIUM ANSWER QUESTIONS\n"
        "(4 questions x 3 marks = 12 Marks)\n"
        "Q7. Metals reaction with acid\n"
        "Q8. Flame & Combustion:\n"
        "Draw a neat labeled diagram showing the three distinct zones of a candle flame.\n"
        "SECTION C: LONG ANSWER & DETAILED QUESTIONS\n"
        "(2 questions x 5 marks = 10 Marks)\n"
        "Q9. Rusting of iron"
    )
    page_res = QuestionPageResult(
        page_number=1,
        questions=[
            QuestionItem(raw_question_number=None, question_text=mega_text),
            QuestionItem(raw_question_number="Q7", question_text="Metals reaction with acid", marks=3.0, section="SECTION B"),
            QuestionItem(
                raw_question_number="Q8",
                question_text="Flame & Combustion:\nDraw a neat labeled diagram showing the three distinct zones of a candle flame.",
                marks=3.0,
                section="SECTION B",
            ),
            QuestionItem(raw_question_number="Q9", question_text="Rusting of iron", marks=5.0, section="SECTION C"),
        ],
    )
    p_info = {"page_number": 1, "ocr_width": 1000, "ocr_height": 1400, "width": 1000, "height": 1400}
    doc = parse_question_paper_structure([(p_info, page_res)])

    nums = [q.display_number for q in doc.questions]
    assert nums == ["7", "8", "9"]

    q8 = next(q for q in doc.questions if q.display_number == "8")
    assert q8.question_text.count("Flame & Combustion") == 1
    assert "SECTION C" not in q8.question_text
    assert q8.max_marks == 3.0





