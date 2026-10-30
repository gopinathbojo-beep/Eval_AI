"""AI labeler: a language model settles what the keyword rules cannot.

- Question types: questions whose type is only a marks guess (type_source "default") are classified by the model.
- Marking points: answer-key entries without criteria are split into points whose marks add up to the question's marks.

Runs only when a labeling model is configured (INDIC_TEXT_MODEL for Indian-language subjects). Everything the model
returns is checked; anything unusable is dropped and the rule result stays, so a model outage never blocks an upload.
"""
from __future__ import annotations
import logging
from typing import Any
from ..ocr import prompts
from ..ocr.internvl import AIResponseError, AIUnavailable, chat_structured
from ..ocr.schemas import KeyCriteriaLabels, QuestionTypeLabels
from ..formatter.common.numbering import normalize_question_number
from ..formatter.common.recovery import _extract_distinct_numbers, _tokenize

log = logging.getLogger("adem.labeler")

QUESTION_TYPES = {"mcq", "fill_blank", "true_false", "match", "numerical", "short_answer", "descriptive", "other"}
_TYPE_BATCH = 8
_CRITERIA_BATCH = 3


def _batches(xs: list, n: int):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def label_question_types(questions: list[Any], model: str) -> int:
    """Classify the questions whose type is only a marks guess. Returns how many were labeled."""
    todo = {str(i): q for i, q in enumerate(questions) if q.type_source == "default"}
    done = 0
    for chunk in _batches(list(todo.items()), _TYPE_BATCH):
        items = [{"id": i, "marks": q.max_marks, "text": q.question_text[:1200]} for i, q in chunk]
        try:
            call = chat_structured(prompts.LABELER_SYSTEM, prompts.question_type_label_prompt(items), QuestionTypeLabels,
                                   model=model)
        except (AIUnavailable, AIResponseError) as e:
            log.warning("Question type labeling skipped (%s): %s", model, getattr(e, "detail", e))
            continue
        for lab in call.parsed.labels:
            q = todo.get(lab.id)
            qtype = (lab.question_type or "").strip().lower()
            if q is not None and q.type_source == "default" and qtype in QUESTION_TYPES:
                q.question_type, q.type_source = qtype, "ai"
                done += 1
    return done


def _grounded(point: str, answer_tokens: set[str]) -> bool:
    """A point must reuse words or numbers of the official answer; a point with none of them was invented."""
    toks = _tokenize(point) | _extract_distinct_numbers(point)
    return not toks or bool(toks & answer_tokens)


def _valid_points(lab, total: float, answer: str) -> list[str] | None:
    pts = [c for c in lab.criteria if (c.point or "").strip() and c.marks is not None and c.marks > 0]
    if not pts or abs(sum(c.marks for c in pts) - total) > 0.01:
        return None
    answer_tokens = _tokenize(answer) | _extract_distinct_numbers(answer)
    if not all(_grounded(c.point, answer_tokens) for c in pts):
        return None
    return [f"{c.marks:g} Mark{'s' if c.marks != 1 else ''}: {c.point.strip()}" for c in pts]


def label_key_criteria(keys: list[Any], canonical_questions: list[Any], model: str) -> int:
    """Give marking points to answer-key entries that have none. Returns how many were labeled."""
    by_norm = {q.normalized_number: q for q in canonical_questions if getattr(q, "normalized_number", None)}
    todo: dict[str, tuple[Any, float, str]] = {}
    for i, k in enumerate(keys):
        if k.criteria or not (k.answer_text or "").strip():
            continue
        q = by_norm.get(normalize_question_number(k.raw_question_number) or "")
        total = k.marks if k.marks is not None else getattr(q, "max_marks", None)
        if total and total > 0:
            todo[str(i)] = (k, float(total), getattr(q, "question_text", "") or "")
    done = 0
    for chunk in _batches(list(todo.items()), _CRITERIA_BATCH):
        items = [{"id": i, "marks": total, "question": qtext[:600], "answer": k.answer_text[:2000]}
                 for i, (k, total, qtext) in chunk]
        try:
            call = chat_structured(prompts.LABELER_SYSTEM, prompts.criteria_label_prompt(items), KeyCriteriaLabels,
                                   model=model)
        except (AIUnavailable, AIResponseError) as e:
            log.warning("Marking point labeling skipped (%s): %s", model, getattr(e, "detail", e))
            continue
        for lab in call.parsed.keys:
            entry = todo.get(lab.id)
            if entry is None:
                continue
            k, total, _ = entry
            points = _valid_points(lab, total, k.answer_text)
            if points is None:
                log.info("Discarded AI marking points for key %s (marks did not add up or not in the answer)",
                         k.raw_question_number)
                continue
            k.criteria = points
            if k.marks is None:
                k.marks = total
            done += 1
    return done
