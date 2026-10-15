"""Deterministic label -> exam question mapping with evidence-based OCR recovery.

Rules:
* Only an EXACT normalised-number match with exactly one candidate maps automatically (MAPPED).
* "3" vs {3(a), 3(b)}, duplicates, unknown labels never auto-map.
* "3(a)" vs an exam whose question 3 is a single question (parts kept inside it) maps to 3 as a part of it.
* When OCR misreads handwritten labels (e.g. Q17 for Q1, Q27 for Q2), evidence-based
  recovery generates ranked candidates with confidence scores and explanations for teacher review.
* Teacher can accept suggestions with a single click.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterable, Protocol
from .numbering import is_sub_question, normalize_question_number, parent_number
from .ocr_recovery import find_recovery_candidates, _tokenize

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


def _details(questions: list, score: float, reason: str) -> list[dict]:
    return [{"id": q.id, "num": q.normalized_number, "score": score, "reason": reason} for q in questions]


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
        # Check for content contradiction if answer_text has strong keywords
        if answer_text and len(_tokenize(answer_text)) >= 4:
            q_tokens = _tokenize(getattr(exact[0], "question_text", None))
            ans_tokens = _tokenize(answer_text)
            exact_overlap = len(ans_tokens & q_tokens)
            if exact_overlap == 0:
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
                _details(exact, round(ocr_confidence, 2), "exact label match, low OCR confidence"),
            )
        return MappingResult(MAPPED, exact[0].id, norm)
    if len(exact) > 1:
        return MappingResult(
            NEEDS_REVIEW,
            None,
            norm,
            "Several exam questions share this number",
            [q.id for q in exact],
            _details(exact, 0.5, "same question number"),
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
                _details(related, 0.5, f"sub-question of {norm}"),
            )
    else:  # "3(a)" but exam only has "3" or a different depth
        whole = [q for q in qs if q.normalized_number == parent]
        if len(whole) == 1 and not any(is_sub_question(q.normalized_number) and parent_number(q.normalized_number) == parent
                                       for q in qs):
            # The exam keeps question 3 as one question with its parts inside, so "3(a)" is part of it
            if ocr_confidence is not None and ocr_confidence < min_confidence:
                return MappingResult(NEEDS_REVIEW, None, norm,
                                     f"Part of question {parent} but OCR confidence {ocr_confidence:.2f} is low",
                                     [whole[0].id], _details(whole, round(ocr_confidence, 2), f"part of question {parent}"))
            return MappingResult(MAPPED, whole[0].id, norm, f"Part of question {parent}")
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
                _details(related, 0.5, f"related to {norm}"),
            )

    # Check OCR recovery for digit confusion (e.g. Q17 -> Q1, Q27 -> Q2) or sequence/content
    rec_cands = find_recovery_candidates(raw_label, answer_text, q_list, answer_position, total_answers)
    if rec_cands:
        top = rec_cands[0]
        return MappingResult(
            NEEDS_REVIEW,
            None,
            norm,
            f"No exact question for '{norm}'. Suggestion: Q{top.normalized_number} ({top.reason})",
            [c.question_id for c in rec_cands],
            [{"id": c.question_id, "num": c.normalized_number, "score": c.score, "reason": c.reason} for c in rec_cands],
        )

    return MappingResult(UNMAPPED, None, norm, f"No exam question numbered '{norm}'")


def flag_duplicates(rows: list, id_attr: str = "exam_question_id", allow_parts: bool = True) -> set[str]:
    """Return question ids targeted by 2+ rows. Caller marks those rows DUPLICATE_MAPPING.

    With allow_parts, rows that are different parts of one question ("9(a)", "9(b)" -> question 9) are not
    duplicates (student answers). Answer keys need exactly one row per question, so they pass allow_parts=False.
    """
    groups: dict[str, list] = {}
    for r in rows:
        qid = getattr(r, id_attr)
        if qid:
            groups.setdefault(qid, []).append(r)
    return {q for q, rs in groups.items() if len(rs) > 1 and not (allow_parts and _distinct_parts(rs))}


def _distinct_parts(rows: list) -> bool:
    nums = [getattr(r, "normalized_number", None) for r in rows]
    return all(n and is_sub_question(n) for n in nums) and len(set(nums)) == len(nums)
