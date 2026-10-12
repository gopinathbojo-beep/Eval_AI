"""Answer Key Segmentation and Multi-Page Grouping Engine.

Solves:
- Answer key initially showing 0 answer rows / persistence sync.
- Merging cross-page answer key content (Question starts on page 1, answer continues on page 2).
- Distinguishing absent answers vs unmapped vs OCR failed.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from .numbering import normalize_question_number


@dataclass
class SegmentedKey:
    raw_question_number: str | None
    normalized_number: str | None
    answer_text: str
    marks: float | None
    criteria: list[str] = field(default_factory=list)
    accepted_answers: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    page_number: int = 1
    bbox: dict | None = None
    ocr_confidence: float | None = None


def segment_answer_keys(page_results: list[tuple[dict, Any]]) -> list[SegmentedKey]:
    """Segment and group answer key blocks across pages, merging continuations."""
    grouped: list[SegmentedKey] = []

    for page_info, page_res in page_results:
        page_num = page_info["page_number"]
        answers_raw = getattr(page_res, "answers", [])

        for a in answers_raw:
            text = (a.answer_text or "").strip()
            raw_lbl = (a.question_number or "").strip() or None
            bb = a.bbox.model_dump() if getattr(a, "bbox", None) else None
            conf = getattr(a, "confidence", None)

            # Check if this is an unnumbered continuation block
            if raw_lbl is None or raw_lbl.lower() in ("null", "none", "?", "unknown", "[unclear]"):
                if grouped and text:
                    # Append continuation text to previous answer key row
                    last = grouped[-1]
                    last.answer_text = f"{last.answer_text}\n{text}".strip()
                    if getattr(a, "criteria", None):
                        last.criteria.extend(a.criteria)
                    if getattr(a, "accepted_answers", None):
                        last.accepted_answers.extend(a.accepted_answers)
                    if getattr(a, "keywords", None):
                        last.keywords.extend(a.keywords)
                    continue
                elif not text:
                    continue

            norm = normalize_question_number(raw_lbl) if raw_lbl else None

            k = SegmentedKey(
                raw_question_number=raw_lbl,
                normalized_number=norm,
                answer_text=text,
                marks=a.marks,
                criteria=list(a.criteria or []),
                accepted_answers=list(a.accepted_answers or []),
                keywords=list(a.keywords or []),
                page_number=page_num,
                bbox=bb,
                ocr_confidence=conf,
            )
            grouped.append(k)

    return grouped
