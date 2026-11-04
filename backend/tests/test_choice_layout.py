"""Internal choices printed as a bare "Q23" with "(A)." on the next line, and visually impaired versions that
carry their own OR (CBSE Mathematics 2026-27 sample paper, Q19/Q23 and Q34)."""
import fitz

from app.cbse.build import _alternatives, combined
from app.cbse.extraction import Fragment, Node, choice_signature, tree_total
from app.cbse.layout import _anchors


def test_bare_q_label_is_a_question_number():
    doc = fitz.open()
    page = doc.new_page()
    y = 80
    for line in ["Q19. Assertion: The value of the integral is 4", "Q20. Assertion: A general solution ...",
                 "Q21", "(A). Evaluate the integral", "OR", "Q21", "(B). Evaluate another integral",
                 "Q22. If y = sin(x + y) then prove that y = 1.", "Q23", "(A). A line passing through the points",
                 "OR", "Q23", "(B). A rectangle ABCD is such that", "Q24. For two non-zero vectors"]:
        page.insert_text((45, y), line, fontsize=11)
        y += 30
    roots = [root for root, _y, _x in _anchors(page)]
    # without "Q23" counted, the model's own Q23 was re-filed under Q19 as a layout "correction"
    assert roots == [19, 20, 21, 21, 22, 23, 23, 24]


def _fragment(text, tree_id, label):
    return Fragment(root=34, text=text, marks=5, tree=Node(id=tree_id, kind="point", label=label, text=text, marks=5))


def test_visually_impaired_versions_with_their_own_or_are_one_audience_choice():
    page = {"page_number": 6}
    fragments = [
        (page, _fragment("Q34 (A). Using Integration, find the area of the region {(x, y): 0 <= y <= ...}", "34a", "(A)")),
        (page, _fragment("Q34 (B). Using Integration, find the area bounded by y^2 = 2x and x - 2y = 0.", "34b", "(B)")),
        ({"page_number": 7}, _fragment("For Visually Impaired: Q34 (A). Find the area enclosed within 25x^2 + 16y^2 = 400",
                                       "34via", "(A)")),
        ({"page_number": 7}, _fragment("Q34 (B). Find the area bounded by y^2 = 8x, x = 2, x = 5 and the x-axis.",
                                       "34vib", "(B)")),
    ]
    tree = _alternatives(fragments, printed_choice=True)
    assert tree["kind"] == "choose" and [g["audience"] for g in tree["children"]] == ["standard", "accessible"]
    standard, accessible = tree["children"]
    assert [c["text"][:7] for c in standard["children"]] == ["Q34 (A)", "Q34 (B)"]
    assert len(accessible["children"]) == 2 and "Visually" in accessible["children"][0]["text"]
    assert "25x^2" in accessible["children"][0]["text"] and "8x" in accessible["children"][1]["text"]
    for audience in ("standard", "accessible"):
        options = {"accessibility": audience}
        assert tree_total(tree, options) == 5
        assert choice_signature(tree, options) == [(1, 2)]  # one internal choice, like the board pattern
    # the build path reshapes trees afterwards: the audience groups must survive it
    _text, built, _issues, marks, _section = combined(fragments, {"accessibility": "standard"}, printed_choice=True)
    assert marks == 5 and [g["audience"] for g in built["children"]] == ["standard", "accessible"]
    assert choice_signature(built, {"accessibility": "accessible"}) == [(1, 2)]


def test_a_single_visually_impaired_version_stays_a_flat_alternative():
    page = {"page_number": 3}
    fragments = [(page, _fragment("Q12 (A). Draw the graph of y = x^2.", "12a", "(A)")),
                 (page, _fragment("For Visually Impaired: Q12 (B). Describe the graph of y = x^2.", "12b", "(B)"))]
    tree = _alternatives(fragments, printed_choice=True)
    assert [c["audience"] for c in tree["children"]] == ["standard", "accessible"]
