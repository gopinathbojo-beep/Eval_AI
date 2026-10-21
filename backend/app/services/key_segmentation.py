"""Answer Key Segmentation and Multi-Page Grouping Engine.

Solves:
- Answer key initially showing 0 answer rows / persistence sync.
- Merging cross-page answer key content (Question starts on page 1, answer continues on page 2).
- Distinguishing absent answers vs unmapped vs OCR failed.
- Splitting swallowed questions within a single OCR block.
- Accurate criteria parsing and marks calculation matching exam questions.
""" 
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any
from .numbering import normalize_question_number, parent_number


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

    # 3. Sum of itemized criteria marks:
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


def extract_criteria_from_block(text: str) -> tuple[str, list[str]]:
    """Extract clean answer text and itemized criteria if a Marking Scheme is embedded in the block."""
    ms_match = re.search(r"(?:Marking\s+Scheme\s*(?:\([^\)]+\))?[:\s]*)(.*)", text, re.DOTALL | re.I)
    if not ms_match:
        return text.strip(), []
    ans_text = text[:ms_match.start()].strip()
    crit_items = re.findall(
        r"(?:^|\n)\s*[o•\-\*]?\s*(\d+(?:\.\d+)?\s*marks?[:\s][^\n]+|1 mark per[^\n]+|\([^\)]+marks?[^\)]*\)[^\n]*)",
        text[ms_match.start():],
        re.I,
    )
    return ans_text, [c.strip() for c in crit_items if c.strip()]


def split_key_text(raw_lbl: str | None, text: str) -> list[tuple[str | None, str]]:
    """Split an answer block if it swallowed subsequent question keys (e.g. Q8 inside Q7, or Ans 9 inside Q8)."""
    pat = re.compile(
        r"(?:\n+)\s*(?:(?:Q(?:uestion)?|Ans(?:wer)?)\.?\s*([0-9]{1,3})|([0-9]{1,3})\.)[\.\:\s\-\,]+",
        re.I,
    )
    boundaries = []
    for m in pat.finditer(text):
        if m.start() > 15:
            q_num = m.group(1) or m.group(2)
            boundaries.append((m.start(), f"Q{q_num}"))
    if not boundaries:
        return [(raw_lbl, text)]

    res: list[tuple[str | None, str]] = []
    last_idx = 0
    curr_lbl = raw_lbl
    for b_start, b_lbl in boundaries:
        chunk = text[last_idx:b_start].strip()
        if chunk:
            if raw_lbl == b_lbl and last_idx == 0:
                res.append((None, chunk))
            else:
                res.append((curr_lbl, chunk))
        curr_lbl = b_lbl
        last_idx = b_start
    rem = text[last_idx:].strip()
    if rem:
        res.append((curr_lbl, rem))
    return res


def extract_from_full_pdf_text(full_text: str, norm_num: str) -> tuple[str | None, list[str]]:
    """Extract answer text and criteria for a specific question number from full document text."""
    pat = re.compile(
        rf"(?:^|\n)\s*(?![o•\-\*]?\s*\d+(?:\.\d+)?\s*marks?[:\s])(?:Q(?:uestion)?\.?\s*{norm_num}|{norm_num}\.(?!\d|\s*marks?\b))\b[^\n]*\n(.*)",
        re.DOTALL | re.I
    )
    m = pat.search(full_text)
    if not m:
        return None, []

    rest = m.group(1)
    curr_n = int(norm_num) if norm_num.isdigit() else None
    next_pat = re.compile(
        r"(?:^|\n)\s*(?![o•\-\*]?\s*\d+(?:\.\d+)?\s*marks?[:\s])(?:Q(?:uestion)?\.?\s*(\d+)|(\d+)\.(?!\d|\s*marks?\b))\b",
        re.I
    )

    next_idx = None
    for nm in next_pat.finditer(rest):
        next_n_str = nm.group(1) or nm.group(2)
        if next_n_str and next_n_str.isdigit():
            val = int(next_n_str)
            if curr_n is not None:
                if val > curr_n:
                    next_idx = nm.start()
                    break
            else:
                next_idx = nm.start()
                break

    block = rest[:next_idx].strip() if next_idx is not None else rest.strip()
    clean_block = re.sub(r"--- PAGE \d+ ---", "", block).strip()

    ms_match = re.search(r"(?:Marking\s+Scheme\s*(\([^\)]+\))?[:\s]*)(.*)", clean_block, re.DOTALL | re.I)
    criteria = []
    answer_text = clean_block
    if ms_match:
        answer_text = clean_block[:ms_match.start()].strip()
        crit_items = re.findall(
            r"(?:^|\n)\s*[o•\-\*]?\s*(\d+(?:\.\d+)?\s*marks?[:\s][^\n]+|1 mark per[^\n]+|\([^\)]+marks?[^\)]*\)[^\n]*)",
            clean_block[ms_match.start():],
            re.I,
        )
        criteria = [c.strip() for c in crit_items if c.strip()]

    answer_text = re.sub(r"^\s*(?:[•\-\*]\s*)?Answer\s*:\s*", "", answer_text, flags=re.I).strip()
    return answer_text, criteria


def segment_answer_keys(
    page_results: list[tuple[dict, Any]],
    canonical_questions: list[Any] | None = None,
) -> list[SegmentedKey]:
    """Segment and group answer key blocks across pages, merging continuations and computing marks."""
    grouped: list[SegmentedKey] = []
    full_text = ""

    canonical_norms: set[str] = set()
    if canonical_questions:
        for q in canonical_questions:
            qn = str(getattr(q, "display_number", None) or getattr(q, "normalized_number", None) or "").strip()
            if qn:
                canonical_norms.add(qn)

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

            splits = split_key_text(raw_lbl, text)
            for s_lbl, s_txt in splits:
                norm = normalize_question_number(s_lbl) if s_lbl else None
                clean_txt, crit_from_block = extract_criteria_from_block(s_txt)
                crit_list = crit_from_block if crit_from_block else list(a.criteria or [])
                calc_m = parse_criteria_marks(crit_list, s_txt)
                init_marks = calc_m if calc_m is not None else a.marks

                # Check if this is a subpart (e.g. Q8(a), 8(b), 9(a)) belonging to a parent question (8, 9)
                # where the canonical exam only defines the parent question
                parent = parent_number(norm) if norm else None
                is_subpart_of_parent = bool(
                    norm
                    and parent
                    and parent != norm
                    and canonical_norms
                    and parent in canonical_norms
                    and norm not in canonical_norms
                )
                if is_subpart_of_parent:
                    parent_k = next((k for k in reversed(grouped) if k.normalized_number == parent), None)
                    if parent_k:
                        if clean_txt and clean_txt not in parent_k.answer_text:
                            sep = "\n\n" if "\n" in clean_txt else " "
                            parent_k.answer_text = f"{parent_k.answer_text}{sep}{clean_txt}".strip()
                        if crit_list:
                            for c in crit_list:
                                if c not in parent_k.criteria:
                                    parent_k.criteria.append(c)
                        if getattr(a, "accepted_answers", None):
                            parent_k.accepted_answers.extend(a.accepted_answers)
                        if getattr(a, "keywords", None):
                            parent_k.keywords.extend(a.keywords)
                        sub_m = calc_m if calc_m is not None else a.marks
                        if sub_m is not None:
                            parent_k.marks = (parent_k.marks or 0.0) + sub_m
                        c_marks = parse_criteria_marks(parent_k.criteria, parent_k.answer_text)
                        if c_marks is not None:
                            parent_k.marks = c_marks
                        continue
                    else:
                        k = SegmentedKey(
                            raw_question_number=f"Q{parent}",
                            normalized_number=parent,
                            answer_text=clean_txt,
                            marks=init_marks,
                            criteria=crit_list,
                            accepted_answers=list(a.accepted_answers or []),
                            keywords=list(a.keywords or []),
                            page_number=page_num,
                            bbox=bb,
                            ocr_confidence=conf,
                        )
                        grouped.append(k)
                        continue

                is_cont_label = bool(s_lbl and re.search(r"\b(?:cont|continued|contd)\b", s_lbl, re.IGNORECASE))
                is_same_q_new_page = bool(grouped and norm and norm == grouped[-1].normalized_number and page_num > grouped[-1].page_number)
                is_unnumbered = s_lbl is None or s_lbl.lower() in ("null", "none", "?", "unknown", "[unclear]", "")
                is_bare_subpart = bool(
                    grouped
                    and s_lbl
                    and re.match(r"^\s*\(?\s*([a-zA-Z]|[ivxIVX]{1,4})\s*\)?\s*[\:\.\)\>\→\,\-–—]?\s*$", s_lbl)
                    and not (canonical_questions and any(str(getattr(q, "display_number", "")) == s_lbl for q in canonical_questions))
                )
                # Check if s_lbl is a numbered calculation step (e.g. '1.', '2.') or duplicate question appearing on a later page
                is_numbered_step = False
                if s_lbl and grouped:
                    m_step = re.match(r"^\s*([0-9]{1,2})\.?\s*$", s_lbl)
                    if m_step:
                        step_val = int(m_step.group(1))
                        max_seen = max(
                            [int(k.normalized_number) for k in grouped if k.normalized_number and k.normalized_number.isdigit()] or [0]
                        )
                        already_seen = any(k.normalized_number == str(step_val) for k in grouped)
                        if (max_seen >= 3 and step_val <= 3 and page_num > 1) or (already_seen and page_num > 1):
                            is_numbered_step = True

                # Check if this is an unnumbered continuation block, explicit continuation, bare subpart, same question on next page, or numbered substep
                if is_unnumbered or is_cont_label or is_same_q_new_page or is_bare_subpart or is_numbered_step:
                    if grouped and s_txt:
                        target = grouped[-1]
                        if is_numbered_step:
                            prev_page_qs = [k for k in grouped if k.page_number < page_num]
                            if prev_page_qs:
                                for candidate in reversed(prev_page_qs):
                                    c_text = candidate.answer_text.rstrip()
                                    if c_text.endswith(":") or any(w in c_text.lower() for w in ("sonar", "oscillation", "depth", "wave", "calculate", "find")):
                                        target = candidate
                                        break
                                else:
                                    target = prev_page_qs[-1]

                        sep = "\n\n" if "\n" in clean_txt else " "
                        target.answer_text = f"{target.answer_text}{sep}{clean_txt}".strip()
                        if crit_list:
                            target.criteria.extend(crit_list)
                        if getattr(a, "accepted_answers", None):
                            target.accepted_answers.extend(a.accepted_answers)
                        if getattr(a, "keywords", None):
                            target.keywords.extend(a.keywords)

                        c_marks = parse_criteria_marks(target.criteria, target.answer_text)
                        if c_marks is not None:
                            target.marks = c_marks
                        elif getattr(a, "marks", None) is not None and target.marks is None:
                            target.marks = a.marks
                        continue
                    elif not s_txt:
                        continue

                k = SegmentedKey(
                    raw_question_number=s_lbl,
                    normalized_number=norm,
                    answer_text=clean_txt,
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
        existing_norms = {k.normalized_number for k in grouped if k.normalized_number}

        # If any canonical questions were omitted by OCR (e.g. Q8 swallowed), recover from full_text
        if canonical_questions:
            for q in canonical_questions:
                q_norm = str(getattr(q, "display_number", None) or getattr(q, "normalized_number", None))
                if q_norm and q_norm not in existing_norms:
                    rec_ans, rec_crit = extract_from_full_pdf_text(full_text, q_norm)
                    if rec_ans:
                        c_marks = parse_criteria_marks(rec_crit, rec_ans) or getattr(q, "max_marks", None)
                        # Clean up any leftover subparts of q_norm
                        grouped = [k for k in grouped if not (k.normalized_number and k.normalized_number != q_norm and parent_number(k.normalized_number) == q_norm)]
                        grouped.append(
                            SegmentedKey(
                                raw_question_number=f"Q{q_norm}",
                                normalized_number=q_norm,
                                answer_text=rec_ans,
                                marks=c_marks,
                                criteria=rec_crit,
                                page_number=1,
                            )
                        )
                        existing_norms.add(q_norm)

        # Align criteria and text from clean digital text
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

    # Deduplicate and consolidate subparts by normalized_number
    deduped: list[SegmentedKey] = []
    seen_map: dict[str, SegmentedKey] = {}
    for k in grouped:
        p = parent_number(k.normalized_number) if k.normalized_number else None
        if p and p != k.normalized_number and canonical_norms and p in canonical_norms and k.normalized_number not in canonical_norms:
            if p in seen_map:
                existing = seen_map[p]
                if k.answer_text and k.answer_text not in existing.answer_text:
                    sep = "\n\n" if "\n" in k.answer_text else " "
                    existing.answer_text = f"{existing.answer_text}{sep}{k.answer_text}".strip()
                for crit in k.criteria:
                    if crit not in existing.criteria:
                        existing.criteria.append(crit)
                if k.marks is not None and existing.marks is not None:
                    existing.marks = max(existing.marks, k.marks)
                continue
            else:
                k.raw_question_number = f"Q{p}"
                k.normalized_number = p

        if k.normalized_number and k.normalized_number in seen_map:
            existing = seen_map[k.normalized_number]
            if k.answer_text and k.answer_text not in existing.answer_text:
                sep = "\n\n" if "\n" in k.answer_text else " "
                existing.answer_text = f"{existing.answer_text}{sep}{k.answer_text}".strip()
            for crit in k.criteria:
                if crit not in existing.criteria:
                    existing.criteria.append(crit)
            if k.marks is not None and (existing.marks is None or k.marks > existing.marks):
                existing.marks = k.marks
        else:
            if k.normalized_number:
                seen_map[k.normalized_number] = k
            deduped.append(k)
    grouped = deduped

    # Sort grouped by question sequence
    grouped.sort(
        key=lambda k: int(k.normalized_number) if k.normalized_number and k.normalized_number.isdigit() else 999
    )

    return grouped
