"""Choices in a paper: which questions a total counts.

Either/or: "38 (a) ... OR (b) ...", "38 (அ) ... அல்லது (ஆ) ...". Each alternative is its own question (38(a), 38(b))
so it maps, keys and grades like any other, and the alternatives share ExamQuestion.choice_group ("38"). A student
answers one, so a choice counts once in every total; when a student answered more than one, the higher mark counts.

Answer any N: "Answer any four", "எவையேனும் நான்கு வினாக்களுக்கு மட்டும் விடையளிக்கவும்". The section's questions carry
answer_any = N; compulsory ones ("21 -வது வினாவிற்குக் கட்டாயமாக") always count, then the student's best up to N.
"""
from __future__ import annotations
import re
from typing import Any, Iterable
from ..tamil import format as tamil_format

# "OR" alone on a line, between the alternatives (Tamil "அல்லது": tamil_format)
_EITHER_OR = re.compile(r"^\s*[-–—(\[]*\s*OR\s*[-–—)\]]*\s*$", re.IGNORECASE)


def is_either_or_line(line: str) -> bool:
    return bool(_EITHER_OR.match(line)) or (tamil_format.has_tamil(line) and tamil_format.is_either_or_line(line))


# "... OR" ending a line, or "OR (b) ..." opening one, next to an alternative's label: put "OR" on its own line
_OR_WORD = r"(?:OR|அல்லது)"
_ALT_LABEL = rf"\(?[ \t]*(?:[{tamil_format.SUB_LETTERS}]|[a-hA-H])[ \t]*\)"
_OR_AT_LINE_END = re.compile(rf"(?<=\S)[ \t]+({_OR_WORD})[ \t]*\n(?=[ \t]*{_ALT_LABEL})")
_OR_AT_LINE_START = re.compile(rf"^([ \t]*{_OR_WORD})[ \t]+(?={_ALT_LABEL})", re.M)
# Inline "OR (b)" or "அல்லது (ஆ)" inside a line: put OR on its own line
_OR_INLINE = re.compile(rf"(?<=\S)[ \t]+({_OR_WORD})[ \t]+(?={_ALT_LABEL})")
# A capital "OR" ending a line is the marker even with no label after it ("... Uniform. OR\nYou are Rohit ...");
# Tamil "அல்லது" also means "or" inside sentences, so it needs the label
_CAPITAL_OR_AT_LINE_END = re.compile(r"(?<=\S)[ \t]+(OR)[ \t]*\n")


def isolate_either_or(text: str) -> str:
    text = _CAPITAL_OR_AT_LINE_END.sub(r"\n\1\n", _OR_AT_LINE_END.sub(r"\n\1\n", text or ""))
    text = _OR_INLINE.sub(r"\n\1\n", text)
    return _OR_AT_LINE_START.sub(r"\1\n", text)


def split_alternatives(text: str) -> list[str]:
    """The alternatives of "(a) ... OR (b) ..."; one item when the text holds no choice."""
    parts: list[list[str]] = [[]]
    for line in isolate_either_or(text).splitlines():
        if is_either_or_line(line):
            parts.append([])
        else:
            parts[-1].append(line)
    return [t for t in ("\n".join(p).strip() for p in parts) if t]


def _mark(marks: dict, q: Any) -> float:
    m = marks.get(getattr(q, "id", None))
    return -1.0 if m is None else m


def units(questions: Iterable[Any], marks: dict | None = None) -> list[Any]:
    """One question per choice: every plain question, and per choice the alternative with the highest mark in `marks`
    (question id -> mark), else its first alternative. Order is kept."""
    qs = list(questions)
    marks = marks or {}
    best: dict[str, Any] = {}
    for q in qs:
        g = getattr(q, "choice_group", None)
        if g and (g not in best or _mark(marks, q) > _mark(marks, best[g])):
            best[g] = q
    return [q for q in qs if not getattr(q, "choice_group", None) or best[q.choice_group] is q]


def counted(questions: Iterable[Any], marks: dict | None = None) -> list[Any]:
    """The questions a total counts. Each choice counts once (units). In an "answer any N" section (answer_any) the
    compulsory questions count, then the best of the rest up to N: by the student's marks when `marks` is given, by
    maximum marks for the paper's own total. Order is kept."""
    qs = units(questions, marks)
    score = (lambda q: _mark(marks, q)) if marks else (lambda q: q.max_marks or 0)
    sections: dict[str, list[Any]] = {}
    for q in qs:
        if getattr(q, "answer_any", None):
            sections.setdefault(q.section or "", []).append(q)
    dropped: set[int] = set()
    for sec_qs in sections.values():
        must = [q for q in sec_qs if getattr(q, "compulsory", False)]
        rest = sorted((q for q in sec_qs if not getattr(q, "compulsory", False)), key=score, reverse=True)
        dropped.update(id(q) for q in rest[max(0, sec_qs[0].answer_any - len(must)):])
    return [q for q in qs if id(q) not in dropped]


def max_total(questions: Iterable[Any]) -> float:
    """The paper's maximum: each choice counts once, an "answer any N" section its best N."""
    return sum(q.max_marks or 0 for q in counted(questions))
