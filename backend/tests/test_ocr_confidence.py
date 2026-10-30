"""Reading confidence measured from InternVL's token probabilities, not the number it writes in its JSON."""
import math

from app.ocr import confidence
from app.ocr.schemas import AnswerKeyPageResult, StudentPageResult


def _tokens(*pieces):
    """(text, probability) pieces as Ollama's logprobs list."""
    return [{"token": t, "logprob": math.log(p), "bytes": list(t.encode("utf-8"))} for t, p in pieces]


RAW = '{"answers": [{"question_number": "1", "answer_text": "நீர் சுழற்சி\nமழை", "confidence": 0.95}]}'
LOGPROBS = _tokens(('{"answers": [{"question_number": "1", "answer_text": "', 0.99), ("நீ", 0.9), ("ர்", 0.5),
                   (" சுழ", 0.99), ("ற்சி", 1.0), ("\n", 0.99), ("மழை", 0.8), ('", "confidence": 0.95}]}', 0.99))


def test_word_confidence_is_the_product_of_its_tokens_and_the_field_their_mean():
    assert confidence.field_confidences(RAW, LOGPROBS, "answer_text") == [round((0.45 + 0.99 + 0.8) / 3, 3)]


def test_measured_confidence_replaces_the_models_own():
    page = StudentPageResult.model_validate({"answers": [{"question_number": "1", "answer_text": "நீர் சுழற்சி\nமழை",
                                                          "ocr_confidence": 0.95}]})
    confidence.apply(page, RAW, LOGPROBS)
    assert page.answers[0].ocr_confidence == round((0.45 + 0.99 + 0.8) / 3, 3)
    key = AnswerKeyPageResult.model_validate({"answers": [{"question_number": "1", "answer_text": "x", "confidence": 0.95}]})
    confidence.apply(key, RAW, None)  # no logprobs (an older Ollama): the model's own number stays
    assert key.answers[0].confidence == 0.95
    confidence.apply(key, RAW, _tokens(("something else", 0.5)))  # tokens that do not spell the reply: unchanged
    assert key.answers[0].confidence == 0.95
