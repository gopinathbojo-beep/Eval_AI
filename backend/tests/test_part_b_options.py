"""Accountancy Part B: both options sit under one question number with their labels, nothing is asked when the exam is
created, the AI decides once per sheet which option the student answered, and only that option is marked."""
from types import SimpleNamespace as NS

from app.cbse import grading
from app.cbse.build import combined, mark_branches
from app.cbse.extraction import Fragment, Page, leaves, only_selected, option_text, tree_total
from app.ocr.schemas import EvaluationResult
from app.services import part_b


def _tree(root, marks, *parts, audience=None, kind="all"):
    children = [{"id": f"q{root}.{n}", "kind": "point", "label": n, "text": n, "marks": m, "children": []} for n, m in parts]
    return {"id": f"q{root}", "kind": kind, "label": str(root), "text": "", "marks": marks, "audience": audience, "children": children}


def _frag(root, text, marks=1, continues=False, **tree):
    return {"root": root, "text": text, "marks": None if continues else marks, "section": "B", "continues": continues,
            "tree": _tree(root, marks, ("a", marks), **tree)}


def _results(*pages):
    out = []
    for n, (text, fragments) in enumerate(pages, 1):
        out.append(({"page_number": n, "page_text": text}, Page.model_validate({"page_number": n, "fragments": fragments})))
    return out


PAPER = _results(
    ("Part A", [_frag(26, "Last of Part A", 6)]),
    ("Part B :- Analysis of Financial Statements (Option - I)", [_frag(27, "Cost of materials?"), _frag(28, "Current ratio?")]),
    ("continues", [_frag(28, "more of the ratio", continues=True)]),
    ("Part B: Computerised Accounting (Option - II)", [_frag(27, "Which Excel error?"), _frag(28, "Cell reference?")]),
)


def _built(root):
    mark_branches(PAPER)
    frags = [(p, f) for p, r in PAPER for f in r.fragments if f.root == root]
    return combined(frags, {"accessibility": "standard"}, True)


def test_the_numbers_restarting_mark_the_second_option_and_part_a_is_left_alone():
    mark_branches(PAPER)
    seq = [(f.root, f.branch) for _, r in PAPER for f in r.fragments]
    assert seq == [(26, None), (27, "financial"), (28, "financial"), (28, "financial"),
                   (27, "computerised"), (28, "computerised")]


def test_a_paper_without_option_headings_is_not_touched():
    plain = _results(("Section A", [_frag(1, "One"), _frag(2, "Two")]), ("Section B", [_frag(1, "One again")]))
    mark_branches(plain)
    assert all(f.branch is None for _, r in plain for f in r.fragments)


def test_both_options_sit_under_one_number_with_their_labels():
    text, tree, problems, marks, section = _built(28)
    assert text.startswith("Option I: Analysis of Financial Statements\nCurrent ratio?\nmore of the ratio\nOR\n")
    assert "Option II: Computerised Accounting\nCell reference?" in text
    assert marks == 1 and section == "B" and problems == []
    assert tree["kind"] == "choose" and tree["limit"] == 1
    assert [c["audience"] for c in tree["children"]] == ["financial", "computerised"]
    ids = [n["id"] for n in leaves(tree, {})]
    assert len(ids) == len(set(ids))                                  # the options never share a criterion id
    assert tree_total(tree, {}) == 1                                  # alternatives, never extra marks


def test_only_the_students_option_is_marked():
    text, tree, *_ = _built(27)
    options = {"accountancy_option": "computerised"}
    assert [n["id"] for n in leaves(tree, options)] == ["com-q27.a"]
    assert tree_total(tree, options) == 1
    assert len(only_selected(tree, options)["children"]) == 1
    assert option_text(text, "computerised") == "Which Excel error?"
    assert option_text(text, "financial") == "Cost of materials?"
    assert option_text("A plain question", "financial") == "A plain question"

    q, key = NS(max_marks=1, question_type="short_answer", display_number="27", question_text=text, structure={}), \
        NS(answer_text=text, rubric={"cbse_tree": tree}, accepted_answers=[])
    prompt = grading.prompt(q, key, "#REF! error", options, [], [])
    assert "Which Excel error?" in prompt and "Cost of materials?" not in prompt and "fin-q27" not in prompt
    award = EvaluationResult.model_validate({"marks_awarded": 1, "criterion_awards": [
        {"id": "com-q27.a", "marks": 1, "evidence_quotes": ["#REF! error"]}]})
    assert grading.validate_result(award, q, key, options, "#REF! error").marks_awarded == 1


def test_an_undecided_sheet_is_marked_on_the_option_that_earns_most():
    _, tree, *_ = _built(27)
    assert {n["id"] for n in leaves(tree, {})} == {"fin-q27.a", "com-q27.a"}
    assert tree_total(tree, {}, {"fin-q27.a": 0, "com-q27.a": 1}) == 1


def test_creating_an_accountancy_exam_asks_nothing(client, auth):
    catalog = client.get("/api/subjects/catalog?grade=12", headers=auth).json()["12"]
    assert all(not s["options"] for s in catalog)
    r = client.post("/api/exams/simple", headers=auth, json={
        "name": "Accounts", "grade": "12", "section": "A", "subject_key": "12-accountancy"})
    assert r.status_code == 201, r.text
    assert "accountancy_option" not in r.json()["standard_options"]


def test_the_ai_decides_once_for_the_sheet(client, auth):
    from app.database import SessionLocal
    from app.models import AnswerSheetDocument, Evaluation, Exam, ExamQuestion, Student, StudentAnswer

    exam = client.post("/api/exams/simple", headers=auth, json={
        "name": "Accounts B", "grade": "12", "section": "B", "subject_key": "12-accountancy"}).json()
    text, tree, *_ = _built(27)
    db = SessionLocal()
    try:
        q = ExamQuestion(exam_id=exam["id"], display_number="27", normalized_number="27", question_text=text, max_marks=1,
                         position=27, structure={"root": 27, "tree": tree})
        plain = ExamQuestion(exam_id=exam["id"], display_number="1", normalized_number="1", question_text="Part A",
                             max_marks=1, position=1, structure={"root": 1})
        kid = Student(class_id=db.get(Exam, exam["id"]).class_id, roll_number="B1", name="B One")
        sheet = AnswerSheetDocument(exam_id=exam["id"], original_filename="s.pdf", original_file="s.pdf",
                                    mime_type="application/pdf", file_size=1, status="READY", pages=[])
        db.add_all([q, plain, kid, sheet])
        db.flush()
        ev = Evaluation(exam_id=exam["id"], student_id=kid.id, answer_sheet_id=sheet.id, status="DRAFT")
        db.add(ev)
        db.flush()
        db.add(StudentAnswer(evaluation_id=ev.id, exam_question_id=plain.id, answer_text="A part A answer", status="MAPPED", position=1))
        db.commit()
        calls = []

        def ask(system, prompt):
            calls.append(prompt)
            return part_b.OptionChoice(option="Computerised")

        assert part_b.student_option(db, ev, ask=ask) is None and calls == []   # no Part B answer: nothing to decide
        db.add(StudentAnswer(evaluation_id=ev.id, exam_question_id=q.id, answer_text="Option II. #REF! error", status="MAPPED", position=2))
        db.commit()
        assert part_b.student_option(db, ev, ask=ask) == "computerised" and len(calls) == 1
        assert "Which Excel error?" in calls[0] and "Cost of materials?" in calls[0] and "Option II. #REF!" in calls[0]
        assert part_b.student_option(db, ev, ask=lambda s, p: part_b.OptionChoice(option="both")) is None
    finally:
        db.close()


def test_a_visual_described_without_a_position_does_not_reject_the_page():
    page = Page.model_validate({"page_number": 1, "fragments": [{"root": 34, "text": "Balance sheet", "visuals": [
        {"kind": "diagram", "description": "Balance Sheet table"}]}]})
    assert page.fragments[0].visuals[0].bbox == {}


def test_an_assertion_reason_question_in_one_option_keeps_its_choices():
    from app.cbse.build import share_assertion_reason_options
    pages = _results(("p", [_frag(28, "Assertion (A): Current ratio.\nReason (R): Inventory."), _frag(29, "Furniture?")]),
                     ("p", [_frag(27, "Which error?"), _frag(28, "Cell reference? (A) # (B) ~ (C) $ (D) x")]))
    share_assertion_reason_options(pages)
    first, second = pages[0][1].fragments[0], pages[1][1].fragments[1]
    assert "correct explanation" in first.text and "correct explanation" not in second.text


def test_a_lettered_alternative_is_not_a_continuation_and_needs_no_marks_of_its_own():
    from app.cbse.build import fix_false_continuations
    pages = _results(("p", [_frag(31, "31 A. Comparative statement", 3)]),
                     ("p", [_frag(31, "31 B. Common size statement", 3, continues=True)]))
    fix_false_continuations(pages, {31})
    pieces = [(p, f) for p, r in pages for f in r.fragments]
    assert pieces[1][1].continues is False and pieces[1][1].marks is None
    text, tree, _, marks, _ = combined(pieces, {}, True)
    assert tree["kind"] == "choose" and len(tree["children"]) == 2 and marks == 3 and tree_total(tree, {}) == 3


def test_a_part_b_opening_a_page_of_an_unrepeated_number_stays_a_continuation():
    from app.cbse.build import fix_false_continuations
    pages = _results(("p", [_frag(12, "A. First part", 3)]), ("p", [_frag(12, "B. Second part", 3, continues=True)]))
    fix_false_continuations(pages, set())
    assert pages[1][1].fragments[0].continues is True


def test_a_question_keeps_the_assertion_reason_list_printed_with_it():
    from app.cbse.build import share_assertion_reason_options
    first = "Assertion (A): One.\nReason (R): Two.\n(A) Both correct, R explains A\n(B) Both correct, R does not explain A\n(C) A false, R true\n(D) A true, R false"
    second = "Assertion (A): Three.\nReason (R): Four.\n(A) Both correct, R explains A\n(B) Both correct, R does not explain A\n(C) A true, R false\n(D) A false, R true"
    pages = _results(("p", [_frag(9, first)]), ("p", [_frag(28, second)]))
    share_assertion_reason_options(pages)
    assert "(C) A false, R true" in pages[0][1].fragments[0].text
    assert "(C) A true, R false" in pages[1][1].fragments[0].text
