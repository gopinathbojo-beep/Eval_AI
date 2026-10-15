"""Deterministic label -> exam question mapping with evidence-based OCR recovery.

Rules:
* Only an EXACT normalised-number match with exactly one candidate maps automatically (MAPPED).
* "3" vs {3(a), 3(b)}, "3(a)" vs {3}, duplicates, unknown labels never auto-map.
* When OCR misreads handwritten labels (e.g. Q17 for Q1, Q27 for Q2), evidence-based
  recovery generates ranked candidates with confidence scores and explanations for teacher review.
* Teacher can accept suggestions with a single click.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterable, Protocol
from .numbering import normalize_question_number, parent_number
from .ocr_recovery import find_recovery_candidates, _tokenize, _extract_distinct_numbers

MAPPED = "MAPPED"
SUGGESTED = "SUGGESTED"
NEEDS_REVIEW = "NEEDS_REVIEW"
UNMAPPED = "UNMAPPED"


class QuestionLike(Protocol):
    id: str
    normalized_number: str | None


@dataclass
class MappingResult:
    status: str
    question_id: str | None = None
    normalized_number: str | None = None
    note: str | None = None
    candidates: list[str] = field(default_factory=list)  # exam question ids offered to teacher
    candidate_details: list[dict] = field(default_factory=list)


def map_label(
    raw_label: str | None,
    questions: Iterable[QuestionLike],
    ocr_confidence: float | None = None,
    min_confidence: float = 0.0,
    answer_text: str | None = None,
    answer_position: int = 1,
    total_answers: int = 1,
) -> MappingResult:
    q_list = list(questions)
    qs = [q for q in q_list if getattr(q, "normalized_number", None)]
    norm = normalize_question_number(raw_label)

    if norm is None:
        # Check if OCR recovery / sequence can suggest candidates
        if answer_text or answer_position > 1:
            rec_cands = find_recovery_candidates(raw_label, answer_text, q_list, answer_position, total_answers)
            if rec_cands:
                return MappingResult(
                    NEEDS_REVIEW,
                    None,
                    None,
                    f"No label: candidate suggested based on {rec_cands[0].reason}",
                    [c.question_id for c in rec_cands],
                    [{"id": c.question_id, "num": c.normalized_number, "score": c.score, "reason": c.reason} for c in rec_cands],
                )
        return MappingResult(UNMAPPED, None, None, "No readable question number")

    exact = [q for q in qs if q.normalized_number == norm]
    if len(exact) == 1:
        # Check for content contradiction if answer_text has strong keywords or distinct constants
        if answer_text and (len(_tokenize(answer_text)) >= 2 or len(_extract_distinct_numbers(answer_text)) >= 2):
            q_tokens = _tokenize(getattr(exact[0], "question_text", None))
            ans_tokens = _tokenize(answer_text)
            q_nums = _extract_distinct_numbers(getattr(exact[0], "question_text", None))
            ans_nums = _extract_distinct_numbers(answer_text)
            exact_has_content = bool(ans_tokens & q_tokens) or bool(ans_nums & q_nums)
            if not exact_has_content:
                rec_cands = find_recovery_candidates(raw_label, answer_text, q_list, answer_position, total_answers)
                if rec_cands and rec_cands[0].question_id != exact[0].id and rec_cands[0].score >= 0.70:
                    top = rec_cands[0]
                    return MappingResult(
                        NEEDS_REVIEW,
                        top.question_id,
                        top.normalized_number,
                        f"Student wrote '{norm}' but content matches Q{top.normalized_number} ({top.reason})",
                        [top.question_id, exact[0].id],
                        [{"id": top.question_id, "num": top.normalized_number, "score": top.score, "reason": top.reason}],
                    )
        if ocr_confidence is not None and ocr_confidence < min_confidence:
            return MappingResult(
                NEEDS_REVIEW,
                None,
                norm,
                f"Exact label match but OCR confidence {ocr_confidence:.2f} is low",
                [exact[0].id],
            )
        return MappingResult(MAPPED, exact[0].id, norm)
    if len(exact) > 1:
        return MappingResult(
            NEEDS_REVIEW,
            None,
            norm,
            "Several exam questions share this number",
            [q.id for q in exact],
        )

    # No exact match. Offer structurally related questions to the teacher.
    parent = parent_number(norm)
    if norm == parent:  # "3" but exam has 3(a), 3(b)
        related = [q for q in qs if parent_number(q.normalized_number) == parent]
        if related:
            return MappingResult(
                NEEDS_REVIEW,
                None,
                norm,
                f"Label '{norm}' has no exact question; exam has sub-questions",
                [q.id for q in related],
            )
    else:  # "3(a)" but exam only has "3" or a different depth
        related = [
            q for q in qs
            if q.normalized_number == parent or (parent_number(q.normalized_number) == parent and q.normalized_number.startswith(norm))
        ]
        if related:
            return MappingResult(
                NEEDS_REVIEW,
                None,
                norm,
                f"Label '{norm}' has no exact question; related questions exist",
                [q.id for q in related],
            )

    # Check OCR recovery for digit confusion (e.g. Q17 -> Q1, Q27 -> Q2) or sequence/content
    rec_cands = find_recovery_candidates(raw_label, answer_text, q_list, answer_position, total_answers)
    if rec_cands:
        top = rec_cands[0]
        target_qid = top.question_id if top.score >= 0.70 else None
        target_norm = top.normalized_number if top.score >= 0.70 else norm
        return MappingResult(
            NEEDS_REVIEW,
            target_qid,
            target_norm,
            f"Candidate for '{norm}': Q{top.normalized_number} ({top.reason})",
            [c.question_id for c in rec_cands],
            [{"id": c.question_id, "num": c.normalized_number, "score": c.score, "reason": c.reason} for c in rec_cands],
        )

    return MappingResult(UNMAPPED, None, norm, f"No exam question numbered '{norm}'")


def flag_duplicates(rows: list, id_attr: str = "exam_question_id") -> set[str]:
    """Return question ids targeted by 2+ rows. Caller marks those rows DUPLICATE_MAPPING."""
    seen: dict[str, int] = {}
    for r in rows:
        qid = getattr(r, id_attr)
        if qid:
            seen[qid] = seen.get(qid, 0) + 1
    return {q for q, n in seen.items() if n > 1}
