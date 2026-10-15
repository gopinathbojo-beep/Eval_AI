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

_PAGE_FURNITURE = re.compile(
    r"\W*(?:page\s*\d+(?:\s*of\s*\d+)?|\d{1,3}|p\.?\s*t\.?\s*o\.?|please\s+turn\s+over|turn\s+over|continued(?:\s+on\s+next\s+page)?)\W*",
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
    has_parts: bool = False          # sub-parts (a)/(i)/(1)... were merged into this question
    last_part: str | None = None     # token of the most recently merged part, e.g. "b", "ii", "2"
    part_style: str | None = None    # trailing punctuation of that part's label, e.g. ")" in "1)"


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
    first_on_page: bool = False,
    own_marks: float | None = None,
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

    # 3b. First unlabelled block at the top of a new page: the question from the previous page carries on
    #     (text, options, table). Headings/instructions were already filtered out by the caller; a block with its
    #     own printed marks is a separate unnumbered question.
    if is_unnumbered and first_on_page and page_num > last_q.page_end and own_marks is None:
        return True

    # An unlabelled block with its own marks is its own question, not the tail of the previous one
    if is_unnumbered and own_marks is not None:
        return False

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


_PART_TEXT_PREFIX = re.compile(
    r"^\s*(\(\s*(?:[a-zA-Z]|[ivxIVX]{1,5}|\d{1,2})\s*\)|(?:[a-zA-Z]|[ivxIVX]{1,5})[\)\.])\s+(.+)$", re.DOTALL)
_NUMERIC_OR_ROMAN_LABEL = re.compile(r"^\(?\s*(\d{1,2}|[ivxIVX]{1,5})\s*[\)\.\:]?$")
_ANY_INLINE_MARKS = re.compile(r"\(\s*(\d+(?:\.\d+)?)\s*(?:marks?|m)\s*\)", re.IGNORECASE)
_ROMAN_TO_INT = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10}


def _seq_value(tok: str | None) -> int | None:
    if not tok:
        return None
    if tok.isdigit():
        return int(tok)
    return _ROMAN_TO_INT.get(tok.lower())


def _part_token(label: str | None, last_q: StructuredQuestion | None, used_numbers: set[str]) -> str | None:
    """If `label` marks a sub-part of `last_q` (a whole question), return the part token, else None.

    Sub-parts are merged into their question (one question per printed number). Recognised forms:
    letters (a) a) b.; roman (i) ii) iii.; numbers (1) (2); "9(b)", "9.1", "9b" under question 9; and bare
    "1." / "2)" only when they open or continue the current part sequence and cannot be the next main number.
    """
    if not label or last_q is None or not last_q.normalized_number or is_sub_question(last_q.normalized_number):
        return None
    lbl, own = label.strip(), last_q.normalized_number
    norm = normalize_question_number(lbl)
    if norm and is_sub_question(norm) and parent_number(norm) == own:
        return norm[len(own) + 1:].split(")", 1)[0]
    m = _NUMERIC_OR_ROMAN_LABEL.match(lbl)
    if not m:
        return extract_subquestion_token(lbl)          # (a), a), b.
    raw = m.group(1).lower()
    val, prev = _seq_value(raw), last_q.last_part
    continues = (prev is not None and _seq_value(prev) is not None and val == _seq_value(prev) + 1
                 and prev.isdigit() == raw.isdigit())
    opens = val == 1 and not last_q.has_parts
    if lbl.startswith("(") or not raw.isdigit():       # (1) (ii) ii) iii.
        return raw if continues or opens or str(val) in used_numbers else None
    # bare "1." / "2)": normally a main question number. Accept it as a part when its punctuation differs from the
    # question's own label ("2." ... "1)" "2)"), or when it cannot be the next main number.
    style = _label_style(lbl)
    distinct = style != _label_style(last_q.raw_question_number)
    if continues and ((distinct and style == last_q.part_style) or str(val) != _next_main(used_numbers)):
        return raw
    if opens and (distinct or raw != own) and str(val) != _next_main(used_numbers):
        return raw
    return None


def _label_style(label: str | None) -> str:
    s = (label or "").strip()
    return s[-1] if s and s[-1] in ").:" else ""


def _next_main(used_numbers: set[str]) -> str:
    nums = [int(n) for n in used_numbers if n.isdigit()]
    return str(max(nums) + 1) if nums else "1"


def _merge_part(last_q: StructuredQuestion, tok: str, text: str, marks: float | None, page_num: int,
                label: str | None = None) -> None:
    body = text.strip()
    if marks is not None and not _ANY_INLINE_MARKS.search(body):
        body = f"{body} ({marks:g} mark{'s' if marks != 1 else ''})"
    if not re.match(rf"^\(?\s*{re.escape(tok)}\s*[\)\.]", body, re.IGNORECASE):
        body = f"({tok}) {body}"
    last_q.question_text = f"{last_q.question_text.rstrip()}\n{body}".strip()
    last_q.page_end = max(last_q.page_end, page_num)
    last_q.has_parts, last_q.last_part, last_q.part_style = True, tok, _label_style(label)


def _finalise_parts(q: StructuredQuestion) -> None:
    """A question with merged parts is worth the sum of its printed part marks (never less than it was given)."""
    parts_sum = sum(float(x) for x in _ANY_INLINE_MARKS.findall(q.question_text))
    if parts_sum > 0 and (q.max_marks is None or parts_sum > q.max_marks + 1e-9):
        q.max_marks = parts_sum
    if q.max_marks is not None and q.review_reason:
        reasons = [r for r in q.review_reason.split("; ") if r != "Marks not found"]
        q.review_reason = "; ".join(reasons) or None
        if not reasons and q.verification_status == "NEEDS_REVIEW":
            q.verification_status = "UNVERIFIED"


def parse_question_paper_structure(page_results: list[tuple[dict, Any]]) -> DocumentStructure:
    """Parse raw page extraction results into a unified DocumentStructure model."""
    doc_struct = DocumentStructure()
    current_section: str | None = None
    section_marks_rule: float | None = None
    current_passage: str | None = None

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

        first_on_page = True
        for q in questions_raw:
            text = (q.question_text or "").strip()
            raw_label = (q.raw_question_number or "").strip() or None
            marks = q.marks
            if not raw_label and _PAGE_FURNITURE.fullmatch(text):
                continue  # "Page 2", "P.T.O.", "Turn over" - never content
            is_first_block, first_on_page = first_on_page, False

            # Sub-part of the current question ((a), (ii), (2), 9(b), 9.1 ...): merge it into that question
            last_q = doc_struct.questions[-1] if doc_struct.questions else None
            used = {parent_number(x.normalized_number) for x in doc_struct.questions if x.normalized_number}
            part_label, part_text = raw_label, text
            if raw_label is None or raw_label.lower() in ("null", "none", "?", "unknown", ""):
                pm = _PART_TEXT_PREFIX.match(text)
                part_label, part_text = (pm.group(1), pm.group(2)) if pm else (None, text)
            tok = _part_token(part_label, last_q, used)
            if tok is not None:
                _merge_part(last_q, tok, part_text, marks, page_num, part_label)
                continue

            # If raw_label is missing or empty, attempt to extract label from start of question text
            if raw_label is None or raw_label.lower() in ("null", "none", "?", "unknown", ""):
                extracted_lbl, rest_text = _extract_label_from_text_prefix(text)
                ext_norm = normalize_question_number(extracted_lbl) if extracted_lbl else None
                # A number read out of the text that an earlier question already has (e.g. "5R Principle" inside
                # Q10) is part of the sentence, not a new label.
                if (ext_norm and parent_number(ext_norm) in used and last_q is not None
                        and parent_number(ext_norm) != parent_number(last_q.normalized_number or "")):
                    extracted_lbl = None
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

            # Check if this block continues the previous question (cross-page continuation e.g. Q4 or Q6 table)
            last_q = doc_struct.questions[-1] if doc_struct.questions else None
            if _is_question_continuation(raw_label, text, last_q, page_num, is_first_block, marks):
                sep = "\n\n" if is_table_block(text) else " " if (last_q.question_text and not last_q.question_text.endswith(("\n", ".", "?", ":", ";", "!"))) else "\n"
                last_q.question_text = f"{last_q.question_text}{sep}{text}".strip()
                last_q.page_end = max(last_q.page_end, page_num)
                # If last_q had no marks assigned, check if the continuation provides marks
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
                # Attach to the last question instead of creating a standalone sub-question
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
                    applicable = [s for s in page_sections if s["offset"] <= q_pos]
                    if applicable:
                        latest_sec = applicable[-1]
                        current_section = latest_sec["title"]
                        if latest_sec["rule"] is not None:
                            section_marks_rule = latest_sec["rule"]
                        if current_section not in doc_struct.sections:
                            doc_struct.sections.append(current_section)

            # Check if question itself specifies a section
            # (a question's own title, e.g. "Corrosion & Chemical Properties:", is not a section)
            own_section = q.section.strip() if q.section and q.section.strip() else None
            if own_section and own_section.rstrip(":") == text.strip().rstrip(":"):
                own_section = None
            if own_section:
                new_sec = own_section
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


            # Check if unnumbered block is standalone
            is_unnumbered = raw_label is None or raw_label.lower() in ("null", "none", "?", "unknown", "")
            if is_unnumbered:
                if doc_struct.questions:
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
                if norm is None:
                    # Check if raw_label is a subquestion token like '(b)', '(c)', 'b.', 'c.'
                    sub_tok = extract_subquestion_token(raw_label)
                    if sub_tok and doc_struct.questions:
                        # Find the parent question number from the last question
                        last_q = doc_struct.questions[-1]
                        parent = parent_number(last_q.normalized_number or last_q.display_number or "1")
                        norm = f"{parent}({sub_tok})"
                        display_num = norm
                    else:
                        display_num = raw_label or "?"
                else:
                    display_num = norm

            # Inherit section marks or extract inline marks if not explicitly found
            assigned_marks = marks
            if assigned_marks is None:
                # Check for explicit inline marks e.g. "(2 marks)", "(1 mark)", "(1.5 marks)"
                m_inline = _INLINE_MARKS_PATTERN.search(text)
                if m_inline:
                    try:
                        assigned_marks = float(m_inline.group(1))
                    except ValueError:
                        pass
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
                section=own_section or current_section,
                page_start=page_num,
                page_end=page_num,
                bbox=bbox_dict,
                ocr_confidence=q.confidence,
                verification_status="NEEDS_REVIEW" if reasons else "UNVERIFIED",
                review_reason="; ".join(reasons) or None,
            )
            doc_struct.questions.append(sq)

    for sq in doc_struct.questions:
        if sq.has_parts:
            _finalise_parts(sq)
    return doc_struct
