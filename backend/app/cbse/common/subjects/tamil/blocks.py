"""Tamil OCR blocks, before the Tamil parsers (paper.py) read them. Tamil subjects only.

IndicOCR can return several questions as one block: "வினா 1 ... வினா 2. ... வினா 3. ...", or a section heading or
marks rule followed by its questions ("பகுதி - ஆ ...\nவினா 5. ..."). Each question becomes its own block, labelled
with the number printed on it. The same holds for question papers and answer keys.

On answer sheets it often boxes a handwritten question number on its own ("3)" in the margin) and then the answer
beside it, sometimes with the number repeated; the number and its answer are joined back into one block.
"""
from __future__ import annotations
import re
from typing import Any

from ...numbering import normalize_question_number, parent_number

# A question's number opening a line inside a block: "வினா 2. ...", "கேள்வி 5:", "வினா எண் 3."
_EMBEDDED_Q = re.compile(r"(?m)^[ \t]*(?:வினா|கேள்வி)[ \t]*(?:எண்[ \t]*)?(\d{1,2})[ \t]*[.:)][ \t]*")


def _split(item: Any, text_field: str, label_field: str) -> list[Any]:
    """One item per question in the block; the first keeps the block's own label, marks and other fields."""
    text = getattr(item, text_field) or ""
    label = (getattr(item, label_field) or "").strip()
    own = normalize_question_number(label) if label else None
    own_num = int(parent_number(own)) if own and parent_number(own).isdigit() else 0
    cuts = [m for m in _EMBEDDED_Q.finditer(text) if int(m.group(1)) > own_num and (m.start() > 0 or not label)]
    if not cuts:
        return [item]
    pieces = []
    head = text[:cuts[0].start()].strip()
    if head:
        pieces.append(item.model_copy(update={text_field: head}))
    for i, m in enumerate(cuts):
        body = text[m.end():cuts[i + 1].start() if i + 1 < len(cuts) else len(text)].strip()
        pieces.append(item.model_copy(update={label_field: m.group(1), text_field: body, "marks": None}))
    return pieces


def split_question_blocks(item: Any) -> list[Any]:
    """A question paper block (QuestionItem)."""
    return _split(item, "question_text", "raw_question_number")


def split_key_blocks(item: Any) -> list[Any]:
    """An answer key block (AnswerKeyItem)."""
    return _split(item, "answer_text", "question_number")


_LONE_NUMBER = re.compile(r"^\s*(\d{1,3})\s*[.)]?\s*$")


def _is_lone_number(item: dict) -> bool:
    """A block holding only its own question number: "3)" labelled 3 (not an answer "7" to question 3)."""
    lbl, text = item.get("question_number"), (item.get("answer_text") or "").strip()
    m = _LONE_NUMBER.match(text)
    return bool(lbl) and (not text or bool(m and normalize_question_number(m.group(1)) == normalize_question_number(lbl)))


def _union(a: dict | None, b: dict | None) -> dict | None:
    if not a or not b:
        return a or b
    x0, y0 = min(a["x"], b["x"]), min(a["y"], b["y"])
    x1, y1 = max(a["x"] + a["width"], b["x"] + b["width"]), max(a["y"] + a["height"], b["y"] + b["height"])
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}


def join_lone_numbers(items: list[dict]) -> list[dict]:
    """Student answer blocks: a lone question number takes the block after it as its answer. That block may repeat
    the number ("3)\\nஅ) ..."), start with a sub-part ("அ) ...") or have no label; one numbered for another question
    is left alone."""
    out: list[dict] = []
    for it in items:
        lone = out[-1] if out and _is_lone_number(out[-1]) else None
        own = normalize_question_number(lone["question_number"]) if lone else None
        nxt = normalize_question_number(it["question_number"]) if it.get("question_number") else None
        if lone is None or (nxt and nxt[0].isdigit() and nxt != own):
            out.append(it)
            continue
        sub = it["question_number"] if it.get("question_number") and nxt != own else None
        lone["answer_text"] = f"{sub} {it['answer_text']}".strip() if sub else it["answer_text"]
        lone["bbox"] = _union(lone.get("bbox"), it.get("bbox"))
    return out
