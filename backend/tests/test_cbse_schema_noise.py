import pytest
from pydantic import ValidationError

from app.cbse.extraction import Page


def test_misplaced_schema_diagnostic_does_not_discard_valid_source_fragment():
    page = Page.model_validate({"page_number": 1, "fragments": [
        {"root": 7, "text": "The complete printed answer", "marks": 2},
        "issues_found_in_source_text_or_structure_if_any",
    ]})
    assert len(page.fragments) == 1
    assert page.fragments[0].text == "The complete printed answer"


@pytest.mark.parametrize("fragments", [["issues_found_in_source_text"], [
    {"root": 7, "text": "Answer"}, "Unstructured answer text that might contain source content",
]])
def test_unrecognised_or_entirely_invalid_fragment_arrays_still_fail(fragments):
    with pytest.raises(ValidationError):
        Page.model_validate({"page_number": 1, "fragments": fragments})
