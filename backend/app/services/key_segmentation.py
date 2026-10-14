"""Answer Key Segmentation and Multi-Page Grouping Engine.

Solves:
- Answer key initially showing 0 answer rows / persistence sync.
- Merging cross-page answer key content (Question starts on page 1, answer continues on page 2).
- Distinguishing absent answers vs unmapped vs OCR failed.
"""
from __future__ import annotations
import re
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


def parse_criteria_marks(criteria: list[str], text: str = "") -> float | None:
    """Parse question marks from marking scheme criteria or inline totals."""
    # 1. Check for explicit question marking scheme total: e.g. "Marking Scheme (5 Marks Total):"
    m_tot = re.search(r"Marking\s+Scheme\s*\(\s*(\d+(?:\.\d+)?)\s*(?:marks?|m)\s*(?:Total)?\s*\)", text, re.I)
    if m_tot:
        return float(m_tot.group(1))

    # 2. Check each criteria line for explicit total:
    for c in criteria:
        m_tot = re.search(r"\(\s*(\d+(?:\.\d+)?)\s*(?:marks?|m)\s*Total\s*\)", c, re.I)
        if m_tot:
            return float(m_tot.group(1))

    # 3. Check for "1 mark per ... pair" or "1 mark each"
    for c in criteria:
        if "1 mark per" in c.lower() or "1 mark each" in c.lower():
            return 3.0

    # 4. Sum of itemized criteria marks:
    total = 0.0
    found_count = 0
    for c in criteria:
        # Ignore deduction notes like "(Deduct 1/2 mark...)"
        if re.search(r"\bdeduct\b", c, re.I):
            continue
        # Pattern A: starts with "1 Mark:" or "1.5 Marks:"
        m_start = re.match(r"^\s*(\d+(?:\.\d+)?)\s*(?:marks?|m)\b\s*[:\-]", c, re.I)
        if m_start:
            total += float(m_start.group(1))
            found_count += 1
            continue
        # Pattern B: ends with "(1 Mark)" or "(1.5 Marks)"
        m_end = re.search(r"\(\s*(\d+(?:\.\d+)?)\s*(?:marks?|m)\s*\)\s*$", c, re.I)
        if m_end:
            total += float(m_end.group(1))
            found_count += 1
            continue

    if found_count > 0 and total > 0:
        return total

    return None


def extract_from_full_pdf_text(full_text: str, norm_num: str) -> tuple[str | None, list[str]]:
    """Extract answer text and criteria for a specific question number from full document text."""
    pat = re.compile(rf"(?:^|\n)\s*(?:Q\.?\s*{norm_num}|{norm_num}\.)\b[^\n]*\n(.*)", re.DOTALL | re.I)
    m = pat.search(full_text)
    if not m:
        return None, []

    rest = m.group(1)
    # Stop at next question
    next_q = re.search(r"(?:^|\n)\s*(?:Q\.?\s*\d+|\d+\.)\b", rest, re.I)
    block = rest[:next_q.start()].strip() if next_q else rest.strip()

    # Strip page boundary markers
    clean_block = re.sub(r"--- PAGE \d+ ---", "", block).strip()

    # Extract marking scheme from clean_block
    ms_match = re.search(r"(?:Marking\s+Scheme\s*(\([^\)]+\))?[:\s]*)(.*)", clean_block, re.DOTALL | re.I)
    criteria = []
    answer_text = clean_block
    if ms_match:
        answer_text = clean_block[:ms_match.start()].strip()
        ms_text = ms_match.group(2)
        crit_items = re.findall(r"(?:^|\n)\s*[o•\-\*]?\s*(\d+(?:\.\d+)?\s*marks?[:\s][^\n]+|1 mark per[^\n]+|\([^\)]+marks?[^\)]*\)[^\n]*)", ms_text, re.I)
        criteria = [c.strip() for c in crit_items if c.strip()]

    # Strip "Answer:" prefix from answer_text
    answer_text = re.sub(r"^\s*[•\-\*]?\s*Answer\s*:\s*", "", answer_text, flags=re.I).strip()
    return answer_text, criteria


def segment_answer_keys(page_results: list[tuple[dict, Any]]) -> list[SegmentedKey]:
    """Segment and group answer key blocks across pages, merging continuations and computing marks."""
    grouped: list[SegmentedKey] = []
    full_text = ""

    # Aggregate digital text across pages if available
    for page_info, _ in page_results:
        pt = page_info.get("page_text") or ""
        if pt:
            full_text += f"\n--- PAGE {page_info.get('page_number', 1)} ---\n" + pt

    for page_info, page_res in page_results:
        page_num = page_info["page_number"]
        answers_raw = getattr(page_res, "answers", [])

        for a in answers_raw:
            text = (a.answer_text or "").strip()
            raw_lbl = (a.question_number or "").strip() or None
            bb = a.bbox.model_dump() if getattr(a, "bbox", None) else None
            conf = getattr(a, "confidence", None)

            norm = normalize_question_number(raw_lbl) if raw_lbl else None
            is_cont_label = bool(raw_lbl and re.search(r"\b(?:cont|continued|contd)\b", raw_lbl, re.IGNORECASE))
            is_same_q_new_page = bool(grouped and norm and norm == grouped[-1].normalized_number and page_num > grouped[-1].page_number)
            is_unnumbered = raw_lbl is None or raw_lbl.lower() in ("null", "none", "?", "unknown", "[unclear]", "")

            # Check if this is an unnumbered continuation block, explicit continuation, or same question on next page
            if is_unnumbered or is_cont_label or is_same_q_new_page:
                if grouped and text:
                    # Append continuation text to previous answer key row
                    last = grouped[-1]
                    sep = "\n\n" if "\n" in text or "|" in text else " "
                    last.answer_text = f"{last.answer_text}{sep}{text}".strip()
                    if getattr(a, "criteria", None):
                        last.criteria.extend(a.criteria)
                    if getattr(a, "accepted_answers", None):
                        last.accepted_answers.extend(a.accepted_answers)
                    if getattr(a, "keywords", None):
                        last.keywords.extend(a.keywords)

                    # Recompute marks for the merged question
                    c_marks = parse_criteria_marks(last.criteria, last.answer_text)
                    if c_marks is not None:
                        last.marks = c_marks
                    elif getattr(a, "marks", None) is not None and last.marks is None:
                        last.marks = a.marks
                    continue
                elif not text:
                    continue

            crit_list = list(a.criteria or [])
            calc_m = parse_criteria_marks(crit_list, text)
            init_marks = calc_m if calc_m is not None else a.marks

            k = SegmentedKey(
                raw_question_number=raw_lbl,
                normalized_number=norm,
                answer_text=text,
                marks=init_marks,
                criteria=crit_list,
                accepted_answers=list(a.accepted_answers or []),
                keywords=list(a.keywords or []),
                page_number=page_num,
                bbox=bb,
                ocr_confidence=conf,
            )
            grouped.append(k)

    # Recovery / alignment pass using full_text from document
    if full_text:
        for k in grouped:
            if not k.normalized_number:
                continue
            rec_ans, rec_crit = extract_from_full_pdf_text(full_text, k.normalized_number)
            if rec_ans and (len(k.answer_text) < 15 or len(rec_ans) > len(k.answer_text)):
                k.answer_text = rec_ans
            if rec_crit:
                k.criteria = rec_crit
            c_marks = parse_criteria_marks(k.criteria, k.answer_text)
            if c_marks is not None:
                k.marks = c_marks

    return grouped

