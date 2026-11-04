"""Answer sheets whose answers are each written under their own number (CBSE Accountancy, Science).

The number the student wrote decides: content never moves a clearly written answer to another question, because
answers to one question often read like another's (journal lines, Assertion-Reason options, chemistry terms). Only a
number the model could not read with confidence is placed by content, and only forward from the last question read.
Each question gets exactly one answer: its parts ("I)", "B)") and its pieces on later pages are joined to it, and its
crop runs from where it starts to where the next answer starts, across pages, so tables and drawings show whole.
"""
from __future__ import annotations

import re
from typing import Any

from .answers import SegmentedAnswer
from .numbering import normalize_question_number, parent_number
from .recovery import find_recovery_candidates

SURE = 0.6       # question_number_confidence from which the written number is trusted
CONTENT = 0.7    # recovery score from which an unreadable number is placed by its content
_NUMBER = re.compile(r"\d+")


def _root(label: str | None) -> int | None:
    norm = parent_number(normalize_question_number(label) or "") if label else ""
    match = _NUMBER.search(norm or "")
    return int(match.group()) if match else None


_PLAIN_NUMBER = re.compile(r"^\W*(?:Q\.?\s*)?\d+\W*$", re.IGNORECASE)  # "23", "Q23", "23.", "19,"


def _written(block: Any, current: int | None) -> tuple[int | None, bool]:
    """The question number the student wrote on this block, and whether it can be trusted as written.

    A plain number heading the model gave no confidence for is still a written number. A bare part label ("a)",
    "(ii)") has no number of its own: the question the model put it under counts, but only from the current
    question on, so a part never jumps back to an earlier answer."""
    raw = block.raw_question_label or block.question_number
    conf = block.question_number_confidence
    # only digits are a written question number: "II) i)" is a part (Roman numerals number parts, not questions)
    written = _root(raw) if raw and re.search(r"\d", raw) else None
    if written is not None:
        plain = bool(raw and _PLAIN_NUMBER.match(raw.strip()))
        return written, (conf or 0) >= SURE or (conf is None and plain)
    placed = _root(block.normalized_question_label or block.question_number)
    if placed is not None and (conf or 0) >= SURE and (current is None or placed >= current):
        return placed, True
    return None, False


def _claimed_later(blocks, root: int, current: int) -> bool:
    """Whether a later block starts question `root` as written (the real one, so an earlier claim was misread)."""
    return any(_written(b, current)[0] == root and _written(b, current)[1] for _p, b in blocks)


def segment_answers(page_results: list[tuple[dict, Any]], canonical_questions: list[Any] | None = None):
    questions = {int(q.normalized_number): q for q in canonical_questions or [] if str(q.normalized_number).isdigit()}
    if not questions:
        return None
    blocks = []  # (page, answer block) in reading order
    for page, result in page_results:
        items = sorted(getattr(result, "answers", []) or [],
                       key=lambda a: (a.bbox.y if getattr(a, "bbox", None) else 0))
        blocks += [(page, a) for a in items]
    answers: dict[int, dict] = {}
    order: list[int] = []
    current = None
    for index, (page, block) in enumerate(blocks):
        text = (block.answer_text or "").strip()
        written, trusted = _written(block, current)
        sure = trusted and written in questions
        root = written if sure else None
        if (root is not None and current is not None and root == current + 2 and current + 1 in questions
                and current + 1 not in answers and _claimed_later(blocks[index + 1:], root, current)):
            # "28." read as "29." when the real 29 follows: the skipped question, unless the content says otherwise
            ranked = find_recovery_candidates(None, text, [questions[current + 1], questions[root]])
            if not ranked or _root(ranked[0].normalized_number) == current + 1 or ranked[0].score < CONTENT:
                root = current + 1
        if (root is not None and current is not None and root != current and (block.question_number_confidence or 0) < 0.8
                and _claimed_later(blocks[index + 1:], root, current)):
            # an unsure number that the next answer writes again ("C)" read as "28)" above the real "28) a)"): this
            # piece is the current answer's next part, unless its content clearly is the other question's
            ranked = find_recovery_candidates(None, text, [questions[current], questions[root]])
            if not (ranked and _root(ranked[0].normalized_number) == root and ranked[0].score >= CONTENT):
                root = current
        if root is not None and current is not None and root < current and root in answers:
            # back to a question already answered ("16 B" read as "11."): the current answer goes on, unless its
            # content clearly is the earlier question's (a part the student added later)
            ranked = find_recovery_candidates(None, text, [questions[root], questions[current]])
            if not (ranked and _root(ranked[0].normalized_number) == root and ranked[0].score >= CONTENT):
                root = current
        if root is None and text and written is not None:
            # a number written but not read with confidence: the question whose content this is, after the last
            # one read. A piece with no number at all ("MCQ's", a table carried over) continues the current answer
            later = [q for n, q in questions.items() if current is None or n > current]
            found = find_recovery_candidates(None, text, later)
            top = found[0] if found else None
            if top is not None and top.score >= CONTENT and (current is None or _root(top.normalized_number) <= current + 3):
                root = _root(top.normalized_number)
        if root is None:
            root = current  # no number of its own: the answer being written continues
        if root is None:
            continue
        piece = {"page": page, "bbox": block.bbox.model_dump() if getattr(block, "bbox", None) else None,
                 "next": next((b.bbox.model_dump() for p, b in blocks[index + 1:]
                               if p is page and getattr(b, "bbox", None)), None)}
        if root not in answers:
            answers[root] = {"label": block.raw_question_label or f"Q{root}", "texts": [], "pieces": [],
                             "confs": [], "page": page["page_number"]}
            order.append(root)
        entry = answers[root]
        if text and text not in entry["texts"]:
            entry["texts"].append(text)
        entry["pieces"].append(piece)
        if block.ocr_confidence is not None:
            entry["confs"].append(block.ocr_confidence)
        current = root
    out = []
    for position, root in enumerate(order, start=1):
        entry = answers[root]
        text = "\n".join(entry["texts"])
        first = next((p for p in entry["pieces"] if p["bbox"]), None)
        answer = SegmentedAnswer(
            raw_question_number=f"Q{root}", normalized_number=str(root), answer_text=text, raw_ocr_text=text,
            page_number=entry["page"], bbox=first["bbox"] if first else None,
            ocr_confidence=max(entry["confs"]) if entry["confs"] else None, position=position)
        answer.pieces = [_band(p) for p in entry["pieces"]]  # see pipeline._answer_crop
        out.append(answer)
    return out


def _band(piece: dict) -> tuple[int, dict | None]:
    """The answer's full-width band on one page, model-image pixels: from its top to the next answer's top (or the
    page bottom), so every line, table and account of it is inside and nothing of the next answer."""
    page, box, nxt = piece["page"], piece["bbox"], piece["next"]
    width, height = page.get("ocr_width") or 0, page.get("ocr_height") or 0
    if not box or not width or not height:
        return page["page_number"], None
    top = max(0.0, float(box["y"]) - 0.01 * height)
    bottom = float(nxt["y"]) if nxt and float(nxt["y"]) > top else float(height)
    return page["page_number"], {"x": 0, "y": top, "width": float(width), "height": max(1.0, bottom - top)}
