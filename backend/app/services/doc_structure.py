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
from .numbering import normalize_question_number, is_sub_question, parent_number, extract_subquestion_token

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

_INLINE_MARKS_PATTERN = re.compile(
    r"\(\s*(\d+(?:\.\d+)?)\s*(?:marks?|m)\s*\)\s*$",
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
    if not s or len(s) > 100:
        return False
    # Never treat a block containing a question mark as a heading
    if "?" in s:
        return False
    # Never treat a block with subquestion markers like (a), (b), (i) as a heading
    if re.search(r"\([a-d]\)|\([ivx]+\)", s, re.IGNORECASE):
        return False
    # If multiple lines, check if it contains question interrogatives or verbs
    lines = [l.strip() for l in s.splitlines() if l.strip()]
    if len(lines) > 2:
        return False
    if len(lines) > 1 and any(q_word in lines[1].lower() for q_word in ("why", "how", "what", "which", "where", "who", "explain", "define", "calculate", "write", "find", "draw")):
        return False
    # Section or Part headings: e.g. "SECTION B: MEDIUM ANSWER QUESTIONS"
    if re.match(r"^\s*(?:section|part|unit|group)\s+[a-z0-9ivx]+\b", s, re.IGNORECASE):
        return True
    # Standalone subject or skill headings (only 1 line, short, <= 40 chars)
    if len(lines) == 1 and len(s) <= 40 and any(p.match(s) for p in _HEADING_PATTERNS):
        return True
    return False


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
    if len(pipe_lines) >= 2 or (len(lines) == 1 and "|" in lines[0] and lines[0].count("|") >= 2):
        return True
    # Check for unformatted table headers like "Line", "Incorrect Word", "Correct Word"
    header_keywords = ("incorrect", "correct", "column a", "column b", "line", "statement", "true/false")
    has_header = any(kw in lines[0].lower() for kw in header_keywords)
    has_table_rows = sum(bool(re.search(r"^\([a-z0-9]\)", l) or "___" in l or "\t" in l or "  " in l) for l in lines[1:]) >= 1
    if has_header and has_table_rows:
        return True
    return False


def is_passage_block(text: str) -> bool:
    if is_table_block(text):
        return False
    s = text.strip()
    if len(s) < 150:
        return False
    # Check if text is predominantly narrative or descriptive text without question question-mark
    if "?" not in s and ("." in s or "\n" in s) and not re.search(r"^\s*(?:Q\d|\d+[\.\)])", s):
        # Likely a reading passage or context paragraph
        return True
    return False


def _is_question_continuation(
    raw_label: str | None,
    text: str,
    last_q: StructuredQuestion | None,
    page_num: int,
) -> bool:
    if not last_q:
        return False

    lbl = (raw_label or "").strip()
    is_unnumbered = not lbl or lbl.lower() in ("null", "none", "?", "unknown", "")

    # If this block has an explicit new question number that is NOT the same as last_q, it's not a continuation
    if not is_unnumbered and not re.search(r"\b(?:cont|continued|contd)\b", lbl, re.IGNORECASE):
        norm = normalize_question_number(lbl)
        if norm and norm != last_q.normalized_number:
            return False

    # 1. Explicit continuation marker in label e.g. "Q4 cont", "4 (continued)", "(cont)"
    if lbl and re.search(r"\b(?:cont|continued|contd)\b", lbl, re.IGNORECASE):
        norm = normalize_question_number(lbl)
        if not norm or norm == last_q.normalized_number:
            return True

    # 2. Repeated question number on a new page (e.g. Page 1 ends with Q4, Page 2 starts with Q4 / 4)
    if lbl and page_num > last_q.page_end:
        norm = normalize_question_number(lbl)
        if norm and norm == last_q.normalized_number:
            return True

    # 3. Tables (e.g. Editing table with Line | Incorrect Word | Correct Word)
    if is_table_block(text):
        return True

    # 4. Check negative signals that prove this is a NEW question, NEVER a continuation
    # If the text has a new section or subject header e.g. "Reading Comprehension:", "Literature:", "Grammar:", "Section C:"
    if re.match(r"^\s*(?:Reading\s+Comprehension|Literature|Grammar|Writing\s+Skills|Section\s+[A-Z]|Part\s+[A-Z])[\:\b]", text, re.IGNORECASE):
        return False
    # If it contains instructions to read a passage or answer questions
    if re.search(r"\b(?:Read\s+the\s+(?:following|short|given)?\s*(?:passage|poem|text)|Answer\s+(?:the\s+following|all|any))\b", text, re.IGNORECASE):
        return False
    # If it has subquestions starting at (a), it's a new multi-part question
    if re.search(r"^\s*\(a\)\s+", text, re.MULTILINE):
        return False
    # If it contains its own question marks and is a complete standalone question while last_q is already complete
    last_clean = last_q.question_text.rstrip()
    if "?" in text and last_clean.endswith(("?", ".", "!")):
        return False

    # 5. Unnumbered block continuation signals
    if is_unnumbered:
        # Starts with lowercase or continuation punctuation
        if text and (text[0].islower() or text.startswith((",", ";", ")", "-", "•", "*", "→", "↑"))):
            return True

        # Continuation subquestion tokens like (b), (c)
        if re.match(r"^\s*\([b-z]\)\s+", text, re.IGNORECASE):
            return True

        # Previous question text ended abruptly without sentence terminator
        if last_clean and not last_clean.endswith(("?", ".", ":", "!", '"', "”", ")")):
            return True
        if re.search(r"\b(?:and|or|to|of|in|with|that|which|is|are|the|a|an)\s*$", last_clean, re.IGNORECASE):
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


def _is_pure_topic_title(raw_label: str | None, text: str) -> bool:
    """Check if this item is purely a subject/topic header (e.g. 'Fluid Mechanics & Atmospheric Physics:')."""
    s = text.strip()
    if not s or len(s) > 80:
        return False
    if s.endswith(":") and "?" not in s:
        verbs = ("define", "explain", "state", "calculate", "what", "why", "how", "differentiate", "arrange", "name", "choose", "write", "find", "draw", "describe")
        if not any(v in s.lower().split() for v in verbs):
            return True
    return False


def _is_numbered_substep_or_item(raw_label: str | None, text: str, last_q: StructuredQuestion | None) -> bool:
    """Detect if label '1.', '2.', '3.' is a calculation step or bullet under an ongoing question."""
    if not last_q or not raw_label:
        return False
    m = re.match(r"^\s*([0-9]{1,2})\.?\s*$", raw_label)
    if not m:
        return False
    num = int(m.group(1))
    last_norm = last_q.normalized_number or last_q.display_number or ""
    last_parent = parent_number(last_norm)
    last_p_int = int(last_parent) if last_parent.isdigit() else 0
    last_clean = last_q.question_text.rstrip()
    if last_p_int >= 2 or is_sub_question(last_norm) or last_clean.endswith(":"):
        if num <= 5:
            return True
    return False


def _consolidate_subquestions(questions: list[StructuredQuestion]) -> list[StructuredQuestion]:
    """Consolidate fragmented subquestions (e.g. 1(a), 1(b)) into parent questions (1, 2...)."""
    parent_map: dict[str, list[StructuredQuestion]] = {}
    for q in questions:
        norm = q.normalized_number or q.display_number or ""
        p = parent_number(norm)
        parent_map.setdefault(p, []).append(q)

    has_multi = any(len(qs) > 1 for qs in parent_map.values())
    if not has_multi:
        return questions

    consolidated = []
    for p_num, sub_qs in parent_map.items():
        if len(sub_qs) == 1:
            consolidated.append(sub_qs[0])
            continue
        first_q = sub_qs[0]
        merged_texts = []
        for sq in sub_qs:
            st = sq.question_text.strip()
            sub_tok = extract_subquestion_token(sq.raw_question_number or sq.display_number or "")
            if sub_tok and not st.startswith(f"({sub_tok})"):
                st = f"({sub_tok}) {st}"
            merged_texts.append(st)
        combined_text = "\n".join(merged_texts)

        sec = first_q.section or ""
        rule_mark = extract_section_marks_rule(sec)
        if rule_mark is None:
            if "SECTION A" in sec.upper():
                rule_mark = 2.0
            elif "SECTION B" in sec.upper():
                rule_mark = 3.0
            elif "SECTION C" in sec.upper():
                rule_mark = 5.0

        sub_marks = [sq.max_marks for sq in sub_qs if sq.max_marks is not None]
        if rule_mark is not None:
            parent_marks = rule_mark
        elif sub_marks:
            parent_marks = sum(sub_marks)
        else:
            parent_marks = None

        new_q = StructuredQuestion(
            raw_question_number=f"Q{p_num}",
            normalized_number=p_num,
            display_number=p_num,
            question_text=combined_text,
            question_type=first_q.question_type or "descriptive",
            max_marks=parent_marks,
            section=first_q.section,
            page_start=first_q.page_start,
            page_end=max(sq.page_end for sq in sub_qs),
            bbox=first_q.bbox,
            ocr_confidence=first_q.ocr_confidence,
            verification_status="UNVERIFIED",
        )
        consolidated.append(new_q)
    return consolidated


def parse_question_paper_structure(page_results: list[tuple[dict, Any]]) -> DocumentStructure:
    """Parse raw page extraction results into a unified DocumentStructure model."""
    doc_struct = DocumentStructure()
    current_section: str | None = None
    section_marks_rule: float | None = None
    current_passage: str | None = None
    pending_topic: tuple[str | None, str] | None = None

    for page_info, page_res in page_results:
        page_num = page_info["page_number"]
        page_text = page_info.get("page_text") or ""
        questions_raw = getattr(page_res, "questions", [])

        # Extract any sections present in page_text with their character offsets
        page_sections = []
        if page_text:
            for m in re.finditer(r"^\s*(SECTION\s+[A-Z0-9IVX]+(?:\s*[:\-]\s*[^\n]+)?)\s*$", page_text, re.IGNORECASE | re.MULTILINE):
                sec_header = m.group(1).strip()
                following_text = page_text[m.end():m.end() + 200]
                rule = extract_section_marks_rule(following_text) or extract_section_marks_rule(sec_header)
                page_sections.append({
                    "offset": m.start(),
                    "title": sec_header,
                    "rule": rule,
                })

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
                if current_section not in doc_struct.sections:
                    doc_struct.sections.append(current_section)
                rule = extract_section_marks_rule(text)
                section_marks_rule = rule if rule is not None else marks
                continue

            # Check if this block is a section instruction
            if raw_label is None and is_instruction(text):
                doc_struct.instructions.append(text)
                rule = extract_section_marks_rule(text)
                if rule is not None:
                    section_marks_rule = rule
                continue

            last_q = doc_struct.questions[-1] if doc_struct.questions else None

            # Check if this item is a pure topic title like 'Fluid Mechanics & Atmospheric Physics:'
            if _is_pure_topic_title(raw_label, text):
                pending_topic = (raw_label, text)
                continue

            # Check if this is an internal numbered step like '1.', '2.', '3.' under ongoing question
            if _is_numbered_substep_or_item(raw_label, text, last_q):
                last_q.question_text = f"{last_q.question_text}\n{raw_label} {text}".strip()
                last_q.page_end = max(last_q.page_end, page_num)
                continue

            # Check if this block continues the previous question (cross-page continuation e.g. Q4 or Q6 table)
            if _is_question_continuation(raw_label, text, last_q, page_num):
                sep = "\n\n" if is_table_block(text) else " " if (last_q.question_text and not last_q.question_text.endswith(("\n", ".", "?", ":", ";", "!"))) else "\n"
                last_q.question_text = f"{last_q.question_text}{sep}{text}".strip()
                last_q.page_end = max(last_q.page_end, page_num)
                if last_q.max_marks is None:
                    m_inline = _INLINE_MARKS_PATTERN.search(text)
                    if m_inline:
                        try:
                            last_q.max_marks = float(m_inline.group(1))
                        except ValueError:
                            pass
                    elif marks is not None:
                        last_q.max_marks = marks
                continue

            # Check if this is an option/blank belonging to previous question
            if _is_option_or_blank_item(raw_label, text) and doc_struct.questions:
                last_q = doc_struct.questions[-1]
                bullet = f"({raw_label.strip('()')})" if not raw_label.startswith("(") else raw_label
                last_q.question_text = f"{last_q.question_text}\n{bullet} {text}".strip()
                last_q.page_end = max(last_q.page_end, page_num)
                continue

            # Check if this block is a reading passage
            if raw_label is None and is_passage_block(text):
                current_passage = text
                continue

            # Section alignment from digital PDF page text if available
            has_pdf_sec_alignment = False
            if page_sections and page_text:
                q_pos = -1
                if raw_label:
                    lbl_pat = re.compile(rf"\b{re.escape(raw_label.rstrip('.'))}\b", re.IGNORECASE)
                    m_lbl = lbl_pat.search(page_text)
                    if m_lbl:
                        q_pos = m_lbl.start()
                if q_pos == -1 and len(text) > 15:
                    snippet = text[:35].strip()
                    m_snip = re.search(re.escape(snippet), page_text, re.IGNORECASE)
                    if m_snip:
                        q_pos = m_snip.start()

                if q_pos != -1:
                    has_pdf_sec_alignment = True
                    applicable = [s for s in page_sections if s["offset"] <= q_pos]
                    if applicable:
                        latest_sec = applicable[-1]
                        current_section = latest_sec["title"]
                        if latest_sec["rule"] is not None:
                            section_marks_rule = latest_sec["rule"]
                        if current_section not in doc_struct.sections:
                            doc_struct.sections.append(current_section)

            # If not explicitly aligned by PDF offset, check q.section
            if not has_pdf_sec_alignment and q.section and q.section.strip():
                new_sec = q.section.strip()
                if new_sec != current_section:
                    current_section = new_sec
                    if current_section not in doc_struct.sections:
                        doc_struct.sections.append(current_section)
                    rule = extract_section_marks_rule(current_section)
                    section_marks_rule = rule if rule is not None else marks
                elif marks is not None:
                    section_marks_rule = marks

            # Check if question text begins with a section heading
            m_sec = re.match(r"^\s*(SECTION\s+[A-Z0-9IVX]+(?:\s*[:\-]\s*[^\n]+)?)\s*(?:\n|\r|\Z)(.*)", text, re.IGNORECASE | re.DOTALL)
            if m_sec:
                current_section = m_sec.group(1).strip()
                text = m_sec.group(2).strip()
                if current_section not in doc_struct.sections:
                    doc_struct.sections.append(current_section)
                rule = extract_section_marks_rule(current_section) or extract_section_marks_rule(text[:100])
                if rule is not None:
                    section_marks_rule = rule

            # Check if text indicates Section C (Writing Skills / Creative Writing / Long Answer)
            if current_section and "SECTION B" in current_section.upper():
                if re.match(r"^\s*(?:Writing\s+Skills|Long\s+Answer|Creative\s+Writing)\b", text, re.IGNORECASE):
                    current_section = "SECTION C: LONG ANSWER & WRITING SKILLS"
                    section_marks_rule = 5.0
                    if current_section not in doc_struct.sections:
                        doc_struct.sections.append(current_section)

            # Recover truncated question text from digital page_text if available
            if page_text and len(text.strip()) < 35 and not text.strip().endswith((".", "?", "!", ")")):
                search_lbl = raw_label or ""
                pat_rec = re.compile(rf"{re.escape(search_lbl)}[.\s\-]+({re.escape(text.strip())}[^\n]+)", re.IGNORECASE)
                m_rec = pat_rec.search(page_text)
                if m_rec:
                    text = m_rec.group(1).strip()
                elif text.strip():
                    pat_snip = re.compile(rf"({re.escape(text.strip())}[^\n]+)", re.IGNORECASE)
                    m_snip = pat_snip.search(page_text)
                    if m_snip:
                        text = m_snip.group(1).strip()

            # Attach pending topic if present
            full_text = text
            if pending_topic:
                t_raw, t_text = pending_topic
                full_text = f"{t_text}\n{full_text}"
                if (raw_label is None or raw_label.startswith("(")) and t_raw:
                    t_norm = normalize_question_number(t_raw)
                    if t_norm:
                        raw_label = f"{t_norm}{raw_label or ''}"
                pending_topic = None

            # Check if unnumbered block is standalone
            is_unnumbered = raw_label is None or raw_label.lower() in ("null", "none", "?", "unknown", "")
            if is_unnumbered:
                if doc_struct.questions:
                    inferred_pos = len(doc_struct.questions) + 1
                    raw_label = None
                    norm = str(inferred_pos)
                    display_num = str(inferred_pos)
                else:
                    if is_instruction(text):
                        doc_struct.instructions.append(text)
                        continue
                    inferred_pos = 1
                    raw_label = None
                    norm = "1"
                    display_num = "1"
            else:
                norm = normalize_question_number(raw_label)
                if norm is None:
                    sub_tok = extract_subquestion_token(raw_label)
                    if sub_tok and doc_struct.questions:
                        last_q = doc_struct.questions[-1]
                        parent = parent_number(last_q.normalized_number or last_q.display_number or "1")
                        norm = f"{parent}({sub_tok})"
                        display_num = norm
                    else:
                        display_num = raw_label or "?"
                else:
                    display_num = norm

            # Inherit section marks or extract inline marks
            assigned_marks = marks
            m_inline = _INLINE_MARKS_PATTERN.search(text)
            inline_val = float(m_inline.group(1)) if m_inline else None
            if section_marks_rule is not None:
                if inline_val is not None and inline_val >= section_marks_rule:
                    assigned_marks = inline_val
                else:
                    assigned_marks = section_marks_rule
            elif inline_val is not None:
                assigned_marks = inline_val

            if current_passage:
                full_text = f"[Reading Passage Context]\n{current_passage}\n\n{full_text}"
                current_passage = None

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
                section=current_section or q.section,
                page_start=page_num,
                page_end=page_num,
                bbox=bbox_dict,
                ocr_confidence=q.confidence,
                verification_status="NEEDS_REVIEW" if reasons else "UNVERIFIED",
                review_reason="; ".join(reasons) or None,
            )
            doc_struct.questions.append(sq)

    doc_struct.questions = _consolidate_subquestions(doc_struct.questions)
    return doc_struct
