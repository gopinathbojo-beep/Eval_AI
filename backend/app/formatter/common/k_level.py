"""Bloom's knowledge levels (K1..K6) and course outcomes for questions, plus marks summaries per level.

Suggestions are rule-based from the question's command verb, never from the model, and are always shown to the
teacher as suggestions until confirmed.
"""
from __future__ import annotations
import re
from collections import OrderedDict
from functools import lru_cache
from importlib import import_module
from ... import formatter

K_LEVELS = OrderedDict([("K1", "Remember"), ("K2", "Understand"), ("K3", "Apply"),
                        ("K4", "Analyse"), ("K5", "Evaluate"), ("K6", "Create")])

_VERBS: dict[str, tuple[str, ...]] = {
    "K1": ("define", "list", "name", "state", "recall", "label", "mention", "what is", "what are", "who", "when", "where",
           "write the formula", "write down", "recite", "match", "fill in", "true or false", "choose", "select", "tick",
           "identify", "give the meaning", "expand", "write the full form"),
    "K2": ("explain", "describe", "discuss", "summarise", "summarize", "interpret", "illustrate", "outline", "why",
           "give reason", "give reasons", "give example", "give examples", "classify", "paraphrase", "indicate",
           "what happens", "what do you mean", "what do you understand", "translate", "predict", "relate", "rewrite"),
    "K3": ("solve", "calculate", "compute", "find", "determine", "apply", "use", "demonstrate", "show that", "prove",
           "draw", "sketch", "simplify", "factorise", "factorize", "convert", "verify", "complete", "balance", "plot",
           "construct", "measure", "how many", "how much", "frame", "change the", "transform", "write balanced",
           "write the balanced", "write a balanced", "write the chemical equation", "write chemical equation",
           "write the equation", "write the word equation", "write word equation"),
    "K4": ("analyse", "analyze", "compare", "contrast", "differentiate", "distinguish", "examine", "categorise",
           "categorize", "infer", "investigate", "break down", "relationship between", "difference between"),
    "K5": ("justify", "assess", "critique", "criticise", "criticize", "judge", "defend", "appraise", "argue",
           "recommend", "evaluate", "give your opinion", "do you agree", "comment on", "which is better", "conclude"),
    "K6": ("design", "create", "compose", "formulate", "develop", "plan", "invent", "devise", "propose", "write a story",
           "write a letter", "write an essay", "write a paragraph", "write a speech", "write an article", "draft",
           "imagine", "prepare a", "suggest"),
}
_PATTERNS = [(lvl, re.compile(r"\b" + re.escape(v) + r"\b")) for lvl, verbs in _VERBS.items() for v in verbs]
_MATH_EVALUATE = re.compile(r"\bevaluate\b[^a-z]{0,6}[\d(\[√∫]")
# "Expand and simplify (3x+4y)²" is algebra (K3), not expanding an abbreviation (K1)
_MATH_EXPAND = re.compile(r"\bexpand\b(?=[^.?]*(?:simplif|identit|[\d²³]))")
DEFAULT_K_LEVEL = "K1"  # no command verb ("Calorific value of a fuel?"): a recall question


@lru_cache(maxsize=None)
def _subject_patterns(module: str) -> list[tuple[str, re.Pattern]]:
    """The subject formatter's own command words (Tamil "எழுதுக", "ஏன்" ...), see its k_level_verbs hook."""
    return [(lvl, re.compile(p)) for lvl, pats in import_module(module).k_level_verbs().items() for p in pats]


def suggest_k_level(text: str | None) -> str | None:
    """The level of the command verb that appears first in the question; K1 when there is text but no command
    verb, so every question gets a suggestion. None only for empty text."""
    t = (text or "").lower()
    if not re.search(r"[^\W\d_]", t):
        return None
    if _MATH_EVALUATE.search(t):  # "Evaluate 3² + 4²" is a calculation, not a judgement
        t = _MATH_EVALUATE.sub(" calculate ", t)
    t = _MATH_EXPAND.sub(" simplify ", t)
    best: tuple[int, int, str] | None = None
    for lvl, pat in _PATTERNS + _subject_patterns(formatter.current().__name__):
        m = pat.search(t)
        # earliest verb wins; at the same position prefer the longer phrase ("write a letter" over "write")
        if m and (best is None or (m.start(), -len(m.group())) < best[:2]):
            best = (m.start(), -len(m.group()), lvl)
    return best[2] if best else DEFAULT_K_LEVEL


def normalize_course_outcome(v: str | None) -> str | None:
    s = re.sub(r"\s+", "", (v or "")).upper()
    if not s:
        return None
    if s.isdigit():
        s = f"CO{s}"
    return s[:20]


def apply_suggestions(questions) -> int:
    """Fill K levels for questions the teacher has not tagged. Returns how many changed."""
    n = 0
    for q in questions:
        if q.k_level_source == "TEACHER":
            continue
        k = suggest_k_level(q.question_text)
        if k != q.k_level or (k and q.k_level_source != "SUGGESTED"):
            q.k_level, q.k_level_source = k, ("SUGGESTED" if k else None)
            n += 1
    return n


def summarize(questions, marks_by_question: dict[str, float | None]) -> dict:
    """Scored vs maximum marks grouped by K level and by course outcome (questions without a tag are 'Untagged')."""
    def group(key) -> list[dict]:
        rows: dict[str, dict] = {}
        for q in questions:
            k = key(q) or "Untagged"
            r = rows.setdefault(k, {"key": k, "questions": 0, "max_marks": 0.0, "scored": 0.0})
            r["questions"] += 1
            r["max_marks"] += q.max_marks or 0.0
            r["scored"] += marks_by_question.get(q.id) or 0.0
        order = list(K_LEVELS) + sorted(k for k in rows if k not in K_LEVELS and k != "Untagged") + ["Untagged"]
        out = []
        for k in order:
            if k in rows:
                r = rows[k]
                r["label"] = K_LEVELS.get(k, k)
                r["percentage"] = round(100.0 * r["scored"] / r["max_marks"], 1) if r["max_marks"] else None
                out.append(r)
        return out
    return {"k_levels": group(lambda q: q.k_level), "course_outcomes": group(lambda q: q.course_outcome)}
