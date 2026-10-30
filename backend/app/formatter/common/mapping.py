"""Deterministic label -> exam question mapping with 7-tier evidence hierarchy and OCR recovery.

Evidence Hierarchy:
1. Exact structural label match (normalized number + section scope)
2. Section and parent-question match (e.g. key '1' -> exam {1(a), 1(b)} with review suggestion)
3. Subquestion hierarchy match (e.g. bare '(b)' matched to sibling under active parent)
4. Explicit question references (e.g. 'Reference: Q5')
5. Consistency with verified document structure
6. Question content and subject matter supporting evidence (lexical + numerical constants)
7. Sequence or neighboring questions strictly as context, NEVER as sole proof of a match.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol
from .numbering import normalize_question_number, parent_number
from .recovery import find_recovery_candidates, _tokenize, _extract_distinct_numbers

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
    evidence_tier: str | None = None


def _extract_section_from_label(raw_label: str | None) -> tuple[str | None, str | None]:
    """If raw label contains an explicit section prefix like 'Section A - 1', split it."""
    if not raw_label:
        return None, None
    m = re.match(r"^\s*((?:SECTION|PART|UNIT|GROUP)\s+[A-Z0-9IVX]+)\s*[\-\:\–\—]\s*(.*)$", raw_label, re.IGNORECASE)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None, raw_label


def map_label(
    raw_label: str | None,
    questions: Iterable[QuestionLike],
    ocr_confidence: float | None = None,
    min_confidence: float = 0.0,
    answer_text: str | None = None,
    answer_position: int = 1,
    total_answers: int = 1,
    section: str | None = None,
    prev_question_id: str | None = None,
    check_content: bool = True,
) -> MappingResult:
    """Map a question or answer label to an authoritative exam question using the 7-tier evidence hierarchy.

    check_content=False trusts an exact label over content similarity (printed answer keys).
    """
    q_list = list(questions)
    qs = [q for q in q_list if getattr(q, "normalized_number", None)]

    sec_hint, clean_raw = _extract_section_from_label(raw_label)
    active_sec = section or sec_hint
    eff_raw = clean_raw if clean_raw is not None else raw_label

    norm = normalize_question_number(eff_raw)

    # Tier 4 Pre-Check: Explicit text references inside answer text (e.g. "Reference: Q5", "Question 4:")
    explicit_ref_norm: str | None = None
    if answer_text:
        m_ref = re.search(r"\b(?:reference|refer\s+to|regarding|re)\s*[:\-–]?\s*Q(?:uestion)?\.?\s*([0-9]{1,3}(?:\([a-zA-Z0-9]+\))?)", answer_text, re.I)
        if m_ref:
            explicit_ref_norm = normalize_question_number(m_ref.group(1))

    # If label is missing or unparseable:
    if norm is None:
        if explicit_ref_norm:
            matching_ref = [q for q in qs if q.normalized_number == explicit_ref_norm]
            if len(matching_ref) == 1:
                return MappingResult(
                    status=NEEDS_REVIEW,
                    question_id=matching_ref[0].id,
                    normalized_number=explicit_ref_norm,
                    note=f"No label: matched via explicit text reference to Q{explicit_ref_norm}",
                    candidates=[matching_ref[0].id],
                    candidate_details=[{"id": matching_ref[0].id, "num": explicit_ref_norm, "score": 0.85, "reason": "Explicit text reference"}],
                    evidence_tier="TIER_4_EXPLICIT_REFERENCE",
                )

        # Tier 6: Lexical & numeric constants recovery
        if answer_text or answer_position > 1:
            rec_cands = find_recovery_candidates(eff_raw, answer_text, q_list, answer_position, total_answers)
            if rec_cands and rec_cands[0].score >= 0.60:
                top = rec_cands[0]
                return MappingResult(
                    status=NEEDS_REVIEW,
                    question_id=top.question_id,
                    normalized_number=top.normalized_number,
                    note=f"No label: candidate suggested based on {top.reason}",
                    candidates=[c.question_id for c in rec_cands],
                    candidate_details=[{"id": c.question_id, "num": c.normalized_number, "score": c.score, "reason": c.reason} for c in rec_cands],
                    evidence_tier="TIER_6_CONTENT_RECOVERY",
                )
        return MappingResult(status=UNMAPPED, note="No readable question number and insufficient content evidence to suggest a mapping")

    # Tier 3: Subquestion hierarchy match for bare subquestion tokens: e.g. "(a)", "(b)", "(i)", "(ii)"
    if norm.startswith("("):
        sub_tok = norm.strip("()")
        # Find candidate exam questions with this subquestion token
        sub_cands = [q for q in qs if f"({sub_tok})" in (q.normalized_number or "")]

        # If previous answer was mapped to a parent question or sibling, rank sibling first
        ranked_cands = list(sub_cands)
        if prev_question_id:
            prev_q = next((q for q in qs if q.id == prev_question_id), None)
            if prev_q:
                prev_p = parent_number(prev_q.normalized_number or "")
                ranked_cands.sort(key=lambda q: 0 if parent_number(q.normalized_number or "") == prev_p else 1)

        if len(ranked_cands) == 1:
            top_q = ranked_cands[0]
            return MappingResult(
                status=NEEDS_REVIEW,
                question_id=top_q.id,
                normalized_number=top_q.normalized_number,
                note=f"Subquestion label '{norm}' proposed for Q{top_q.normalized_number}",
                candidates=[top_q.id],
                candidate_details=[{"id": top_q.id, "num": top_q.normalized_number, "score": 0.80, "reason": "Subquestion hierarchy match"}],
                evidence_tier="TIER_3_SUBQUESTION_HIERARCHY",
            )
        elif len(ranked_cands) > 1:
            return MappingResult(
                status=NEEDS_REVIEW,
                question_id=ranked_cands[0].id if prev_question_id else None,
                normalized_number=ranked_cands[0].normalized_number if prev_question_id else None,
                note=f"Subquestion label '{norm}' matches multiple questions in exam",
                candidates=[q.id for q in ranked_cands],
                candidate_details=[{"id": q.id, "num": q.normalized_number, "score": 0.60, "reason": "Multiple subquestions share this token"} for q in ranked_cands],
                evidence_tier="TIER_3_SUBQUESTION_HIERARCHY",
            )
        else:
            return MappingResult(status=UNMAPPED, normalized_number=norm, note=f"Exam has no subquestion with label '{norm}'")

    # Tier 1 & Tier 2: Structural Label Match
    exact = [q for q in qs if q.normalized_number == norm]

    # Section disambiguation if multiple questions share the same number across sections
    if len(exact) > 1 and active_sec:
        sec_clean = active_sec.lower()
        sec_exact = [q for q in exact if getattr(q, "section", None) and sec_clean in q.section.lower()]
        if len(sec_exact) == 1:
            exact = sec_exact

    if len(exact) == 1:
        matched_q = exact[0]

        # Tier 6 Contradiction Check: Did the student write e.g. '1' but answer question 5?
        if check_content and answer_text and (len(_tokenize(answer_text)) >= 2 or len(_extract_distinct_numbers(answer_text)) >= 2):
            q_tokens = _tokenize(getattr(matched_q, "question_text", None))
            ans_tokens = _tokenize(answer_text)
            q_nums = _extract_distinct_numbers(getattr(matched_q, "question_text", None))
            ans_nums = _extract_distinct_numbers(answer_text)
            exact_has_content = bool(ans_tokens & q_tokens) or bool(ans_nums & q_nums)

            rec_cands = find_recovery_candidates(eff_raw, answer_text, q_list, answer_position, total_answers)
            if rec_cands and rec_cands[0].question_id != matched_q.id:
                top = rec_cands[0]
                top_q = next((q for q in q_list if q.id == top.question_id), None)
                top_nums = _extract_distinct_numbers(getattr(top_q, "question_text", None)) if top_q else set()
                generic_consts = {"100", "0", "1", "2", "3"}
                top_dist_nums = (ans_nums & top_nums) - q_nums - generic_consts
                exact_dist_nums = (ans_nums & q_nums) - top_nums - generic_consts

                should_suggest_alt = False
                if not exact_has_content and top.score >= 0.70:
                    should_suggest_alt = True
                elif top_dist_nums and not exact_dist_nums and top.score >= 0.85:
                    should_suggest_alt = True
                elif not exact_has_content and top.score >= 0.95 and not exact_dist_nums:
                    should_suggest_alt = True

                if should_suggest_alt:
                    return MappingResult(
                        status=NEEDS_REVIEW,
                        question_id=top.question_id,
                        normalized_number=top.normalized_number,
                        note=f"Student wrote '{norm}' but content matches Q{top.normalized_number} ({top.reason})",
                        candidates=[top.question_id, matched_q.id],
                        candidate_details=[
                            {"id": top.question_id, "num": top.normalized_number, "score": top.score, "reason": top.reason},
                            {"id": matched_q.id, "num": norm, "score": 0.50, "reason": "Written label"},
                        ],
                        evidence_tier="TIER_6_CONTENT_CONTRADICTION",
                    )

        if ocr_confidence is not None and ocr_confidence < min_confidence:
            return MappingResult(
                status=NEEDS_REVIEW,
                question_id=None,
                normalized_number=norm,
                note=f"Exact label match but reading confidence {ocr_confidence:.2f} is below threshold",
                candidates=[matched_q.id],
                candidate_details=[{"id": matched_q.id, "num": norm, "score": ocr_confidence, "reason": "Low reading confidence"}],
                evidence_tier="TIER_1_EXACT_LABEL_LOW_CONFIDENCE",
            )

        return MappingResult(status=MAPPED, question_id=matched_q.id, normalized_number=norm, evidence_tier="TIER_1_EXACT_LABEL")

    if len(exact) > 1:
        sec_names = ", ".join(filter(None, [getattr(q, "section", None) for q in exact])) or "multiple sections"
        return MappingResult(
            status=NEEDS_REVIEW,
            normalized_number=norm,
            note=f"Ambiguous: multiple exam questions share label '{norm}' ({sec_names})",
            candidates=[q.id for q in exact],
            candidate_details=[{"id": q.id, "num": q.normalized_number, "score": 0.5, "reason": f"Section: {getattr(q, 'section', 'None')}"} for q in exact],
            evidence_tier="TIER_2_SECTION_AMBIGUITY",
        )

    # Tier 2: Parent / Subquestion structural relationship
    parent = parent_number(norm)
    if norm == parent:  # e.g. Student or Key wrote "3", but exam has "3(a)", "3(b)"
        related = [q for q in qs if parent_number(q.normalized_number or "") == parent]
        if related:
            return MappingResult(
                status=NEEDS_REVIEW,
                normalized_number=norm,
                note=f"Label '{norm}' refers to parent question; exam has subquestions",
                candidates=[q.id for q in related],
                candidate_details=[{"id": q.id, "num": q.normalized_number, "score": 0.70, "reason": "Subquestion under parent"} for q in related],
                evidence_tier="TIER_2_SECTION_PARENT",
            )
    else:  # e.g. Student wrote "3(a)", but exam only has "3"
        parent_exact = [q for q in qs if q.normalized_number == parent]
        if parent_exact:
            return MappingResult(
                status=NEEDS_REVIEW,
                question_id=parent_exact[0].id,
                normalized_number=parent,
                note=f"Label '{norm}' is a subpart; exam has parent question '{parent}'",
                candidates=[parent_exact[0].id],
                candidate_details=[{"id": parent_exact[0].id, "num": parent, "score": 0.75, "reason": "Parent question match"}],
                evidence_tier="TIER_2_SECTION_PARENT",
            )

    # Tier 6: Check OCR recovery for digit confusion (e.g. handwritten Q1 misread as Q17, Q2 as Q27)
    rec_cands = find_recovery_candidates(eff_raw, answer_text, q_list, answer_position, total_answers)
    if rec_cands:
        top = rec_cands[0]
        if top.score >= 0.65:
            return MappingResult(
                status=NEEDS_REVIEW,
                question_id=top.question_id,
                normalized_number=top.normalized_number,
                note=f"Candidate for '{norm}': Q{top.normalized_number} ({top.reason})",
                candidates=[c.question_id for c in rec_cands],
                candidate_details=[{"id": c.question_id, "num": c.normalized_number, "score": c.score, "reason": c.reason} for c in rec_cands],
                evidence_tier="TIER_6_CONTENT_RECOVERY",
            )

    return MappingResult(status=UNMAPPED, normalized_number=norm, note=f"No exam question numbered '{norm}'")


def flag_duplicates(rows: list, id_attr: str = "exam_question_id") -> set[str]:
    """Return question ids targeted by 2+ rows. Caller marks those rows DUPLICATE_MAPPING."""
    seen: dict[str, int] = {}
    for r in rows:
        qid = getattr(r, id_attr, None)
        if qid:
            seen[qid] = seen.get(qid, 0) + 1
    return {q for q, n in seen.items() if n > 1}


def detect_mapping_anomalies(answers: list, exam_questions: list) -> list[dict[str, Any]]:
    """Detect structural mapping anomalies across the whole evaluation before evaluation runs."""
    anomalies = []
    q_ids = {q.id for q in exam_questions}
    seen_qids: dict[str, list[str]] = {}

    for a in answers:
        if getattr(a, "status", None) == "IGNORED":
            continue
        qid = getattr(a, "exam_question_id", None)
        aid = getattr(a, "id", None) or "unknown"
        if qid:
            seen_qids.setdefault(qid, []).append(aid)
            if qid not in q_ids:
                anomalies.append({
                    "type": "NON_EXISTENT_QUESTION",
                    "answer_id": aid,
                    "question_id": qid,
                    "reason": "Answer is mapped to a question ID that does not exist in the exam.",
                })

    for qid, aids in seen_qids.items():
        if len(aids) > 1:
            anomalies.append({
                "type": "DUPLICATE_ASSIGNMENT",
                "question_id": qid,
                "answer_ids": aids,
                "reason": f"Multiple answers ({len(aids)}) are assigned to the same question.",
            })

    unmapped = [a for a in answers if getattr(a, "status", None) == "UNMAPPED"]
    if unmapped:
        anomalies.append({
            "type": "UNMAPPED_ANSWERS",
            "count": len(unmapped),
            "answer_ids": [a.id for a in unmapped],
            "reason": f"{len(unmapped)} student answers have no assigned question.",
        })

    return anomalies

