"""Student Answer Segmentation and Grouping Engine.

Solves:
- Answer splitting into multiple fragmented records (e.g. Q7(a) broken by '1)' and '2)').
- Missing question number treated as new answer instead of continuation.
- Content numbering (1), 2), 3), (i), (ii)) confused with question numbering.
- Loss of continuation text across OCR blocks and pages.
- Loss of sub-question context (current_question = 7, part = a).
- Reconstructs semantic answer groups with merged text, bounding boxes, and confidence.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Any
from .numbering import normalize_question_number, is_sub_question, parent_number


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


# Sub-part markers: e.g. "(a)", "(b)", "a)", "b)", "(i)", "(ii)"
_SUBPART_PATTERN = re.compile(
    r"^\s*\(?\s*([a-zA-Z]|[ivxIVX]{1,4})\s*\)?\s*[\:\.\)]?\s*$",
)


def _is_content_bullet(label: str | None, text: str, current_q: str | None) -> bool:
    """Determine if a block's label/prefix is merely an answer content bullet rather than a new exam question."""
    if not current_q:
        return False
    lbl_clean = str(label or "").strip()
    txt_clean = text.strip()

    # Punctuation/delimiter indicating list bullet: '1)', '2.', '(1)', '(2)', '(i)'
    bullet_delim = re.match(r"^(?:(\d{1,2}|[ivxIVX]{1,4})\s*[\)\.\-]|(?:\(([0-9a-zA-Z]{1,4})\)))\s*$", lbl_clean)
    text_delim = re.match(r"^(?:(\d{1,2}|[ivxIVX]{1,4})\s*[\)\.\-]|(?:\(([0-9a-zA-Z]{1,4})\)))\s*", txt_clean)

    if bullet_delim:
        num = bullet_delim.group(1) or bullet_delim.group(2)
        curr_p = parent_number(current_q)
        # If current question is e.g. 7, and bullet is 1 or 2
        if curr_p.isdigit() and num.isdigit():
            if int(curr_p) > int(num):
                return True
        elif is_sub_question(current_q):
            # Inside sub-questions like 7(a), any 1), 2), 3) or (i), (ii) is a content bullet
            if num.isdigit() or num.lower() in ("i", "ii", "iii", "iv", "v", "a", "b", "c"):
                return True

    if text_delim and not lbl_clean:
        # Unlabelled block starting with 1), 2), etc.
        return True

    return False


def _is_subpart_transition(label: str | None, current_parent: str | None) -> str | None:
    """If the label is just a bare subpart like '(b)' or 'b)' or 'part b', return the subpart token."""
    if not label or not current_parent:
        return None
    s = str(label).strip()
    # Ensure it's not a full question like "3(b)"
    if "(" in s and any(c.isdigit() for c in s.split("(")[0]):
        return None
    m = _SUBPART_PATTERN.match(s)
    if m:
        sub = m.group(1).lower()
        if len(sub) <= 4:
            return sub
    return None


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


def segment_student_answers(page_results: list[tuple[dict, Any]]) -> list[SegmentedAnswer]:
    """Segment and group raw OCR blocks into coherent student answers across pages."""
    grouped: list[SegmentedAnswer] = []

    curr_raw_label: str | None = None
    curr_norm_num: str | None = None
    curr_text_parts: list[str] = []
    curr_page: int = 1
    curr_bbox: dict | None = None
    curr_confs: list[float] = []

    def flush_current():
        nonlocal curr_raw_label, curr_norm_num, curr_text_parts, curr_page, curr_bbox, curr_confs
        if not curr_text_parts and not curr_raw_label:
            return
        full_text = "\n".join(curr_text_parts).strip()
        if not full_text and not curr_raw_label:
            return
        avg_conf = sum(curr_confs) / len(curr_confs) if curr_confs else None

        ans = SegmentedAnswer(
            raw_question_number=curr_raw_label,
            normalized_number=curr_norm_num,
            answer_text=full_text,
            raw_ocr_text=full_text,
            page_number=curr_page,
            bbox=curr_bbox,
            ocr_confidence=round(avg_conf, 2) if avg_conf is not None else None,
            position=len(grouped) + 1,
        )
        grouped.append(ans)

        curr_raw_label = None
        curr_norm_num = None
        curr_text_parts = []
        curr_bbox = None
        curr_confs = []

    for page_info, page_res in page_results:
        page_num = page_info["page_number"]
        answers_raw = getattr(page_res, "answers", [])

        for a in answers_raw:
            text = (a.answer_text or "").strip()
            raw_lbl = (a.question_number or "").strip() or None
            bb = a.bbox.model_dump() if getattr(a, "bbox", None) else None
            conf = getattr(a, "ocr_confidence", None)

            # Check if this item is a content bullet e.g. "1)", "2)", "3)" under an ongoing question
            if curr_norm_num and _is_content_bullet(raw_lbl, text, curr_norm_num):
                bullet_prefix = f"{raw_lbl} " if raw_lbl else ""
                curr_text_parts.append(f"{bullet_prefix}{text}".strip())
                if bb and curr_page == page_num:
                    curr_bbox = _merge_bboxes(curr_bbox, bb)
                if conf is not None:
                    curr_confs.append(conf)
                continue

            # Case: Label is null/empty or 'none'/'unclear'
            if raw_lbl is None or raw_lbl.lower() in ("null", "none", "?", "unknown", "[unclear]"):
                # Top-of-page continuation across pages
                if page_num > 1 and not curr_text_parts and grouped:
                    last = grouped[-1]
                    last.answer_text = f"{last.answer_text}\n{text}".strip()
                    last.raw_ocr_text = f"{last.raw_ocr_text}\n{text}".strip()
                    continue
                else:
                    # Unnumbered independent block -> create unmapped record
                    flush_current()
                    curr_raw_label = None
                    curr_norm_num = None
                    curr_page = page_num
                    if text:
                        curr_text_parts.append(text)
                    curr_bbox = bb
                    if conf is not None:
                        curr_confs.append(conf)
                    flush_current()
                    continue

            # Case: Label is a bare sub-part transition e.g. "(b)", "b)" under current parent
            sub_part = _is_subpart_transition(raw_lbl, parent_number(curr_norm_num) if curr_norm_num else None)
            if sub_part and curr_norm_num:
                parent = parent_number(curr_norm_num)
                flush_current()
                curr_raw_label = f"Q{parent}({sub_part})"
                curr_norm_num = f"{parent}({sub_part})"
                curr_page = page_num
                if text:
                    curr_text_parts.append(text)
                curr_bbox = bb
                if conf is not None:
                    curr_confs.append(conf)
                continue

            # Case: Genuine question label (e.g. Q1, 2, 3, 3(b))
            norm = normalize_question_number(raw_lbl)
            flush_current()
            curr_raw_label = raw_lbl
            curr_norm_num = norm
            curr_page = page_num
            if text:
                curr_text_parts.append(text)
            curr_bbox = bb
            if conf is not None:
                curr_confs.append(conf)

    flush_current()
    for i, g in enumerate(grouped, 1):
        g.position = i
    return grouped
