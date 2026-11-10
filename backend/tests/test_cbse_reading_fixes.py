"""Fixes found by running every CBSE sample paper end to end (2026-11-10)."""
from types import SimpleNamespace

from app.cbse import layout
from app.cbse.build import clean_text
from app.cbse.extraction import Fragment, Node, merge_nodes


def test_a_section_heading_on_a_run_on_line_keeps_the_answers():
    """Chemistry marking scheme: "Section-A 1 B. Amine R ... 2 C. ..." read as one line lost all of Q1."""
    text = "Section-A 1 B. Amine R will give white precipitate with Hinsberg reagent. 2 C. [NiCl4] is tetrahedral"
    assert clean_text(text).startswith("1 B. Amine R")
    assert clean_text("SECTION A\n1. What is x?") == "1. What is x?"
    assert clean_text("Section B (2 marks each) 17. Explain") == "17. Explain"


def test_the_prompts_example_values_are_not_kept_as_criteria():
    f = Fragment(root=1, text="x", criteria=["verbatim marking instructions", "Award 1 mark for the formula"],
                 accepted_answers=["explicit alternatives", "3F"])
    assert f.criteria == ["Award 1 mark for the formula"] and f.accepted_answers == ["3F"]


def test_any_n_of_m_parts_continue_over_a_page_break():
    """English Language and Literature Q3: "Complete any ten of the twelve tasks", parts VII-XII on the next page."""
    first = Node(id="q3", kind="choose", limit=10, children=[
        Node(id=f"q3.{p}", kind="point", marks=1) for p in ("i", "ii", "iii", "iv", "v", "vi")])
    more = Node(id="q3", kind="all", children=[Node(id=f"q3.{p}", kind="point", marks=1)
                                              for p in ("vii", "viii", "ix", "x", "xi", "xii")])
    (tree,), problems = merge_nodes([first, more])
    assert len(tree["children"]) == 12 and tree["limit"] == 10 and not problems
    # an "A or B" choice still carries the next page into its last alternative
    either = Node(id="q9", kind="choose", limit=1, children=[Node(id="q9.A", kind="all"), Node(id="q9.B", kind="all")])
    rest = Node(id="q9", kind="all", children=[Node(id="q9.b2", kind="point", marks=2)])
    (tree,), _ = merge_nodes([either, rest])
    assert [c["id"] for c in tree["children"]] == ["q9.A", "q9.B"] and tree["children"][1]["children"]


def test_roman_numbered_parts_read_as_whole_questions_go_back_to_their_question():
    """The model returned grammar parts VII ... XII as questions 7 ... 12 on a page that prints no 7 ... 12."""
    def piece(root, text):
        return Fragment(root=root, text=text, marks=1, tree=Node(id=f"q{root}", kind="point", marks=1))
    page = SimpleNamespace(fragments=[piece(7, "VII The given question has an error."),
                                      piece(8, "VIII Juhi asked her friend"), piece(4, "WRITING A. You are Maya"),
                                      piece(9, "In the story the balcony")])
    layout._keep_roman_parts(page, printed_here={4}, lead=3, page_number=6)
    assert [f.root for f in page.fragments] == [3, 3, 4, 9]  # "In the story" is no Roman label: left as it is
    assert page.fragments[0].continues and page.fragments[0].tree.children[0].id.startswith("q3.vii")
    assert [layout._roman(x) for x in ("IV", "VII", "IX", "XII")] == [4, 7, 9, 12]
