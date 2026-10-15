"""Deterministic maths checks for evaluation.

The OCR model transcribes formulas as text (x², x^2, (a)/(b), √, π, sometimes LaTeX). This module parses that
text with sympy, without ever eval-ing raw input, and compares the student's working with the answer key:

- final answer equivalence (1024/243 == (4/3)^5, 2156/3 ~ 718.67, 22/7 vs 3.14),
- which numeric results and formulas of the key appear in the student's working,
- arithmetic steps that do not hold (student slip or OCR misread),
- notation that looks like a lost exponent ("R 2 - r 2", "x2 + y2").

The result is handed to the evaluator as facts, and used afterwards to flag AI marks that contradict it.
Nothing here awards marks: the teacher stays the authority.
"""
from __future__ import annotations
import logging
import random
import re
from dataclasses import dataclass, field

import sympy
from sympy.parsing.sympy_parser import parse_expr, standard_transformations

log = logging.getLogger("adem.math_check")

_FUNCS = {"sqrt": sympy.sqrt, "sin": sympy.sin, "cos": sympy.cos, "tan": sympy.tan,
          "log": sympy.log, "ln": sympy.log, "exp": sympy.exp}
_CONSTS = {"pi": sympy.pi}
_NAMES = sorted([*_FUNCS, *_CONSTS], key=len, reverse=True)
# Short words that would otherwise be read as products of single-letter variables.
_STOPWORDS = {
    "a", "i",  # only as whole runs inside prose; single letters are handled before this check
    "an", "as", "at", "be", "by", "do", "if", "in", "is", "it", "of", "on", "or", "so", "to", "up", "we",
    "and", "are", "but", "can", "for", "get", "has", "its", "let", "not", "now", "put", "sum", "the", "use",
    "was", "who", "why", "how", "new", "old", "one", "two", "six", "ten", "per", "all", "any", "add",
    "cm", "mm", "km", "kg", "mg", "ml", "rs", "sq", "mol", "ans", "eq", "lhs", "rhs",
}
_MAX_LEN = 240
_MAX_EXPONENT = 100
_MAX_LITERAL_DIGITS = 15

_SUP_CHARS = "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁽⁾ⁿᵐˣ"
_SUP = str.maketrans(_SUP_CHARS, "0123456789+-()nmx")
_SUB = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_VULGAR = {"½": "(1/2)", "¼": "(1/4)", "¾": "(3/4)", "⅓": "(1/3)", "⅔": "(2/3)", "⅕": "(1/5)", "⅛": "(1/8)"}
_TOKEN = re.compile(r"\s*(?:(?P<num>\d+(?:\.\d+)?|\.\d+)|(?P<id>[A-Za-z]+(?:_[A-Za-z0-9]+)?)|(?P<op>\*\*|[-+*/()]))")


# ---------- normalisation ----------

def _brace_arg(s: str, i: int) -> tuple[str, int] | None:
    """The {...} group starting at s[i] (or a single character), and the index after it."""
    while i < len(s) and s[i] == " ":
        i += 1
    if i >= len(s):
        return None
    if s[i] != "{":
        return s[i], i + 1
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
    return None


def _latex(s: str) -> str:
    s = s.replace("$", "")
    for a, b in ((r"\left", ""), (r"\right", ""), (r"\,", " "), (r"\!", ""), (r"\;", " "), (r"\ ", " "),
                 (r"\times", "*"), (r"\cdot", "*"), (r"\div", "/"), (r"\pi", "pi "), (r"\approx", "≈"),
                 (r"\dfrac", r"\frac"), (r"\tfrac", r"\frac")):
        s = s.replace(a, b)
    for _ in range(20):
        i = s.find(r"\frac")
        if i < 0:
            break
        num = _brace_arg(s, i + 5)
        den = _brace_arg(s, num[1]) if num else None
        if not num or not den:
            return s  # malformed: leave it, the tokenizer will reject it
        mixed = "+" if i > 0 and s[i - 1].isdigit() else ""  # 718\frac{2}{3} is a mixed number
        s = f"{s[:i]}{mixed}(({num[0]})/({den[0]})){s[den[1]:]}"
    for _ in range(20):
        i = s.find(r"\sqrt")
        if i < 0:
            break
        j, root = i + 5, None
        if j < len(s) and s[j] == "[":
            k = s.find("]", j)
            if k < 0:
                return s
            root, j = s[j + 1:k], k + 1
        arg = _brace_arg(s, j)
        if not arg:
            return s
        rep = f"(({arg[0]})^(1/({root})))" if root else f"sqrt({arg[0]})"
        s = s[:i] + rep + s[arg[1]:]
    s = re.sub(r"_\{([A-Za-z0-9]+)\}", r"_\1", s)
    return s.replace("{", "(").replace("}", ")")


def _normalize(s: str) -> str:
    if "\\" in s or "$" in s:
        s = _latex(s)
    for k, v in _VULGAR.items():
        s = s.replace(k, v)
    s = re.sub(f"[{_SUP_CHARS}]+", lambda m: "^(" + m.group().translate(_SUP) + ")", s)
    s = re.sub(r"(?<=[A-Za-z])[₀-₉]+", lambda m: "_" + m.group().translate(_SUB), s)
    s = re.sub(r"√\s*(\d+(?:\.\d+)?|[A-Za-z])", r"sqrt(\1)", s).replace("√", "sqrt")
    for a in "×·⋅∙✕":
        s = s.replace(a, "*")
    s = s.replace("÷", "/").replace("π", "pi ")
    for a in "−–—":
        s = s.replace(a, "-")
    s = s.replace("[", "(").replace("]", ")")
    s = re.sub(r"(?<=\d)\s*%", "*(1/100)", s)
    s = s.replace("°", "")
    return s.replace("^", "**")


_UNITS_MULTI = r"(?:cm|mm|km|kg|mg|ml|mol|sq\.?\s*units?|units?|sq\.?\s*(?:cm|m))"


def _strip_units(s: str) -> str:
    s = re.sub(r"(?:Rs\.?|INR|₹|\$)\s*", "", s)
    s = re.sub(rf"(?<=[\d\s)])\s*{_UNITS_MULTI}\s*(?:\^\s*\(?[23]\)?|[²³23])?(?![A-Za-z])", " ", s)
    # Single-letter units only where they cannot be a variable: squared/cubed after a number, or trailing.
    s = re.sub(r"(?<=\d)\s*[mgsl](?:\s*[²³]|\^\(?[23]\)?)(?![A-Za-z(])", " ", s)
    s = re.sub(r"(?<=\d)\s+[mgsl]\s*$", "", s)
    return s.strip()


def _tokens(s: str) -> list[tuple[str, str]] | None:
    out, pos = [], 0
    while pos < len(s):
        if s[pos:].strip() == "":
            break
        m = _TOKEN.match(s, pos)
        if not m or m.end() == pos:
            return None
        pos = m.end()
        if m.group("num"):
            digits = m.group("num").split(".")[0]
            if len(digits) > _MAX_LITERAL_DIGITS:
                return None
            out.append(("num", m.group("num")))
        elif m.group("op"):
            out.append(("op", m.group("op")))
        else:
            run = m.group("id")
            if "_" in run:
                base = run.split("_", 1)[0]
                if len(base) > 2:
                    return None
                out.append(("sym", run))
                continue
            if run.lower() in _STOPWORDS and len(run) > 1:
                return None
            if run in _FUNCS:
                out.append(("fn", run))
                continue
            if run in _CONSTS:
                out.append(("sym", run))
                continue
            if run.isupper() and 2 <= len(run) <= 4:  # TSA, CSA, AB (a segment)
                out.append(("sym", run))
                continue
            i, plain = 0, 0
            while i < len(run):
                name = next((n for n in _NAMES if run.startswith(n, i)), None)
                if name:
                    out.append(("fn" if name in _FUNCS else "sym", name))
                    i += len(name)
                    plain = 0
                else:
                    out.append(("sym", run[i]))
                    i += 1
                    plain += 1
                    if plain > 3:  # four or more loose letters is a word, not a product
                        return None
    return out


def _emit(toks: list[tuple[str, str]]) -> str | None:
    out: list[str] = []
    prev: tuple[str, str] | None = None
    for t in toks:
        kind, text = t
        if prev is not None:
            pk, pt = prev
            if pk == "fn" and text != "(":
                return None
            closing = pk == "op" and pt == ")"
            if kind == "num" and (pk in ("num", "sym") or closing):
                return None  # "2 3", "x2", "(a+b)2": almost always a lost exponent, never guess
            if (kind == "sym" or kind == "fn" or text == "(") and (pk in ("num", "sym") or closing):
                out.append("*")
        out.append(text)
        prev = t
    if prev and prev[0] == "fn":
        return None
    return " ".join(out)


def _balanced(s: str) -> bool:
    depth = 0
    for c in s:
        depth += (c == "(") - (c == ")")
        if depth < 0:
            return False
    return depth == 0


def _safe_tree(expr: sympy.Basic) -> bool:
    for p in expr.atoms(sympy.Pow):
        e = p.exp
        if not e.free_symbols:
            try:
                if any(isinstance(a, sympy.Pow) for a in sympy.preorder_traversal(e)):
                    return False  # stacked numeric towers like 2^(3^(4^5))
                v = complex(sympy.N(e, 15))
            except Exception:
                return False
            if abs(v) > _MAX_EXPONENT:
                return False
    return True


def parse_math(text: str) -> sympy.Expr | None:
    """Parse one expression (no '=') or return None. Input is tokenized and rebuilt first, so only numbers,
    + - * / ** ( ), whitelisted functions and single-letter/subscripted symbols ever reach sympy."""
    if not text or len(text) > _MAX_LEN:
        return None
    s = _normalize(text)
    toks = _tokens(s)
    if not toks:
        return None
    src = _emit(toks)
    if not src or not _balanced(src):
        return None
    local: dict = {}
    for kind, name in toks:
        if kind == "sym" and name not in _CONSTS:
            local[name] = sympy.Symbol(name)
    local.update(_FUNCS)
    local.update(_CONSTS)
    try:
        expr = parse_expr(src, local_dict=local, transformations=standard_transformations, evaluate=False)
    except Exception:
        return None
    if not isinstance(expr, sympy.Expr) or not _safe_tree(expr):
        return None
    return expr


# ---------- numeric comparison ----------

def _value(expr: sympy.Expr, subs: dict | None = None) -> complex | None:
    try:
        v = complex(sympy.N(expr, 20, subs=subs) if subs else sympy.N(expr, 20))
    except Exception:
        return None
    if v != v or abs(v) == float("inf") or abs(v.imag) > 1e-9 * max(1.0, abs(v.real)):
        return None
    return v


def _decimals(raw: str) -> int | None:
    m = re.fullmatch(r"\s*[-+]?\d*\.(\d+)\s*", _strip_units(raw))
    return len(m.group(1)) if m else None


def _close(a: complex, b: complex, rel: float) -> bool:
    return abs(a - b) <= rel * max(abs(a), abs(b), 1e-12) + 1e-12


def match_values(a: sympy.Expr, a_raw: str, b: sympy.Expr, b_raw: str) -> str | None:
    """'exact', 'rounded' (one side is a rounded decimal), 'approx' (e.g. pi as 3.14 vs 22/7) or None."""
    syms = a.free_symbols | b.free_symbols
    if syms:
        return "exact" if _same_function(a, b) else None
    va, vb = _value(a), _value(b)
    if va is None or vb is None:
        return None
    if _close(va, vb, 1e-9):
        return "exact"
    for raw in (a_raw, b_raw):
        d = _decimals(raw)
        if d is not None and abs(va - vb) <= 0.5 * 10 ** -d * 1.0001 + 1e-12:
            return "rounded"
    if _close(va, vb, 2e-3):
        return "approx"
    return None


def _same_function(a: sympy.Expr, b: sympy.Expr, trials: int = 5) -> bool:
    syms = sorted(a.free_symbols | b.free_symbols, key=lambda s: s.name)
    rng = random.Random(20261015)
    checked = 0
    for _ in range(trials):
        subs = {s: sympy.Float(rng.uniform(1.3, 3.7), 20) for s in syms}
        va, vb = _value(a, subs), _value(b, subs)
        if va is None or vb is None:
            continue
        if not _close(va, vb, 1e-9):
            return False
        checked += 1
    return checked >= 2


def equations_equivalent(a: tuple[sympy.Expr, sympy.Expr], b: tuple[sympy.Expr, sympy.Expr]) -> bool:
    (la, ra), (lb, rb) = a, b
    if _same_function(la, lb) and _same_function(ra, rb):
        return True
    if _same_function(la, rb) and _same_function(ra, lb):
        return True
    # V = πr²h vs V_cyl = πhr²: same right-hand side under a different name.
    if isinstance(la, sympy.Symbol) and isinstance(lb, sympy.Symbol) and _same_function(ra, rb):
        return True
    if _same_function(la, ra) or _same_function(lb, rb):
        return False  # identities only match side by side (checked above)
    f, g = la - ra, lb - rb
    if f.free_symbols != g.free_symbols or not f.free_symbols:
        return False
    syms = sorted(f.free_symbols, key=lambda s: s.name)
    rng = random.Random(7)
    ratio, checked = None, 0
    for _ in range(5):
        subs = {s: sympy.Float(rng.uniform(1.3, 3.7), 20) for s in syms}
        vf, vg = _value(f, subs), _value(g, subs)
        if vf is None or vg is None or abs(vg) < 1e-12:
            continue
        r = vf / vg
        if ratio is None:
            ratio = r
        elif not _close(r, ratio, 1e-8):
            return False
        checked += 1
    return checked >= 2 and ratio is not None and abs(ratio) > 1e-12


# ---------- statements ----------

@dataclass
class Part:
    raw: str
    expr: sympy.Expr | None


@dataclass
class Statement:
    raw: str
    parts: list[Part]
    final: bool = False
    group: int = 0  # clauses split on "or" share a group: they are alternatives

    def parsed(self) -> list[Part]:
        return [p for p in self.parts if p.expr is not None]

    def is_computation(self) -> bool:
        return len(self.parts) >= 2 and any(
            p.expr is not None and not p.expr.free_symbols and not p.expr.is_Atom for p in self.parts)


_FINAL = re.compile(r"(final\s+answer|\bans(?:wer)?\b|∴|\btherefore\b|\bhence\b|\bthus\b)", re.I)
_BULLET = re.compile(r"^\s*(?:[-*•▪◦]+|\d{1,2}[.)](?!\d)|\((?:[a-h]|[ivx]{1,4}|\d{1,2})\)|[a-h][.)](?=\s))\s*")
_LEAD_WORDS = re.compile(r"^\s*(?:∴|therefore|hence|thus|so|ans(?:wer)?\.?|final\s+answer)\s*[:.\-]?\s*", re.I)


def _strip_label(line: str) -> str:
    line = _BULLET.sub("", line, count=1)
    colon = [m.start() for m in re.finditer(r":", line)
             if not (m.start() > 0 and line[m.start() - 1].isdigit() and line[m.start() + 1:m.start() + 2].isdigit())]
    if colon:
        line = line[colon[-1] + 1:]
    return _LEAD_WORDS.sub("", line)


def _parse_part(raw: str, first: bool) -> Part:
    text = _strip_units(raw)
    expr = parse_math(text)
    if expr is None and first:
        words = text.split()
        for k in (1, 2):  # "Outer radius R" -> "R", "Volume of metal V" -> "V"
            lead = words[:-k]
            if lead and all(w.isalpha() for w in lead) and any(len(w) >= 3 for w in lead):
                expr = parse_math(" ".join(words[-k:]))
                if expr is not None:
                    break
    return Part(raw.strip(), expr)


def parse_statements(text: str, max_lines: int = 80) -> list[Statement]:
    out: list[Statement] = []
    group = 0
    for line in (text or "").splitlines()[:max_lines]:
        if not line.strip() or not re.search(r"\d|[=²³√π^]", line):
            continue
        final = bool(_FINAL.search(line))
        body = _strip_label(line)
        body = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", body)  # 43,560 -> 43560
        for clause in re.split(r"[;,]|⇒|=>|→|\bi\.e\.", body):
            group += 1
            for alt in re.split(r"\s+or\s+|\s+OR\s+", clause):
                if not alt.strip():
                    continue
                raws = [r for r in re.split(r"=|≈|≅", alt)]
                parts = [_parse_part(r, i == 0) for i, r in enumerate(raws) if r.strip()]
                if alt.lstrip().startswith(("=", "≈")):  # "= 1232": continues the previous line's chain
                    parts.insert(0, Part("", None))
                if any(p.expr is not None for p in parts):
                    out.append(Statement(alt.strip(), parts, final, group))
    return out


# ---------- analysis ----------

@dataclass
class MathReport:
    key_finals: list[Part] = field(default_factory=list)
    student_final: Part | None = None
    final_status: str | None = None  # match | rounded | approx | in_working | mismatch | not_found
    key_values: list[tuple[str, str | None]] = field(default_factory=list)  # (key value, match kind or None)
    formulas: list[tuple[str, bool]] = field(default_factory=list)
    student_slips: list[str] = field(default_factory=list)
    key_slips: list[str] = field(default_factory=list)
    ocr_warnings: list[str] = field(default_factory=list)

    @property
    def applicable(self) -> bool:
        return bool(self.key_finals or self.key_values or self.formulas)

    def prompt_section(self) -> str:
        if not self.applicable:
            return ""
        lines = ["AUTOMATIC MATHS CHECK (computed exactly by the backend with a computer algebra system; "
                 "trust these results over your own arithmetic)"]
        if self.key_finals:
            key = " or ".join(p.raw for p in self.key_finals)
            if self.final_status in ("match", "rounded", "approx"):
                how = {"match": "EQUIVALENT to the key", "rounded": "EQUIVALENT to the key (correctly rounded)",
                       "approx": "EQUIVALENT up to an approximation such as pi = 3.14"}[self.final_status]
                lines.append(f"- Final answer: key {key}; student {self.student_final.raw} -> {how}.")
            elif self.final_status == "in_working":
                lines.append(f"- Final answer: key {key}; the student's last result is {self.student_final.raw}, "
                             "but the key's answer does appear in the student's working.")
            elif self.final_status == "mismatch":
                lines.append(f"- Final answer: key {key}; student {self.student_final.raw} -> NOT equivalent.")
            else:
                lines.append(f"- Final answer: key {key}; no readable final result found in the student's answer.")
        if self.key_values:
            found = sum(1 for _, k in self.key_values if k)
            detail = ", ".join(f"{v} {'yes' if k else 'no'}" for v, k in self.key_values)
            lines.append(f"- Key results present in the student's working: {found} of {len(self.key_values)} ({detail}).")
        if self.formulas:
            detail = "; ".join(f"{f} {'yes' if ok else 'no'}" for f, ok in self.formulas)
            lines.append(f"- Key formulas written by the student (any equivalent form): {detail}.")
        if self.student_slips:
            lines.append("- Steps in the student's working that do not hold: " + "; ".join(self.student_slips) + ".")
        if self.ocr_warnings:
            lines.append("- Possible misreads in the transcription (check before deducting marks): "
                         + "; ".join(self.ocr_warnings) + ".")
        lines.append("Use these facts for method and answer marks. A 'no' is not proof of an error: the student may "
                     "have used another valid method, so judge the working itself.")
        return "\n".join(lines)


def _final_parts(stmts: list[Statement], loose: bool = False) -> list[Part]:
    """The marked final answer ("Ans", "Final Answer", ∴), else the result of the last chain of working.
    loose (student side): a bare last value such as "1/2" also counts."""
    finals = [s for s in stmts if s.final and s.parsed()]
    if finals:
        last_group = finals[-1].group
        return [s.parsed()[-1] for s in finals if s.group == last_group]
    for s in reversed(stmts):
        if len(s.parts) >= 2 and s.parsed():
            return [s.parsed()[-1]]
    if loose and stmts:
        return [stmts[-1].parsed()[-1]]
    return []


def _slips(stmts: list[Statement], limit: int = 4) -> list[str]:
    out = []
    for s in stmts:
        for a, b in zip(s.parts, s.parts[1:]):
            if a.expr is None or b.expr is None or a.expr.free_symbols or b.expr.free_symbols:
                continue
            if match_values(a.expr, a.raw, b.expr, b.raw) is None:
                out.append(f"\"{a.raw} = {b.raw}\"")
                if len(out) >= limit:
                    return out
    return out


_LOST_EXP = [
    re.compile(r"(?<![A-Za-z])([A-Za-z])\s+([234])(?=\s*(?:[-+−=×*/)]|$))"),   # R 2 - r 2
    re.compile(r"(\))\s*([234])(?=\s*(?:[-+−=×*/)]|$))"),                      # (x + 1/x) 2 =
    re.compile(r"(?<![A-Za-z])([a-z])([234])(?=\s*[-+−=)])"),                     # x2 + y2
]


def ocr_warnings(text: str, limit: int = 4) -> list[str]:
    out: list[str] = []
    for line in (text or "").splitlines():
        if not re.search(r"[=+\-−×*/^²³]", line):
            continue
        for rx in _LOST_EXP:
            for m in rx.finditer(line):
                frag = line[max(0, m.start() - 6):m.end() + 6].strip()
                w = f"\"{frag}\" may be a lost exponent ({m.group(1)}^{m.group(2)})"
                if w not in out:
                    out.append(w)
        body = line.replace("[", "(").replace("]", ")").replace("{", "(").replace("}", ")")
        if "[unclear]" not in line.lower() and body.count("(") != body.count(")"):
            out.append(f"\"{line.strip()[:60]}\" has unbalanced brackets")
        if len(out) >= limit:
            break
    return out[:limit]


def analyze(key_text: str, student_text: str, accepted: list[str] | None = None) -> MathReport:
    rep = MathReport()
    key = parse_statements(key_text)
    stu = parse_statements(student_text)

    rep.key_finals = _final_parts(key)
    for a in accepted or []:
        e = parse_math(_strip_units(a))
        if e is not None:
            rep.key_finals.append(Part(a.strip(), e))
    rep.key_slips = _slips(key)
    rep.student_slips = _slips(stu)
    rep.ocr_warnings = ocr_warnings(student_text)

    stu_values = [p for s in stu for p in s.parsed()]

    def best(target: Part) -> str | None:
        kinds = [match_values(target.expr, target.raw, p.expr, p.raw) for p in stu_values]
        for k in ("exact", "rounded", "approx"):
            if k in kinds:
                return k
        return None

    seen: list[sympy.Expr] = []
    for s in key:
        if not (s.is_computation() or s.final):
            continue
        p = s.parsed()[-1]
        if p.expr.free_symbols or any(match_values(p.expr, p.raw, q, "") == "exact" for q in seen):
            continue
        seen.append(p.expr)
        rep.key_values.append((p.raw, best(p)))
        if len(rep.key_values) >= 10:
            break

    stu_eqs = [(a.expr, b.expr) for s in stu for a, b in zip(s.parts, s.parts[1:])
               if a.expr is not None and b.expr is not None and a.expr.free_symbols and b.expr.free_symbols]
    for s in key:
        if len(s.parts) < 2 or s.parts[0].expr is None or s.parts[1].expr is None:
            continue
        la, ra = s.parts[0].expr, s.parts[1].expr
        if not (la.free_symbols and ra.free_symbols) or (la.is_Atom and ra.is_Atom):
            continue
        ok = any(equations_equivalent((la, ra), e) for e in stu_eqs)
        rep.formulas.append((f"{s.parts[0].raw} = {s.parts[1].raw}", ok))
        if len(rep.formulas) >= 6:
            break

    if rep.key_finals:
        sf = _final_parts(stu, loose=True)
        rep.student_final = sf[-1] if sf else None
        if rep.student_final is None:
            rep.final_status = "not_found"
        else:
            kinds = [match_values(k.expr, k.raw, rep.student_final.expr, rep.student_final.raw)
                     for k in rep.key_finals]
            kind = next((k for k in ("exact", "rounded", "approx") if k in kinds), None)
            if kind:
                rep.final_status = "match" if kind == "exact" else kind
            elif any(best(k) for k in rep.key_finals):
                rep.final_status = "in_working"
            else:
                rep.final_status = "mismatch"
    return rep


def safe_analyze(key_text: str, student_text: str, accepted: list[str] | None = None) -> MathReport | None:
    """analyze() that never breaks an evaluation."""
    try:
        rep = analyze(key_text, student_text, accepted)
        return rep if rep.applicable else None
    except Exception:
        log.exception("maths check failed")
        return None


def review_note(rep: MathReport | None, marks: float, max_marks: float) -> tuple[str | None, float | None]:
    """A teacher-facing note and a confidence cap when the AI's marks contradict the maths check."""
    if rep is None:
        return None, None
    notes, cap = [], None
    if rep.final_status in ("match", "rounded", "approx") and marks <= 1e-9:
        notes.append("final answer is equivalent to the key but 0 marks were proposed")
        cap = 0.4
    elif rep.final_status in ("mismatch", "not_found") and marks >= max_marks - 1e-9 \
            and not any(k for _, k in rep.key_values):
        notes.append("final answer does not match the key but full marks were proposed")
        cap = 0.4
    if rep.ocr_warnings:
        notes.append("possible misread in the maths: " + "; ".join(rep.ocr_warnings[:2]))
        cap = min(cap or 0.6, 0.6)
    if rep.key_slips:
        notes.append("the answer key's own arithmetic does not hold at " + "; ".join(rep.key_slips[:2]))
        cap = min(cap or 0.6, 0.6)
    if not notes:
        return None, None
    return "[Maths check: " + "; ".join(notes) + ". Please review.]", cap
