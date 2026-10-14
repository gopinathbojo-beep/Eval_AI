"""Student Answer Segmentation and Grouping Engine.

Turns the per-page OCR blocks into one record per answered question:
- Unlabelled blocks continue the answer in progress, including across page breaks (an answer that starts at the
  bottom of page 1 and continues at the top of page 2 stays ONE answer).
- A repeated label ("Q3" again at the top of the next page, "Q3 contd") continues that answer.
- Content numbering inside an answer (1), 2), (i), (ii), bullets) is kept as answer text, not split off.
- A bare part label ("(b)", "b)") after "7(a)" starts the next part "7(b)".
- When the exam's question labels are known they decide ambiguous cases ("2)" under Q7 is a point of the
  answer unless it is the start of an unanswered exam question 2).
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Iterable
from .numbering import extract_subquestion_token, is_sub_question, normalize_question_number, parent_number


@dataclass
class SegmentedAnswer:
    raw_question_number: str | None
    normalized_number: str | None
    answer_text: str
    raw_ocr_text: str
    page_number: int
    bbox: dict | None
    ocr_confidence: float | None
    position: int = 0


_NULL_LABELS = {"", "null", "none", "?", "unknown", "[unclear]", "unclear", "n/a", "-"}
_CONT_LABEL = re.compile(r"\b(?:cont|contd|continued|continuation)\b\.?", re.IGNORECASE)
# "1)", "2.", "(3)", "ii)", "(iv)" - forms that are used both for question labels and for points inside an answer
_BULLET_LABEL = re.compile(r"^\s*(?:(\d{1,2}|[ivxIVX]{1,4})\s*[\)\.\-]|\(\s*(\d{1,2}|[a-zA-Z]{1,4})\s*\))\s*$")
_BULLET_TEXT = re.compile(r"^\s*(?:\d{1,2}\s*[\)\.]|\(\s*(?:\d{1,2}|[ivx]{1,4})\s*\)|[ivx]{1,4}\s*\)|[•\-\*→])\s*", re.IGNORECASE)
_ROMAN_PARTS = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"}
LOW_LABEL_CONFIDENCE = 0.5


def _merge_bboxes(bb1: dict | None, bb2: dict | None) -> dict | None:
    if not bb1:
        return bb2
    if not bb2:
        return bb1
    try:
        x1 = min(bb1["x"], bb2["x"])
        y1 = min(bb1["y"], bb2["y"])
        x2 = max(bb1["x"] + bb1["width"], bb2["x"] + bb2["width"])
        y2 = max(bb1["y"] + bb1["height"], bb2["y"] + bb2["height"])
        return {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}
    except (KeyError, TypeError):
        return bb1


@dataclass
class _Group:
    raw_label: str | None
    norm: str | None
    page: int
    bbox: dict | None = None
    parts: list[str] = field(default_factory=list)
    confs: list[float] = field(default_factory=list)
    label_conf: float | None = None
    last_bullet: int | None = None
    last_bullet_style: str | None = None
    last_page: int = 0

    def __post_init__(self):
        self.last_page = self.page

    def add(self, text: str, page: int, bbox: dict | None, conf: float | None, prefix: str | None = None):
        t = f"{prefix} {text}".strip() if prefix else text
        if t:
            self.parts.append(t)
        if bbox and page == self.page:
            self.bbox = _merge_bboxes(self.bbox, bbox)
        if conf is not None:
            self.confs.append(conf)
        self.last_page = max(self.last_page, page)


def _is_null_label(lbl: str | None) -> bool:
    return lbl is None or lbl.strip().lower() in _NULL_LABELS


def _has_question(known: set[str] | None, norm: str) -> bool:
    """Exam has this question or sub-questions of it."""
    return bool(known) and (norm in known or any(k.startswith(norm + "(") for k in known))


def _bullet_style(s: str) -> str:
    """Delimiter style of a list marker: '1)' -> ')', '2.' -> '.', '(3)' -> '()'."""
    s = s.strip()
    if s.startswith("("):
        return "()"
    m = re.match(r"^\w{1,4}\s*([\)\.\-])", s)
    return m.group(1) if m else ""


def _bullet_token(lbl: str) -> str | None:
    m = _BULLET_LABEL.match(lbl)
    if not m:
        return None
    return (m.group(1) or m.group(2)).lower()


def _classify(lbl: str, cur: _Group | None, known: set[str] | None, seen: set[str],
              page_num: int) -> tuple[str, str | None]:
    """Decide what a labelled block is. Returns (kind, normalized) with kind in
    'bullet' (point inside current answer), 'continue' (same answer goes on), 'new' (start a new answer)."""
    cur_norm = cur.norm if cur else None
    if _CONT_LABEL.search(lbl):
        base = normalize_question_number(_CONT_LABEL.sub("", lbl).strip(" -:.()"))
        if cur and (base is None or base == cur_norm):
            return "continue", cur_norm
    norm = normalize_question_number(lbl)
    # The same label again after a page break is the answer carrying on ("Q3" repeated at the top of page 2).
    # On the same page it is a second attempt -> separate record, flagged as a duplicate for the teacher.
    if cur_norm and norm == cur_norm and page_num > cur.last_page:
        return "continue", cur_norm

    tok = _bullet_token(lbl)
    sub_tok = extract_subquestion_token(lbl)

    # Bare part label: "(b)", "b)", "(ii)", "ii)" relative to the current question.
    # ("ii)" also normalizes to main question 2, so roman labels are checked against both readings.)
    part = sub_tok or (tok if tok and not tok.isdigit() else None)
    if cur_norm and part:
        parent = parent_number(cur_norm)
        nested = f"{cur_norm}({part})"
        sibling = f"{cur_norm.rsplit('(', 1)[0]}({part})" if is_sub_question(cur_norm) else f"{parent}({part})"
        if known:
            for cand in (nested, sibling, f"{parent}({part})"):
                if cand in known:
                    return "new", cand
        if norm and part in _ROMAN_PARTS and not is_sub_question(cur_norm) and parent.isdigit() \
                and norm == str(int(parent) + 1) and (not known or norm in known):
            return "new", norm  # roman-numbered paper: "II." right after question I
        if known:
            return "bullet", None
        # Without the exam's labels: letters are parts, roman numerals inside a part are points
        if part in _ROMAN_PARTS and is_sub_question(cur_norm):
            return "bullet", None
        return "new", sibling

    # Numeric "2)" / "2." / "(2)" while an answer is in progress: a point of that answer, or a new question?
    if cur and tok and tok.isdigit():
        n = int(tok)
        running_list = cur.last_bullet is not None and n == cur.last_bullet + 1 \
            and cur.last_bullet_style == _bullet_style(lbl)
        if known is not None and known:
            if not _has_question(known, str(n)) or str(n) in seen or running_list:
                return "bullet", None
            return "new", norm
        cur_p = parent_number(cur_norm) if cur_norm else ""
        if running_list or is_sub_question(cur_norm or "") or (cur_p.isdigit() and int(cur_p) > n and str(n) in seen) \
                or (cur_p.isdigit() and n == 1 and int(cur_p) > 1):
            return "bullet", None
    return "new", norm


def segment_student_answers(page_results: list[tuple[dict, Any]],
                            known_numbers: Iterable[str] | None = None) -> list[SegmentedAnswer]:
    """Group raw OCR blocks into coherent student answers across pages.

    `known_numbers` are the exam's normalized question numbers; when given they resolve ambiguous labels.
    """
    known = {k for k in (known_numbers or []) if k} or None
    grouped: list[SegmentedAnswer] = []
    seen: set[str] = set()
    cur: _Group | None = None

    def flush():
        nonlocal cur
        if cur is None:
            return
        text = "\n".join(cur.parts).strip()
        if text or cur.raw_label:
            conf = sum(cur.confs) / len(cur.confs) if cur.confs else None
            if cur.label_conf is not None and cur.label_conf < LOW_LABEL_CONFIDENCE:
                conf = min(conf, cur.label_conf) if conf is not None else cur.label_conf
            grouped.append(SegmentedAnswer(
                raw_question_number=cur.raw_label,
                normalized_number=cur.norm,
                answer_text=text,
                raw_ocr_text=text,
                page_number=cur.page,
                bbox=cur.bbox,
                ocr_confidence=round(conf, 2) if conf is not None else None,
                position=len(grouped) + 1,
            ))
        if cur.norm:
            seen.add(cur.norm)
            seen.add(parent_number(cur.norm))
        cur = None

    for page_info, page_res in page_results:
        page_num = page_info["page_number"]
        for a in getattr(page_res, "answers", []) or []:
            text = (a.answer_text or "").strip()
            raw_lbl = (a.question_number or "").strip() or None
            bb = a.bbox.model_dump() if getattr(a, "bbox", None) else None
            conf = getattr(a, "ocr_confidence", None)
            label_conf = getattr(a, "question_number_confidence", None)

            if _is_null_label(raw_lbl):
                if not text:
                    continue
                if cur is None:
                    # Text before any label (first page top, or the student never numbered it)
                    cur = _Group(None, None, page_num, bb)
                cur.add(text, page_num, bb, conf)
                if _BULLET_TEXT.match(text):
                    m = re.match(r"^\s*\(?(\d{1,2})", text)
                    if m:
                        cur.last_bullet, cur.last_bullet_style = int(m.group(1)), _bullet_style(text)
                continue

            kind, norm = _classify(raw_lbl, cur, known, seen, page_num)
            if kind == "continue" and cur is not None:
                cur.add(text, page_num, bb, conf)
                continue
            if kind == "bullet" and cur is not None:
                cur.add(text, page_num, bb, conf, prefix=raw_lbl)
                tok = _bullet_token(raw_lbl)
                if tok and tok.isdigit():
                    cur.last_bullet, cur.last_bullet_style = int(tok), _bullet_style(raw_lbl)
                continue

            flush()
            if norm and norm != normalize_question_number(raw_lbl):
                # Bare part label resolved against the previous question: "(b)" after Q7(a) -> Q7(b)
                raw_lbl = f"Q{norm}"
            cur = _Group(raw_lbl, norm, page_num, bb, label_conf=label_conf)
            cur.add(text, page_num, None, conf)

    flush()
    for i, g in enumerate(grouped, 1):
        g.position = i
    return grouped
