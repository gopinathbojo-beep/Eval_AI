"""Bare numbers in a paper's text (an instruction count, a date opening a passage line) are not question numbers,
and a mis-encoded (legacy Hindi font) PDF text layer is never copied into questions."""
import pymupdf
from app.cbse import layout


def _paper(pages):
    doc = pymupdf.open()
    for lines in pages:
        page = doc.new_page()
        for y, x, text in lines:
            page.insert_text((x, y), text)
    return doc


def test_bare_numbers_must_continue_the_question_sequence():
    doc = _paper([
        [(80, 40, "21 sub-questions in this section"), (200, 40, "1 Read the passage below"), (260, 60, "text")],
        [(80, 40, "27 June 2025 the passage goes on"), (200, 60, "(I) a part of question 1")],
        [(80, 40, "2 Read the poem below"), (200, 40, "3 Change the voice")],
    ])
    layout._by_doc.clear()
    assert [[r for r, _y, _x in layout._anchors(p)] for p in doc] == [[1], [], [2, 3]]


def test_mis_encoded_hindi_text_layer_is_detected():
    garbled = "िांि –ग में प़ाठ््् पुस्तक और पूरक प़ाठ््् पुस्तक पर आध़ाररत कुि 5 प्रश्न हैं, उप प्रश्नों की सांख़््ा 21 है " * 2
    clean = "खंड - ग में पाठ्य पुस्तक और पूरक पाठ्य पुस्तक पर आधारित कुल 5 प्रश्न हैं, उप प्रश्नों की संख्या 21 है " * 2
    assert layout.garbled_text_layer(garbled)
    assert not layout.garbled_text_layer(clean)
    assert not layout.garbled_text_layer("Section A: answer any four questions. " * 5)
