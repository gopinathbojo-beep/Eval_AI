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
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any
from ... import formatter
from .numbering import normalize_question_number, is_sub_question, parent_number, extract_label_from_text_prefix, subquestion_value
from .recovery import find_recovery_candidates, _tokenize, _extract_distinct_numbers
from ...ocr.student_text import active_student_text, cancelled_block


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
    mapping_note: str | None = None


# Sub-part markers: e.g. "(a)", "(b)", "a)", "b)", "(i)", "(ii)", "a>", "b>", "a,", "b,"
_SUBPART_PATTERN = re.compile(
    r"^\s*\(?\s*([a-zA-Z]|[ivxIVX]{1,4})\s*\)?\s*[\:\.\)\>\→\,\-–—]?\s*$",
)


# Part marker opening a line of answer text: "a) ...", "(b) ...", "ii. ...", "a, ..."
_PART_MARKER = re.compile(r"^\s*\(?\s*([a-zA-Z]|[ivxIVX]{1,4})\s*[\)\.\:,]\s*")
_PART_MARKER_LINE = re.compile(r"^\s*\(?\s*([a-zA-Z]|[ivxIVX]{1,4})\s*[\)\.\:,]\s*", re.MULTILINE)


def _split_parts(
    raw_lbl: str | None, text: str, exam_norms: set[str | None]
) -> list[tuple[str | None, str]]:
    """Split one block holding several parts ("Q5: a) ... b) ...") when the exam scores 5(a), 5(b) separately."""
    norm = normalize_question_number(raw_lbl) if raw_lbl else None
    p = parent_number(norm) if norm else ""
    if not p or not text:
        return [(raw_lbl, text)]
    toks = {n[len(p) + 1:-1] for n in exam_norms if n and n.startswith(f"{p}(") and n.count("(") == 1}
    if len(toks) < 2:
        return [(raw_lbl, text)]
    marks = [m for m in _PART_MARKER_LINE.finditer(text) if m.group(1).lower() in toks]
    if len({m.group(1).lower() for m in marks}) < 2:
        return [(raw_lbl, text)]
    res: list[tuple[str | None, str]] = []
    head = text[:marks[0].start()].strip()
    if head:
        res.append((raw_lbl, head))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        piece = text[m.end():end].strip()
        if piece:
            res.append((f"Q{p}({m.group(1).lower()})", piece))
    return res


def _previous_part(parent: str, sub_tok: str, exam_norms: set[str | None]) -> str | None:
    """The exam part just before sub_tok under parent ('b' -> 'a', 'ii' -> 'i'), if the exam has it."""
    val = subquestion_value(sub_tok)
    for n in exam_norms:
        if n and n.startswith(f"{parent}(") and n.count("(") == 1:
            tok = n[len(parent) + 1:-1]
            if subquestion_value(tok) == val - 1 and (tok in _ROMAN_TOKENS) == (sub_tok in _ROMAN_TOKENS):
                return tok
    return None


_ROMAN_TOKENS = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"}


def _is_content_bullet(
    label: str | None, text: str, current_q: str | None, exam_norms: set[str | None] | None = None
) -> bool:
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
        # "(b)" after 5(a) is the next part, not a bullet, when the exam scores 5(b) on its own
        if exam_norms and f"{curr_p}({num.lower()})" in exam_norms:
            return False
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


# Printed answer-sheet furniture the model sometimes transcribes as an answer, or tacks onto one: the details box
# repeated on every continuation sheet, headings the student copies from the paper, the page count.
_SHEET_FIELD = re.compile(
    r"\b(?:roll\s*no|name\s*[:.\-]|class\s*(?:&|and)\s*sec|exam\s*[:.\-]|subject\s*[:.\-]|date\s*[:.\-]|"
    r"sign(?:ature)?\s+of\s+(?:the\s+)?invigilator|reg(?:ister|istration)?\.?\s*no|admission\s*no)", re.I)
_ALWAYS_HEADER = re.compile(r"\b(?:roll\s*no|invigilator)\b", re.I)
_SCHOOL_LINE = re.compile(r"^[^a-z]*\b(?:SCHOOL|VIDYALAYA|VIDYALAYAM|ACADEMY|CBSE)\b[^a-z]*$")
_SECTION_ONLY = re.compile(r"^\s*sec(?:tion|\.)?\s*[-–:.]?\s*(?:[A-E]|I{1,3}|IV|V)\s*[-.:]?\s*$", re.I)
_PAGE_COUNT = re.compile(r"^\s*total\s+(?:no\.?\s+of\s+)?pages?\b.{0,20}$", re.I)


def _strip_sheet_furniture(text: str) -> str:
    """The answer text without the sheet's details box, copied section headings and page counts."""
    lines = text.splitlines()
    header = any(len(_SHEET_FIELD.findall(line)) >= 2 or _ALWAYS_HEADER.search(line) for line in lines)
    kept = [line for line in lines
            if not (_SECTION_ONLY.match(line) or _PAGE_COUNT.match(line)
                    or len(_SHEET_FIELD.findall(line)) >= 2 or _ALWAYS_HEADER.search(line)
                    or (header and (_SCHOOL_LINE.match(line.strip()) or _SHEET_FIELD.match(line.strip()))))]
    return "\n".join(kept).strip() if len(kept) != len(lines) else text


# Handwritten part markers that read as numbers: roman II and III (straight strokes: "11", "111") and a capital
# B ("13"). A plain "1" is left alone: it is just as often the start of a numbered list.
_MARKER_LOOKALIKES = {"11": "ii", "111": "iii", "13": "b"}


def _misread_part_marker(raw_lbl: str | None, current: str | None, answered: set[str],
                         exam_norms: set[str | None]) -> str | None:
    """The part token a label really is ("(ii)"), when a number written inside the current answer points back to
    a question already answered and looks like a part marker: II read as 11 inside Q16, B read as 13 inside Q28."""
    if not raw_lbl or not current:
        return None
    core = re.sub(r"^\s*(?:q(?:uestion|n)?\s*\.?\s*)", "", raw_lbl.strip(), flags=re.I)
    core = re.sub(r"[\s.)\]:,>\-–→]+$", "", core).lower()
    token = _MARKER_LOOKALIKES.get(core)
    parent = parent_number(current)
    if not token or not parent.isdigit() or int(core) >= int(parent) or core not in answered:
        return None
    has_parts = any(n and n.startswith(f"{parent}(") for n in exam_norms)
    if has_parts and f"{parent}({token})" not in exam_norms:
        return None  # the exam scores other parts of this question: no such part to read it as
    return f"({token})"


def _split_swallowed_answers(
    raw_lbl: str | None,
    text: str,
    canonical_questions: list[Any] | None = None,
) -> list[tuple[str | None, str]]:
    if not text or len(text.strip()) < 40:
        return [(raw_lbl, text)]

    boundaries: list[tuple[int, str]] = []

    valid_nums: set[str] = set()
    curr_p_num: int | None = None
    if raw_lbl:
        m_curr = re.search(r"(\d+)", str(raw_lbl))
        if m_curr:
            curr_p_num = int(m_curr.group(1))

    topic_patterns: list[tuple[str, str]] = []

    if canonical_questions:
        _GENERIC_STOP = {
            "answer", "questions", "following", "marks", "mark", "short", "passage",
            "read", "write", "given", "below", "section", "part", "convert", "directed",
            "mention", "find", "identify", "explain", "describe", "sentence", "sentences"
        }
        for q in canonical_questions:
            q_num = getattr(q, "display_number", None) or getattr(q, "normalized_number", None)
            if q_num:
                valid_nums.add(str(q_num))
            q_txt = getattr(q, "question_text", "")
            if not q_num or not q_txt:
                continue

            # 1. Quoted terms/phrases in question
            for m_q in re.finditer(r'["\'\u201c\u2018\u00ab\u201d\u2019\u00bb\ufffd]([^\n"\'\u201c\u2018\u201d\u2019\ufffd]{4,45})["\'\u201c\u2018\u201d\u2019\u00bb\ufffd]', q_txt):
                clean_q = m_q.group(1).strip()
                if len(clean_q) >= 4 and not any(w in clean_q.lower() for w in ["unclear", "blank"]):
                    topic_patterns.append((rf"(?:\n\n+|\n)\s*(?:[a-zA-Z0-9\(\)\.\-:\>\→]{{0,8}}\s*)?\b{re.escape(clean_q)}\b", str(q_num)))

            # 2. Title-cased phrases / named entities (e.g. story titles, poem names)
            title_matches = re.findall(r"\b[A-Z][a-zA-Z]*(?:'s)?(?:\s+(?:and|the|in|of|is|to|a|an|for|on|from)\s+|\s+)[A-Z][a-zA-Z]*(?:'s)?(?:\s+[A-Za-z][a-zA-Z]*(?:'s)?){0,4}\b", q_txt)
            for tp in title_matches:
                tp_clean = tp.strip()
                if len(tp_clean) >= 6 and not any(w in tp_clean.lower() for w in ["reading comprehension", "writing skills", "creative writing", "question paper"]):
                    topic_patterns.append((rf"(?:\n\n+|\n)\s*(?:[a-zA-Z0-9\(\)\.\-:\>\→]{{0,8}}\s*)?\b{re.escape(tp_clean)}\b", str(q_num)))

            # 3. Leading content phrases from lines
            for line in q_txt.splitlines()[:6]:
                line_clean = re.sub(r"^(?:[A-Za-z\s]+:|\([a-z0-9]+\))\s*", "", line).strip()
                words = [w for w in re.split(r"[^a-zA-Z0-9\']+", line_clean) if w]
                for i in range(len(words) - 1):
                    chunk = " ".join(words[i:i+3])
                    words_in_chunk = [w.lower() for w in words[i:i+3]]
                    if len(chunk) >= 10 and not any(sw in words_in_chunk for sw in _GENERIC_STOP):
                        topic_patterns.append((rf"(?:\n\n+|\n)\s*(?:[a-zA-Z0-9\(\)\.\-:\>\→]{{0,8}}\s*)?\b{re.escape(chunk)}\b", str(q_num)))

    # 1. Embedded question labels: e.g. \n\nQ5, \n\nQ.5, \n\nQuestion 5, \n\nQ2,, or bare \n\n3), \n\n4), \n\n6>, \n\n9>
    num_pat = re.compile(
        r"(?:\n+)\s*(?:(?:Q(?:uestion)?\.?\s*([0-9]{1,2})\s*[\,\.\:\)\>\→\-\–\—]?)|([0-9]{1,2})\s*[\)\.\-:\>\→\,])(?:\s+|(?:[a-zA-Z]))",
        re.IGNORECASE
    )
    for m in num_pat.finditer(text):
        if m.start() < 15:
            continue
        num_str = m.group(1) or m.group(2)
        if not num_str:
            continue

        # Check if preceding line indicates a content bullet (e.g. 'zones:', 'properties:')
        preceding = text[:m.start()].rstrip()
        last_line = preceding.splitlines()[-1] if preceding.splitlines() else ""
        if last_line.strip().endswith(":") or any(w in last_line.lower() for w in [
            "zones", "reasons", "types", "properties", "following", "because", "points", "steps", "factors", "principles"
        ]):
            continue

        is_explicit_q = bool(m.group(1))
        line = text[m.start():].lstrip().splitlines()[0]
        if not is_explicit_q and re.match(r"^\d+\s*[-+\u2212\u00d7\u00f7=]\s*\d", line):
            continue
        # If not an explicit Q prefix, check if it's a small content bullet (1, 2, 3) inside an ongoing answer
        int_n = int(num_str) if num_str.isdigit() else 0
        if not is_explicit_q and curr_p_num is not None and curr_p_num >= int_n and int_n in (1, 2, 3):
            continue

        # If canonical questions are known, ensure this is a question number in the exam
        if valid_nums and num_str not in valid_nums:
            continue

        boundaries.append((m.start(), num_str))

    # 2. Topic/story patterns matching exam questions
    whole_questions = bool(canonical_questions) and all(getattr(q, "structure", None) for q in canonical_questions)
    for pat_str, target_num in ([] if whole_questions else topic_patterns):
        # Never jump backwards or match the ongoing question via topic phrase
        if curr_p_num is not None and target_num.isdigit() and int(target_num) <= curr_p_num:
            continue
        try:
            for m in re.finditer(pat_str, text, re.IGNORECASE):
                if m and m.start() > 20:
                    if not any(abs(b[0] - m.start()) < 25 for b in boundaries):
                        boundaries.append((m.start(), target_num))
        except re.error:
            pass

    boundaries.sort(key=lambda x: x[0])
    if not boundaries:
        return [(raw_lbl, text)]

    res: list[tuple[str | None, str]] = []
    last_idx = 0
    curr_lbl = raw_lbl
    for b_start, b_num in boundaries:
        first_part = text[last_idx:b_start].strip()
        if first_part:
            res.append((curr_lbl, first_part))
        curr_lbl = f"Q{b_num}"
        last_idx = b_start
    rem = text[last_idx:].strip()
    if rem:
        res.append((curr_lbl, rem))
    return res


# --- Sheets whose OCR labels were invented -------------------------------------------------------
# The vision model sometimes stamps one guessed label (e.g. "Q3", copied from the question list it is
# shown) on every block, while its own `raw_question_label` shows it read no such number. Those labels
# are dropped and answers are rebuilt from what the student wrote: inline numbers ("6,A, i,"), part
# numbering restarts (viii -> ii), and content. Only numbers the student wrote become labels.

_IDENTITY_BLOCK = re.compile(r"^\s*name\s*[:\-.]", re.I)
_INLINE_Q = re.compile(r"^[ \t]*(?:[A-Za-z][ \t]?)?(?:Q[ \t]*)?(\d{1,2})[ \t]*[,/][ \t]*(?:[ABab][ \t]*[,/]?[ \t]*)?", re.M)
_INLINE_Q_PREFIXED = re.compile(r"^[ \t]*Q[ \t]*(\d{1,2})\b[ \t]*[,.:)>]?[ \t]*", re.M | re.I)
_PART_TOKEN = re.compile(r"^\s*\(?\s*([ivxIVX]{1,5}|[a-hA-H])\s*[\),.;:]")
_CONTENT_MIN = 0.6


_LABEL_WORDS = {"que", "ques", "question", "ans", "answer", "sol", "solution", "part", "sec", "section", "roll"}


def _label_is_invented(a: Any) -> bool:
    """The label was guessed: what the model says it read there is answer/question text (real words) and does
    not start with the label's number. Short readings like "57" (a misread "5>") or "a)" are genuine labels."""
    lbl = normalize_question_number(getattr(a, "question_number", None))
    raw = getattr(a, "raw_question_label", None)
    if not lbl or not raw:
        return False
    m = re.match(r"^\s*[A-Za-z]?\s*(?:Q\s*)?(\d{1,2})", str(raw))
    if m and m.group(1) == parent_number(lbl):
        return False
    words = [w for w in re.findall(r"[A-Za-z]{3,}", str(raw))
             if w.lower() not in _LABEL_WORDS and not re.fullmatch(r"[ivxIVX]+", w)]
    return bool(words)


def _split_on_markers(text: str, parents: set[str]) -> list[tuple[str | None, str]]:
    """Split text at the student's inline question numbers and at part-numbering restarts."""
    cuts: list[tuple[int, str | None, int]] = []  # (start, label, text start)
    for pat in (_INLINE_Q_PREFIXED, _INLINE_Q):
        for m in pat.finditer(text):
            if m.group(1) in parents and not any(abs(c[0] - m.start()) < 3 for c in cuts):
                cuts.append((m.start(), f"Q{m.group(1)}", m.end()))
    # restarts: a line opening with (i)/(ii)/(a)/(b) after the numbering reached iv or d
    top = 0
    pos = 0
    for line in text.splitlines(keepends=True):
        m = _PART_TOKEN.match(line)
        if any(c[0] == pos for c in cuts):
            top = 0
        if m:
            v = subquestion_value(m.group(1))
            if v <= 2 and top >= 4 and not any(abs(c[0] - pos) < 3 for c in cuts):
                cuts.append((pos, None, pos))
                top = 0
            top = max(top, v)
        pos += len(line)
    cuts.sort()
    pieces: list[tuple[str | None, str]] = []
    prev_end, prev_lbl = 0, None
    for start, lbl, body in cuts:
        chunk = text[prev_end:start].strip()
        if chunk:
            pieces.append((prev_lbl, chunk))
        prev_end, prev_lbl = body, lbl
    tail = text[prev_end:].strip()
    if tail:
        pieces.append((prev_lbl, tail))
    return pieces


_CONTENT_MARGIN = 0.1


def _equation_anchors(text: str) -> set[str]:
    """Literal equation boundaries, treating an inequality's boundary as its plotted line."""
    text = unicodedata.normalize("NFKC", text or "").translate(str.maketrans({"−": "-", "≤": "=", "≥": "="}))
    term = r"(?:\d+(?:\.\d+)?\s*\*?\s*)?[a-zA-Z]"
    expression = term + r"(?:\s*[+-]\s*" + term + r")*"
    pattern = r"(?<![\w])(" + expression + r")\s*(?:<=|>=|=)\s*(" + expression + r"|[+-]?\d+(?:\.\d+)?)(?![\w])"
    return {re.sub(r"\s+|\*", "", left + "=" + right).casefold() for left, right in re.findall(pattern, text)}


def _math_question(text: str, canonical_questions: list[Any]) -> str | None:
    """Match distinctive literal equation shapes against this paper only."""
    # A Cartesian line written without a heading after an inserted graph page
    # can resume an earlier 3-D answer. Require the same explicit equation shape
    # in exactly one canonical question, rather than assuming page adjacency.
    def cartesian(value):
        return (bool(re.search(r"\bx\b", value, re.I)) and bool(re.search(r"\by\b", value, re.I))
                and bool(re.search(r"\bz\b", value, re.I)) and value.count("=") >= 2 and "/" in value)
    if cartesian(text):
        matches = [q for q in canonical_questions if cartesian(q.question_text or "")]
        if len(matches) == 1:
            return parent_number(matches[0].normalized_number)
    equations = _equation_anchors(text)
    if len(equations) >= 2:
        matches = sorted(((len(equations & _equation_anchors(q.question_text)), q.normalized_number)
                          for q in canonical_questions), reverse=True)
        if matches and matches[0][0] >= 2 and (len(matches) == 1 or matches[0][0] > matches[1][0]):
            return parent_number(matches[0][1])
    return None


def _content_question(text: str, canonical_questions: list[Any]) -> str | None:
    """The question the text clearly belongs to: a good score that beats the runner-up by a margin."""
    math_match = _math_question(text, canonical_questions)
    if math_match:
        return math_match
    rec = find_recovery_candidates(None, text, canonical_questions)
    if not rec or rec[0].score < _CONTENT_MIN:
        return None
    top = parent_number(rec[0].normalized_number)
    runner = next((r for r in rec[1:] if parent_number(r.normalized_number) != top), None)
    return top if runner is None or rec[0].score - runner.score >= _CONTENT_MARGIN else None


def _segment_invented_labels(
    page_results: list[tuple[dict, Any]], canonical_questions: list[Any]
) -> list[SegmentedAnswer] | None:
    """Rebuild answers for a sheet with invented labels; None when every label is genuine."""
    blocks = [(p["page_number"], a) for p, res in page_results for a in getattr(res, "answers", [])]
    invented = sum(_label_is_invented(a) for _, a in blocks)
    if invented < 2 or invented * 3 < len(blocks):  # one odd block is not enough to distrust the whole sheet
        return None
    parents = {parent_number(getattr(q, "normalized_number", "") or "") for q in canonical_questions} - {""}

    groups: list[dict] = []  # {label, question, texts, page, bbox, confs}

    def add(page: int, a: Any, label: str | None, text: str, first_piece: bool) -> None:
        norm = normalize_question_number(label) if label else None
        q_from_label = parent_number(norm) if norm else None
        cur = groups[-1] if groups else None
        cur_q = cur and (cur["question"] or None)
        content_q = None if q_from_label else _content_question(text, canonical_questions)

        if q_from_label:
            new = not cur or q_from_label != cur_q
        elif cur is None:
            new = True
        elif content_q and content_q != cur_q:
            new = True           # the content belongs to another question
        else:
            # Same question by content (alternatives like 6B restart numbering) or no evidence: keep going.
            # A restart split inside a block (Q1 viii -> Q2 ii) with no content evidence also starts anew.
            new = not first_piece and not content_q
        if new:
            groups.append({"label": f"Q{q_from_label}" if q_from_label else None, "question": q_from_label or content_q,
                           "texts": [], "page": page, "bbox": a.bbox.model_dump() if getattr(a, "bbox", None) else None,
                           "confs": []})
        g = groups[-1]
        g["texts"].append(text)
        if g["question"] is None:
            g["question"] = content_q
        if getattr(a, "ocr_confidence", None) is not None:
            g["confs"].append(a.ocr_confidence)

    for page, a in blocks:
        text = _strip_sheet_furniture((a.answer_text or "").strip())
        if not text:
            continue
        if page == blocks[0][0] and _IDENTITY_BLOCK.match(text) and re.search(r"\broll\b", text, re.I):
            continue  # the student's name/roll box, not an answer
        label = None if _label_is_invented(a) else getattr(a, "question_number", None)
        pieces = _split_on_markers(text, parents)
        for i, (p_lbl, p_txt) in enumerate(pieces):
            add(page, a, p_lbl or (label if i == 0 else None), p_txt, i == 0)

    out = []
    for i, g in enumerate(groups, 1):
        text = "\n".join(g["texts"]).strip()
        norm = normalize_question_number(g["label"]) if g["label"] else None
        out.append(SegmentedAnswer(
            raw_question_number=g["label"], normalized_number=norm, answer_text=text, raw_ocr_text=text,
            page_number=g["page"], bbox=g["bbox"],
            ocr_confidence=round(sum(g["confs"]) / len(g["confs"]), 2) if g["confs"] else None, position=i,
        ))
    return out


def _math_anchors(text: str) -> set[str]:
    """Literal matrix identifiers, coefficients and distinctive printed numbers; no algebra is solved."""
    text = unicodedata.normalize("NFKC", text or "")
    tokens = re.findall(r"\b[A-Z]{2,4}\b|(?<!\w)\d{4,}(?!\w)|(?<!\w)\d+(?:\.\d+)?\s*[a-z]\b", text)
    common = {"OR", "AND", "THE", "LET", "SOL", "IF", "PT", "GN", "LHS", "RHS", "LHL", "RHL"}
    return {re.sub(r"\s+", "", token) for token in tokens if token not in common}


def _working_continues_previous(text: str, previous, claimed, prior_parts: list[str]) -> bool:
    """Prefer continuity when distinctive working supports it over a guessed number."""
    lines = [line.strip() for line in text.splitlines() if line.strip() and not re.match(r"^section\b", line, re.I)]
    if any(re.match(r"^(?:Q(?:uestion)?\.?\s*\d+|\d+\s*\([a-zivx]+\)|\d+\s*[.)]\s*(?:sol(?:n|ution)?|given))", line, re.I)
           for line in lines[:3]):
        return False
    present = _math_anchors(text)
    supported = present & _math_anchors((previous.question_text or "") + "\n" + "\n".join(prior_parts))
    competing = present & _math_anchors(claimed.question_text or "")
    distinct = supported - competing
    if len(distinct) >= 2 or any(re.fullmatch(r"[A-Z]{2,4}", token) for token in distinct):
        return True
    # Descriptive subparts can also be assigned a guessed next question number.
    # Require several distinctive source terms and almost no support for that
    # claimed question; a shared generic word such as "iron" is insufficient.
    words = _tokenize(text)
    prior_words = words & _tokenize(previous.question_text or "")
    competing_words = words & _tokenize(claimed.question_text or "")
    return len(prior_words - competing_words) >= 4 and len(competing_words) <= 1


# --- The model decides where each answer starts and ends ----------------------------------------------
# The sheet's OCR blocks become numbered lines (reading order, across pages), sent with the question list and the
# subject's answer_sheet_format(); the model returns each answer's question and first/last line. The reply is checked
# (known numbers, ranges inside the sheet, in order, no overlap); anything unusable returns None and the rules below run.

log = logging.getLogger("adem.segmenter")
_MAX_LINES = 1500


def _sheet_lines(page_results: list[tuple[dict, Any]]) -> list[dict]:
    """Every written line of the sheet with its page, block box and confidence."""
    out: list[dict] = []
    for page_info, res in page_results:
        page = page_info["page_number"]
        for a in getattr(res, "answers", []):
            text = (a.answer_text or "").strip()
            for cb in getattr(a, "content_blocks", None) or []:
                if isinstance(cb, dict) and not cancelled_block(cb):
                    t = (cb.get("text") or cb.get("raw_text") or "").strip()
                    if t and t not in text:
                        text = f"{text}\n{t}".strip()
            text = active_student_text(text).strip()
            if not text:
                continue
            label = (getattr(a, "raw_question_label", None) or "").strip()
            if getattr(a, "label_origin", "unknown") == "written" and label and not text.startswith(label):
                text = f"{label} {text}"  # the written number is evidence the model should see
            bbox = a.bbox.model_dump() if getattr(a, "bbox", None) else None
            for line in text.splitlines():
                if line.strip():
                    out.append({"page": page, "text": line.rstrip(), "bbox": bbox,
                                "conf": getattr(a, "ocr_confidence", None)})
    return out


def _resolve_number(number: str | None, known: dict[str, str]) -> str | None:
    """The exam's own number for what the model returned; the parent when only the parent is scored."""
    norm = normalize_question_number(number) if number else None
    if not norm:
        return None
    if norm in known:
        return norm
    p = parent_number(norm)
    return p if p in known else None


def _model_segment(page_results: list[tuple[dict, Any]], canonical_questions: list[Any], model: str | None):
    """Answers with model-decided boundaries, or None to fall back to the rules."""
    from ...ocr import prompts
    from ...ocr.internvl import AIResponseError, AIUnavailable, chat_structured
    from ...ocr.schemas import AnswerSpans

    if not model or not canonical_questions:
        return None
    lines = _sheet_lines(page_results)
    if not lines or len(lines) > _MAX_LINES:
        return None
    known = {q.normalized_number: q.normalized_number for q in canonical_questions if q.normalized_number}
    questions = [{"number": getattr(q, "display_number", None) or q.normalized_number,
                  "marks": getattr(q, "max_marks", None), "text": (q.question_text or "")[:300].replace("\n", " ")}
                 for q in canonical_questions]
    from ... import formatter
    sheet_format = getattr(formatter.current(), "answer_sheet_format", lambda: "")()
    prompt = prompts.answer_spans_prompt(questions, [(i, ln["page"], ln["text"]) for i, ln in enumerate(lines)],
                                         sheet_format)
    try:
        call = chat_structured(prompts.LABELER_SYSTEM, prompt, AnswerSpans, model=model)
    except (AIUnavailable, AIResponseError) as e:
        log.warning("Model answer boundaries skipped (%s): %s", model, getattr(e, "detail", e))
        return None

    spans = sorted((s for s in call.parsed.answers if s.start_line is not None and s.end_line is not None),
                   key=lambda s: s.start_line)
    last_end = -1
    for s in spans:
        if not (0 <= s.start_line <= s.end_line < len(lines)) or s.start_line <= last_end:
            log.warning("Model answer boundaries rejected: bad or overlapping range %s-%s", s.start_line, s.end_line)
            return None
        last_end = s.end_line
    if not spans:
        return None

    out: list[SegmentedAnswer] = []
    for s in spans:
        chunk = lines[s.start_line:s.end_line + 1]
        norm = _resolve_number(s.question_number, known)
        pieces: dict[int, dict | None] = {}
        for ln in chunk:
            pieces[ln["page"]] = _merge_bboxes(pieces.get(ln["page"]), ln["bbox"])
        confs = [ln["conf"] for ln in chunk if ln["conf"] is not None]
        text = "\n".join(ln["text"] for ln in chunk).strip()
        first_page = chunk[0]["page"]
        ans = SegmentedAnswer(
            raw_question_number=f"Q{norm}" if norm else None, normalized_number=norm,
            answer_text=text, raw_ocr_text=text, page_number=first_page, bbox=pieces[first_page],
            ocr_confidence=round(sum(confs) / len(confs), 2) if confs else None, position=len(out) + 1,
            mapping_note="Answer start and end decided by the model",
        )
        if len(pieces) > 1:
            ans.pieces = list(pieces.items())  # one stitched crop across the pages it covers (pipeline)
        out.append(ans)
    return out
# An answer that is a choice: "D) A is false but R is true", "C. 4.0 A", "(b) 20 s"
_CHOICE_ANSWER = re.compile(r"^\s*\(?[A-Da-d]\s*[).:]")
# Words every option list shares: they say nothing about which question an answer belongs to
_SHARED_WORDS = {"but", "true", "false", "both", "correct", "incorrect", "explanation", "not", "none", "all",
                 "option", "statement", "assertion", "reason", "and", "only", "neither", "nor", "either"}


def _telling_words(text: str | None) -> set[str]:
    """Content words that can tell one question from another: no roman numerals, letters or shared option words.
    Subscripts count as digits, so CH₃COOH is a word."""
    return {w for w in _tokenize(unicodedata.normalize("NFKC", text or ""))
            if not re.fullmatch(r"[ivx]+|[a-z]", w) and w not in _SHARED_WORDS}


def _label_holds(text: str, norm: str, current: str | None, top: Any, top_q: Any, rec: list,
                 numbers: bool) -> bool:
    """The number the student wrote stands against a content match pointing elsewhere when the content is no real
    evidence: the written question matches as well as the other one; the answer shares fewer than two telling words
    and none of its distinctive numbers (numbers) with the other question; or it is a short choice written right
    after the previous question's answer ("8. D) A is false but R is true" after 7: option wording is common to
    many questions)."""
    own_score = max((r.score for r in rec if parent_number(r.normalized_number or "") == parent_number(norm)), default=0)
    if own_score >= top.score - 0.05:
        return True
    if not numbers and top_q is not None and len(_telling_words(text) & _telling_words(getattr(top_q, "question_text", ""))) < 2:
        return True
    prev, mine = parent_number(current or ""), parent_number(norm)
    in_order = prev.isdigit() and mine.isdigit() and int(mine) == int(prev) + 1
    return in_order and bool(_CHOICE_ANSWER.match(text or "")) and len(text.strip()) <= 160


# "cells to move.\n\nA) The amount of energy ...": a sentence ending, then the answer's own first part
_CARRIED_LEAD = re.compile(r"^([a-z][a-z ,;'\-]*[a-z][.;]?)[ \t]*\n\s*(?=\(?(?:[A-Da-d]|[ivx]{1,4})\s*[).:]|[*•\-]\s)")


def _carried_lead(text: str) -> str | None:
    """The words opening a page's first numbered answer that finish the previous page's sentence: lower-case
    words only (no numbers or working), at least two of them, followed by this answer's own first part marker."""
    match = _CARRIED_LEAD.match(text or "")
    if not match or len(match[1]) > 120 or len(match[1].split()) < 2:
        return None
    return match[1]


def segment_student_answers(
    page_results: list[tuple[dict, Any]],
    canonical_questions: list[Any] | None = None,
) -> list[SegmentedAnswer]:
    """Segment and group raw OCR blocks into coherent student answers across pages."""
    from ...config import get_settings
    if canonical_questions and not get_settings().ai_join_answers:
        # the AI joiner (services/ai_joiner) is off: the model decides where each answer starts and ends here;
        # with the joiner on, this function is its rule-based fallback and makes no AI call of its own
        by_model = _model_segment(page_results, canonical_questions, get_settings().ai_model)
        if by_model is not None:
            return by_model
    own = formatter.current().segment_answers(page_results, canonical_questions)  # see app/formatter
    if own is not None:
        return own
    if canonical_questions:
        rebuilt = _segment_invented_labels(page_results, canonical_questions)
        if rebuilt is not None:
            return rebuilt
    grouped: list[SegmentedAnswer] = []
    exam_norms = {getattr(q, "normalized_number", None) for q in (canonical_questions or [])}
    whole_questions = bool(canonical_questions) and all(getattr(q, "structure", None) for q in canonical_questions)
    by_number = {q.normalized_number: q for q in (canonical_questions or [])}

    curr_raw_label: str | None = None
    curr_norm_num: str | None = None
    curr_text_parts: list[str] = []
    curr_page: int = 1
    curr_bbox: dict | None = None
    curr_confs: list[float] = []
    curr_was_redirected: bool = False
    curr_label_moved = False  # the current answer's written label was misread: its content moved it here
    curr_page_parts: dict[int, dict] = {}

    def append_text(text):
        curr_text_parts.append(text)
        part = curr_page_parts.setdefault(page_num, {"texts": [], "bbox": None, "confs": []})
        part["texts"].append(text)
        part["bbox"] = _merge_bboxes(part["bbox"], bb)
        if conf is not None:
            part["confs"].append(conf)

    def flush_current():
        nonlocal curr_raw_label, curr_norm_num, curr_text_parts, curr_bbox, curr_confs, curr_was_redirected, curr_label_moved
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
        if whole_questions and curr_page_parts:
            # Keep each page as a separate source block, mapped to the same
            # whole question, so grading and sheet previews retain every page.
            for source_page, part in curr_page_parts.items():
                continuation = source_page != curr_page
                page_text = "\n".join(part["texts"]).strip()
                page_conf = sum(part["confs"]) / len(part["confs"]) if part["confs"] else None
                grouped.append(SegmentedAnswer(
                    raw_question_number=None if continuation else curr_raw_label,
                    normalized_number=curr_norm_num, answer_text=page_text, raw_ocr_text=page_text,
                    page_number=source_page, bbox=part["bbox"], ocr_confidence=page_conf,
                    position=len(grouped) + 1,
                    mapping_note=f"Source grouping: continuation of question {parent_number(curr_norm_num)}" if continuation else None,
                ))
        else:
            grouped.append(ans)
        curr_page_parts.clear()

        curr_raw_label = None
        curr_norm_num = None
        curr_text_parts = []
        curr_bbox = None
        curr_confs = []
        curr_was_redirected = False
        curr_label_moved = False

    for page_info, page_res in page_results:
        page_num = page_info["page_number"]
        answers_raw = getattr(page_res, "answers", [])

        # Expand any swallowed answers within blocks
        expanded_items: list[tuple[str | None, str, dict | None, float | None]] = []
        for a in answers_raw:
            a_text = (a.answer_text or "").strip()
            # If content_blocks contains distinct text blocks, concatenate them
            if getattr(a, "content_blocks", None):
                cb_texts = []
                for cb in a.content_blocks:
                    if cancelled_block(cb):
                        continue
                    if isinstance(cb, dict):
                        t = (cb.get("text") or cb.get("raw_text") or "").strip()
                        if t and t not in a_text:
                            cb_texts.append(t)
                if cb_texts:
                    a_text = f"{a_text}\n" + "\n".join(cb_texts)
                    a_text = a_text.strip()
            # Cancelled headings and formulas cannot start questions or influence
            # content mapping. The complete OCR remains in the saved page record.
            if a_text.strip() and not active_student_text(a_text).strip():
                continue  # everything in the block is struck out (a cancelled heading such as "~~9)~~")
            a_text = _strip_sheet_furniture(active_student_text(a_text).strip())
            a_lbl = (a.question_number or "").strip() or None
            if getattr(a, "label_origin", "unknown") == "continuation":
                a_lbl = None
            if a_lbl and _SECTION_ONLY.match(a_lbl):
                a_lbl = None  # "Section-B" read as the label: a heading, not a question number
            source_label = (getattr(a, "raw_question_label", None) or "").strip()
            if whole_questions:
                # Bare subparts cannot acquire a new parent from content alone.
                if re.fullmatch(r"(?:\s*\([a-zivx]+\)\s*)+", source_label, re.I):
                    a_lbl = None
            if not a_text and not (a_lbl and normalize_question_number(a_lbl)):
                continue  # only sheet furniture, or nothing left after struck-out writing
            a_bb = a.bbox.model_dump() if getattr(a, "bbox", None) else None
            a_conf = getattr(a, "ocr_confidence", None)
            splits = _split_swallowed_answers(a_lbl, a_text, canonical_questions)
            for s_lbl, s_txt in splits:
                for p_lbl, p_txt in _split_parts(s_lbl, s_txt, exam_norms):
                    expanded_items.append((p_lbl, p_txt, a_bb, a_conf))

        if expanded_items and curr_text_parts and page_num > curr_page and expanded_items[0][0]:
            lbl0, text0, bb0, conf0 = expanded_items[0]
            if (lead := _carried_lead(text0)):
                curr_text_parts.append(lead)  # the end of the previous page's answer, read into this page's first one
                expanded_items[0] = (lbl0, text0[len(lead):].strip(), bb0, conf0)

        for raw_lbl, text, bb, conf in expanded_items:
            answered = {parent_number(g.normalized_number) for g in grouped if g.normalized_number}
            if marker := _misread_part_marker(raw_lbl, curr_norm_num, answered, exam_norms):
                raw_lbl = marker
            content_q = _content_question(text, canonical_questions) if not raw_lbl and canonical_questions and text else None
            if whole_questions and curr_norm_num and curr_text_parts:
                previous = by_number.get(parent_number(curr_norm_num))
                claimed = by_number.get(parent_number(normalize_question_number(raw_lbl) or ""))
                if previous and not ((getattr(previous, "max_marks", None) or 0) <= 1):
                    other = by_number.get(content_q)
                    if not raw_lbl and other and other is not previous and _working_continues_previous(text, previous, other, curr_text_parts):
                        content_q = parent_number(curr_norm_num)
                    missing_label = not raw_lbl
                    heading_label, _ = extract_label_from_text_prefix(text)
                    heading_norm = normalize_question_number(heading_label or "") or ""
                    has_heading = bool(heading_norm and not heading_norm.startswith("(") and parent_number(heading_norm).isdigit())
                    if ((missing_label and not has_heading and (not content_q or content_q == parent_number(curr_norm_num)))
                            or (claimed and claimed is not previous and _working_continues_previous(text, previous, claimed, curr_text_parts))):
                        append_text(text)
                        if bb and curr_page == page_num:
                            curr_bbox = _merge_bboxes(curr_bbox, bb)
                        if conf is not None:
                            curr_confs.append(conf)
                        continue
            # An unnumbered block whose content clearly answers another question is that question's answer with
            # its number missed by OCR ("4)" lost, leaving "(a) ... (b) ..."), not a bullet of the current answer
            if content_q and content_q != (parent_number(curr_norm_num) if curr_norm_num else None):
                flush_current()
                curr_norm_num = content_q
                curr_was_redirected = True  # numbered by content: a following block labelled the same joins it
                curr_page = page_num
                append_text(text)
                curr_bbox = bb
                if conf is not None:
                    curr_confs.append(conf)
                continue

            # Check if this item is a content bullet e.g. "1)", "2)", "3)" under an ongoing question
            if curr_norm_num and _is_content_bullet(raw_lbl, text, curr_norm_num, exam_norms):
                bullet_prefix = f"{raw_lbl} " if raw_lbl else ""
                append_text(f"{bullet_prefix}{text}".strip())
                if bb and curr_page == page_num:
                    curr_bbox = _merge_bboxes(curr_bbox, bb)
                if conf is not None:
                    curr_confs.append(conf)
                continue

            # If raw_lbl is missing or empty, attempt to extract label from start of answer text (e.g. "1>", "Q1,")
            if raw_lbl is None or raw_lbl.lower() in ("null", "none", "?", "unknown", "[unclear]", ""):
                extracted_lbl, rest_text = extract_label_from_text_prefix(text)
                if extracted_lbl:
                    raw_lbl = extracted_lbl
                    text = rest_text

            # Label carrying a heading, e.g. "c) SR Principles": the part marker is the label, the rest is answer text
            if raw_lbl and normalize_question_number(raw_lbl) is None:
                m_lbl = _PART_MARKER.match(raw_lbl)
                if m_lbl and raw_lbl[m_lbl.end():].strip():
                    text = f"{raw_lbl[m_lbl.end():].strip()}\n{text}".strip()
                    raw_lbl = f"({m_lbl.group(1).lower()})"

            # An unlabelled block opening with a part marker ("B. F1 ...") on the page of a numbered answer is that
            # question's next part, not an unnumbered answer of its own
            if ((raw_lbl is None or raw_lbl.lower() in ("null", "none", "?", "unknown", "[unclear]"))
                    and curr_norm_num and page_num == curr_page and (m_next := _PART_MARKER.match(text or ""))):
                raw_lbl = f"({m_next.group(1).lower()})"

            # Case: Label is null/empty or 'none'/'unclear'
            if raw_lbl is None or raw_lbl.lower() in ("null", "none", "?", "unknown", "[unclear]"):
                # Top-of-page continuation across pages
                if page_num > curr_page and curr_text_parts:
                    append_text(text)
                    if bb and curr_page == page_num:
                        curr_bbox = _merge_bboxes(curr_bbox, bb)
                    if conf is not None:
                        curr_confs.append(conf)
                    continue
                elif page_num > 1 and not curr_text_parts and grouped:
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
                        append_text(text)
                    curr_bbox = bb
                    if conf is not None:
                        curr_confs.append(conf)
                    flush_current()
                    continue

            # Check if content strongly matches a different canonical question (redirecting misread labels)
            is_redirected = False
            norm = normalize_question_number(raw_lbl)
            if (whole_questions and norm and curr_norm_num and parent_number(norm) != parent_number(curr_norm_num)
                    and any(g.normalized_number and parent_number(g.normalized_number) == parent_number(norm) for g in grouped)):
                # A duplicated earlier number may be a handwritten digit misread.
                # Require forward answer order plus distinctive source constants.
                rec = find_recovery_candidates(raw_lbl, text, canonical_questions)
                top = rec[0] if rec else None
                target = by_number.get(parent_number(top.normalized_number or "")) if top else None
                claimed = by_number.get(parent_number(norm))
                previous = by_number.get(parent_number(curr_norm_num))
                if target and claimed and top.score >= .8:
                    constants = ((_extract_distinct_numbers(text) & _extract_distinct_numbers(target.question_text))
                                 - _extract_distinct_numbers(claimed.question_text) - {"0", "1", "2", "3", "100"})
                    if (previous and len(constants) >= 2 and target.position > previous.position):
                        norm = target.normalized_number
                        raw_lbl = f"Q{norm}"
                        is_redirected = True
            if norm and canonical_questions and not whole_questions and text and len(_tokenize(text)) >= 2:
                exact_match = [q for q in canonical_questions if q.normalized_number in (norm, parent_number(norm))]
                rec = find_recovery_candidates(raw_lbl, text, canonical_questions)
                top_p = parent_number(rec[0].normalized_number or "") if rec else ""
                bare_sub = norm.startswith("(")
                # Content pointing anywhere inside the written question (5 / 5(a) / 5(b) share a topic)
                # confirms the label rather than exposing a misread; for a bare "(b)", the question
                # currently being answered.
                confirms_label = bool(rec) and (
                    (not bare_sub and top_p == parent_number(norm))
                    or (bare_sub and curr_norm_num is not None and top_p == parent_number(curr_norm_num))
                )
                if rec and not confirms_label:
                    top = rec[0]
                    # Check if norm was already mapped in an earlier answer or is currently active
                    already_mapped = (
                        (curr_norm_num is not None and parent_number(curr_norm_num) == parent_number(norm))
                        or any(
                            g.normalized_number and parent_number(g.normalized_number) == parent_number(norm)
                            for g in grouped
                        )
                    )
                    top_q = next((q for q in canonical_questions if q.normalized_number == top.normalized_number), None)
                    top_nums = _extract_distinct_numbers(getattr(top_q, "question_text", None)) if top_q else set()
                    exact_nums = _extract_distinct_numbers(getattr(exact_match[0], "question_text", None)) if exact_match else set()
                    ans_nums = _extract_distinct_numbers(text)

                    generic_consts = {"100", "0", "1", "2", "3"}
                    top_dist_nums = (ans_nums & top_nums) - exact_nums - generic_consts
                    exact_dist_nums = (ans_nums & exact_nums) - top_nums - generic_consts

                    # Labels read one behind ("4)" as "3>", "5)" as "4>" after a skipped Q3): the answer before
                    # was moved by content onto this very number, so this one's content decides too
                    shifted = (curr_label_moved and curr_norm_num is not None
                               and parent_number(curr_norm_num) == parent_number(norm)
                               and not any(g.normalized_number and parent_number(g.normalized_number) == top_p
                                           for g in grouped))
                    should_redirect = False
                    if not exact_match and top.score >= 0.70:
                        should_redirect = True
                    elif shifted and top.score >= 0.65:
                        should_redirect = True
                    elif already_mapped and top.score >= 0.75:
                        should_redirect = True
                    elif top_dist_nums and not exact_dist_nums and top.score >= 0.85:
                        should_redirect = True
                    elif top.score >= 0.95 and not exact_dist_nums:
                        should_redirect = True

                    if should_redirect and exact_match and _label_holds(
                            text, norm, curr_norm_num, top, top_q, rec, bool(top_dist_nums)):
                        should_redirect = False

                    if should_redirect:
                        written = norm
                        norm = top.normalized_number
                        # A bare "(a)" keeps its written part under the question the content points to
                        if bare_sub and f"{top_p}{written}" in exam_norms:
                            norm = f"{top_p}{written}"
                        raw_lbl = f"Q{norm}"
                        is_redirected = True

            p = parent_number(norm) if norm else None
            exam_has_subq = any(
                is_sub_question(getattr(q, "normalized_number", ""))
                and parent_number(getattr(q, "normalized_number", "")) == p
                for q in (canonical_questions or [])
            )

            # "Q5" whose answer opens with "a) ..." when the exam has 5(a), 5(b): it is part (a)
            if exam_has_subq and norm == p:
                m_part = _PART_MARKER.match(text or "")
                if m_part and f"{p}({m_part.group(1).lower()})" in exam_norms:
                    norm = f"{p}({m_part.group(1).lower()})"
                    raw_lbl = f"Q{norm}"
                    text = text[m_part.end():]

            # Case: Sub-part transition or sub-question where exam defines only the parent question
            sub_part = _is_subpart_transition(raw_lbl, parent_number(curr_norm_num) if curr_norm_num else None)
            if sub_part and curr_norm_num:
                parent = parent_number(curr_norm_num)
                parent_has_subq = any(
                    is_sub_question(getattr(q, "normalized_number", ""))
                    and parent_number(getattr(q, "normalized_number", "")) == parent
                    for q in (canonical_questions or [])
                )
                if not parent_has_subq:
                    # Exam scores the question as a whole: fold the part in, keeping its marker
                    if text and not re.match(rf"^\s*\(?{re.escape(sub_part)}[\)\.\:,]", text, re.IGNORECASE):
                        text = f"({sub_part}) {text}"
                    append_text(text)
                    if bb and curr_page == page_num:
                        curr_bbox = _merge_bboxes(curr_bbox, bb)
                    if conf is not None:
                        curr_confs.append(conf)
                    continue
                elif curr_norm_num == parent and (prev_part := _previous_part(parent, sub_part, exam_norms)):
                    # "Q5 <answer>" then "b) ...": the unmarked answer was part (a)
                    curr_norm_num = f"{parent}({prev_part})"
                    curr_raw_label = f"Q{curr_norm_num}"
                    flush_current()
                    curr_raw_label = f"Q{parent}({sub_part})"
                    curr_norm_num = f"{parent}({sub_part})"
                    curr_page = page_num
                    if text:
                        append_text(text)
                    curr_bbox = bb
                    if conf is not None:
                        curr_confs.append(conf)
                    continue
                elif curr_norm_num == f"{parent}({sub_part})" and page_num > curr_page:
                    # Same part relabelled at the top of the next page: the answer was cut across pages
                    append_text(text)
                    if conf is not None:
                        curr_confs.append(conf)
                    continue
                else:
                    flush_current()
                    curr_raw_label = f"Q{parent}({sub_part})"
                    curr_norm_num = f"{parent}({sub_part})"
                    curr_page = page_num
                    if text:
                        append_text(text)
                    curr_bbox = bb
                    if conf is not None:
                        curr_confs.append(conf)
                    continue

            if canonical_questions and p and not exam_has_subq and is_sub_question(norm):
                # Keep the part marker ("(b) ...") so the folded answer still shows which part is which
                sub_tok = norm[len(p):]
                if text and not re.match(rf"^\s*\(?{re.escape(sub_tok.strip('()'))}[\)\.\:,]", text, re.IGNORECASE):
                    text = f"{sub_tok} {text}"
                if curr_norm_num and parent_number(curr_norm_num) == p:
                    append_text(text)
                    if bb and curr_page == page_num:
                        curr_bbox = _merge_bboxes(curr_bbox, bb)
                    if conf is not None:
                        curr_confs.append(conf)
                    continue
                else:
                    flush_current()
                    curr_raw_label = f"Q{p}"
                    curr_norm_num = p
                    curr_page = page_num
                    if text:
                        append_text(text)
                    curr_bbox = bb
                    if conf is not None:
                        curr_confs.append(conf)
                    continue

            # If current block has the exact same normalized number as ongoing question across pages or with explicit continuation
            # A label repeated on a later page right after its own answer is that answer cut across pages
            # (students often rewrite "Q4" at the top of the next page); same-page repeats stay separate.
            is_explicit_cont = bool(raw_lbl and re.search(r"\b(?:cont|continued|contd)\b", raw_lbl, re.IGNORECASE))
            if curr_norm_num and norm == curr_norm_num and (
                curr_was_redirected or page_num > curr_page or is_explicit_cont or whole_questions
            ):
                curr_raw_label = curr_raw_label or raw_lbl  # an answer numbered by content takes the written label
                append_text(text)
                if bb and curr_page == page_num:
                    curr_bbox = _merge_bboxes(curr_bbox, bb)
                if conf is not None:
                    curr_confs.append(conf)
                continue

            # Case: Genuine question label (e.g. Q1, 2, 3, 3(b))
            flush_current()
            curr_raw_label = raw_lbl
            curr_norm_num = norm
            curr_was_redirected = curr_label_moved = is_redirected
            curr_page = page_num
            if text:
                append_text(text)
            curr_bbox = bb
            if conf is not None:
                curr_confs.append(conf)

    flush_current()

    for i, g in enumerate(grouped, 1):
        g.position = i
    if whole_questions:
        # A page may have an option column and a separate rough-work column.
        # Present one page block per question without losing either source region.
        page_groups = {}
        combined = []
        for answer in grouped:
            identity = (answer.page_number, answer.normalized_number) if answer.normalized_number else None
            existing = page_groups.get(identity) if identity else None
            if existing:
                existing.answer_text += "\n" + answer.answer_text
                existing.raw_ocr_text += "\n" + answer.raw_ocr_text
                existing.bbox = _merge_bboxes(existing.bbox, answer.bbox)
            else:
                combined.append(answer)
                if identity:
                    page_groups[identity] = answer
        grouped = combined
        for position, answer in enumerate(grouped, 1):
            answer.position = position
    return grouped
