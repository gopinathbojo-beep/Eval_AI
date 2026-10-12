"""Question-number normalisation. Pure functions, no I/O.

normalize_question_number("Q1") -> "1"
normalize_question_number("3 (a)") -> "3(a)"
Unparseable input returns None (never a guess).
"""
from __future__ import annotations
import re

_PREFIX = re.compile(
    r"^\s*(?:(?:section|part|unit|group|sec)\s+[a-z0-9ivx]+\s*[\-\:\–\—]?\s*)?(?:question|ques|qn|q\.?\s*no\.?|q|answer|ans|no\.?|வினா)\s*[\.\:\-]?\s*(?=\d|\(|\b[ivx]+\b)",
    re.IGNORECASE,
)
_ROMAN = re.compile(r"^(?:i{1,3}|iv|v|vi{1,3}|ix|x)$", re.IGNORECASE)
_ROMAN_VALS = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10}
_NULLISH = {"", "null", "none", "unknown", "n/a", "na", "?", "-", "[unclear]", "unclear"}


def _clean_token(tok: str) -> str | None:
    tok = tok.strip().lower()
    if re.fullmatch(r"[a-z]", tok) or _ROMAN.match(tok):
        return tok
    if re.fullmatch(r"\d{1,2}", tok):
        return str(int(tok))
    return None


def normalize_question_number(raw: str | int | None) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if s.lower() in _NULLISH:
        return None
    s = _PREFIX.sub("", s).strip()
    s = s.replace("（", "(").replace("）", ")").replace("[", "(").replace("]", ")")

    # Parenthesized main number: (1), (2), (1)(a), (1) a
    pm = re.match(r"^\(\s*(\d{1,3})\s*\)(.*)$", s)
    if pm:
        number = str(int(pm.group(1)))
        rest = pm.group(2).strip()
    else:
        # Standard leading number: 1, 1., 1), 1:
        m = re.match(r"^(\d{1,3})(.*)$", s)
        if not m:
            # Standalone Roman numeral question: I, II, III, IV...
            rm = re.match(r"^([ivxIVX]{1,5})[\.\:\)]?\s*(.*)$", s)
            if rm and _ROMAN.match(rm.group(1)):
                number = str(_ROMAN_VALS[rm.group(1).lower()])
                rest = rm.group(2).strip()
            else:
                return None
        else:
            number = str(int(m.group(1)))
            rest = m.group(2).strip()

    # Dotted subnumber: 1.1 -> 1(1), 1.a -> 1(a)
    if rest.startswith(".") and not rest.startswith(".."):
        dm = re.match(r"^\.\s*(\d{1,2}|[a-zA-Z]{1,4})(.*)$", rest)
        if dm:
            tok = _clean_token(dm.group(1))
            if tok:
                rest = f"({tok}){dm.group(2)}"
            else:
                rest = re.sub(r"^\.[\.\:\)]?\s*", "", rest)
        else:
            rest = re.sub(r"^\.[\.\:\)]?\s*", "", rest)
    elif rest.startswith("/") and not rest.startswith("//"):
        sm = re.match(r"^/\s*(\d{1,2}|[a-zA-Z]{1,4})(.*)$", rest)
        if sm:
            tok = _clean_token(sm.group(1))
            if tok:
                rest = f"({tok}){sm.group(2)}"
            else:
                rest = re.sub(r"^/[\.\:\)]?\s*", "", rest)
        else:
            rest = re.sub(r"^/[\.\:\)]?\s*", "", rest)
    elif not rest.startswith("("):
        rest = re.sub(r"^[\.\:\)]\s*", "", rest)

    rest = re.sub(r"^[\-–—\.]\s*", "", rest)
    rest = rest.rstrip(" .:")
    parts: list[str] = []
    # optional single bare token directly after number: "3a", "3 a", "3-a"
    bm = re.match(r"^([a-zA-Z]{1,4})(?=\(|$)", rest)
    if bm:
        tok = _clean_token(bm.group(1))
        if tok is None:
            return None
        parts.append(tok)
        rest = rest[bm.end():]
    while rest:
        pm = re.match(r"^\(\s*([a-zA-Z0-9]{1,4})\s*\)\s*", rest)
        if not pm:
            return None  # leftover junk -> refuse to guess
        tok = _clean_token(pm.group(1))
        if tok is None:
            return None
        parts.append(tok)
        rest = rest[pm.end():]
    return number + "".join(f"({p})" for p in parts)



def parent_number(normalized: str) -> str:
    return normalized.split("(", 1)[0]


def is_sub_question(normalized: str) -> bool:
    return "(" in normalized
