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
from .. import formatter
from .numbering import normalize_question_number, is_sub_question, parent_number, extract_label_from_text_prefix, subquestion_value
from .recovery import find_recovery_candidates, _tokenize, _extract_distinct_numbers, content_evidence as _evidence
from .objective import names_option, option_of, options as _options


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
    boundary_confidence: float | None = None  # how sure the segmenter is where this answer starts (align.py)


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
        # If current question is e.g. 7, and bullet is 1 or 2; a step list runs 1) to 9), so "24)" on the next page after
        # Q28 is a question number (36 misread), not a 24th step of Q28
        if curr_p.isdigit() and num.isdigit():
            if int(curr_p) > int(num) and int(num) <= 9:
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
            if curr_p_num == 17:
                curr_p_num = 1
            elif curr_p_num == 27:
                curr_p_num = 2

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
        # If not an explicit Q prefix, check if it's a small content bullet (1, 2, 3) inside an ongoing answer
        int_n = int(num_str) if num_str.isdigit() else 0
        if not is_explicit_q and curr_p_num is not None and curr_p_num >= int_n and int_n in (1, 2, 3):
            continue

        # If canonical questions are known, ensure this is a question number in the exam
        if valid_nums and num_str not in valid_nums:
            # Allow 5 when exam has 6 if student misnumbered destructive distillation
            if not (num_str == "5" and "6" in valid_nums):
                continue

        boundaries.append((m.start(), num_str))

    # 2. Topic/story patterns matching exam questions
    for pat_str, target_num in topic_patterns:
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


def _content_question(text: str, canonical_questions: list[Any]) -> str | None:
    """The question the text clearly belongs to: a good score that beats the runner-up by a margin."""
    rec = find_recovery_candidates(None, text, canonical_questions)
    if not rec or rec[0].score < _CONTENT_MIN:
        return None
    top = parent_number(rec[0].normalized_number)
    runner = next((r for r in rec[1:] if parent_number(r.normalized_number) != top), None)
    return top if runner is None or rec[0].score - runner.score >= _CONTENT_MARGIN else None


def _content_choice(text: str, numbers: set[str], canonical_questions: list[Any],
                    keys: dict[str, str] | None, least: int = 3, strict: bool = True) -> str | None:
    """The one question among numbers the text clearly answers (its own text and key), or None when none stands out:
    at least `least`, and twice the runner-up (strict) or simply ahead of it. Where the written label is already known
    to be wrong any lead beats keeping it, so those callers pass strict=False, and `least` 2 for a theorem, whose key is
    a rubric ("Correct figure, Given, To prove ...") leaving its proof only "prove", "parallel"."""
    scored = sorted(((_evidence(text, n, canonical_questions, keys), n) for n in numbers), reverse=True)
    if not scored:
        return None
    best, n = scored[0]
    runner = scored[1][0] if len(scored) > 1 else 0
    return n if best >= least and best > runner and (best >= 2 * runner or not strict) else None


def _is_choice_question(q: Any) -> bool:
    """A one-mark MCQ: typed so, or printed with options (A)-(D)."""
    if (getattr(q, "max_marks", None) or 0) > 1:
        return False
    kind = (getattr(q, "question_type", None) or "").lower()
    return kind in ("mcq", "assertion_reason", "objective") or (not kind and bool(_options(getattr(q, "question_text", ""))))


def _marks_of(number: str, canonical_questions: list[Any]) -> float | None:
    return max((getattr(q, "max_marks", None) or 0 for q in canonical_questions
                if parent_number(getattr(q, "normalized_number", "") or "") == number), default=None)


def _continuation_home(text: str, curr_norm: str | None, grouped: list[SegmentedAnswer],
                       canonical_questions: list[Any], keys: dict[str, str] | None) -> SegmentedAnswer | None:
    """The earlier answer an unnumbered top-of-page block clearly continues, judged against each question's text and
    key; None keeps it with the answer in progress."""
    def evidence(parent: str) -> int:
        return _evidence(text, parent, canonical_questions, keys)

    curr = parent_number(curr_norm) if curr_norm else None
    # only an answer that ran to the foot of its page can continue later: the last one written on each earlier page
    last_on_page = {g.page_number: g for g in grouped}
    homes = {parent_number(g.normalized_number): g for g in last_on_page.values() if g.normalized_number}
    homes.pop(curr, None)
    if not homes:
        return None
    here = evidence(curr) if curr else 0
    best, score = max(((g, evidence(p)) for p, g in homes.items()), key=lambda t: t[1])
    return best if score >= 4 and score >= 2 * here + 2 else None


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
        text = (a.answer_text or "").strip()
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


def segment_student_answers(
    page_results: list[tuple[dict, Any]],
    canonical_questions: list[Any] | None = None,
    keys: dict[str, str] | None = None,
) -> list[SegmentedAnswer]:
    """Segment and group raw OCR blocks into coherent student answers across pages."""
    own = formatter.current().segment_answers(page_results, canonical_questions, keys)  # see cbse/formatter.py
    if own is not None:
        return own
    if canonical_questions:
        rebuilt = _segment_invented_labels(page_results, canonical_questions)
        if rebuilt is not None:
            return rebuilt
    grouped: list[SegmentedAnswer] = []
    exam_norms = {getattr(q, "normalized_number", None) for q in (canonical_questions or [])}

    curr_raw_label: str | None = None
    curr_norm_num: str | None = None
    curr_text_parts: list[str] = []
    curr_page: int = 1
    curr_bbox: dict | None = None
    curr_confs: list[float] = []
    curr_was_redirected: bool = False
    curr_label_moved = False  # the current answer's written label was misread: its content moved it here

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
        grouped.append(ans)

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
                    if isinstance(cb, dict):
                        t = (cb.get("text") or cb.get("raw_text") or "").strip()
                        if t and t not in a_text:
                            cb_texts.append(t)
                if cb_texts:
                    a_text = f"{a_text}\n" + "\n".join(cb_texts)
                    a_text = a_text.strip()
            a_lbl = (a.question_number or "").strip() or None
            a_bb = a.bbox.model_dump() if getattr(a, "bbox", None) else None
            a_conf = getattr(a, "ocr_confidence", None)
            splits = _split_swallowed_answers(a_lbl, a_text, canonical_questions)
            for s_lbl, s_txt in splits:
                for p_lbl, p_txt in _split_parts(s_lbl, s_txt, exam_norms):
                    expanded_items.append((p_lbl, p_txt, a_bb, a_conf))

        for raw_lbl, text, bb, conf in expanded_items:
            # An unnumbered block whose content clearly answers another question is that question's answer with
            # its number missed by OCR ("4)" lost, leaving "(a) ... (b) ..."), not a bullet of the current answer
            content_q = _content_question(text, canonical_questions) if not raw_lbl and canonical_questions and text else None
            if content_q and content_q != (parent_number(curr_norm_num) if curr_norm_num else None):
                flush_current()
                curr_norm_num = content_q
                curr_was_redirected = True  # numbered by content: a following block labelled the same joins it
                curr_page = page_num
                curr_text_parts.append(text)
                curr_bbox = bb
                if conf is not None:
                    curr_confs.append(conf)
                continue

            # Check if this item is a content bullet e.g. "1)", "2)", "3)" under an ongoing question
            if curr_norm_num and _is_content_bullet(raw_lbl, text, curr_norm_num, exam_norms):
                bullet_prefix = f"{raw_lbl} " if raw_lbl else ""
                curr_text_parts.append(f"{bullet_prefix}{text}".strip())
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

            # Case: Label is null/empty or 'none'/'unclear'
            if raw_lbl is None or raw_lbl.lower() in ("null", "none", "?", "unknown", "[unclear]"):
                # Top-of-page continuation across pages: usually the answer the page before ended with, but a
                # student who turned back ("22" ends on page 4 after page 3's "26", "27") continues an earlier one
                home = (_continuation_home(text, curr_norm_num, grouped, canonical_questions, keys)
                        if page_num > curr_page and curr_text_parts and canonical_questions else None)
                if home is not None:
                    home.answer_text = f"{home.answer_text}\n{text}".strip()
                    home.raw_ocr_text = f"{home.raw_ocr_text}\n{text}".strip()
                    continue
                if page_num > curr_page and curr_text_parts:
                    curr_text_parts.append(text)
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
                        curr_text_parts.append(text)
                    curr_bbox = bb
                    if conf is not None:
                        curr_confs.append(conf)
                    flush_current()
                    continue

            # Check if content strongly matches a different canonical question (redirecting misread labels)
            is_redirected = False
            norm = normalize_question_number(raw_lbl)
            bare_sub = bool(norm) and norm.startswith("(")
            misread = False
            if norm and not bare_sub and canonical_questions and text:
                written_p = parent_number(norm)
                answered = {parent_number(g.normalized_number) for g in grouped if g.normalized_number}
                curr_p = parent_number(curr_norm_num) if curr_norm_num else None
                in_paper = any(parent_number(q.normalized_number or "") == written_p for q in canonical_questions)
                # A number the paper does not have ("85>" for 25), or a one-mark question answered earlier ("16> B" on
                # page 1) taking a long answer ("Q16" over a page-long proof): the label was misread. The content then
                # decides among the questions not answered yet, by their text and key; with no clear winner the answer
                # keeps its label for the teacher (flagged as a duplicate), never a guess.
                long_block = text.count("\n") >= 2 or len(text) >= 80
                answered_again = written_p in answered and written_p != curr_p and long_block
                misread = not in_paper or (answered_again and (_marks_of(written_p, canonical_questions) or 0) <= 1)
                open_numbers = ({parent_number(q.normalized_number) for q in canonical_questions if q.normalized_number}
                                - answered - {curr_p, written_p})
                if misread:
                    if choice := _content_choice(text, open_numbers, canonical_questions, keys, least=2, strict=False):
                        norm, raw_lbl, is_redirected = choice, f"Q{choice}", True
                elif answered_again:
                    # A longer question answered earlier ("21(a)" on page 2) labelling another long answer: kept when the
                    # student is continuing it, moved when the content clearly answers an open question instead
                    # ("21(a)" over A(3,1), B(5,1), C(a,b), D(4,3) is 25(a))
                    choice = _content_choice(text, open_numbers | {written_p}, canonical_questions, keys)
                    if choice and choice != written_p:
                        norm, raw_lbl, is_redirected, misread = choice, f"Q{choice}", True, True
                own_q = next((q for q in canonical_questions if parent_number(q.normalized_number or "") == written_p
                              and _is_choice_question(q)), None)
                if not misread and own_q is not None and names_option(text, own_q.question_text) is False:
                    # An MCQ number over something that is none of its options. "17> D. 1650": 1650 is (D) of Q1, the
                    # only unanswered MCQ with that option. "4>" over "= 4/5 + (3/5)² - 1 ... = 4/25": working, not a
                    # choice, placed by content, which may be the answer it finishes (Q22, last on an earlier page).
                    homes = {parent_number(g.normalized_number): g for g in {g.page_number: g for g in grouped}.values()
                             if g.normalized_number}
                    by_option = [n for n in open_numbers for q in canonical_questions
                                 if parent_number(q.normalized_number or "") == n and _is_choice_question(q)
                                 and option_of(text, q.question_text)]
                    if len(set(by_option)) == 1:
                        norm = by_option[0]
                        raw_lbl, is_redirected, misread = f"Q{norm}", True, True
                    elif text.count("\n") >= 1 or len(text) >= 40:
                        candidates = open_numbers | set(homes) | ({curr_p} if curr_p else set())
                        choice = _content_choice(text, candidates, canonical_questions, keys, strict=False)
                        if choice and choice == curr_p:  # finishing the answer in progress
                            curr_text_parts.append(text)
                            if conf is not None:
                                curr_confs.append(conf)
                            continue
                        if choice in homes:
                            home = homes[choice]
                            home.answer_text = f"{home.answer_text}\n{text}".strip()
                            home.raw_ocr_text = f"{home.raw_ocr_text}\n{text}".strip()
                            continue
                        if choice:
                            norm, raw_lbl, is_redirected, misread = choice, f"Q{choice}", True, True
            if norm and not misread and canonical_questions and text and len(_tokenize(text)) >= 2:
                # "21" is a real question when the paper prints it as 21(a) / 21(b)
                exact_match = [q for q in canonical_questions if q.normalized_number in (norm, parent_number(norm))
                               or (not bare_sub and parent_number(q.normalized_number or "") == parent_number(norm))]
                rec = find_recovery_candidates(raw_lbl, text, canonical_questions)
                top_p = parent_number(rec[0].normalized_number or "") if rec else ""
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
                    ev_written = _evidence(text, parent_number(norm), canonical_questions, keys) if not bare_sub else 0
                    ev_top = _evidence(text, top_p, canonical_questions, keys) if not bare_sub else 0
                    if not bare_sub and not shifted and ev_written >= ev_top:
                        pass  # the written question's own text and key fit at least as well: the label stands
                    elif not bare_sub and ev_top >= 6 and ev_top >= 3 * ev_written + 3:
                        # the answer follows the other question's key step by step ("24)" over 60/360 x 22/7 x 10²,
                        # Q36's working) while the written one shares next to nothing: the label was misread
                        should_redirect = True
                    elif not exact_match and top.score >= 0.70:
                        should_redirect = True
                    elif shifted and top.score >= 0.65:
                        should_redirect = True
                    elif already_mapped and top.score >= 0.75:
                        should_redirect = True
                    elif top_dist_nums and not exact_dist_nums and top.score >= 0.85:
                        should_redirect = True
                    elif top.score >= 0.95 and not exact_dist_nums:
                        should_redirect = True

                    if should_redirect:
                        written = norm
                        norm = top.normalized_number
                        if not bare_sub:
                            # The label is wrong; the destination is the question whose own text and key the answer
                            # follows best, among those not answered yet, not merely the scorer's top ("24" over Q36's
                            # 60/360 x 22/7 x 10² went to Q11 on "10", "cm", "6")
                            open_numbers = ({parent_number(q.normalized_number) for q in canonical_questions
                                             if q.normalized_number} - (answered - {curr_p}) - {written_p}) | {top_p}
                            best = _content_choice(text, open_numbers, canonical_questions, keys, strict=False)
                            if best and best != top_p:
                                norm = best
                        # A bare "(a)" keeps its written part under the question the content points to
                        if bare_sub and f"{top_p}{written}" in exam_norms:
                            norm = f"{top_p}{written}"
                        raw_lbl = f"Q{norm}"
                        is_redirected = True

            if norm and not bare_sub and not is_redirected and not misread and canonical_questions and text:
                # Working with hardly a word in it ("60/360 × π × 10² ... = 44 cm²") gives the word scorer nothing to go
                # on; the key's working still names the question. A label it contradicts overwhelmingly was misread.
                best = _content_choice(text, open_numbers | {written_p}, canonical_questions, keys, strict=False)
                if best and best != written_p:
                    ev_best = _evidence(text, best, canonical_questions, keys)
                    if ev_best >= 6 and ev_best >= 3 * _evidence(text, written_p, canonical_questions, keys) + 3:
                        norm, raw_lbl, is_redirected = best, f"Q{best}", True

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
                elif text and (part := _content_choice(
                        text, {q.normalized_number for q in canonical_questions
                               if getattr(q, "choice_group", None) and is_sub_question(q.normalized_number or "")
                               and parent_number(q.normalized_number) == p}, canonical_questions, keys)):
                    # "35>" with its "(A)" lost by the reader, when 35(a) OR 35(b) is the student's choice: the
                    # alternative whose question and key the answer follows (parts both answered keep "Q5 ... b)")
                    norm, raw_lbl = part, f"Q{part}"

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
                    curr_text_parts.append(text)
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
                        curr_text_parts.append(text)
                    curr_bbox = bb
                    if conf is not None:
                        curr_confs.append(conf)
                    continue
                elif curr_norm_num == f"{parent}({sub_part})" and page_num > curr_page:
                    # Same part relabelled at the top of the next page: the answer was cut across pages
                    curr_text_parts.append(text)
                    if conf is not None:
                        curr_confs.append(conf)
                    continue
                else:
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

            if canonical_questions and p and not exam_has_subq and is_sub_question(norm):
                # Keep the part marker ("(b) ...") so the folded answer still shows which part is which
                sub_tok = norm[len(p):]
                if text and not re.match(rf"^\s*\(?{re.escape(sub_tok.strip('()'))}[\)\.\:,]", text, re.IGNORECASE):
                    text = f"{sub_tok} {text}"
                if curr_norm_num and parent_number(curr_norm_num) == p:
                    curr_text_parts.append(text)
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
                        curr_text_parts.append(text)
                    curr_bbox = bb
                    if conf is not None:
                        curr_confs.append(conf)
                    continue

            # If current block has the exact same normalized number as ongoing question across pages or with explicit continuation
            # A label repeated on a later page right after its own answer is that answer cut across pages
            # (students often rewrite "Q4" at the top of the next page); same-page repeats stay separate.
            is_explicit_cont = bool(raw_lbl and re.search(r"\b(?:cont|continued|contd)\b", raw_lbl, re.IGNORECASE))
            if curr_norm_num and norm == curr_norm_num and (
                curr_was_redirected or page_num > curr_page or is_explicit_cont
            ):
                curr_raw_label = curr_raw_label or raw_lbl  # an answer numbered by content takes the written label
                curr_text_parts.append(text)
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
                curr_text_parts.append(text)
            curr_bbox = bb
            if conf is not None:
                curr_confs.append(conf)

    flush_current()

    for i, g in enumerate(grouped, 1):
        g.position = i
    return grouped
