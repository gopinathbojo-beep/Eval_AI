"""Questions with sub-parts ((a), (i), (1), 9.1 ...) are kept as one question with the parts inside it."""
from types import SimpleNamespace

from app.ocr.internvl import _drop_malformed_items
from app.ocr.schemas import QuestionPageResult
from app.services.doc_structure import parse_question_paper_structure
from app.services.mapping import MAPPED, flag_duplicates, map_label
from app.services.mapping_service import _merge_key_parts


def page(n, items):
    return ({"page_number": n}, QuestionPageResult.model_validate({"questions": [
        {"raw_question_number": lbl, "question_text": t, "marks": m} for lbl, t, m in items]}))


def parse(*pages):
    return [(q.display_number, q.max_marks) for q in parse_question_paper_structure(list(pages)).questions]


def test_heading_with_parts_across_pages_is_one_question():
    """The real layout: Q9's title and (a) on page 1, (b) and (c) on page 2, then Q10 as a heading + parts."""
    st = parse_question_paper_structure([
        page(1, [("Q8", "Draw a candle flame.", 3),
                 ("Q9", "Corrosion & Chemical Properties:\n(a) What is rusting of iron? (2 marks)", 5)]),
        ({"page_number": 2}, QuestionPageResult.model_validate({"questions": [
            {"raw_question_number": "(b)", "question_text": "Why do copper vessels turn green? (2marks)", "marks": 2},
            {"raw_question_number": "(c)", "question_text": "List two methods to prevent corrosion. (1 mark)", "marks": 1},
            {"raw_question_number": "Q10.", "question_text": "Polymerization & Environmental Impact:",
             "section": "Polymerization & Environmental Impact:"},
            {"raw_question_number": "(a)", "question_text": "Why are plastics widely used?", "marks": 2},
            {"raw_question_number": "(b)", "question_text": "Biodegradable vs non-biodegradable.", "marks": 2},
            {"raw_question_number": "(c)", "question_text": "State the 5R principle.", "marks": 1}]})),
    ])
    assert [(q.display_number, q.max_marks) for q in st.questions] == [("8", 3), ("9", 5), ("10", 5)]
    q9, q10 = st.questions[1], st.questions[2]
    assert "(b) Why do copper" in q9.question_text and "(c) List two" in q9.question_text and q9.page_end == 2
    assert q10.question_text.startswith("Polymerization") and "(c) State the 5R principle. (1 mark)" in q10.question_text
    assert q10.section != "Polymerization & Environmental Impact:"  # its title is not a section
    assert q10.verification_status == "UNVERIFIED"                   # marks came from its parts


def test_numeric_roman_and_dotted_parts():
    assert parse(page(1, [("Q1", "Define x.", 2), ("Q2", "Solve:", None), ("(1)", "x+1=2", 1), ("(2)", "2x=4", 2),
                          ("Q3", "Prove y.", 3)])) == [("1", 2), ("2", 3), ("3", 3)]
    assert parse(page(1, [("1.", "Define x.", 2), ("2.", "Solve:", None), ("1)", "a", 1), ("2)", "b", 1), ("3)", "c", 1),
                          ("3.", "Prove y.", 3)])) == [("1", 2), ("2", 3), ("3", 3)]
    assert parse(page(1, [("Q1", "Define x.", 2), ("Q2", "Answer:", None), ("i)", "a", 1), ("ii)", "b", 1),
                          ("(iii)", "c", 1), ("Q3", "Prove y.", 3)])) == [("1", 2), ("2", 3), ("3", 3)]
    assert parse(page(1, [("1", "Define x.", 2), ("2", "Answer:", None), ("2.1", "a", 1), ("2.2", "b", 2),
                          ("3", "Prove y.", 3)])) == [("1", 2), ("2", 3), ("3", 3)]


def test_unlabelled_parts_found_in_text():
    st = parse_question_paper_structure([page(1, [("Q1", "Define x.", 2), ("Q2", "Metals:", None),
                                                  (None, "(a) What is rust? (2 marks)", None),
                                                  (None, "(b) Why green? (1 mark)", None), ("Q3", "Prove y.", 3)])])
    assert [(q.display_number, q.max_marks) for q in st.questions] == [("1", 2), ("2", 3), ("3", 3)]


def test_main_numbering_is_not_mistaken_for_parts():
    assert parse(page(1, [("I.", "Define x.", 2), ("II.", "Explain y.", 2), ("III.", "Prove z.", 3)])) == \
        [("1", 2), ("2", 2), ("3", 3)]
    assert parse(page(1, [("1.", "Define x.", 2), ("2.", "Solve:", None), ("1.", "a", 1), ("2.", "b", 1),
                          ("3.", "Prove y.", 3)])) == [("1", 2), ("2", 2), ("3", 3)]
    # separately printed 3(a), 3(b) with no question 3 heading are still one question 3, worth its parts' marks
    assert parse(page(1, [("Q1", "Define x.", 2), ("3 (a)", "Describe.", 3), ("3-b", "Draw.", 5)])) == \
        [("1", 2), ("3", 8)]


def test_page_with_one_garbled_item_keeps_the_rest():
    obj = {"page_number": 2, "questions": [{"raw_question_number": "(b)", "question_text": "ok"}, "question_type"]}
    cleaned, dropped = _drop_malformed_items(obj)
    assert dropped == 1 and len(QuestionPageResult.model_validate(cleaned).questions) == 1
    assert _drop_malformed_items({"criteria": ["a", "b"]}) == ({"criteria": ["a", "b"]}, 0)


def test_student_parts_map_to_whole_question_and_are_not_duplicates():
    qs = [SimpleNamespace(id="q9", normalized_number="9")]
    rows = []
    for lbl in ("9(a)", "9(b)"):
        r = map_label(lbl, qs)
        assert r.status == MAPPED and r.question_id == "q9"
        rows.append(SimpleNamespace(exam_question_id=r.question_id, normalized_number=r.normalized_number))
    assert flag_duplicates(rows) == set()
    assert flag_duplicates(rows, allow_parts=False) == {"q9"}          # answer keys: one row per question
    rows.append(SimpleNamespace(exam_question_id="q9", normalized_number="9(a)"))
    assert flag_duplicates(rows) == {"q9"}                             # the same part twice is a duplicate


def test_key_part_rows_combine_into_one_key():
    q9 = SimpleNamespace(id="q9", normalized_number="9", max_marks=5)
    keys = [SimpleNamespace(exam_question_id="q9", normalized_number=n, answer_text=t, raw_ocr_text=t, marks=m,
                            criteria=[c], accepted_answers=[], keywords=[w], mapping_note=None, is_active=True)
            for n, t, m, c, w in (("9(a)", "Iron oxide forms", 2, "1 mark: oxide", "rust"),
                                  ("9(b)", "Copper carbonate", 2, "1 mark: carbonate", "rust"),
                                  ("9(c)", "Painting, galvanising", 1, "1 mark: two methods", "paint"))]
    deleted = []
    _merge_key_parts(SimpleNamespace(delete=deleted.append), keys, {"q9": q9})
    head = keys[0]
    assert head.answer_text == "(a) Iron oxide forms\n(b) Copper carbonate\n(c) Painting, galvanising"
    assert head.marks == 5 and head.normalized_number == "9" and head.keywords == ["rust", "paint"]
    assert head.criteria[0] == "(a) 1 mark: oxide" and deleted == keys[1:]


def test_stem_total_is_not_added_to_part_marks():
    """A 5 mark question printed as "Q9 ... (5 marks)" with parts 2+2+1 stays worth 5, not 10."""
    assert parse(page(1, [("Q9", "Corrosion: (5 marks)", 5), ("(a)", "What is rusting? (2 marks)", 2),
                          ("(b)", "Why do copper vessels turn green? (2 marks)", 2),
                          ("(c)", "Two ways to prevent corrosion. (1 mark)", 1),
                          ("Q10", "Define a polymer.", 3)])) == [("9", 5), ("10", 3)]


def test_stem_that_repeats_its_parts_is_not_counted_twice():
    """The model returned the whole question with its parts, then each part again (seen on a physics paper)."""
    a = "(a) Calculate the depth of the seabed. (2 marks)"
    b = "(b) A string completes 1200 oscillations in 15 s. Calculate: 1. Frequency (1.5 marks) 2. Period (1.5 marks)"
    st = parse_question_paper_structure([page(1, [("Q9", f"Wave Motion: {a} {b}", None), ("(a)", a, 2), ("(b)", b, 3)])])
    assert [(q.display_number, q.max_marks) for q in st.questions] == [("9", 5)]
    assert st.questions[0].question_text.count("Calculate the depth") == 1


def test_first_part_labelled_as_the_part_opens_the_question():
    """The model labels a question by its first part ("Q5(a).") with the stem above "(a)": still one question 5."""
    assert parse(page(1, [
        ("Q4.", "Factorise 16x^4 - 81y^4", 2),
        ("Q5(a).", "Mensuration:\nThe canal is a trapezium 12 m and 8 m wide, 4 m deep.\n(a) Find its area. (1.5 marks)", 1.5),
        ("Q5(b).", "(b) The canal is 250 m long: find the volume. (1.5 marks)", 1.5),
        ("Q6(a).", "Depreciation:\nEquipment worth Rs. 1,25,000 depreciates 8% then 10%.\n(a) Find its value.", 3),
    ]), page(2, [
        (None, "(b) Find the total drop in value.", None),
        ("Q7.", "Expand (a+b)^2.", 3),
    ])) == [("4", 2), ("5", 3), ("6", 3), ("7", 3)]


def test_whole_key_then_part_key_become_one_key():
    """Key "Q5" (stem + part a) then "5(b)": one key for question 5. A first row carrying the question's total
    is not added to the part again."""
    from app.services.mapping_service import _combined_marks
    q = SimpleNamespace(id="q5", normalized_number="5", max_marks=3.0)
    head = SimpleNamespace(id="k1", exam_question_id="q5", normalized_number="5", answer_text="(a) 40 m2",
                           raw_ocr_text="", criteria=[], accepted_answers=[], keywords=[], marks=1.5, is_active=True)
    part = SimpleNamespace(id="k2", exam_question_id="q5", normalized_number="5(b)", answer_text="10000 m3",
                           raw_ocr_text="", criteria=[], accepted_answers=[], keywords=[], marks=1.5, is_active=True)
    deleted = []
    _merge_key_parts(SimpleNamespace(delete=deleted.append), [head, part], {"q5": q})
    assert head.marks == 3 and head.normalized_number == "5" and deleted == [part]
    assert head.answer_text == "(a) 40 m2\n(b) 10000 m3"
    assert _combined_marks([3.0, 1.5], head_is_part=False, q_max=3.0) == 3.0
    assert _combined_marks([1.5, 1.5], head_is_part=True, q_max=3.0) == 3.0
