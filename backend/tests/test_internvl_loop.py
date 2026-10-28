"""A page reply that loops until it is cut off is a failed read, never an empty page; the retry is told how to avoid it."""
import json

import pytest

from app.ocr import internvl
from app.ocr.parser import ParseError, extract_json_object
from app.ocr.schemas import QuestionPageResult

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
