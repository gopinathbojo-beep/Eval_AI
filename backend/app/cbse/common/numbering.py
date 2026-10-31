"""Question-number normalisation. Pure functions, no I/O.

normalize_question_number("Q1") -> "1"
normalize_question_number("3 (a)") -> "3(a)"
Unparseable input returns None (never a guess).
"""
from __future__ import annotations
import re
from .subjects.tamil import format as tamil_format

_PREFIX = re.compile(
    r"^\s*(?:(?:section|part|unit|group|sec)\s+[a-z0-9ivx]+\s*[\-\:\–\—]?\s*)?"
    r"(?:question\s*no\.?|ques\s*no\.?|qn\s*no\.?|q\.?\s*no\.?|question|ques|qn|q|answer|ans|solution|sol|no\.?|வினா|விடை|கேள்வி|பதில்|प्रश्न|उत्तर)"
    r"\s*[\.\:\-\>\→\,]?\s*(?=\d|\(|\b[ivx]+\b|[a-z]\b)",
    re.IGNORECASE,
)
_MEASURE_UNITS = re.compile(
    r"^\s*\d+(?:\.\d+)?\s*(?:kg|g|mg|cm|mm|m|km|v|mv|kv|ma|amps?|amperes?|w|kw|hz|khz|mhz|sec|min|hr|hrs|hours?|marks?|pts?|points?|%|percent|deg|°c|°f|k|pa|kpa|n|j|kj|cal|kcal|mol|l|ml|db|rpm|bits?|bytes?|kb|mb|gb)\b",
    re.IGNORECASE,
)
_ROMAN = re.compile(r"^(?:i{1,3}|iv|v|vi{1,3}|ix|x|xi{1,3}|xiv|xv)$", re.IGNORECASE)
_ROMAN_VALS = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
    "xi": 11, "xii": 12, "xiii": 13, "xiv": 14, "xv": 15,
}
_NULLISH = {"", "null", "none", "unknown", "n/a", "na", "?", "-", "[unclear]", "unclear"}


def subquestion_value(tok: str | None) -> int:
    """Returns integer rank for subquestion token: Roman numerals (i->1, xii->12), letters (a->1, z->26), or digits (1->1)."""
    if not tok:
        return 0
    t = tok.strip().lower()
    if t in _ROMAN_VALS:
        return _ROMAN_VALS[t]
    if len(t) == 1 and 'a' <= t <= 'z':
        return ord(t) - ord('a') + 1
    if t.isdigit():
        return int(t)
    return 0


def _clean_token(tok: str) -> str | None:
    tok = tok.strip().lower()
    if re.fullmatch(r"[a-z]", tok) or _ROMAN.match(tok):
        return tok
    if re.fullmatch(r"\d{1,2}", tok):
        return str(int(tok))
    return None


# A question of a part whose numbering restarts: "B1", "B-5(a)", "Part B 3" (capital part letter; Part A keeps plain
# numbers). Lower case is left alone: "b1" is more likely a misread sub-part than a part.
_PART_NUMBER = re.compile(r"^(?:part\s*)?([B-F])\s*[-–.]?\s*(\d{1,3}(?!\d).*)$")


def part_and_number(normalized: str | None) -> tuple[str, int] | None:
    """("B", 5) for "B5" / "B5(a)", ("", 5) for "5(a)"; None when the number is not a question number."""
    m = re.match(r"^([B-F]?)(\d{1,3})(?:\(|$)", normalized or "")
    return (m.group(1), int(m.group(2))) if m else None


def normalize_question_number(raw: str | int | None) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if tamil_format.has_tamil(s):
        s = tamil_format.latin_label(s)
    if s.lower() in _NULLISH:
        return None
    if m := _PART_NUMBER.match(re.sub(r"(?i)^part\b", "part", s)):
        inner = normalize_question_number(m.group(2))
        return f"{m.group(1)}{inner}" if inner and inner[0].isdigit() else None

    # Measurements / units guard: prevent floats with units (e.g. 1.5 kg, 10 cm, 5 marks) from being parsed as Q numbers
    if _MEASURE_UNITS.match(s):
        return None

    # Large 4+ digit numbers (e.g. 2024, 1947, 10000) are dates/years/amounts, never question numbers
    if re.match(r"^\d{4,}", s):
        return None

    had_prefix = bool(_PREFIX.search(s))
    s = _PREFIX.sub("", s).strip()
    s = s.replace("（", "(").replace("）", ")").replace("[", "(").replace("]", ")")
    s = re.sub(r"^[\,\:\-\>\→\.]\s*", "", s)

    # Bare subquestion: (a), (b), (i), (ii), a), b), i), ii), a., b., i., ii.
    m_bare_sub = re.match(r"^(?:\(\s*([a-zA-Z]{1,4}|[ivxIVX]{1,5})\s*\)|([a-zA-Z]|[ivxIVX]{1,5})[\.\)\:\>\→\,\-–—])\s*$", s)
    if m_bare_sub:
        tok = _clean_token(m_bare_sub.group(1) or m_bare_sub.group(2))
        if tok:
            return f"({tok})"

    # Parenthesized main number: (1), (2), (1)(a), (1) a
    pm = re.match(r"^\(\s*(\d{1,3})\s*\)(.*)$", s)
    if pm:
        number = str(int(pm.group(1)))
        rest = pm.group(2).strip()
        had_delim = True
    else:
        # Check if leading number has a delimiter like 1., 1), 1:, 1>, 1,, 1-, or just 1
        m_delim = re.match(r"^(\d{1,3})\s*([\.\:\)\>\→\}\]\,\-–—])\s*(.*)$", s)
        if m_delim:
            number = str(int(m_delim.group(1)))
            had_delim = True
            delim = m_delim.group(2)
            rest = m_delim.group(3).strip()
            if delim in (".", "/") and rest:
                rest = f"{delim}{rest}"
        else:
            m = re.match(r"^(\d{1,3})(.*)$", s)
            if not m:
                rm = re.match(r"^([ivxIVX]{1,5})[\.\:\)\>\→\,]?\s*(.*)$", s)
                if rm and _ROMAN.match(rm.group(1)):
                    number = str(_ROMAN_VALS[rm.group(1).lower()])
                    rest = rm.group(2).strip()
                    had_delim = True
                else:
                    return None
            else:
                number = str(int(m.group(1)))
                rest = m.group(2).strip()
                had_delim = False

    # Universal chained subparts parsing: e.g. .1.1, (a)(i), .a.i, /1/a, etc.
    parts: list[str] = []

    # Optional single bare token directly after number: "3a", "3 a", "3-a", "3(a)", "3 a)"
    bm = re.match(r"^\s*([a-zA-Z]{1,3})(?=\(|\)|$|[\s\,\.\:\-\>\→])", rest)
    if bm and len(bm.group(1)) <= 2:
        tok = _clean_token(bm.group(1))
        if tok is not None:
            parts.append(tok)
            rest = re.sub(r"^\)", "", rest[bm.end():]).strip()

    while rest:
        rest = rest.strip(" :>-→,")
        if not rest:
            break
        # Parenthesized token: (a), (1), (i)
        if rest.startswith("("):
            pm = re.match(r"^\(\s*([a-zA-Z0-9]{1,4})\s*\)(.*)$", rest)
            if pm:
                tok = _clean_token(pm.group(1))
                if tok is not None:
                    parts.append(tok)
                    rest = pm.group(2)
                    continue
        # Dotted or slashed token: .1, /a, .i
        dm = re.match(r"^[./]\s*(\d{1,2}|[a-zA-Z]{1,4})(.*)$", rest)
        if dm:
            tok = _clean_token(dm.group(1))
            if tok is not None:
                parts.append(tok)
                rest = dm.group(2)
                continue
        break

    rest = rest.strip(" :>-→,.")
    if rest:
        if not (had_delim or had_prefix):
            return None

    return number + "".join(f"({p})" for p in parts)



def parent_number(normalized: str) -> str:
    if not normalized or normalized.startswith("("):
        return ""
    return normalized.split("(", 1)[0]


def subpart_path(normalized: str | None) -> list[str]:
    """Returns list of subpart tokens: '1(a)(ii)' -> ['a', 'ii'], '(b)' -> ['b'], '1' -> []"""
    if not normalized:
        return []
    return re.findall(r"\(([^)]+)\)", normalized)


def is_sub_question(normalized: str) -> bool:
    return bool(normalized and "(" in normalized)


def extract_subquestion_token(raw: str | None) -> str | None:
    """Extracts a bare subquestion token (e.g. '(b)' -> 'b', 'b>' -> 'b', '(ii)' -> 'ii') if raw is purely a subquestion label."""
    if raw is None:
        return None
    s = str(raw).strip()
    if tamil_format.has_tamil(s):
        s = tamil_format.latin_subparts(s)
    if s.lower() in _NULLISH:
        return None
    s = _PREFIX.sub("", s).strip()
    s = s.replace("（", "(").replace("）", ")").replace("[", "(").replace("]", ")")
    # Subquestion in parentheses e.g. (a), (b), (i)
    pm = re.match(r"^\(\s*([a-zA-Z]{1,4}|[ivxIVX]{1,5})\s*\)$", s)
    if pm:
        return _clean_token(pm.group(1))
    # Subquestion with dot, paren, colon, comma, dash, or angle bracket: a), b., i), a>, b>, a,, b,
    sm = re.match(r"^([a-zA-Z]{1,4}|[ivxIVX]{1,5})[\.\)\:\>\→\,\-–—]$", s)
    if sm:
        return _clean_token(sm.group(1))
    # Compound question with subquestion e.g. 10(a), Q10(a), 1(b)
    cm = re.search(r"\(\s*([a-zA-Z]{1,4}|[ivxIVX]{1,5})\s*\)", s)
    if cm:
        return _clean_token(cm.group(1))
    return None


def extract_label_from_text_prefix(text: str) -> tuple[str | None, str]:
    """Check if question or answer text begins with an explicit question label like '01.', '1.', 'Q1:', 'Q1,', '1>', '01/02', etc."""
    s = text.strip()
    if tamil_format.has_tamil(s) and (tamil := tamil_format.extract_label_prefix(s)) is not None:
        return tamil

    # Pattern 1: Q1, Q.1, Question 1, Qn 1, etc. with :, ., comma, >, or whitespace
    m_q = re.match(r"^\s*(?:(?:Q(?:uestion)?|Qn|Ques)\.?\s*([0-9]+[a-zA-Z\(\)]*))[\.\:\)\s\-\/\,\>\→]+(.*)", s, re.IGNORECASE | re.DOTALL)
    if m_q:
        lbl = m_q.group(1).strip()
        rest = m_q.group(2).strip()
        return lbl, (rest if rest else s)

    # Pattern 2: Parenthesized number or Roman/letter subquestion e.g. (1), (2), (i), (ii), (a)
    m_paren = re.match(r"^\s*\(\s*([0-9]{1,3}(?:[a-zA-Z]|\([a-zA-Z0-9]+\))?|[a-zA-Z]{1,2}|[ivxIVX]{1,5})\s*\)[\.\:\s\-\/\,\>\→]*(.*)", s, re.DOTALL)
    if m_paren:
        inner = m_paren.group(1).strip()
        rest = m_paren.group(2).strip()
        if inner.isdigit():
            lbl = inner
        else:
            lbl = f"({inner})"
        return lbl, (rest if rest else s)

    # Pattern 3: Number followed by separator: e.g. '01.', '1)', '1 -', '01/02', '1.a', '3(a)', '1>', '1,'
    m_num = re.match(r"^\s*([0-9]{1,3}(?:[\.\-\/][0-9]{1,3}|\([a-zA-Z0-9]+\)|[a-zA-Z])?)[\.\:\)\s\-\/\,\>\→]+(.*)", s, re.DOTALL)
    if m_num:
        lbl = m_num.group(1).strip()
        rest = m_num.group(2).strip()
        if len(lbl) <= 6 and not (len(lbl) == 4 and lbl.startswith("20")):
            return lbl, (rest if rest else s)

    return None, s


_PART_MARK = re.compile(r"\b(?:PART|SECTION)\s*[-–:]?\s*([B-F]|II|III|IV|V|VI)\b", re.IGNORECASE)
_PART_LETTERS = {"II": "B", "III": "C", "IV": "D", "V": "E", "VI": "F"}


def part_labels(items: list, qs: list) -> list[str | None]:
    """Labels for answers or keys (in sheet order) that belong to a part whose numbering restarts ("Q1" in Part B ->
    "B1"); None for the rest. Answers need raw_question_number and answer_text.

    Students rarely write the part. In order of strength: a part written in the label or the answer's opening ("B1",
    "Part B"); a number the student has already answered in this part (a second "1" starts the next part); a long
    written answer under a number whose earlier-part question is a multiple choice."""
    letters = sorted({pn[0] for q in qs if (pn := part_and_number(parent_number(q.normalized_number or ""))) and pn[0]})
    if not letters:
        return [None] * len(items)
    order = [""] + letters
    by_num = {q.normalized_number: q for q in qs}
    idx, used, out = 0, set(), []
    for a in items:
        out.append(None)
        if getattr(a, "status", None) == "IGNORED":
            continue
        if m := _PART_MARK.search(f"{a.raw_question_number or ''} {(a.answer_text or '')[:40]}"):
            letter = _PART_LETTERS.get(m.group(1).upper(), m.group(1).upper())
            if letter in order and order.index(letter) != idx:
                idx, used = order.index(letter), set()
        norm = normalize_question_number(a.raw_question_number) if a.raw_question_number else None
        pn = part_and_number(norm)
        if not pn or pn[0]:
            if pn:
                idx, used = order.index(pn[0]) if pn[0] in order else idx, used
            continue
        if norm in used and idx + 1 < len(order):
            idx, used = idx + 1, set()
        if not order[idx] and idx + 1 < len(order) and f"{order[idx + 1]}{norm}" in by_num:
            q = by_num.get(norm)
            if q is not None and getattr(q, "question_type", None) == "mcq" and len((a.answer_text or "").split()) > 8:
                idx, used = idx + 1, set()  # a written answer under an MCQ's number: the student is in the next part
        used.add(norm)
        if order[idx]:
            out[-1] = f"{order[idx]}{norm}"
    return out
