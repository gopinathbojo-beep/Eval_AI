"""Which Part B option a student answered (Accountancy 055: Analysis of Financial Statements or Computerised
Accounting).

The paper says a student attempts ONLY ONE option. Each student's option is read from the sheet itself: every
answer mapped to a Part B question is compared with the two options' printed questions (shared words), and the
option most of them match is that student's option. Grading then marks Part B against that option alone, so the
other option never adds marks. When the answers split evenly between the options the sheet is MIXED: the teacher
is told, and grading keeps the better option per question.
"""
from __future__ import annotations

import re

from .build import BRANCH_LABELS

MIXED = "MIXED"
_WORD = re.compile(r"[a-z]{4,}")
_COMMON = {"what", "which", "following", "from", "with", "that", "this", "their", "state", "explain", "prepare",
           "calculate", "given", "information", "will", "year", "ended", "march", "were", "have", "been", "under",
           "they", "following:", "answer", "basis", "above", "below", "shown", "show"}


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall((text or "").casefold()) if w not in _COMMON}


def branch_texts(question) -> dict[str, str]:
    """The printed text of each option of a Part B question, from its "[Part B - ...]" headings."""
    text = question.question_text or ""
    out = {}
    for name, label in BRANCH_LABELS.items():
        start = text.find(f"[Part B - {label}]")
        if start < 0:
            continue
        rest = text[start + len(label) + 11:]
        nxt = min((rest.find(f"[Part B - {other}]") for other in BRANCH_LABELS.values()
                   if other != label and rest.find(f"[Part B - {other}]") >= 0), default=len(rest))
        out[name] = rest[:nxt]
    return out


def _is_branched(question) -> bool:
    tree = (question.structure or {}).get("tree") or {}
    return any(c.get("audience") in BRANCH_LABELS for c in tree.get("children") or [])


def vote(answers_by_question: dict, questions: dict) -> str | None:
    """financial / computerised / MIXED / None (no Part B answer tells)."""
    counts = {name: 0 for name in BRANCH_LABELS}
    for qid, text in answers_by_question.items():
        q = questions.get(qid)
        if q is None or not _is_branched(q):
            continue
        said = _words(text)
        shared = {name: len(said & _words(t)) for name, t in branch_texts(q).items()}
        if len(shared) < 2:
            continue
        (best, top), (_, second) = sorted(shared.items(), key=lambda kv: -kv[1])[:2]
        if top >= 2 and top > second * 1.2:
            counts[best] += 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    if ranked[0][1] == 0:
        return None
    if ranked[0][1] == ranked[1][1]:
        return MIXED
    return ranked[0][0]


def sheet_option(db, ev, exam) -> str | None:
    """The Part B option this student answered, or None when the exam has no options or the sheet does not say."""
    options = exam.standard_options or {}
    if options.get("accountancy_option"):
        return options["accountancy_option"]  # the exam itself fixed the option
    if not (exam.standard_profile_id or "").endswith("055"):
        return None
    from ..models import ExamQuestion, StudentAnswer
    questions = {q.id: q for q in db.query(ExamQuestion).filter_by(exam_id=exam.id)}
    texts: dict[str, str] = {}
    for a in db.query(StudentAnswer).filter_by(evaluation_id=ev.id):
        if a.exam_question_id in questions and a.status not in ("IGNORED", "UNMAPPED"):
            texts[a.exam_question_id] = (texts.get(a.exam_question_id, "") + "\n" + (a.answer_text or "")).strip()
    return vote(texts, questions)
