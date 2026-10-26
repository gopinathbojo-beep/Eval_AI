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
from .numbering import (
    normalize_question_number,
    is_sub_question,
    parent_number,
    extract_subquestion_token,
    extract_label_from_text_prefix,
    subquestion_value,
)

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
    # Tamil: "answer all/any ... questions", "குறிப்பு:" (note), "நேரம்:" (time)
    re.compile(r"^\s*(?:(?:அனைத்து|ஏதேனும்|எவையேனும்|பின்வரும்).{0,60}விடையளி|குறிப்பு\s*:|நேரம்\s*:)"),
]

# "marks" in English or Tamil (மதிப்பெண் / மதிப்பெண்கள் / மதி.)
_MARK_WORD = r"(?:marks?|m|மதிப்பெண்கள்|மதிப்பெண்|மதி\.?)"

# Marks rule in section or instruction: e.g. "4 x 2 = 8 marks", "4 questions x 2 marks = 8 marks", "2 marks each",
# "தலா 2 மதிப்பெண்" / "2 மதிப்பெண்கள் வீதம்" (2 marks each)
_MARKS_RULE_PATTERNS = [
    re.compile(rf"(\d+)\s*(?:questions?|qn|q)?\s*[×x*]\s*(\d+(?:\.\d+)?)\s*{_MARK_WORD}?\s*=\s*(\d+(?:\.\d+)?)\s*{_MARK_WORD}?", re.IGNORECASE),
    re.compile(rf"(\d+(?:\.\d+)?)\s*{_MARK_WORD}\s+(?:each|வீதம்)", re.IGNORECASE),
    re.compile(r"each\s+(?:question\s+)?(?:carries|is\s+worth)\s*(\d+(?:\.\d+)?)\s*(?:marks?|m)?", re.IGNORECASE),
    re.compile(rf"\(\s*(\d+(?:\.\d+)?)\s*{_MARK_WORD}\s*each\s*\)", re.IGNORECASE),
    re.compile(rf"தலா\s*(\d+(?:\.\d+)?)\s*{_MARK_WORD}"),
]

_MAX_MARKS_PATTERN = re.compile(
    r"(?:(?:maximum|max\.?|total)\s*(?:marks?)?|(?:மொத்த\s*)?மதிப்பெண்கள்?)\s*[:=\-]\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

_INLINE_MARKS_PATTERN = re.compile(
    rf"\(\s*(\d+(?:\.\d+)?)\s*{_MARK_WORD}\s*\)\s*$",
    re.IGNORECASE,
)

# Tamil section heading: "பகுதி – அ", "பகுதி - I", "பிரிவு 2" (not "பகுதியில்", "பகுதி அனைத்து ...")
_TAMIL_SECTION = r"(?:பகுதி|பிரிவு)\s*[-–—:]?\s*(?:[அ-ஔ]|[ivxIVX]+|[0-9]+|[A-Za-z])(?![஀-௿\w])"
_SECTION_LINE = re.compile(rf"^\s*(?:(?:section|part)\s+[a-z0-9ivx]+\b|{_TAMIL_SECTION})", re.IGNORECASE)

# Tamil commands and question words: "விளக்குக" (explain), "எழுதுக"/"எழுதவும்" (write), "ஏன்" (why), "எவ்வாறு" (how)
_TAMIL_QUESTION_WORD = re.compile(
    r"[஀-௿]+(?:ுக|க்க|வும்)(?=[\s.?!:,;)]|$)|(?:^|\s)(?:ஏன்|எவ்வாறு|எப்படி|யாவை|யார்|என்ன|எது|எவை|எங்கு|எத்தனை)(?=[\s.?!:,;]|$)"
)
_MCQ_OPTION = re.compile(r"(?:^|\s)\(?\s*([அஆஇஈ]|[a-dA-D])\s*[\)\.]")


def infer_question_type(text: str, marks: float | None = None) -> str:
    """Question type from the question text itself (English or Tamil), for OCR engines that do not classify."""
    return keyword_question_type(text) or default_question_type(text, marks)


def keyword_question_type(text: str) -> str | None:
    """The type a keyword or layout clue proves (பொருத்துக -> match, options (அ)-(ஈ) -> mcq), or None."""
    t = text or ""
    if re.search(r"பொருத்துக|பொருத்தவும்|\bmatch\s+the\b", t, re.I):
        return "match"
    if re.search(r"சரியா\s*தவறா|சரி\s*(?:அல்லது|/)\s*தவறு|\btrue\s*(?:or|/)\s*false\b", t, re.I):
        return "true_false"
    if re.search(r"நிரப்புக|நிரப்பவும்|கோடிட்ட\s*இட|_{3,}|\.{5,}|\bfill\s+in\b", t, re.I):
        return "fill_blank"
    opts = {m.group(1).lower() for m in _MCQ_OPTION.finditer(t)}
    if (len(opts & {"அ", "ஆ", "இ", "ஈ"}) >= 3 or len(opts & {"a", "b", "c", "d"}) >= 4
            or re.search(r"சரியான\s*விடையைத்?\s*தேர்|\bchoose\s+the\s+correct\b", t, re.I)):
        return "mcq"
    if re.search(r"கணக்கிடுக|கணக்கிடவும்|மதிப்பைக்?\s*காண்க|\bcalculate\b|\bfind\s+the\s+value\b", t, re.I):
        return "numerical"
    if re.search(r"ஓரிரு\s*சொற்களில்|ஒரு\s*சொல்லில்|சுருக்கமாக|\bin\s+one\s+word\b|\bbriefly\b", t, re.I):
        return "short_answer"
    return None


def default_question_type(text: str, marks: float | None = None) -> str:
    """A guess from marks alone, used when no keyword decides the type (the AI labeler may replace it)."""
    return "short_answer" if marks is not None and marks <= 2 else "descriptive"


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
    # Where question_type came from: "ocr" (the model said), "rule" (a keyword proved it), "default" (marks guess)
    type_source: str | None = None


@dataclass
class DocumentStructure:
    exam_max_marks: float | None = None
    questions: list[StructuredQuestion] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    stated_question_count: int | None = None
    stated_printed_pages: int | None = None
    exam_duration_minutes: int | None = None
    qp_code: str | None = None
    passages: dict[str, str] = field(default_factory=dict)
    unclassified_blocks: list[dict] = field(default_factory=list)


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
    # Section or Part headings: e.g. "SECTION B: MEDIUM ANSWER QUESTIONS", "பகுதி – அ"
    if re.match(r"^\s*(?:section|part|unit|group)\s+[a-z0-9ivx]+\b", s, re.IGNORECASE) or re.match(rf"^\s*{_TAMIL_SECTION}", s):
        return True
    # Standalone subject or skill headings (only 1 line, short, <= 40 chars)
    if len(lines) == 1 and len(s) <= 40 and any(p.match(s) for p in _HEADING_PATTERNS):
        return True
    return False


def is_section_heading_line(line: str) -> bool:
    """One line that opens a section: "SECTION B ...", "PART II", "பகுதி – அ"."""
    return bool(_SECTION_LINE.match(line))


def is_instruction(text: str) -> bool:
    s = text.strip()
    if not s:
        return False
    if any(p.search(s) for p in _INSTRUCTION_PATTERNS):
        return True
    if any(p.search(s) for p in _MARKS_RULE_PATTERNS) and "?" not in s and len(s) < 120:
        return True
    return False


def is_document_header(text: str) -> bool:
    """Detect if text block is exam metadata/title/header (e.g. 'CBSE CHEMISTRY QUESTION PAPER\\nTime: 1 hr\\nMax Marks: 30')."""
    s = text.strip()
    if not s or "?" in s:
        return False
    has_title_kw = bool(re.search(r"\b(?:QUESTION\s+PAPER|EXAMINATION|TEST\s+PAPER|PERIODIC\s+TEST|ANNUAL\s+EXAM|MID[\s\-]+TERM)\b", s, re.IGNORECASE))
    has_meta_kw = bool(re.search(r"\b(?:Time\s+Allowed|Maximum\s+Marks|Max\.?\s+Marks|Total\s+Marks|Duration\s*:)\b", s, re.IGNORECASE))
    # Tamil needs a value, so a question that merely mentions "நேரம்" (time) is not a header
    has_meta_kw = has_meta_kw or bool(re.search(r"(?:நேரம்|மொத்த\s*மதிப்பெண்கள்?|மதிப்பெண்கள்)\s*[:\-]\s*\d", s))
    if (has_title_kw or has_meta_kw) and not re.search(r"\b(?:Calculate|Explain|Differentiate|Define|Prove|Find|Solve|Draw|Write\s+balanced)\b", s, re.IGNORECASE):
        return True
    return False


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
    if len(s) < 180:
        return False
    # If text contains imperative question verbs, it is an exam question, NEVER a reading passage
    if re.search(
        r"\b(?:Draw|Explain|Identify|Calculate|State|Define|Describe|Show|Prove|Differentiate|Find|Solve|Write|Distinguish|Compare|List|Name|Give\s+reasons?)\b",
        s,
        re.IGNORECASE,
    ) or _TAMIL_QUESTION_WORD.search(s):
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
    marks: float | None = None,
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

    # If incoming text is an exact or near duplicate of last_q, it is NEVER a continuation
    if text and last_q.question_text:
        norm_incoming = re.sub(r"\s+", " ", text.strip().lower())
        norm_last = re.sub(r"\s+", " ", last_q.question_text.strip().lower())
        if norm_incoming == norm_last or (len(norm_incoming) > 35 and norm_incoming in norm_last):
            return False

    # 2. Repeated question number on a new page (e.g. Page 1 ends with Q4, Page 2 starts with Q4 / 4)
    if lbl and page_num > last_q.page_end:
        norm = normalize_question_number(lbl)
        if norm and norm == last_q.normalized_number:
            return True

    # 3. Tables (e.g. Editing table with Line | Incorrect Word | Correct Word)
    if is_table_block(text):
        return True

    # 4. Check negative signals that prove this is a NEW question, NEVER a continuation
    # If the text has a section or subject header e.g. "Reading Comprehension:", "Literature:", "Grammar:", "Section C:"
    if re.search(r"\b(?:SECTION|PART|UNIT|GROUP)\s+[A-Z0-9IVX]+\b", text, re.IGNORECASE):
        return False
    if re.match(r"^\s*(?:Reading\s+Comprehension|Literature|Grammar|Writing\s+Skills|Section\s+[A-Z]|Part\s+[A-Z])[\:\b]", text, re.IGNORECASE):
        return False
    # If it contains instructions to read a passage or answer questions
    if re.search(r"\b(?:Read\s+the\s+(?:following|short|given)?\s*(?:passage|poem|text)|Answer\s+(?:the\s+following|all|any))\b", text, re.IGNORECASE):
        return False
    # If it has subquestions starting at (a), it's a new multi-part question
    if re.search(r"^\s*\(a\)\s+", text, re.MULTILINE):
        return False
    # If this block has its own marks, it is a new question
    if marks is not None and marks > 0:
        return False
    # If the text starts with a capitalized imperative question verb, it's a new question
    if re.match(r"^\s*(?:Define|Explain|State|Calculate|What|Why|How|Arrange|Find|Describe|Name|Differentiate|Evaluate|Factorise|Expand|Simplify)\b", text):
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
        last_clean = (last_q.question_text or "").rstrip()
        if last_clean and not last_clean.endswith(("?", ".", ":", "!", '"', "”", ")")):
            return True
        if last_clean and re.search(r"\b(?:and|or|to|of|in|with|that|which|is|are|the|a|an)\s*$", last_clean, re.IGNORECASE):
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


# Centralized helper imported from .numbering
_extract_label_from_text_prefix = extract_label_from_text_prefix


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
    if num == last_p_int + 1:  # "3." right after Q2 is the next question, not a step of Q2
        return False
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

        has_explicit_parent = any(sq.raw_question_number and not is_sub_question(sq.normalized_number or "") for sq in sub_qs)
        has_bare_sub = any(sq.raw_question_number and not re.search(r"\d", sq.raw_question_number) for sq in sub_qs)
        first_q = sub_qs[0]
        sec = first_q.section or ""
        rule_mark = extract_section_marks_rule(sec)
        if rule_mark is None:
            if "SECTION A" in sec.upper():
                rule_mark = 2.0
            elif "SECTION B" in sec.upper():
                rule_mark = 3.0
            elif "SECTION C" in sec.upper():
                rule_mark = 5.0

        # Fully-labelled parts ("Q5(a)", "Q5(b)") are one question when their section fixes marks per question
        # (e.g. "4 questions x 3 marks"); without such a rule each part stays separately scored.
        has_labelled_parts = rule_mark is not None and p_num.isdigit() and all(
            sq.raw_question_number and is_sub_question(sq.normalized_number or "") for sq in sub_qs
        )
        if not (has_explicit_parent or has_bare_sub or has_labelled_parts):
            for sq in sub_qs:
                consolidated.append(sq)
            continue

        merged_texts = []
        seen_texts = set()
        for sq in sub_qs:
            st = sq.question_text.strip()
            st_clean = re.sub(r"\s+", " ", st.lower())
            if st_clean in seen_texts:
                continue
            seen_texts.add(st_clean)

            sub_tok = extract_subquestion_token(sq.raw_question_number or sq.display_number or "")
            if sub_tok and not st.startswith(f"({sub_tok})"):
                if "\n" in st:
                    top_line, rest_lines = st.split("\n", 1)
                    if _is_pure_topic_title(None, top_line) and not rest_lines.strip().startswith(f"({sub_tok})"):
                        st = f"{top_line.strip()}\n({sub_tok}) {rest_lines.strip()}"
                    else:
                        st = f"({sub_tok}) {st}"
                else:
                    st = f"({sub_tok}) {st}"

            if any(st in prev or (len(st) > 20 and st[:50] in prev) for prev in merged_texts):
                continue

            merged_texts.append(st)

        if not merged_texts:
            merged_texts = [sub_qs[0].question_text.strip()]

        combined_text = "\n".join(merged_texts)
        cleaned_comb, embedded_secs = _extract_and_strip_embedded_sections(combined_text)
        combined_text = _deduplicate_question_text(cleaned_comb)

        sub_marks = [sq.max_marks for sq in sub_qs if sq.max_marks is not None]
        if rule_mark is not None:
            parent_marks = rule_mark
        elif sub_marks:
            parent_marks = sum(sub_marks) if len(merged_texts) > 1 else max(sub_marks)
        else:
            parent_marks = first_q.max_marks

        new_q = StructuredQuestion(
            raw_question_number=f"Q{p_num}",
            normalized_number=p_num,
            display_number=p_num,
            question_text=combined_text,
            question_type=first_q.question_type,
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


def _extract_and_strip_embedded_sections(
    text: str,
) -> tuple[str, list[tuple[str, str | None, float | None]]]:
    """Scan text for embedded SECTION/PART headers and instruction lines.

    Extracts:
        (cleaned_text, list of (section_title, instruction_line, marks_rule))
    """
    if not text:
        return text, []

    sec_pat = re.compile(
        r"(?:^|\n+)[ \t]*((?:SECTION|PART|UNIT|GROUP)\s+[A-Z0-9IVX]+(?:\s*[:\-]\s*[^\n]+)?)"
        r"(?:[ \t]*\n+[ \t]*(\([^\n]*(?:marks?|questions?)[^\n]*\)|[^\n]*(?:marks?|questions?)[^\n]*))?",
        re.IGNORECASE,
    )

    found_sections: list[tuple[str, str | None, float | None]] = []

    def _replacer(m: re.Match) -> str:
        sec_title = m.group(1).strip()
        sec_inst = m.group(2).strip() if m.group(2) else None
        rule = extract_section_marks_rule(sec_inst or sec_title)
        found_sections.append((sec_title, sec_inst, rule))
        return "\n"

    cleaned = sec_pat.sub(_replacer, text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, found_sections


def _deduplicate_question_text(text: str) -> str:
    """Detect and remove duplicate or high-similarity repeated sentences/paragraphs within a question block."""
    if not text or len(text.strip()) < 15:
        return text

    s = text.strip()
    lines = [l.strip() for l in s.splitlines() if l.strip()]
    if not lines:
        return text

    # 1. Collapse consecutive identical lines (e.g. repeated topic title: "Flame & Combustion:\nFlame & Combustion:")
    dedup_lines = []
    for line in lines:
        if dedup_lines and line.lower() == dedup_lines[-1].lower():
            continue
        dedup_lines.append(line)

    # 2. Check for exact half-block repetition: "Block A... \n Block A..."
    full_joined = "\n".join(dedup_lines)
    half_len = len(full_joined) // 2
    for offset in range(-20, 21):
        mid = half_len + offset
        if 10 < mid < len(full_joined) - 10:
            part1 = full_joined[:mid].strip()
            part2 = full_joined[mid:].strip()
            p1_norm = re.sub(r"\s+", " ", part1.lower())
            p2_norm = re.sub(r"\s+", " ", part2.lower())
            if p1_norm and p1_norm == p2_norm:
                return part1

    # 3. Check for repeated topic header pattern (e.g. "Topic:\nBody\nTopic:\nBody")
    m_topic = re.match(r"^([^:\n]{3,60}:)\s*(.*)", full_joined, re.DOTALL)
    if m_topic:
        topic_header = m_topic.group(1).strip()
        body = m_topic.group(2).strip()
        if topic_header.lower() in body.lower():
            pat_topic = re.compile(rf"(?:^|\n+)\s*{re.escape(topic_header)}\s*", re.IGNORECASE)
            sub_blocks = [b.strip() for b in pat_topic.split(body) if b.strip()]
            if sub_blocks:
                first_body = sub_blocks[0]
                b1_norm = re.sub(r"\s+", " ", first_body.lower())
                all_duplicates = True
                for other_b in sub_blocks[1:]:
                    other_norm = re.sub(r"\s+", " ", other_b.lower())
                    if other_norm != b1_norm and (len(other_norm) > 30 and other_norm not in b1_norm and b1_norm not in other_norm):
                        all_duplicates = False
                        break
                if all_duplicates:
                    return f"{topic_header}\n{first_body}"

    # 4. Sentence-level deduplication: remove exact duplicate question sentences
    raw_sentences = re.split(r"(?<=[.?!])\s+", full_joined)
    if len(raw_sentences) > 2:
        seen_sents = set()
        clean_sents = []
        for sent in raw_sentences:
            s_clean = re.sub(r"\s+", " ", sent.strip().lower())
            if len(s_clean) > 20 and s_clean in seen_sents:
                continue
            if len(s_clean) > 20:
                seen_sents.add(s_clean)
            clean_sents.append(sent.strip())
        full_joined = " ".join(clean_sents)

    return full_joined.strip()


def split_swallowed_qp_blocks(
    raw_label: str | None,
    text: str,
) -> list[tuple[str | None, str]]:
    """Split a block if it contains multiple embedded questions or a header/section combined with a question."""
    pat = re.compile(r"(?:^|\n+)\s*(?:Q(?:uestion)?\.?\s*([0-9]{1,2}))[\.\:\s\-\,]+", re.I)
    boundaries = []
    for m in pat.finditer(text):
        boundaries.append((m.start(), f"Q{m.group(1)}", m.end()))

    # If no question boundaries exist, check for an embedded SECTION header in the middle of text
    if not boundaries:
        sec_m = re.search(
            r"(?:^|\n+)[ \t]*((?:SECTION|PART|UNIT|GROUP)\s+[A-Z0-9IVX]+(?:\s*[:\-]\s*[^\n]+)?)"
            r"(?:[ \t]*\n+[ \t]*(\([^\n]*(?:marks?|questions?)[^\n]*\)|[^\n]*(?:marks?|questions?)[^\n]*))?",
            text,
            re.IGNORECASE,
        )
        if sec_m:
            pre = text[:sec_m.start()].strip()
            sec_full = text[sec_m.start():sec_m.end()].strip()
            post = text[sec_m.end():].strip()
            res: list[tuple[str | None, str]] = []
            if pre:
                res.append((raw_label, pre))
            sec_lines = [l.strip() for l in sec_full.splitlines() if l.strip()]
            if sec_lines:
                res.append((None, sec_lines[0]))
                if len(sec_lines) > 1:
                    res.append((None, "\n".join(sec_lines[1:])))
            if post:
                res.append((None, post))
            return res
        return [(raw_label, text)]

    first_start = boundaries[0][0]
    intro = text[:first_start].strip()
    is_sec_lbl = bool(raw_label and is_heading_or_title(raw_label))

    # If raw_label is None/empty and block starts with an explicit question label without preamble, return that question label!
    if len(boundaries) == 1 and first_start <= 5 and not intro:
        return [(boundaries[0][1], text[boundaries[0][2]:].strip())]

    # If only 1 boundary and it's near the start with no heading/preamble, check if section is embedded in remainder
    if len(boundaries) == 1 and not is_sec_lbl and first_start <= 10:
        chunk = text[boundaries[0][2]:].strip()
        sec_m = re.search(
            r"(?:^|\n+)[ \t]*((?:SECTION|PART|UNIT|GROUP)\s+[A-Z0-9IVX]+(?:\s*[:\-]\s*[^\n]+)?)"
            r"(?:[ \t]*\n+[ \t]*(\([^\n]*(?:marks?|questions?)[^\n]*\)|[^\n]*(?:marks?|questions?)[^\n]*))?",
            chunk,
            re.IGNORECASE,
        )
        if not sec_m:
            return [(raw_label, text)]

    res: list[tuple[str | None, str]] = []
    if intro or is_sec_lbl:
        res.append((raw_label if is_sec_lbl else None, intro))
    for i in range(len(boundaries)):
        b_start, b_lbl, b_end = boundaries[i]
        next_start = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        chunk = text[b_end:next_start].strip()
        m_sec = re.search(
            r"(?:^|\n+)[ \t]*((?:SECTION|PART|UNIT|GROUP)\s+[A-Z0-9IVX]+(?:\s*[:\-]\s*[^\n]+)?)"
            r"(?:[ \t]*\n+[ \t]*(\([^\n]*(?:marks?|questions?)[^\n]*\)|[^\n]*(?:marks?|questions?)[^\n]*))?",
            chunk,
            re.IGNORECASE,
        )
        if m_sec:
            q_part = chunk[:m_sec.start()].strip()
            sec_full = chunk[m_sec.start():m_sec.end()].strip()
            post_part = chunk[m_sec.end():].strip()
            if q_part:
                res.append((b_lbl, q_part))
            sec_lines = [l.strip() for l in sec_full.splitlines() if l.strip()]
            if sec_lines:
                res.append((None, sec_lines[0]))
                if len(sec_lines) > 1:
                    res.append((None, "\n".join(sec_lines[1:])))
            if post_part:
                res.append((None, post_part))
        else:
            res.append((b_lbl, chunk))
    return res



# --- Top-level rebuild -------------------------------------------------------------------------
# Scanned papers (e.g. CBSE English) often come back from OCR with the main question numbers lost:
# passages unnumbered, sub-parts "(i)".."(xii)" as labels, "4." buried in text, "9." in the section
# field. The block-by-block parser above then numbers sub-parts as questions. This pass rebuilds the
# paper from its top-level question starts and is used only when the normal result fails sanity checks.

_TOP_NUM_LABEL = re.compile(r"^\s*(?:Q(?:uestion)?\.?\s*)?(\d{1,2})\s*[\.\)]?\s*$", re.I)
_TOP_NUM_LINE = re.compile(r"^[ \t]*(\d{1,2})[ \t]*\.(?!\d)[ \t]*", re.M)
_SECTION_NUM = re.compile(r"^\s*(\d{1,2})\s*\.\s*(.*)$", re.S)
_QUESTION_OPENER = re.compile(
    r"^\s*(?:Read\s+the\s+(?:text|extracts?|extra|passage|poem|following|given)\b"
    r"|(?:Attempt|Answer|Complete|Do)\s+ANY\s+(?:ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|TEN|\d+)\b)",
    re.I,
)
_LEADING_PART = re.compile(r"^\s*\(\s*([ivxIVX]{1,5}|[a-zA-Z])\s*\)")
_ALTERNATIVE = re.compile(r"^\s*(?:\(\s*[A-D]\s*\)|OR\s*$)")


@dataclass
class _TopQuestion:
    num: int
    texts: list[str]
    start_marks: float | None
    part_marks: list[float]
    section: str | None
    page_start: int
    page_end: int
    bbox: dict | None
    confidence: float | None
    qtype: str | None


def _rebuild_from_question_starts(
    page_results: list[tuple[dict, Any]], stated_count: int | None, exam_max: float | None
) -> list[StructuredQuestion] | None:
    """Rebuild questions 1..N from top-level starts; None unless the result is anchored by the stated
    question count (or, when no count is printed, by the paper total)."""
    limit = stated_count or 99
    cap = exam_max * 0.25 if exam_max else None  # a part claiming >25% of the paper is a misread
    qs: list[_TopQuestion] = []
    section: str | None = None

    def start(num: int, page: int, text: str, q: Any, preface: str | None = None) -> None:
        body = f"{preface.strip()}\n{text}".strip() if preface else text
        qs.append(_TopQuestion(num, [body] if body else [], q.marks, [], section, page, page,
                               q.bbox.model_dump() if getattr(q, "bbox", None) else None, q.confidence, q.question_type))

    def append(page: int, text: str, label: str | None, marks: float | None) -> None:
        cur = qs[-1]
        lbl = (label or "").strip()
        if text and lbl.startswith("(") and not text.lstrip().startswith(lbl):
            text = f"{lbl} {text}"
        if text and text.strip() not in cur.texts:
            cur.texts.append(text.strip())
        if marks is not None and marks > 0 and (cap is None or marks <= cap):
            cur.part_marks.append(marks)
        cur.page_end = max(cur.page_end, page)

    for page_info, page_res in page_results:
        page = page_info["page_number"]
        for q in getattr(page_res, "questions", []):
            text = (q.question_text or "").strip()
            label = (q.raw_question_number or "").strip() or None
            sec = (q.section or "").strip() or None
            sec_num = _SECTION_NUM.match(sec) if sec else None
            if sec and not sec_num:
                section = sec
            nxt = (qs[-1].num + 1) if qs else 1
            nxt = nxt if nxt <= limit else None
            cur_num = qs[-1].num if qs else None

            # 1. Explicit number as the label: "3.", "Q8"
            m = _TOP_NUM_LABEL.match(label) if label else None
            if m:
                n = int(m.group(1))
                if nxt and n == nxt:
                    start(n, page, text, q)
                    continue
                if cur_num and n == cur_num:
                    append(page, text, None, q.marks)
                    continue

            # 2. Number opening a line of the text: "4. Attempt ANY ONE ...", "5.\nAttempt ...", "7. (B) ..."
            handled = False
            for lm in _TOP_NUM_LINE.finditer(text):
                n, after = int(lm.group(1)), text[lm.end():].strip()
                if cur_num and n == cur_num and lm.start() == 0:
                    append(page, after, None, q.marks)
                    handled = True
                    break
                if nxt and n == nxt and (lm.start() == 0 or _QUESTION_OPENER.match(after)):
                    before = text[:lm.start()].strip()
                    if before and qs:
                        append(page, before, label, None)
                    start(n, page, after, q)
                    handled = True
                    break
            if handled:
                continue

            # 3. Number carried in the section field: "9. Answer ANY TWO ..." (unless the block continues
            #    the previous question's parts, e.g. "(iv) ..." after Q8's "(iii)")
            if sec_num and nxt and int(sec_num.group(1)) == nxt:
                lead = _LEADING_PART.match(text)
                if not lead or subquestion_value(lead.group(1)) <= 1:
                    start(nxt, page, text, q, preface=sec_num.group(2))
                    continue

            # 4. Unnumbered question opener: "Read the text given below", "Answer ANY FOUR ..."
            is_part = bool(label and (_LEADING_PART.match(label) or _ALTERNATIVE.match(label)))
            if (nxt and _QUESTION_OPENER.match(text) and not is_part
                    and not _ALTERNATIVE.match(text) and (not qs or qs[-1].texts)):
                start(nxt, page, text, q)
                continue

            # 5. Everything else belongs to the current question (parts, alternatives, OR, passages)
            if qs:
                append(page, text, label, q.marks)

    n = len(qs)
    if n < 2 or (stated_count and n != stated_count):
        return None

    # Marks: a question's own printed total is trusted when it is at least its largest part;
    # the rest of the paper total is shared among the uncertain questions.
    trusted: dict[int, float] = {}
    for tq in qs:
        m = tq.start_marks
        if m and m > 0 and (cap is None or m <= exam_max * 0.5) and m >= max(tq.part_marks, default=0):
            trusted[tq.num] = m
    uncertain = [tq.num for tq in qs if tq.num not in trusted]
    inferred: dict[int, float] = {}
    if uncertain and exam_max:
        share = (exam_max - sum(trusted.values())) / len(uncertain)
        if share > 0 and abs(share * 2 - round(share * 2)) < 1e-9:
            inferred = {num: share for num in uncertain}
    marks = {**trusted, **inferred}
    if not stated_count and (not exam_max or abs(sum(marks.values()) - exam_max) > 1e-6):
        return None

    out: list[StructuredQuestion] = []
    for tq in qs:
        reasons = []
        if tq.num in inferred:
            reasons.append("Marks inferred from the paper total; please check")
        elif tq.num not in marks:
            reasons.append("Marks not found")
        out.append(StructuredQuestion(
            raw_question_number=f"Q{tq.num}",
            normalized_number=str(tq.num),
            display_number=str(tq.num),
            question_text=_deduplicate_question_text("\n".join(tq.texts)),
            question_type=tq.qtype,
            max_marks=marks.get(tq.num),
            section=tq.section,
            page_start=tq.page_start,
            page_end=tq.page_end,
            bbox=tq.bbox,
            ocr_confidence=tq.confidence,
            verification_status="NEEDS_REVIEW" if reasons else "UNVERIFIED",
            review_reason="; ".join(reasons) or None,
        ))
    return out


def _structure_is_broken(doc: DocumentStructure) -> bool:
    """Top-level numbering not 1..k, count differs from the stated count, or marks miss the paper total."""
    parents: list[int] = []
    for q in doc.questions:
        p = parent_number(q.normalized_number or "")
        if not p.isdigit():
            return True
        if not parents or parents[-1] != int(p):
            parents.append(int(p))
    if parents != list(range(1, len(parents) + 1)):
        return True
    if doc.stated_question_count and len(parents) != doc.stated_question_count:
        return True
    total = sum(q.max_marks or 0 for q in doc.questions)
    return bool(doc.exam_max_marks and abs(total - doc.exam_max_marks) > 1e-6)


def parse_question_paper_structure(page_results: list[tuple[dict, Any]]) -> DocumentStructure:
    """Parse raw page extraction results into a unified DocumentStructure model."""
    doc_struct = DocumentStructure()

    # Step 1: Scan global metadata across all pages
    for page_info, page_res in page_results:
        for q in getattr(page_res, "questions", []):
            txt = (getattr(q, "question_text", None) or "").strip()
            if not doc_struct.stated_question_count:
                m_qc = re.search(r"\b(?:contains|comprises)\s+([0-9]{1,3})\s+questions\b", txt, re.I)
                if m_qc:
                    doc_struct.stated_question_count = int(m_qc.group(1))
            if not doc_struct.stated_printed_pages:
                m_pc = re.search(r"\b(?:contains|comprises)\s+([0-9]{1,3})\s+printed\s+pages\b", txt, re.I)
                if m_pc:
                    doc_struct.stated_printed_pages = int(m_pc.group(1))
            if not doc_struct.exam_max_marks:
                m_mm = re.search(r"\b(?:Maximum|Max\.?|Total)\s*Marks?\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\b", txt, re.I)
                if m_mm:
                    doc_struct.exam_max_marks = float(m_mm.group(1))
            if not doc_struct.exam_duration_minutes:
                m_tm = re.search(r"\bTime\s*allowed\s*[:\-]?\s*([0-9]+)\s*(?:hours?|hrs?)\b", txt, re.I)
                if m_tm:
                    doc_struct.exam_duration_minutes = int(m_tm.group(1)) * 60
            if not doc_struct.qp_code:
                m_qp_slash = re.search(r"\b([0-9]{1,3}\/[0-9]{1,3}\/[0-9]{1,3})\b", txt)
                if m_qp_slash:
                    doc_struct.qp_code = m_qp_slash.group(1).strip()
                else:
                    m_qp = re.search(r"\bQ\.?P\.?\s*Code(?:\s*No\.?)?\s*[:\s]*([0-9a-zA-Z\/\-]+)", txt, re.I)
                    if m_qp and m_qp.group(1).lower() not in ("given", "no", "number", "on"):
                        doc_struct.qp_code = m_qp.group(1).strip()

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

        explicit_parents = {
            parent_number(normalize_question_number(q.raw_question_number))
            for q in questions_raw
            if q.raw_question_number and normalize_question_number(q.raw_question_number)
        }

        # (label, text, marks, source block, whether the item is the whole source block)
        expanded_items: list[tuple[str | None, str, float | None, Any, bool]] = []
        for q in questions_raw:
            q_text = (q.question_text or "").strip()
            q_lbl = (q.raw_question_number or "").strip() or None
            splits = split_swallowed_qp_blocks(q_lbl, q_text)

            # Check if this unnumbered block is a redundant full-page transcription dump
            if (q_lbl is None or str(q_lbl).lower() in ("null", "none", "?", "unknown", "")) and len(explicit_parents) >= 2 and len(splits) > 1:
                split_parents = {
                    parent_number(normalize_question_number(s_lbl))
                    for s_lbl, _ in splits
                    if s_lbl and normalize_question_number(s_lbl)
                }
                overlap = split_parents & explicit_parents
                if len(overlap) >= 2 and len(overlap) >= len(split_parents) * 0.5:
                    # drop only the questions extracted separately; keep the rest (e.g. Q1-Q4 found only in the dump)
                    for s_lbl, s_txt in splits:
                        s_norm = normalize_question_number(s_lbl) if s_lbl else None
                        if s_norm and parent_number(s_norm) in explicit_parents:
                            continue
                        if s_txt.strip():
                            expanded_items.append((s_lbl, s_txt, None, q, False))
                    continue

            for s_lbl, s_txt in splits:
                s_marks = q.marks if len(splits) == 1 else None
                expanded_items.append((s_lbl, s_txt, s_marks, q, len(splits) == 1))

        for raw_label, text, marks, q, whole_block in expanded_items:
            # Check if block is document header / metadata
            if (raw_label is None or raw_label.lower() in ("null", "none", "?", "unknown", "")) and is_document_header(text):
                header_max = extract_exam_total_marks(text)
                if header_max and not doc_struct.exam_max_marks:
                    doc_struct.exam_max_marks = header_max
                doc_struct.instructions.append(text)
                m_sec_in_hdr = re.search(r"(SECTION\s+[A-Z0-9IVX]+(?:\s*[:\-]\s*[^\n]+)?)", text, re.IGNORECASE)
                if m_sec_in_hdr:
                    sec_hdr = m_sec_in_hdr.group(1).strip()
                    if sec_hdr not in doc_struct.sections:
                        doc_struct.sections.append(sec_hdr)
                    current_section = sec_hdr
                    rule = extract_section_marks_rule(text[m_sec_in_hdr.start():])
                    if rule is not None:
                        section_marks_rule = rule
                continue

            # Check for overall exam max marks in headers
            header_max = extract_exam_total_marks(text)
            if header_max and not doc_struct.exam_max_marks:
                doc_struct.exam_max_marks = header_max

            # Check if this block is a section heading
            if (raw_label is None and is_heading_or_title(text)) or (raw_label and is_heading_or_title(raw_label)):
                current_section = (raw_label or text or "") if is_heading_or_title(raw_label or "") else (text if len(text) < 80 else (raw_label or text[:80]))
                if current_section and current_section not in doc_struct.sections:
                    doc_struct.sections.append(current_section)
                rule = extract_section_marks_rule(text) or extract_section_marks_rule(raw_label or "")
                section_marks_rule = rule if rule is not None else marks
                if not text or is_heading_or_title(text) or is_instruction(text) or is_heading_or_title(raw_label or ""):
                    continue

            # Check if this block is a section instruction
            if raw_label is None and is_instruction(text):
                doc_struct.instructions.append(text)
                rule = extract_section_marks_rule(text)
                if rule is not None:
                    section_marks_rule = rule
                continue

            # If raw_label is missing or empty, attempt to extract label from start of question text
            if raw_label is None or raw_label.lower() in ("null", "none", "?", "unknown", ""):
                extracted_lbl, rest_text = _extract_label_from_text_prefix(text)
                if extracted_lbl:
                    raw_label = extracted_lbl
                    text = rest_text

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
            if _is_question_continuation(raw_label, text, last_q, page_num, marks):
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

            # If not explicitly aligned by PDF offset, check q.section (one tag on a split block can't describe every part)
            if not has_pdf_sec_alignment and whole_block and q.section and q.section.strip():
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

            # Check if question text has a trailing section heading (e.g. Question 8 swallowed Section C)
            pending_trailing_sec = None
            if raw_label is not None:
                m_trailing_sec = re.search(
                    r"(?:\n+)\s*((?:SECTION|PART|UNIT|GROUP)\s+[A-Z0-9IVX]+(?:\s*[:\-]\s*[^\n]+)?(?:\n+.*)?)$",
                    text,
                    re.IGNORECASE | re.DOTALL,
                )
                if m_trailing_sec:
                    pending_trailing_sec = m_trailing_sec.group(1).strip()
                    text = text[:m_trailing_sec.start()].strip()

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
                if norm is None or (is_sub_question(norm) and not parent_number(norm)):
                    sub_tok = extract_subquestion_token(raw_label)
                    if sub_tok and doc_struct.questions:
                        last_q = doc_struct.questions[-1]
                        parent = parent_number(last_q.normalized_number or last_q.display_number or "1")

                        # Check if parent already has seen this sub_tok or sub_tok sequence reset
                        existing_subtokens = set()
                        for sq in doc_struct.questions:
                            if parent_number(sq.normalized_number or sq.display_number or "") == parent:
                                st = extract_subquestion_token(sq.raw_question_number or sq.normalized_number or "")
                                if st:
                                    existing_subtokens.add(st.lower())

                        parent_has_subtok = (sub_tok.lower() in existing_subtokens) or bool(
                            re.search(rf"(?:^|\n)\s*\({re.escape(sub_tok)}\)", last_q.question_text, re.IGNORECASE)
                        )
                        last_sub = extract_subquestion_token(last_q.raw_question_number or last_q.normalized_number or "")
                        sub_decreased = bool(last_sub and sub_tok.lower() <= last_sub.lower())

                        if parent_has_subtok or sub_decreased:
                            detected_num = None
                            detected_title = None
                            if page_text:
                                curr_parent_int = int(parent) if parent.isdigit() else 0
                                prev_snippet = (last_q.question_text or "")[-30:].strip()
                                curr_snippet = text[:30].strip()
                                p_idx = page_text.find(prev_snippet) if prev_snippet else -1
                                c_idx = page_text.find(curr_snippet) if curr_snippet else -1
                                start_search = (p_idx + len(prev_snippet)) if p_idx != -1 else 0
                                if c_idx != -1 and c_idx >= start_search:
                                    intermediate = page_text[start_search:c_idx]
                                    # The new parent is the nearest question label before this part that is
                                    # higher than the current one (skips "Q9." and stray "2.4" when Q10 starts)
                                    for m_q in re.finditer(r"(?:^|\n)\s*(?:Q(?:uestion)?\.?\s*([0-9]{1,3})|([0-9]{1,3})\.(?!\d))\s*[:\-.]?\s*([^\n]*)", intermediate, re.IGNORECASE):
                                        q_cand = m_q.group(1) or m_q.group(2)
                                        if q_cand and int(q_cand) > curr_parent_int:
                                            detected_num = q_cand.strip()
                                            detected_title = m_q.group(3).strip()

                                if not detected_num:
                                    for m_q in re.finditer(r"(?:^|\n)\s*(?:Q(?:uestion)?\.?\s*([0-9]{1,3})|([0-9]{1,3})\.)\s*[:\-.]?\s*([^\n]*)", page_text, re.IGNORECASE):
                                        q_cand = m_q.group(1) or m_q.group(2)
                                        if q_cand and q_cand.isdigit() and int(q_cand) > curr_parent_int:
                                            detected_num = q_cand.strip()
                                            detected_title = m_q.group(3).strip()
                                            break

                            if detected_num:
                                parent = detected_num
                            elif parent.isdigit():
                                parent = str(int(parent) + 1)

                            if detected_title:
                                full_text = f"{detected_title}\n{full_text}"
                            raw_label = f"Q{parent}({sub_tok})"

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
            part_val = inline_val if inline_val is not None else marks
            if section_marks_rule is not None and norm and is_sub_question(norm) and part_val is not None and 0 < part_val < section_marks_rule:
                # A part's own mark ("(a) ... (2 marks)") is a share of the per-question rule, not the whole rule
                assigned_marks = part_val
            elif section_marks_rule is not None:
                if inline_val is not None and inline_val >= section_marks_rule:
                    assigned_marks = inline_val
                else:
                    assigned_marks = section_marks_rule
            elif inline_val is not None:
                assigned_marks = inline_val

            if current_passage:
                full_text = f"[Reading Passage Context]\n{current_passage}\n\n{full_text}"
                current_passage = None

            # Clean and strip any embedded sections/instructions that leaked into full_text
            cleaned_ft, embedded_secs = _extract_and_strip_embedded_sections(full_text)
            if embedded_secs:
                for s_title, s_inst, s_rule in embedded_secs:
                    if s_title not in doc_struct.sections:
                        doc_struct.sections.append(s_title)
                    current_section = s_title
                    if s_rule is not None:
                        section_marks_rule = s_rule
                        assigned_marks = s_rule
                    if s_inst:
                        doc_struct.instructions.append(s_inst)
            full_text = _deduplicate_question_text(cleaned_ft)

            # Check if this question is a duplicate of the previous question
            if doc_struct.questions and full_text.strip():
                last_q = doc_struct.questions[-1]
                norm_curr = re.sub(r"\s+", " ", full_text.strip().lower())
                norm_prev = re.sub(r"\s+", " ", (last_q.question_text or "").strip().lower())
                if norm_curr and (norm_curr == norm_prev or (len(norm_curr) > 35 and norm_curr in norm_prev)):
                    if current_section and not last_q.section:
                        last_q.section = current_section
                    if assigned_marks and not last_q.max_marks:
                        last_q.max_marks = assigned_marks
                    continue

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
                reasons.append("Low reading confidence")

            if is_heading_or_title(display_num) or is_heading_or_title(raw_label or ""):
                continue

            sq = StructuredQuestion(
                raw_question_number=raw_label,
                normalized_number=norm,
                display_number=display_num,
                question_text=full_text,
                question_type=q.question_type,
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

            if pending_trailing_sec:
                sec_lines = [l.strip() for l in pending_trailing_sec.splitlines() if l.strip()]
                sec_hdr = sec_lines[0]
                if sec_hdr not in doc_struct.sections:
                    doc_struct.sections.append(sec_hdr)
                current_section = sec_hdr
                rule = extract_section_marks_rule(pending_trailing_sec)
                if rule is not None:
                    section_marks_rule = rule
                if len(sec_lines) > 1:
                    doc_struct.instructions.append("\n".join(sec_lines[1:]))

    doc_struct.questions = _consolidate_subquestions(doc_struct.questions)

    # Fallback for papers whose OCR lost the main question numbers (see _rebuild_from_question_starts)
    if _structure_is_broken(doc_struct):
        rebuilt = _rebuild_from_question_starts(page_results, doc_struct.stated_question_count, doc_struct.exam_max_marks)
        if rebuilt:
            doc_struct.questions = rebuilt
    # OCR engines that do not classify (IndicOCR) leave the type empty: infer it from the merged question text
    for sq in doc_struct.questions:
        if sq.question_type:
            sq.type_source = "ocr"
        elif kw := keyword_question_type(sq.question_text):
            sq.question_type, sq.type_source = kw, "rule"
        else:
            sq.question_type, sq.type_source = default_question_type(sq.question_text, sq.max_marks), "default"
    return doc_struct
