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
