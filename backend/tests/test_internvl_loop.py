"""A page reply that loops until it is cut off is a failed read, never an empty page; the retry is told how to avoid it."""
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.ocr import internvl
from app.ocr.parser import ParseError, extract_json_object
from app.ocr.schemas import QuestionPageResult
from app.cbse.extraction import Page as CBSEPage

# Page 4 of the English paper as InternVL answered it: two questions, then a Hindi passage repeated until the limit
LOOPED = ('{"page_number": 4, "questions": [{"raw_question_number": null, "question_text": "1. Were the cards '
          'distributed by Rahul?", "marks": 2}, {"raw_question_number": null, "question_text": "2. A drug has been '
          'invented for me by a scientist.", "marks": 2}, {"raw_question_number": null, "question_text": "(d) Translate '
          'the following into English-\\n' + "\\\\u0938\\\\u094b \\\\u092c\\\\u0947\\\\u090f \\\\u0926\\\\u0947\\\\u0915 " * 40)
GOOD = json.dumps({"page_number": 4, "questions": [
    {"raw_question_number": "(d)", "question_text": "Translate the following into English- [Hindi passage]", "marks": 4},
    {"raw_question_number": "Q5", "question_text": "Answer the following questions in about 30-40 words each.", "marks": 6}]})


def test_cut_off_page_reply_is_not_an_empty_page():
    with pytest.raises(ParseError):
        extract_json_object(LOOPED)
    assert internvl.is_looping(LOOPED)
    assert not internvl.is_looping('{"question_text": "He is worried ...................... examination. ________"}')


def test_retry_after_a_loop_asks_to_skip_the_unreadable_passage(monkeypatch):
    prompts = []

    def model(system, user, image_path, format=None, model=None):
        prompts.append(user)
        return GOOD if internvl.LOOP_HINT in user else LOOPED

    monkeypatch.setattr(internvl, "_call_once", model)
    call = internvl.chat_structured("system", "Read page 4.", QuestionPageResult)
    assert [q.raw_question_number for q in call.parsed.questions] == ["(d)", "Q5"]
    assert call.attempts == 2 and internvl.LOOP_HINT not in prompts[0] and internvl.LOOP_HINT in prompts[1]


def test_output_limit_splits_page_and_merges_regions(monkeypatch, tmp_path):
    image = tmp_path / "page.png"
    cv2.imwrite(str(image), np.full((1000, 700, 3), 255, dtype=np.uint8))
    calls = []

    def model(system, user, image_path, format=None, model=None):
        calls.append(Path(image_path).name)
        if len(calls) == 1:
            raise internvl.AIResponseError(
                "FAILED_PARSE", "AI response exceeded its token limit"
            )
        if "top_split" in Path(image_path).stem:
            return json.dumps({"page_number": 2, "questions": [{
                "raw_question_number": "1", "question_text": "Top question",
                "bbox": {"x": 10, "y": 100, "width": 500, "height": 80}
            }]})
        return json.dumps({"page_number": 2, "questions": [{
            "raw_question_number": "2", "question_text": "Bottom question",
            "bbox": {"x": 10, "y": 200, "width": 500, "height": 80}
        }]})

    monkeypatch.setattr(internvl, "_call_once", model)
    call = internvl.chat_structured("system", "Read page 2.", QuestionPageResult, image)
    assert [q.raw_question_number for q in call.parsed.questions] == ["1", "2"]
    assert call.parsed.questions[1].bbox.y == 660
    assert call.attempts == 2
    assert not list(tmp_path.glob("*_split.png"))


def test_output_limit_merges_cbse_fragments(monkeypatch, tmp_path):
    image = tmp_path / "cbse-page.png"
    cv2.imwrite(str(image), np.full((1000, 700, 3), 255, dtype=np.uint8))
    calls = []

    def model(system, user, image_path, format=None, model=None):
        calls.append(Path(image_path).name)
        if len(calls) == 1:
            raise internvl.AIResponseError(
                "FAILED_PARSE", "AI response exceeded its token limit"
            )
        root = 27 if "top_split" in Path(image_path).stem else 28
        return json.dumps({
            "page_number": 5,
            "metadata": {"class_level": 10 if root == 27 else None},
            "instructions": [f"instruction-{root}"],
            "fragments": [{
                "root": root,
                "text": f"Question {root}",
                "bbox": {"x": 10, "y": 100, "width": 500, "height": 80},
                "tree": {"id": f"q{root}", "kind": "point", "marks": 3,
                         "audience": ["standard"], "children": []},
            }],
            "issues": [],
        })

    monkeypatch.setattr(internvl, "_call_once", model)
    call = internvl.chat_structured("system", "Read CBSE page 5.", CBSEPage, image)
    assert [fragment.root for fragment in call.parsed.fragments] == [27, 28]
    assert call.parsed.fragments[1].bbox["y"] == 560
    assert call.parsed.fragments[0].tree.audience == "standard"
    assert call.parsed.instructions == ["instruction-27", "instruction-28"]
    assert call.parsed.metadata["class_level"] == 10
