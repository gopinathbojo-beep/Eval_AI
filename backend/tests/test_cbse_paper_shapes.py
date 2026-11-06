"""Shapes from the CBSE 2026-27 Class 12 sample papers (synthetic text) that used to send questions to review:
a piece read with question number 0, plain questions with no scoring tree, tree names that differ by page,
metadata spelled two ways, section headings printing marks x questions, and parts labelled (a) after a page break."""
from types import SimpleNamespace as NS

from app.cbse.build import (_CHOICE_LABEL, carry_unnumbered, fix_false_continuations, give_every_question_a_tree,
                            merge_metadata)
from app.cbse.catalog import PROFILES, get_profile
from app.cbse.extraction import CARRIED, Fragment, Page, merge_nodes
from app.cbse.layout import _INSTRUCTION_START, _marks_each


def _page(number, *fragments, metadata=None):
    return ({"page_number": number}, Page(page_number=number, fragments=list(fragments), metadata=metadata or {}))


def test_a_piece_read_as_question_0_joins_the_question_before_it():
    page = Page.model_validate({"page_number": 2, "fragments": [
        {"root": 0, "text": "For Visually Impaired: Find the range of sec^-1 x"},
        {"root": "Q2.", "text": "Domain of sec^-1(2x) is"},
        {"root": None, "text": "(continued options)"}]})
    assert [(f.root, f.continues) for f in page.fragments] == [(CARRIED, True), (2, False), (2, True)]
    results = [_page(1, Fragment(root=1, text="Identify the function")), ({"page_number": 2}, page)]
    carry_unnumbered(results)
    assert [f.root for f in results[1][1].fragments] == [1, 2, 2]


def test_every_question_piece_gets_one_scoring_tree_under_one_name():
    plain = Fragment(root=23, text="Explain the Bhakti movement.\nGive two reasons.", marks=3)
    named = Fragment.model_validate({"root": 37, "text": "Office block", "tree": {
        "id": "37", "kind": "all", "children": [{"id": "37.i", "kind": "point", "marks": 1}]}})
    carried = Fragment(root=37, text="(ii) more parts", continues=True)
    results = [_page(7, plain, named, carried)]
    give_every_question_a_tree(results)
    assert (plain.tree.id, plain.tree.kind, plain.tree.marks) == ("q23", "point", 3)
    assert named.tree.id == "q37" and named.tree.children[0].id == "q37.i"
    assert carried.tree is None


def test_childless_point_and_all_from_two_pages_are_not_a_conflict():
    trees, problems = merge_nodes([{"id": "q27", "kind": "point", "marks": 3, "children": []},
                                   {"id": "q27", "kind": "all", "marks": None, "children": []}])
    assert len(trees) == 1 and problems == []


def test_metadata_most_pages_agree_on_wins_and_spellings_match():
    results = [_page(1, metadata={"class_level": "XII", "subject_name": "MATHEMATICS", "printed_page_count": 1}),
               _page(6, metadata={"class_level": 12, "subject_name": "Mathematics (041)", "printed_page_count": 10}),
               _page(8, metadata={"class_level": 12, "subject_name": "Mathematics", "printed_page_count": 10})]
    metadata, issues = merge_metadata(results)
    assert issues == [] and metadata["class_level"] == 12 and metadata["printed_page_count"] == 10
    tie = [_page(1, metadata={"subject_code": "041"}), _page(2, metadata={"subject_code": "241"})]
    assert merge_metadata(tie)[1] == ["Conflicting subject_code on page 2"]


def test_section_heading_factors_in_either_order():
    assert _marks_each(21, 1, 21) == 1   # "(21x1=21)" over 21 questions
    assert _marks_each(8, 3, 3) == 8     # "(8x3=24)" over 3 questions
    assert _marks_each(6, 3, 6) == 3
    assert _marks_each(None, None, 4) is None


def test_instructions_end_text_recovered_at_a_page_top():
    assert _INSTRUCTION_START.search("Assertion-Reason Based Questions")
    assert _INSTRUCTION_START.search("Directions: Question numbers 19 and 20 are Assertion and Reason based")
    assert not _INSTRUCTION_START.search("d) Both these policies try to establish singular national identities")


def test_lower_case_part_after_a_page_break_stays_a_continuation():
    assert not _CHOICE_LABEL.match("(a) Long term Borrowings 1,20,000")
    assert _CHOICE_LABEL.match("(B) Prepare a Cash Flow Statement")
    results = [_page(11, Fragment(root=34, text="From the following Balance Sheet")),
               _page(12, Fragment(root=34, text="(a) Long term Borrowings 1,20,000", continues=True))]
    fix_false_continuations(results)
    assert results[1][1].fragments[0].continues


def test_class_12_subjects_with_sample_papers_have_a_board_pattern():
    names = {p["name"] for p in PROFILES if p["class_level"] == 12}
    assert {"Mathematics", "Applied Mathematics", "Biotechnology", "Business Studies", "Economics",
            "Entrepreneurship", "Geography", "History", "Home Science", "Informatics Practices", "Psychology",
            "Sociology"} <= names
    maths = get_profile("cbse-12-041")
    assert maths["question_count"] == 38 and maths["parent_marks"][27] == 3 and maths["parent_marks"][33] == 5
    history = get_profile("cbse-12-027")
    assert history["parent_marks"][27:34] == [8, 8, 8, 4, 4, 4, 5]
