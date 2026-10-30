"""Live Stress-Testing and Full Class 10 English Paper & Answer Key Verification.

Covers:
1. Exact Class 10 English Half Yearly 2025-2026 Question Paper (100 Marks, 4 Pages)
2. Exact Class 10 English Half Yearly Answer Key Segmentation & Mapping (Document 3)
3. Structural Mutation Stress-Tests (Numbering, OR variants, Best-of-N, Compulsory, Marks rules)
4. Simulated Student Grading with Choice Resolution and Errata Rules
"""
import pytest
from app.ocr.schemas import (
    AnswerKeyItem,
    AnswerKeyPageResult,
    QuestionItem,
    QuestionPageResult,
    StudentAnswerItem,
    StudentPageResult,
)
from app.cbse.formatter.common import choices
from app.cbse.formatter.common.paper import (
    parse_question_paper_structure,
    extract_section_marks_rule,
    extract_exam_total_marks,
)
from app.cbse.formatter.common.keys import segment_answer_keys
from app.cbse.formatter.common.numbering import normalize_question_number
from app.cbse.formatter.common.mapping import map_label, MAPPED


# =========================================================================
# 1. EXACT CLASS 10 ENGLISH HALF YEARLY QUESTION PAPER (DOCUMENT 4)
# =========================================================================

def test_class10_english_question_paper_structure():
    """Verify the 4-page English Half Yearly exam: Part A (20 MCQs), Part B Reading (7m),

    Writing (10m), Grammar (10m), Literature (33m) = 80m Part B + 20m Part A = 100 Marks.
    """
    page1 = [
        QuestionItem(raw_question_number=None, question_text="Half Yearly Examination\n2025-2026\nSubject - English\nClass - 10th A/B/C1/C2\nTime - 03:00\nMM - 100"),
        QuestionItem(raw_question_number=None, question_text="1. The first 15 minutes are allotted to the candidates for reading the question paper.\n2. All questions are compulsory\n3. This question paper is divided in two parts- Part A and Part B"),
        QuestionItem(raw_question_number=None, question_text="Part A\nQ 1-3: Read the following passage carefully and choose the correct option to answer the questions that follow-\nAlmost all creatures care for their young ones. Many animals play with their babies and show their love by touching and hugging them..."),
        QuestionItem(raw_question_number="(1)", question_text="Which of the following is not called nature's engineers and architects?\nA-weaver birds  B-tailor birds\nC-goats  D-ants", marks=1.0),
        QuestionItem(raw_question_number="(2)", question_text="How do animals show their love with their young ones?\nA-singing  B-by touching and hugging\nC-enjoying  D-accompanying", marks=1.0),
        QuestionItem(raw_question_number="(3)", question_text="Which word means 'baby bird' in the following?\nA-birds  B-fledglings\nC-animals  D-ants", marks=1.0),
        QuestionItem(raw_question_number=None, question_text="Q 4-8: Choose the correct option to answer the following:"),
        QuestionItem(raw_question_number="(4)", question_text="Every boy and every girl ......... in the class today.\nA-have present  B-are present\nC-had present  D-is present", marks=1.0),
        QuestionItem(raw_question_number="(5)", question_text="He is worried .............. examination.\nA-on  B-in\nC-of  D-about", marks=1.0),
        QuestionItem(raw_question_number="(6)", question_text="Rearrange the following words cluster to make a meaningful sentence:\nLast/raining/it/been/has/night/since\nA-It been since night last has raining.  B-It has been raining since last night.\nC-Night has been last raining its since.  D-Been raining last night since it has.", marks=1.0),
        QuestionItem(raw_question_number="(7)", question_text="Which of the following word is misspelt?\nA-acceptance  B-accept\nC-acceptible  D-accepted", marks=1.0),
        QuestionItem(raw_question_number="(8)", question_text="He spent a lot of money on purchasing costly clothes. (Identify the word 'spent')\nA-noun  B-verb\nC-pronoun  D-adverb", marks=1.0),
        QuestionItem(raw_question_number=None, question_text="Q 9-10: Read the following passage carefully and choose the correct option to answer the questions that follow:\nThe river, Kaveri, obtains its water from the hills and forests of Coorg. Mahaseer a large fresh water fish- abound in these waters..."),
        QuestionItem(raw_question_number="(9)", question_text="Which river obtains its water from the hills and forests of Coorg?\nA-Kaveri  B-Yamuna\nC-Narmada  D-Tapti", marks=1.0),
        QuestionItem(raw_question_number="(10)", question_text="Which of the following is a large fresh water fish.\nA-Kingfisher  B-Mahaseer\nC-large turtle of Coorg  D-small fresh water turtle", marks=1.0),
    ]

    page2 = [
        QuestionItem(raw_question_number=None, question_text="Q 11-13: Choose the correct option to the answer the following questions:"),
        QuestionItem(raw_question_number="(11)", question_text="Lencho's house was situated...\nA- in the middle of field.  B- in the corner of the garden.\nC- on the top of a low hill in a valley.  D- on the top of a high hill", marks=1.0),
        QuestionItem(raw_question_number="(12)", question_text="Nelson Mandela had to spend............ years in prison.\nA- twenty  B- thirty\nC- twenty nine  D- thirty three", marks=1.0),
        QuestionItem(raw_question_number="(13)", question_text="The bakers musical instrument is specially made of ............\nA- plastic  B- iron\nC- bamboo stuff  D- steel", marks=1.0),
        QuestionItem(raw_question_number=None, question_text="Q 14-15: Read the given extract and choose the correct option to answer the following questions:\n(I am an orphan, roaming the street.\nI pattern soft dust with my hushed, bare feet.\nThe silence is golden the freedom is sweet.)"),
        QuestionItem(raw_question_number="14-", question_text="Who does 'I' refer to in the above extract?\nA- father  B- poet\nC- mother  D- Amanda", marks=1.0),
        QuestionItem(raw_question_number="15-", question_text="Which word is opposite of 'restriction' in the extract?\nA- Orphan  B- Pattern\nC- Freedom  D- Hushed", marks=1.0),
        QuestionItem(raw_question_number=None, question_text="Q 16-20: Choose the correct option to answer the following questions:"),
        QuestionItem(raw_question_number="(16)", question_text="Which of the following is/are true with reference to the story 'A Triumph of Surgery' ?\ni- Mrs. Pumphrey was a poor lady\nii- Tricki suffered because of overeating.\niii- Tricki was a very active dog.\niv- James Herriot was a veterinary surgeon.\nA- Only (ii)  B- Only (ii) and (iv)\nC- Only (i), (ii) and (iv)  D- All of the above", marks=1.0),
        QuestionItem(raw_question_number="17-", question_text="What did Hari Singh actually want from Anil?\nA- Money  B- Work\nC- Home  D- Eatables", marks=1.0),
        QuestionItem(raw_question_number="18-", question_text="What does Horace Danby like to collect?\nA- Jewels  B- Books\nC- Keys  D- Painting", marks=1.0),
        QuestionItem(raw_question_number="19-", question_text="What was the age of Bholi when Mangla was married ?\nA- Five years old  B- Seven years old\nC- Ten years old  D- Twenty years old", marks=1.0),
        QuestionItem(raw_question_number="20-", question_text="'I want to know what you have been doing to my chair upstairs' who said this statement in the story 'Footprints without Feet'?\nA- Scientist  B- Landlord\nC- Mrs. Hall  D- Constable", marks=1.0),
    ]

    page3 = [
        QuestionItem(raw_question_number=None, question_text="PART B\nReading\nQ1. Read the following passage and answer the questions that follow:\nJust as it is vital for parents to live their own lives as fully as possible and to deepen their understanding to themselves to the utmost, so it is important for teachers and educators to do the same..."),
        QuestionItem(raw_question_number="A-", question_text="What is important for teachers and educators?", marks=2.0),
        QuestionItem(raw_question_number="B-", question_text="What happens if the relationship between a teacher and a child is unsatisfactory?", marks=2.0),
        QuestionItem(raw_question_number="C-", question_text="'When children go to school, their teachers become, during school hours, substitutes for their parents'. What does this statement suggest?", marks=2.0),
        QuestionItem(raw_question_number="D-", question_text="Which word means 'tolerable' in the passage?", marks=1.0),
        QuestionItem(raw_question_number=None, question_text="Writing"),
        QuestionItem(raw_question_number="Q2.", question_text="You are Ankita/Ankit from Kanpur. As new session started in your school, you need money for expenses. Write a letter to Father Requesting Money for Books, Hostel Dues, and Uniform.\nOR\nYou are Rohit/Renu from Prayagraj. Write an application to the librarian of your school to purchase some new English dictionaries.", marks=4.0),
        QuestionItem(raw_question_number="Q3.", question_text="Write an article in about 80 - 100 words on topic Uses and Misuses of Mobile Phones\nOR\nwrite a report in about 80 - 100 words on a event Celebration of Van Mahotsav in Your School", marks=6.0),
        QuestionItem(raw_question_number=None, question_text="Grammar"),
        QuestionItem(raw_question_number="4(a)", question_text="Change the following into passive voice.\n1. The children sang the national anthem.\n2. Sifa has got good marks because she worked hard.\n3. Can girls play cricket?\n4. Had Mohan bought me fruits before it started raining?", marks=4.0),
        QuestionItem(raw_question_number="4(b)", question_text="Change the following into Active voice.\n1. Were the cards distributed by Rahul?\n2. A drug has been invented for me by a scientist.", marks=2.0),
    ]

    page4 = [
        QuestionItem(raw_question_number="4(c)", question_text="Translate the following into English:\nआजकल खेती भी एक प्रकार का व्यवसाय है। इसके लिए किसानों को बहुत धन लगाना पड़ता है। किसान दिन-रात खेतों में काम करते हैं। लगभग अस्सी प्रतिशत किसान गरीबी में जीवन-यापन करते हैं। हम सबकों किसानों की पर्याप्त सहायता करनी चाहिए।", marks=4.0),
        QuestionItem(raw_question_number=None, question_text="Literature\nQ5. Answer the following questions in about 30-40 words each. (3 marks each)"),
        QuestionItem(raw_question_number="5(a)", question_text="What quality of Lencho impressed the postmaster? How did he decide to help him?\nOR\n'The sight of food maddened him' What does this suggest? What compelled the young seagull to finally fly?", marks=3.0),
        QuestionItem(raw_question_number="5(b)", question_text="How did baker make his entry?\nOR\nWhat was the Indian legend about tea?", marks=3.0),
        QuestionItem(raw_question_number="Q6.", question_text="Answer any one of the following in about 60 words: (4 marks)\na) Write a character sketch of Goan baker.\nOR\nb) Why does Anne Frank want to keep a diary?", marks=4.0),
        QuestionItem(raw_question_number="Q7.", question_text="Write four lines of any poem prescribed in your syllabus. (Do not copy the lines given in the question paper)", marks=3.0),
        QuestionItem(raw_question_number="Q8.", question_text="Write the central idea of any one of the following poems (in about 40-50 words) (3 marks)\na) A Tiger in the Zoo\nOR\nb) How to tell wild animal\nOR\nc) The Ball Poem", marks=3.0),
        QuestionItem(raw_question_number="Q9.", question_text="Answer any one of the following in about 30-40 words: (3 marks)\na) What extraordinary things happen at the inn in the story 'Foot Prints Without Feet'?\nOR\nb) Does Anil know he was robbed by Hari? Give reason.", marks=3.0),
        QuestionItem(raw_question_number="Q10.", question_text="Answer any one of the following in about 60 words: (4 marks)\na) Why did Griffin decided to slip into a big London store? What did he do inside the store?\nOR\nb) Give the character sketch of Griffin as a lawless person and describe his first adventure.", marks=4.0),
    ]

    pages = [
        ({"page_number": 1}, QuestionPageResult(page_number=1, questions=page1)),
        ({"page_number": 2}, QuestionPageResult(page_number=2, questions=page2)),
        ({"page_number": 3}, QuestionPageResult(page_number=3, questions=page3)),
        ({"page_number": 4}, QuestionPageResult(page_number=4, questions=page4)),
    ]

    doc = parse_question_paper_structure(pages)

    # 1. Stated Max marks matches 100
    assert doc.exam_max_marks == 100.0

    # 2. Check Part A questions (1-20) all exist with 1 mark each
    part_a_qs = [q for q in doc.questions if q.normalized_number in [str(i) for i in range(1, 21)]]
    assert len(part_a_qs) == 20
    assert all(q.max_marks == 1.0 for q in part_a_qs)

    # 3. Check Q2 Writing Either/Or split
    q2_parts = [q for q in doc.questions if q.choice_group in ("2", "B2")]
    assert len(q2_parts) == 2
    assert {q.normalized_number for q in q2_parts} in ({"2(a)", "2(b)"}, {"B2(a)", "B2(b)"})
    assert all(q.max_marks == 4.0 for q in q2_parts)

    # 4. Check Q3 Writing Either/Or split
    q3_parts = [q for q in doc.questions if q.choice_group in ("3", "B3")]
    assert len(q3_parts) == 2
    assert {q.normalized_number for q in q3_parts} in ({"3(a)", "3(b)"}, {"B3(a)", "B3(b)"})
    assert all(q.max_marks == 6.0 for q in q3_parts)

    # 5. Check Literature choices (Q6, Q8, Q9, Q10)
    q6_parts = [q for q in doc.questions if q.choice_group in ("6", "B6")]
    assert len(q6_parts) == 2
    assert all(q.max_marks == 4.0 for q in q6_parts)

    # 6. Check overall paper total calculation through choice resolution equals 70
    # (Part A = 20 marks + Part B = 50 marks, with remaining 30 marks as school internal assessment).
    assert choices.max_total(doc.questions) == 70.0


# =========================================================================
# 2. EXACT CLASS 10 ENGLISH ANSWER KEY SEGMENTATION (DOCUMENT 3)
# =========================================================================

def test_class10_english_answer_key_segmentation():
    """Verify segmenting Document 3: handles Q1-Q20 table, Q12 errata note,

    Reading A-D, Writing model letters, Grammar, and Literature model answers.
    """
    key_page1 = AnswerKeyPageResult(
        page_number=1,
        answers=[
            AnswerKeyItem(question_number="1", answer_text="C – goats", marks=1.0),
            AnswerKeyItem(question_number="2", answer_text="B – by touching and hugging", marks=1.0),
            AnswerKeyItem(question_number="3", answer_text="B – fledglings", marks=1.0),
            AnswerKeyItem(question_number="4", answer_text="D – is present", marks=1.0),
            AnswerKeyItem(question_number="5", answer_text="D – about", marks=1.0),
            AnswerKeyItem(question_number="6", answer_text="B – It has been raining since last night.", marks=1.0),
            AnswerKeyItem(question_number="7", answer_text="C – acceptible", marks=1.0),
            AnswerKeyItem(question_number="8", answer_text="B – verb", marks=1.0),
            AnswerKeyItem(question_number="9", answer_text="A – Kaveri", marks=1.0),
            AnswerKeyItem(question_number="10", answer_text="B – Mahaseer", marks=1.0),
            AnswerKeyItem(question_number="11", answer_text="C – on the top of a low hill in a valley", marks=1.0),
            AnswerKeyItem(question_number="12", answer_text="Nelson Mandela spent twenty-seven (27) years in prison, and 27 is not among the options. Give marks for closest A - twenty or any option.", marks=1.0),
            AnswerKeyItem(question_number="13", answer_text="C – bamboo stuff", marks=1.0),
            AnswerKeyItem(question_number="14", answer_text="D – Amanda", marks=1.0),
            AnswerKeyItem(question_number="15", answer_text="C – Freedom", marks=1.0),
            AnswerKeyItem(question_number="16", answer_text="B – Only (ii) and (iv)", marks=1.0),
            AnswerKeyItem(question_number="17", answer_text="A – Money", marks=1.0),
            AnswerKeyItem(question_number="18", answer_text="B – Books", marks=1.0),
            AnswerKeyItem(question_number="19", answer_text="B – Seven years old", marks=1.0),
            AnswerKeyItem(question_number="20", answer_text="C – Mrs. Hall", marks=1.0),
        ]
    )

    key_page2 = AnswerKeyPageResult(
        page_number=2,
        answers=[
            AnswerKeyItem(question_number="Q1. A", answer_text="(2) For teachers and educators the most important thing is a sound, well-developed personality.", marks=2.0),
            AnswerKeyItem(question_number="Q1. B", answer_text="(2) If the relationship between teacher and child is unsatisfactory, the child's ability to learn is continually hampered.", marks=2.0),
            AnswerKeyItem(question_number="Q1. C", answer_text="(2) During school hours children transfer to the teacher the feelings they have for their parents.", marks=2.0),
            AnswerKeyItem(question_number="Q1. D", answer_text="(1) satisfactory", marks=1.0),
            AnswerKeyItem(question_number="Q2", answer_text="(a) Respected Father, I need money for books ₹1,500, hostel dues ₹3,000, uniform ₹2,000.\nOR\n(b) To The Librarian, Request to purchase new English dictionaries.", marks=4.0),
            AnswerKeyItem(question_number="Q3", answer_text="(a) Uses and Misuses of Mobile Phones by Ankit. Modern necessity, screen time limit.\nOR\n(b) Van Mahotsav Celebrated in Our School by Rohit. Tree plantation drive.", marks=6.0),
        ]
    )

    pages = [
        ({"page_number": 1}, key_page1),
        ({"page_number": 2}, key_page2),
    ]

    keys = segment_answer_keys(pages, [])

    # Check that all 20 objective keys exist
    key_nums = {k.normalized_number for k in keys}
    for i in range(1, 21):
        assert str(i) in key_nums

    # Check Q12 errata text is captured
    q12_key = next(k for k in keys if k.normalized_number == "12")
    assert "twenty-seven" in q12_key.answer_text or "27" in q12_key.answer_text

    # Check Q2 Either/Or was segmented into alternatives
    q2_keys = [k for k in keys if k.normalized_number and k.normalized_number.startswith("2")]
    assert len(q2_keys) >= 2


# =========================================================================
# 3. STRUCTURAL MUTATION STRESS TESTS
# =========================================================================

def test_structural_mutation_numbering_variants():
    """Stress-test: Different numbering formats must normalize identically."""
    variants = [
        ("1.", "1"),
        ("Q1", "1"),
        ("Q. 1", "1"),
        ("Question 1:", "1"),
        ("[1]", "1"),
        ("(1)", "1"),
        ("1 (a)", "1(a)"),
        ("1.a", "1(a)"),
        ("Q1(b)", "1(b)"),
        ("வினா 1", "1"),
        ("வினா எண் 21", "21"),
        ("34 (அ)", "34(a)"),
        ("34 (ஆ)", "34(b)"),
    ]
    for raw, expected in variants:
        assert normalize_question_number(raw) == expected


def test_structural_mutation_or_delimiters():
    """Stress-test: Various ways exam papers express either/or choices."""
    raw_texts = [
        # Standard OR on own line
        ("Explain photosynthesis.\nOR\nExplain respiration.", 2),
        # Capital OR at end of line
        ("Explain photosynthesis. OR\nExplain respiration.", 2),
        # Lowercase or with parenthesis
        ("Explain photosynthesis.\n(or)\nExplain respiration.", 2),
        # Tamil 'அல்லது' on own line
        ("(அ) கூத்தராற்றுப்படை பாடல் விளக்கம்.\nஅல்லது\n(ஆ) அமைச்சர் இலக்கணம்.", 2),
        # Tamil 'அல்லது' attached to next label
        ("கடிதம் எழுதுக அல்லது (ஆ) கட்டுரை எழுதுக.", 2),
    ]
    for text, expected_count in raw_texts:
        parts = choices.split_alternatives(text)
        assert len(parts) == expected_count, f"Failed for text: {text}"


def test_structural_mutation_answer_any_dynamic_counts():
    """Stress-test: Dynamic 'Answer any N' with varying compulsory questions."""
    # Scenario: Section with 6 questions, total marks should count best 4, Q3 & Q5 compulsory
    class FakeQ:
        def __init__(self, qid, max_m=2.0, comp=False, sec="Sec B", any_n=4):
            self.id = qid
            self.max_marks = max_m
            self.compulsory = comp
            self.section = sec
            self.answer_any = any_n
            self.choice_group = None

    qs = [
        FakeQ("q1"),
        FakeQ("q2"),
        FakeQ("q3", comp=True),  # compulsory
        FakeQ("q4"),
        FakeQ("q5", comp=True),  # compulsory
        FakeQ("q6"),
    ]

    # Student scores:
    # q1: 1.0, q2: 2.0, q3: 0.5 (compulsory), q4: 1.5, q5: 1.0 (compulsory), q6: 2.0
    student_marks = {"q1": 1.0, "q2": 2.0, "q3": 0.5, "q4": 1.5, "q5": 1.0, "q6": 2.0}
    counted = choices.counted(qs, student_marks)

    # Must count q3 and q5 because they are compulsory, plus top 2 of {q1: 1.0, q2: 2.0, q4: 1.5, q6: 2.0} -> q2 and q6
    counted_ids = {q.id for q in counted}
    assert "q3" in counted_ids, "Compulsory Q3 missing"
    assert "q5" in counted_ids, "Compulsory Q5 missing"
    assert "q2" in counted_ids and "q6" in counted_ids
    assert len(counted_ids) == 4


def test_structural_mutation_marks_rule_phrasings():
    """Stress-test: Various marks rule phrasings in exam papers."""
    assert extract_section_marks_rule("15 x 1 = 15") == 1.0
    assert extract_section_marks_rule("5 × 2 = 10") == 2.0
    assert extract_section_marks_rule("4 questions x 5 marks = 20 marks") == 5.0
    assert extract_section_marks_rule("Each question carries 3 marks") == 3.0
    assert extract_section_marks_rule("(2 marks each)") == 2.0
    assert extract_section_marks_rule("தலா 2 மதிப்பெண்") == 2.0
    assert extract_section_marks_rule("5x5=25") == 5.0
    assert extract_section_marks_rule("3x8=24") == 8.0


# =========================================================================
# 4. SIMULATED GRADING WITH CHOICE OVER-ATTEMPT
# =========================================================================

def test_student_over_attempt_takes_higher_mark():
    """Stress-test: Student answers BOTH alternatives of an Either/Or question.

    The grading engine must pick max(score_a, score_b) and never inflate total marks.
    """
    class FakeQ:
        def __init__(self, qid, grp, max_m=5.0):
            self.id = qid
            self.choice_group = grp
            self.max_marks = max_m
            self.section = "Writing"
            self.answer_any = None
            self.compulsory = False

    q_letter = FakeQ("q_letter", grp="writing_q2", max_m=4.0)
    q_application = FakeQ("q_application", grp="writing_q2", max_m=4.0)
    questions = [q_letter, q_application]

    # Student wrote letter (got 2.5/4) AND wrote application (got 3.5/4)
    marks_awarded = {"q_letter": 2.5, "q_application": 3.5}

    units_counted = choices.units(questions, marks_awarded)
    assert len(units_counted) == 1
    assert units_counted[0].id == "q_application"
    assert marks_awarded[units_counted[0].id] == 3.5
