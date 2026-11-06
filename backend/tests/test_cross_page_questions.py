"""Questions that run onto the next page: no false review flags, and the whole-question marks are the ones printed
where the question starts. Nothing here depends on particular question numbers or marks."""
from types import SimpleNamespace as NS

import pytest

from app.cbse.build import _ALTERNATIVE, collect, combined, mark_answer_continuations, use_question_marks
from app.cbse.extraction import Fragment, Node, Page, merge_nodes, tree_total


def leaf(id_, marks, text=""):
    return {"id": id_, "kind": "point", "text": text, "marks": marks, "children": []}


def page(n, *fragments):
    return ({"page_number": n}, Page(page_number=n, fragments=list(fragments)))


def frag(root, text, tree, marks=None, continues=False):
    return Fragment(root=root, text=text, marks=marks, continues=continues, tree=Node.model_validate(tree))


def test_split_mcq_conflicting_leaf_types_is_one_point():
    first = frag(19, "Question\nA. one\nB. two", {"id": "q19", "kind": "all"}, 1)
    second = frag(19, "C. three\nD. four", leaf("q19", None), continues=True)
    _, tree, issues, _, _ = combined([({"page_number": 1}, first), ({"page_number": 2}, second)])
    assert tree["kind"] == "point" and tree["response_type"] == "mcq"
    assert not issues


def test_split_whole_question_choice_keeps_both_branches_complete():
    first = frag(29, "Attempt either option A or B.\nA.\nI. first", leaf("q29", 5), 5)
    second = frag(29, "II. extra\nOR\nB.\nI. second\nII. more", leaf("q29", None))
    second.issues = [_ALTERNATIVE]
    _, tree, issues, _, _ = combined([({"page_number": 1}, first), ({"page_number": 2}, second)])
    assert tree["kind"] == "choose" and tree["limit"] == 1
    assert [child["marks"] for child in tree["children"]] == [5, 5]
    assert "II. extra" in tree["children"][0]["text"]
    assert "II. more" in tree["children"][1]["text"]
    assert not issues


@pytest.mark.parametrize("whole", [2, 4, 5])
def test_stem_on_one_page_parts_on_the_next_is_one_question(whole):
    """Q15-style: the stem alone reads as one item, the parts page as a question with parts. Not a conflict."""
    parts = [leaf("q.a", 1), leaf("q.b", 1), {"id": "q.cd", "kind": "choose", "limit": 1, "marks": whole - 2,
                                              "children": [leaf("q.c", whole - 2), leaf("q.d", whole - 2)]}]
    results = [page(1, frag(7, "In order to study patterns of inheritance ...", leaf("q", whole), marks=whole)),
               page(2, frag(7, "A. Violet flowers ... B. Tall plants ... C. ... OR D. ...",
                            {"id": "q", "kind": "all", "children": parts}))]
    _, tree, issues, marks, _ = combined(collect(NS(), results)[7])
    assert issues == [] and marks == whole
    assert tree["kind"] == "all" and len(tree["children"]) == 3


@pytest.mark.parametrize("whole,guessed", [(3, 1), (5, 2), (2, 1)])
def test_marks_come_from_where_the_question_starts(whole, guessed):
    """Q27-style: the marks column prints the total beside the first part; the carried-over parts print none, so a
    model's guess there (often one part's marks) must not replace or conflict with the printed total."""
    results = [page(1, frag(3, "Other question", leaf("o", 1), marks=1),
                    frag(9, "Give reason for the following: A. ...", {"id": "q9", "kind": "all", "marks": whole,
                                                                         "children": [leaf("q9.a", 1)]}, marks=whole)),
               page(2, frag(9, "B. Milkiness disappears ... C. An iron bridge near the sea ...",
                            {"id": "q9", "kind": "all", "marks": guessed,
                             "children": [leaf("q9.b", 1), leaf("q9.c", 1)]}, marks=guessed),
                    frag(10, "Next question", leaf("n", 4), marks=4))]
    _, tree, issues, marks, _ = combined(collect(NS(), results)[9])
    assert issues == [] and marks == whole
    assert [c["id"] for c in tree["children"]] == ["q9.a", "q9.b", "q9.c"]


def test_a_number_the_next_page_prints_again_is_a_new_printing_not_a_continuation():
    """With the PDF's printed numbers: Q34 (B) or a visually impaired Q34 printed on the next page is an alternative."""
    results = [page(6, frag(34, "Q34 (A). Find the area ...", leaf("a", 5), marks=5)),
               page(7, frag(34, "Find the area enclosed within ...", leaf("b", 5), marks=5))]
    mark_answer_continuations(results, printed={6: {33, 34}, 7: {34, 35}})
    assert results[1][1].fragments[0].continues is False
    mark_answer_continuations(results, printed={6: {33, 34}, 7: {35}})  # not printed on page 7: carried over
    assert results[1][1].fragments[0].continues is True


def test_on_a_scan_an_alternative_label_is_not_a_continuation():
    results = [page(1, frag(12, "Q12 (A). Draw ...", leaf("a", 3), marks=3)),
               page(2, frag(12, "Q12 (B). Describe ...", leaf("b", 3), marks=3))]
    mark_answer_continuations(results)
    assert results[1][1].fragments[0].continues is False


def test_genuinely_conflicting_printed_marks_are_still_flagged_and_resolved_in_page_order():
    results = [page(1, frag(5, "Question five", leaf("q5", 2), marks=2)),
               page(2, frag(6, "Question six", leaf("q6", 1), marks=1),
                    frag(5, "Question five printed again", leaf("q5b", 3), marks=3))]
    _, _, issues, marks, _ = combined(collect(NS(), results)[5])
    assert "Conflicting whole-question marks across pages" in issues and marks == 2


def test_merge_keeps_real_structure_conflicts():
    trees, problems = merge_nodes([{"id": "q", "kind": "all", "children": [leaf("a", 1)]},
                                   {"id": "q", "kind": "choose", "limit": 1, "children": [leaf("b", 1)]}])
    assert len(trees) == 1  # both pieces have parts and disagree: that is a real conflict, handled as before
    trees, problems = merge_nodes([leaf("q", 4), {"id": "q", "kind": "all", "children": [leaf("a", 2), leaf("b", 2)]}])
    assert problems == [] and trees[0]["kind"] == "all" and trees[0]["marks"] == 4


@pytest.mark.parametrize("root", [7, 41])
def test_cross_page_alternative_with_different_ids_retains_nested_solution_methods(root):
    first = frag(root, f"{root}(A). First alternative", {
        "id": f"q{root}A", "kind": "all", "marks": 3,
        "children": [leaf("a1", 1), leaf("a2", 2)],
    }, marks=3)
    second = frag(root, f"OR\n{root}(B). Second alternative\nAlternative Solution:\nAnother solution", {
        "id": f"q{root}", "kind": "choose", "limit": 1,
        "children": [
            {"id": "main", "kind": "all", "label": f"{root}(B)",
             "children": [leaf("b1", 1), leaf("b2", 2)]},
            {"id": "method", "kind": "all", "label": "Alternative Solution",
             "children": [leaf("method1", 3)]},
        ],
    }, continues=True)
    fragments = collect(NS(), [page(1, first), page(2, second)], kind="answer-key")[root]
    assert not second.continues
    use_question_marks(fragments, NS(max_marks=3))
    _, tree, issues, marks, _ = combined(fragments)
    assert issues == [] and marks == 3
    assert tree["kind"] == "choose" and tree["limit"] == 1
    assert len(tree["children"]) == 2
    method_choice = tree["children"][1]
    assert method_choice["kind"] == "choose" and method_choice["choice_type"] == "method"
    assert tree_total(tree, {}) == 3
    assert tree_total(tree, {}, {"a1": 1, "a2": 2, "b1": 1, "b2": 2, "method1": 3}) == 3
    assert tree_total(tree, {}, {"b1": 1, "method1": 1.5}) == 1.5


def test_part_less_question_read_as_different_kinds_on_two_pages_is_one_leaf():
    """A whole question over two pages, read as "point" on one and a part-less "choose" on the next: no conflict."""
    trees, problems = merge_nodes([{"id": "q28", "kind": "point", "marks": 4, "children": []},
                                   {"id": "q28", "kind": "choose", "marks": 4, "children": []}])
    assert problems == []
    assert len(trees) == 1 and trees[0]["kind"] == "point" and trees[0]["marks"] == 4


def test_settled_extraction_issues_are_notes_not_reviews():
    from app.cbse.issues import split
    needs, notes = split(["Conflicting kind for q28", "Page 3: Conflicting section labels across pages",
                          "Model root 7 was corrected to printed question 8 from the source row boundary.",
                          "Missing positive allocation for q4.b", "Allocated marks do not match the printed total for q5"])
    assert notes == ["Conflicting kind for q28", "Page 3: Conflicting section labels across pages",
                     "Model root 7 was corrected to printed question 8 from the source row boundary."]
    assert needs == ["Missing positive allocation for q4.b", "Allocated marks do not match the printed total for q5"]


def test_repeated_question_label_is_a_note():
    from app.cbse.issues import split
    msg = "Repeated whole-question label without a confirmed continuation; review source numbering."
    assert split([msg]) == ([], [msg])


def test_unmarked_mcqs_under_one_total_share_it_equally():
    """Q24-style "6x1 = 6": six MCQs with no marks of their own are 1 mark each, not one 6-mark answer."""
    from app.cbse.extraction import settle_marks
    tree = {"id": "q24", "kind": "point", "marks": 6, "children": [
        {"id": f"q24.{i}", "kind": "point", "marks": None, "response_type": "mcq", "children": []} for i in range(6)]}
    settled = settle_marks(tree, 6)
    assert settled["kind"] == "all" and [c["marks"] for c in settled["children"]] == [1] * 6


def test_case_study_opening_joins_the_first_alternative():
    """Q22-style: the opening (context only) on one page, "A ... OR B" on the next: two alternatives, not three."""
    trees, problems = merge_nodes([
        {"id": "q22", "kind": "all", "marks": 4, "children": [{"id": "q22.ctx", "kind": "context", "children": []}]},
        {"id": "q22", "kind": "choose", "limit": 1, "children": [leaf("q22.A", 4), leaf("q22.B", 4)]}])
    assert problems == [] and [c["id"] for c in trees[0]["children"]] == ["q22.A", "q22.B"]
    assert trees[0]["children"][0]["children"][0]["id"] == "q22.ctx"


def test_page_footer_and_reader_remarks_are_not_question_text():
    from types import SimpleNamespace as NS2
    from app.cbse.build import _drop_page_furniture
    footer = "Note: There is no change in the Question Paper Design and Assessment Pattern."
    results = [({"page_number": n, "page_text": f"{footer}\nPage {n} of 4"},
                NS2(fragments=[NS2(text=t, tree=None)])) for n, t in enumerate(
                   ["Journal entries", "Question 2 text", "Attempt either option A or B.\nRatios", "Cash flow"], 1)]
    results[3][1].fragments[0].text = "Attempt either option A or B.\nCash flow"
    results[1][1].fragments[0].text = f"Question 2 text\n{footer}\nNo further numbered questions are visible on this page."
    _drop_page_furniture(results)
    assert results[1][1].fragments[0].text == "Question 2 text"
    assert results[2][1].fragments[0].text.startswith("Attempt either option A or B.")  # an instruction stays


def test_mcqs_beside_a_stem_repeating_the_whole_marks():
    """Another reading of Q24: a 6-mark "main" part next to the six unmarked MCQs is the case study, not a 7th part."""
    from app.cbse.extraction import settle_marks
    tree = {"id": "q24", "kind": "all", "marks": 6, "children": [
        {"id": "q24.main", "kind": "point", "marks": 6, "response_type": "open", "children": []}] + [
        {"id": f"q24.{i}", "kind": "point", "marks": None, "response_type": "mcq", "children": []} for i in range(6)]}
    settled = settle_marks(tree, 6)
    assert settled["children"][0]["kind"] == "context"
    assert [c["marks"] for c in settled["children"][1:]] == [1] * 6


def test_unmarked_opening_line_joins_the_first_alternative():
    trees, problems = merge_nodes([
        {"id": "q22", "kind": "all", "marks": 4, "children": [{"id": "q22.cap", "kind": "point", "marks": None,
                                                              "children": []}]},
        {"id": "q22", "kind": "choose", "limit": 1, "children": [leaf("q22.A", 4), leaf("q22.B", 4)]}])
    assert problems == [] and [c["id"] for c in trees[0]["children"]] == ["q22.A", "q22.B"]
    assert trees[0]["children"][0]["children"][0]["kind"] == "context"
