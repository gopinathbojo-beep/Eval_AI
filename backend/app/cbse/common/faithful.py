"""What the reading model wrote that the student did not, taken out of each page's blocks before they are grouped into
answers, so only the student's own ink is mapped and graded.

The 4B reading model is given each question's opening words (to read the labels) and knows the subject, and it
sometimes writes from them instead of the page:
  - another question's text inside an answer: "In ∆ABC and ∆PQR, ∠B = ∠Q, ∠R = ∠C and AB = 2PQ, then prove that
    AD/DB = AE/EC" under a Q32 proof is Q16's opening. A run of ECHO_RUN words (two letters or more: coordinates
    like "A(3,1), B(5,1)" a student copies from the question do not count) of a question other than the one the block
    is labelled with is cut out without asking: a student copies their own question, never another one.
  - lines it completed from the question or the key ("Using the identity:", "(since x cannot be negative)"), and a line
    written twice. Each block is compared with its own question and key; a line that shares SUSPECT_RUN words with them,
    or repeats the line before, is put back to the model with the page image (confirm), and a line the model says is
    not on the page is removed. A line is never removed on the text comparison alone: a correct answer matches the key.

The original reading stays in the page's ocr/page-NNN.json; what was removed is returned for the log.
"""
from __future__ import annotations
import re
from typing import Any, Callable

from .numbering import normalize_question_number, parent_number

ECHO_RUN = 6      # words in a row of another question: its text copied in, not written
SUSPECT_RUN = 4   # words in a row of the block's own question or key: checked against the page
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_LETTERS = re.compile(r"[^\W\d_]", re.UNICODE)
_LEAD_NUMBER = re.compile(r"^\s*Q?\.?\s*(\d{1,3})")
_LIST_ROW = re.compile(r"^\s*Q?\s*(\d{1,3}(?:\s*\([a-zA-Z]{1,3}\))?)\s*[>)]?\s*\(\s*\d+(?:\.\d+)?\s*m\s*\)", re.I)

# The reader sometimes writes the student's working as LaTeX ("\(\frac{60}{360} \times \pi \times 10^2\)"); the
# student wrote 60/360 × π × 10². Written back in plain notation: same content, no markup to render or to grade.
_LATEX_SYMBOLS = {r"\times": "×", r"\cdot": "·", r"\div": "÷", r"\pm": "±", r"\pi": "π", r"\theta": "θ",
                  r"\alpha": "α", r"\beta": "β", r"\angle": "∠", r"\triangle": "Δ", r"\Delta": "Δ", r"\leq": "≤",
                  r"\le": "≤", r"\geq": "≥", r"\ge": "≥", r"\neq": "≠", r"\ne": "≠", r"\therefore": "∴",
                  r"\because": "∵", r"\parallel": "∥", r"\sim": "~", r"\infty": "∞", r"\circ": "°", r"\degree": "°",
                  r"\Rightarrow": "⇒", r"\implies": "⇒", r"\rightarrow": "→", r"\to": "→", r"\sqrt": "√"}
_SUPER = str.maketrans("0123456789n+-", "⁰¹²³⁴⁵⁶⁷⁸⁹ⁿ⁺⁻")
_FRAC = re.compile(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
_SQRT = re.compile(r"√\s*\{([^{}]*)\}")
_POWER = re.compile(r"\^\s*(?:\{([0-9n+\-]{1,3})\}|([0-9n]))")
_SYMBOL = re.compile("|".join(re.escape(k) for k in sorted(_LATEX_SYMBOLS, key=len, reverse=True)) + r"(?![A-Za-z])")


def _group(s: str) -> str:
    s = s.strip()
    return f"({s})" if re.search(r"[+\-−×·/ ]", s) and not (s.startswith("(") and s.endswith(")")) else s


def plain_math(text: str) -> str:
    """LaTeX the reader wrote, in the notation on the sheet: "\\frac{1100}{21}" -> "1100/21", "10^2" -> "10²"."""
    if "\\" not in text and "^" not in text:
        return text
    t = re.sub(r"\\[()\[\]]|\$", "", text)
    t = re.sub(r"\\(?:left|right|big|Big)\s*", "", t)
    t = re.sub(r"\\(?:text|mathrm|mathbf)\s*\{([^{}]*)\}", r"\1", t)
    t = _SYMBOL.sub(lambda m: _LATEX_SYMBOLS[m.group()], t)
    for _ in range(4):  # nested fractions, innermost first
        t2 = _FRAC.sub(lambda m: f"{_group(m.group(1))}/{_group(m.group(2))}", t)
        if t2 == t:
            break
        t = t2
    t = _SQRT.sub(lambda m: "√" + _group(m.group(1)), t)
    t = _POWER.sub(lambda m: (m.group(1) or m.group(2)).translate(_SUPER), t)
    return re.sub(r"[ \t]{2,}", " ", t.replace("{", "").replace("}", ""))


# confirm(page_number, lines) -> one answer per line: True written on the page, False not, None unknown
Confirm = Callable[[int, list[str]], list[bool | None]]


def _words(text: str) -> list[re.Match]:
    return list(_WORD.finditer(text or ""))


def _is_word(w: str) -> bool:
    return len(_LETTERS.findall(w)) >= 2


def _norm(w: str) -> str:
    return w.casefold()


def _runs(a: list[str], b: list[str], min_len: int) -> list[tuple[int, int]]:
    """Each maximal stretch of a (start, length) of at least min_len words that also occurs in b, in order."""
    if len(a) < min_len or len(b) < min_len:
        return []
    grams = {tuple(b[i:i + min_len]) for i in range(len(b) - min_len + 1)}
    covered = [False] * len(a)
    for i in range(len(a) - min_len + 1):
        if tuple(a[i:i + min_len]) in grams:
            for j in range(i, i + min_len):
                covered[j] = True
    out, i = [], 0
    while i < len(a):
        if covered[i]:
            j = i
            while j < len(a) and covered[j]:
                j += 1
            out.append((i, j - i))
            i = j
        else:
            i += 1
    return out


def _question_of(label: str | None) -> str | None:
    """'26> To prove ...' -> '26', '21(a) >' -> '21', '(b)' -> None."""
    if not label:
        return None
    norm = normalize_question_number(label.split("\n")[0].strip())
    if norm and not norm.startswith("("):
        return parent_number(norm)
    m = _LEAD_NUMBER.match(label)
    return m.group(1) if m else None


def _texts_by_question(canonical_questions: list[Any], keys: dict[str, str] | None) -> tuple[dict, dict]:
    questions: dict[str, str] = {}
    for q in canonical_questions or []:
        n = parent_number(getattr(q, "normalized_number", "") or "")
        if n:
            questions[n] = f"{questions.get(n, '')} {getattr(q, 'question_text', '') or ''}"
    answers: dict[str, str] = {}
    for n, text in (keys or {}).items():
        p = parent_number(n or "")
        if p:
            answers[p] = f"{answers.get(p, '')} {text or ''}"
    return questions, answers


def _cut_echoes(text: str, own: str | None, questions: dict[str, str]) -> tuple[str, list[str]]:
    """The text without any ECHO_RUN-word run of a question other than its own."""
    found = [m for m in _words(text) if _is_word(m.group())]
    words = [_norm(m.group()) for m in found]
    spans: list[tuple[int, int]] = []
    for n, q_text in questions.items():
        if n == own:
            continue
        for start, length in _runs(words, [_norm(w) for w in _WORD.findall(q_text) if _is_word(w)], ECHO_RUN):
            spans.append((found[start].start(), found[start + length - 1].end()))
    if not spans:
        return text, []
    removed, out, at = [], [], 0
    for s, e in sorted(spans):
        if s < at:
            s = at
        if s >= e:
            continue
        out.append(text[at:s])
        removed.append(text[s:e])
        at = e
    out.append(text[at:])
    cleaned = re.sub(r"[ \t]{2,}", " ", "".join(out))
    cleaned = re.sub(r"^[ \t,;:]+", "", cleaned, flags=re.M).strip()
    return cleaned, removed


def _suspect_lines(lines: list[str], ref_words: list[str]) -> list[int]:
    """Lines sharing SUSPECT_RUN words in a row with the question and key, or repeating the line before. Not every line
    of words: asked about all of them, the 4B model removed lines the student wrote ("Since p & q are integers, the
    RHS is rational") and kept one it had added ("Given that the difference in time is 1 hour:")."""
    out = []
    prev = None
    for i, line in enumerate(lines):
        words = [_norm(w) for w in _WORD.findall(line)]
        if len(words) >= 3 and words == prev:
            out.append(i)
        elif ref_words and _runs(words, ref_words, SUSPECT_RUN):
            out.append(i)
        prev = words or prev
    return out


def check_reading(page_results: list[tuple[dict, Any]], canonical_questions: list[Any] | None,
                  keys: dict[str, str] | None, confirm: Confirm | None) -> list[str]:
    """Each block's answer_text with what the student did not write taken out (in place); what was removed."""
    if not canonical_questions:
        return []
    questions, key_texts = _texts_by_question(canonical_questions, keys)
    one_mark = {parent_number(getattr(q, "normalized_number", "") or "") for q in canonical_questions
                if (getattr(q, "max_marks", None) or 0) <= 1}
    notes: list[str] = []
    seen: set[str] = set()  # questions labelled on an earlier block
    for page, result in page_results:
        page_number = page.get("page_number")
        suspects: list[tuple[Any, int, list[str]]] = []  # (block, line index, lines)
        for block in getattr(result, "answers", None) or []:
            label = getattr(block, "raw_question_label", None) or getattr(block, "question_number", None)
            if label and (m := _LIST_ROW.match(label)):
                # the label is a row of the question list in the prompt ("33(a) (2 m): A. Find the smallest number
                # which ..."): the student wrote only its number
                notes.append(f"p{page_number} {label[:40]!r}: label cut to {m.group(1)!r} (copied from the question list)")
                label = m.group(1)
                for name in ("raw_question_label", "question_number"):
                    if getattr(block, name, None):
                        setattr(block, name, label)
            own = _question_of(label)
            text = plain_math(block.answer_text or "")
            # the model's own label is no alibi: "Q16" over a page-long proof, when Q16 is a one-mark question answered
            # earlier ("16> B"), is the model naming the question it copied; that question's text is cut too
            vouched = own and not (own in seen and own in one_mark and (text.count("\n") >= 2 or len(text) >= 80))
            if own:
                seen.add(own)
            if own:  # an unlabelled block may be the student copying a question out: left alone
                text, cut = _cut_echoes(text, own if vouched else None, questions)
                notes += [f"p{page_number} {label!r}: removed another question's text {c!r}" for c in cut]
            lines = text.split("\n")
            ref = _WORD.findall(f"{questions.get(own, '')} {key_texts.get(own, '')}") if own else []
            for i in _suspect_lines(lines, [_norm(w) for w in ref]):
                suspects.append((block, i, lines))
            block.answer_text = text
        if not suspects or confirm is None:
            continue
        try:
            verdicts = confirm(page_number, [lines[i] for _, i, lines in suspects])
        except Exception as e:  # the check is a safeguard: the reading stands when it cannot run
            notes.append(f"p{page_number}: could not check the reading ({e})")
            continue
        drop: dict[int, set[int]] = {}
        for (block, i, lines), written in zip(suspects, verdicts):
            if written is False:
                drop.setdefault(id(block), set()).add(i)
                notes.append(f"p{page_number}: removed a line not on the page {lines[i]!r}")
        for block, _, lines in suspects:
            if id(block) in drop:
                block.answer_text = "\n".join(l for j, l in enumerate(lines) if j not in drop[id(block)]).strip()
                drop.pop(id(block))
    return notes
