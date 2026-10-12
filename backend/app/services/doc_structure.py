"""Document structure parser for Question Papers.

Transforms raw OCR question blocks into a coherent, structured document model:
- Detects and preserves sections, instructions, and reading passages.
- Never treats headings, instructions, or passages as questions.
- Never invents sub-questions (e.g. Q3(a)) when only main question exists (Q3).
- Keeps option choices (a)/(b)/(c) or blanks inside the question text.
- Inherits section marks rules (e.g. '4 questions x 2 marks = 8 marks' -> 2 marks each).
- Preserves tables as first-class Markdown tables.
- Merges cross-page question continuations seamlessly.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any
from .numbering import normalize_question_number, is_sub_question, parent_number

# Common patterns for section headings and titles
_HEADING_PATTERNS = [
    re.compile(r"^\s*(?:section|part|unit|group)\s+([a-z0-9ivx]+)\b", re.IGNORECASE),
    re.compile(r"^\s*(?:reading\s+comprehension|reading\s+skills|grammar|writing\s+skills|literature|vocabulary)\b", re.IGNORECASE),
    re.compile(r"^\s*(?:general\s+instructions?|instructions?)\b", re.IGNORECASE),
]

# Patterns for general instructions or group instructions
_INSTRUCTION_PATTERNS = [
    re.compile(r"^\s*(?:read\s+the\s+(?:following|short|given)?\s*(?:passage|poem|text|extract)|answer\s+(?:all|any|the\s+following)|choose\s+the\s+correct|fill\s+in\s+the\s+blanks?)\b", re.IGNORECASE),
    re.compile(r"^\s*(?:note\s*:|all\s+questions\s+are\s+compulsory|time\s*:\s*\d|maximum\s+marks?\s*:|max\.?\s*marks?\s*:)", re.IGNORECASE),
]

# Marks rule in section or instruction: e.g. "4 x 2 = 8 marks", "4 questions x 2 marks = 8 marks", "2 marks each"
_MARKS_RULE_PATTERNS = [
    re.compile(r"(\d+)\s*(?:questions?|qn|q)?\s*[×x*]\s*(\d+(?:\.\d+)?)\s*(?:marks?|m)?\s*=\s*(\d+(?:\.\d+)?)\s*(?:marks?|m)?", re.IGNORECASE),
    re.compile(r"(\d+(?:\.\d+)?)\s*(?:marks?|m)\s+each", re.IGNORECASE),
    re.compile(r"each\s+(?:question\s+)?(?:carries|is\s+worth)\s*(\d+(?:\.\d+)?)\s*(?:marks?|m)?", re.IGNORECASE),
    re.compile(r"\(\s*(\d+(?:\.\d+)?)\s*(?:marks?|m)\s*each\s*\)", re.IGNORECASE),
]

_MAX_MARKS_PATTERN = re.compile(
    r"(?:maximum|max\.?|total)\s*(?:marks?)?\s*[:=\-]\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


@dataclass
class StructuredQuestion:
    raw_question_number: str | None
    normalized_number: str | None
    display_number: str
    question_text: str
    question_type: str | None
    max_marks: float | None
    section: str | None
    page_start: int
    page_end: int
    bbox: dict | None
    ocr_confidence: float | None
    verification_status: str = "UNVERIFIED"
    review_reason: str | None = None


@dataclass
class DocumentStructure:
    exam_max_marks: float | None = None
    questions: list[StructuredQuestion] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)


def is_heading_or_title(text: str) -> bool:
    s = text.strip()
    if not s or len(s) > 120:
        return False
    return any(p.search(s) for p in _HEADING_PATTERNS)


def is_instruction(text: str) -> bool:
    s = text.strip()
    if not s:
        return False
    return any(p.search(s) for p in _INSTRUCTION_PATTERNS)


def extract_section_marks_rule(text: str) -> float | None:
    for pat in _MARKS_RULE_PATTERNS:
        m = pat.search(text)
        if m:
            if len(m.groups()) >= 2 and m.group(2):
                try:
                    return float(m.group(2))
                except ValueError:
                    pass
            elif len(m.groups()) >= 1 and m.group(1):
                try:
                    return float(m.group(1))
                except ValueError:
                    pass
    return None


def extract_exam_total_marks(text: str) -> float | None:
    m = _MAX_MARKS_PATTERN.search(text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def is_table_block(text: str) -> bool:
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    if not lines:
        return False
    pipe_lines = [l for l in lines if "|" in l]
    return len(pipe_lines) >= 2 or (len(lines) == 1 and "|" in lines[0] and lines[0].count("|") >= 2)


def is_passage_block(text: str) -> bool:
    s = text.strip()
    if len(s) < 150:
        return False
    # Check if text is predominantly narrative or descriptive text without question question-mark
    if "?" not in s and ("." in s or "\n" in s) and not re.search(r"^\s*(?:Q\d|\d+[\.\)])", s):
        # Likely a reading passage or context paragraph
        return True
    return False


def _is_option_or_blank_item(raw_num: str | None, text: str) -> bool:
    """Detect if an item like '(a) since' or 'b) otherwise' is merely an answer blank or option."""
    if not raw_num:
        return False
    num_norm = normalize_question_number(raw_num)
    if not num_norm:
        return False
    # A single letter option like 'a' or 'b' with very short text (< 40 chars, no question mark)
    if re.fullmatch(r"[a-d]", num_norm.lower()) or re.fullmatch(r"\(?[a-d]\)?", str(raw_num).strip().lower()):
        if len(text.strip()) < 50 and "?" not in text:
            return True
    return False


def _extract_label_from_text_prefix(text: str) -> tuple[str | None, str]:
    """Check if question text begins with an explicit question label like '01.', '1.', 'Q1:', '01/02', etc."""
    s = text.strip()
    # Pattern 1: Q1, Q.1, Question 1, Qn 1, etc.
    m_q = re.match(r"^\s*(?:(?:Q(?:uestion)?|Qn|Ques)\.?\s*([0-9]+[a-zA-Z\(\)]*))[\.\:\)\s\-\/]+(.*)", s, re.IGNORECASE | re.DOTALL)
    if m_q:
        lbl = m_q.group(1).strip()
        rest = m_q.group(2).strip()
        return lbl, (rest if rest else s)

    # Pattern 2: Parenthesized number e.g. (1), (2), (1)(a)
    m_paren = re.match(r"^\s*\(\s*([0-9]{1,3}(?:[a-zA-Z]|\([a-zA-Z0-9]+\))?)\s*\)[\.\:\s\-\/]*(.*)", s, re.DOTALL)
    if m_paren:
        lbl = m_paren.group(1).strip()
        rest = m_paren.group(2).strip()
        return lbl, (rest if rest else s)

    # Pattern 3: Number followed by separator: e.g. '01.', '1)', '1 -', '01/02', '1.a', '3(a)'
    m_num = re.match(r"^\s*([0-9]{1,3}(?:[\.\-\/][0-9]{1,3}|\([a-zA-Z0-9]+\)|[a-zA-Z])?)[\.\:\)\s\-\/]+(.*)", s, re.DOTALL)
    if m_num:
        lbl = m_num.group(1).strip()
        rest = m_num.group(2).strip()
        if len(lbl) <= 6 and not (len(lbl) == 4 and lbl.startswith("20")):
            return lbl, (rest if rest else s)

    return None, s


def parse_question_paper_structure(page_results: list[tuple[dict, Any]]) -> DocumentStructure:
    """Parse raw page extraction results into a unified DocumentStructure model."""
    doc_struct = DocumentStructure()
    current_section: str | None = None
    section_marks_rule: float | None = None
    current_passage: str | None = None

    for page_info, page_res in page_results:
        page_num = page_info["page_number"]
        questions_raw = getattr(page_res, "questions", [])

        for q in questions_raw:
            text = (q.question_text or "").strip()
            raw_label = (q.raw_question_number or "").strip() or None
            marks = q.marks

            # If raw_label is missing or empty, attempt to extract label from start of question text
            if raw_label is None or raw_label.lower() in ("null", "none", "?", "unknown", ""):
                extracted_lbl, rest_text = _extract_label_from_text_prefix(text)
                if extracted_lbl:
                    raw_label = extracted_lbl
                    text = rest_text

            # Check for overall exam max marks in headers
            header_max = extract_exam_total_marks(text)
            if header_max and not doc_struct.exam_max_marks:
                doc_struct.exam_max_marks = header_max

            # Check if this block is a section heading
            if (raw_label is None and is_heading_or_title(text)) or (raw_label and is_heading_or_title(raw_label)):
                current_section = text if len(text) < 80 else (raw_label or text[:80])
                doc_struct.sections.append(current_section)
                rule = extract_section_marks_rule(text)
                if rule is not None:
                    section_marks_rule = rule
                continue

            # Check if this block is a section instruction
            if raw_label is None and is_instruction(text):
                doc_struct.instructions.append(text)
                rule = extract_section_marks_rule(text)
                if rule is not None:
                    section_marks_rule = rule
                continue

            # Check if this block is a reading passage
            if raw_label is None and is_passage_block(text):
                current_passage = text
                continue

            # Check if this is an option/blank belonging to previous question
            if _is_option_or_blank_item(raw_label, text) and doc_struct.questions:
                # Attach to the last question instead of creating a standalone sub-question
                last_q = doc_struct.questions[-1]
                bullet = f"({raw_label.strip('()')})" if not raw_label.startswith("(") else raw_label
                last_q.question_text = f"{last_q.question_text}\n{bullet} {text}".strip()
                last_q.page_end = max(last_q.page_end, page_num)
                continue

            # Check if unnumbered block is a table or continuation of previous question
            is_unnumbered = raw_label is None or raw_label.lower() in ("null", "none", "?", "unknown", "")
            if is_unnumbered:
                if doc_struct.questions:
                    # Append continuation text or table to last question
                    if is_table_block(text):
                        last_q = doc_struct.questions[-1]
                        last_q.question_text = f"{last_q.question_text}\n\n{text}".strip()
                        last_q.page_end = max(last_q.page_end, page_num)
                        continue
                    elif text and (text[0].islower() or text.startswith((",", ";", ")", "-", "•", "*"))):
                        last_q = doc_struct.questions[-1]
                        last_q.question_text = f"{last_q.question_text}\n{text}".strip()
                        last_q.page_end = max(last_q.page_end, page_num)
                        continue
                    # Standalone unnumbered item following existing questions
                    inferred_pos = len(doc_struct.questions) + 1
                    raw_label = None
                    norm = str(inferred_pos)
                    display_num = str(inferred_pos)
                else:
                    # No prior question; check if it's text/instruction
                    if is_instruction(text):
                        doc_struct.instructions.append(text)
                        continue
                    # Standalone first question without a label
                    inferred_pos = 1
                    raw_label = None
                    norm = "1"
                    display_num = "1"
            else:
                norm = normalize_question_number(raw_label)
                display_num = norm or (raw_label or "?")

            # Inherit section marks if question marks not explicitly found
            assigned_marks = marks
            if assigned_marks is None and section_marks_rule is not None:
                assigned_marks = section_marks_rule

            # If a passage was pending and belongs to this section/group, attach note or prefix if first question
            full_text = text
            if current_passage:
                # Prepend reference to passage
                full_text = f"[Reading Passage Context]\n{current_passage}\n\n{text}"
                current_passage = None  # consumed for this group

            bbox_dict = q.bbox.model_dump() if getattr(q, "bbox", None) else None

            reasons: list[str] = []
            if norm is None or is_unnumbered:
                reasons.append("Question number missing or inferred")
            if assigned_marks is None:
                reasons.append("Marks not found")
            if "[UNCLEAR]" in full_text:
                reasons.append("Contains unclear text")
            if not full_text.strip():
                reasons.append("Empty question text")
            if q.confidence is not None and q.confidence < 0.6:
                reasons.append("Low OCR confidence")

            sq = StructuredQuestion(
                raw_question_number=raw_label,
                normalized_number=norm,
                display_number=display_num,
                question_text=full_text,
                question_type=q.question_type or "descriptive",
                max_marks=assigned_marks,
                section=q.section or current_section,
                page_start=page_num,
                page_end=page_num,
                bbox=bbox_dict,
                ocr_confidence=q.confidence,
                verification_status="NEEDS_REVIEW" if reasons else "UNVERIFIED",
                review_reason="; ".join(reasons) or None,
            )
            doc_struct.questions.append(sq)

    return doc_struct
