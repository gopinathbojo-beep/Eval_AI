"""The answer box is optional: every way a model writes it is read, and one that cannot be read is dropped instead
of failing the page (a page once failed because the box came as bbox_width/bbox_height or x2/y2)."""
import pytest

from app.ocr.schemas import StudentPageResult


def _page(box):
    return StudentPageResult.model_validate({"page_number": 6, "answers": [
        {"answer_id": "ans_001", "question_number": "Q24", "answer_text": "|b| = sqrt(35/6)", "bbox": box}]})


@pytest.mark.parametrize("box,expected", [
    ({"x": 43, "y": 173, "width": 950, "height": 550}, (43, 173, 950, 550)),
    ({"x": 43, "y": 173, "bbox_width": 950, "bbox_height": 550}, (43, 173, 950, 550)),
    ({"x": 118, "y": 115, "y2": 368, "x2": 848}, (118, 115, 730, 253)),
    ({"x1": 10, "y1": 20, "x2": 110, "y2": 70}, (10, 20, 100, 50)),
    ([10, 20, 110, 70], (10, 20, 100, 50)),
])
def test_every_box_shape_is_read(box, expected):
    b = _page(box).answers[0].bbox
    assert (b.x, b.y, b.width, b.height) == expected


@pytest.mark.parametrize("box", [{"x": 1}, {"x": "a", "y": 2, "width": 3, "height": 4}, "top-left", 7])
def test_an_unreadable_box_is_dropped_and_the_answer_kept(box):
    page = _page(box)
    assert page.answers[0].bbox is None and page.answers[0].answer_text == "|b| = sqrt(35/6)"
