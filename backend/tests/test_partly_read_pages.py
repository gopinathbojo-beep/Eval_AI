"""A page the AI reads only in part is never dropped whole: the valid question pieces of its reply are kept and the
text it skipped above the first printed number (a question running over from the previous page) is recovered from
the PDF text layer. Shapes from the CBSE Science paper: Q27 B-C carried to the next page, above Q28's case study."""
import fitz

from app.cbse.extraction import PARTLY_READ, Fragment, Page
from app.cbse.layout import _anchors, _reconcile_fragments

_HEADER = "*There is no change in the Question Paper Design and Assessment Pattern."


def _paper(pages):
    doc = fitz.open()
    for lines in pages:
        page = doc.new_page()
        for i, (x, text) in enumerate(lines):
            page.insert_text((x, 60 + 24 * i), text, fontsize=10)
    return doc


def _read(doc, number, fragments, lead):
    page = doc[number - 1]
    meta = {"page_number": number, "ocr_width": page.rect.width, "ocr_height": page.rect.height,
            "width": page.rect.width, "height": page.rect.height}
    result = Page(page_number=number, fragments=fragments)
    _reconcile_fragments(page, meta, result, _anchors(page), lead)
    return result


def test_junk_after_a_valid_piece_keeps_the_piece_and_says_so():
    reply = {"page_number": 9, "fragments": [
        {"root": 28, "text": "Aavya and Vihan are studying the properties of metals.", "marks": 4},
        "issues_list_of_errors_or_ambiguities_found_in_the_source_text_or_image_if_any_found_by_the_system",
    ]}
    page = Page.salvage(reply)
    assert [f.root for f in page.fragments] == [28] and page.fragments[0].marks == 4
    assert PARTLY_READ in page.issues and PARTLY_READ in page.fragments[0].issues
    # nothing to keep, or nothing wrong: the reply stays a failure for the caller to report or retry
    assert Page.salvage({"page_number": 9, "fragments": ["junk"]}) is None
    assert Page.salvage({"page_number": 9, "fragments": [{"root": 1, "text": "ok"}]}) is None


def test_question_continued_above_the_first_number_is_recovered():
    doc = _paper([
        [(30, _HEADER), (30, "27"), (50, "Give reason for the following :"),
         (50, "A. A solution of sports electrolyte drink conducts electricity.")],
        [(30, _HEADER), (50, "B. Milkiness disappears when excess of carbon dioxide is passed through lime water."),
         (50, "C. An iron bridge near the sea rusts much faster than one in a dry hilly region."),
         (30, "28"), (50, "Aavya and Vihan are studying the properties of metals in school.")],
    ])
    result = _read(doc, 2, [Fragment(root=28, text="Aavya and Vihan are studying the properties of metals in school.")], 27)
    carried = next(f for f in result.fragments if f.root == 27)
    assert carried.continues and "Milkiness" in carried.text and "iron bridge" in carried.text
    assert "no change in the Question Paper" not in carried.text  # the running header is not question text
    assert [f.root for f in result.fragments] == [27, 28]


def test_text_the_ai_already_read_or_a_lone_heading_is_not_recovered():
    doc = _paper([
        [(30, "31"), (50, "An electrical appliance rated 1000 W is operated at 250 V."),
         (50, "Answer these questions by selecting the appropriate option given below:")],
        [(50, "C. A is true but R is false."), (50, "D. A is false but R is true."),
         (30, "32"), (50, "Assertion (A): The apparent depth of a coin in water is less than its real depth.")],
        [(30, "SECTION D"), (30, "33"), (50, "State Snell's law of refraction.")],
    ])
    instructions = Fragment(root=32, text="C. A is true but R is false.\nD. A is false but R is true.\n"
                                          "Assertion (A): The apparent depth of a coin in water is less than its real depth.")
    assert [f.root for f in _read(doc, 2, [instructions], 31).fragments] == [32]
    assert [f.root for f in _read(doc, 3, [Fragment(root=33, text="State Snell's law of refraction.")], 32).fragments] == [33]
