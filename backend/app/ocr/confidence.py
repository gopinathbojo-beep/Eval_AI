"""How sure InternVL was of the text it read, measured from the model itself (Ollama's token log-probabilities).

InternVL replies in JSON, one token at a time, choosing the most likely token (temperature 0). The probability of the
chosen token is its certainty at that step. Only the tokens inside the transcribed text count (answer_text,
question_text): JSON punctuation and field names say nothing about how well the page was read. As in IndicOCR's
service (indic_ocr_service/confidence.py), Tesseract and Google Vision:
  word   the probability of the whole word: the product of its tokens' probabilities
  field  the mean of its word confidences

This replaces the "confidence" the model writes into its own JSON, which it mostly copies from the prompt's example.
"""
from __future__ import annotations
import math
import re

_TEXT_FIELDS = {"questions": "question_text", "answers": "answer_text"}  # the transcribed text of each page list
_WORD = re.compile(r"(?:(?!\\[nrt])[^\s])+")  # a run of characters between spaces and JSON escapes \n \r \t


def string_spans(raw: str, key: str) -> list[tuple[int, int]]:
    """Character spans of the string values of `key` in a JSON text, in order (inside the quotes)."""
    spans = []
    for m in re.finditer(rf'"{re.escape(key)}"\s*:\s*"', raw):
        i = m.end()
        while i < len(raw) and raw[i] != '"':
            i += 2 if raw[i] == "\\" else 1
        spans.append((m.end(), min(i, len(raw))))
    return spans


def _token_offsets(raw: str, logprobs: list[dict]) -> list[tuple[int, float]] | None:
    """(character offset where each token starts, its log-probability); None when the tokens do not spell `raw`."""
    data = raw.encode("utf-8")
    out, pos = [], 0
    for t in logprobs:
        b = bytes(t.get("bytes") or t.get("token", "").encode("utf-8"))
        if data[pos:pos + len(b)] != b:
            return None
        out.append((len(data[:pos].decode("utf-8", "ignore")), float(t.get("logprob") or 0.0)))
        pos += len(b)
    return out if pos == len(data) else None


def field_confidences(raw: str, logprobs: list[dict] | None, key: str) -> list[float | None] | None:
    """The measured confidence of each `key` value in the reply, in order; None when it cannot be measured."""
    if not logprobs:
        return None
    tokens = _token_offsets(raw, logprobs)
    if tokens is None:
        return None
    out: list[float | None] = []
    for start, end in string_spans(raw, key):
        words = [(start + m.start(), start + m.end()) for m in _WORD.finditer(raw[start:end])]
        totals = [0.0] * len(words)
        for k, (offset, lp) in enumerate(tokens):
            nxt = tokens[k + 1][0] if k + 1 < len(tokens) else len(raw)
            # a token counts for the word its characters fall in (" cycle" belongs to "cycle", not to the space)
            for w, (ws, we) in enumerate(words):
                if offset < we and nxt > ws:
                    totals[w] += lp
                    break
        out.append(round(sum(math.exp(t) for t in totals) / len(totals), 3) if totals else None)
    return out


def apply(parsed, raw: str, logprobs: list[dict] | None) -> None:
    """Put the measured confidences on the page's items (question/answer-key `confidence`, a student answer's
    `ocr_confidence`), when there is one measurement per item."""
    for attr, key in _TEXT_FIELDS.items():
        items = getattr(parsed, attr, None)
        if not items:
            continue
        confs = field_confidences(raw, logprobs, key)
        if not confs or len(confs) != len(items):
            continue
        for item, c in zip(items, confs):
            if c is None:
                continue
            if hasattr(item, "ocr_confidence"):
                item.ocr_confidence = c
            elif hasattr(item, "confidence"):
                item.confidence = c
