"""OCR Recovery and Evidence-Based Mapping Scorer.

Solves:
- Handwritten question numbers misread (Q1 -> Q17, Q2 -> Q27).
- Lack of OCR recovery mechanism.
- Treating raw OCR as authoritative instead of probabilistic evidence.
- Generates evidence-based candidate suggestions with confidence scores and explanations.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Any
from .numbering import normalize_question_number


@dataclass
class RecoveryCandidate:
    question_id: str
    normalized_number: str
    score: float
    reason: str


# Common handwritten OCR digit confusion patterns from screenshots:
# '17' -> '1' (hook/serif on top of 1 misread as 7)
# '27' -> '2' (loop on base of 2 misread as 7)
# '71' -> '1' or '7'
_DIGIT_CONFUSIONS: dict[str, list[str]] = {
    "17": ["1"],
    "27": ["2"],
    "71": ["1", "7"],
}

_STOP_WORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "will", "have", "has", "had", "they", "them", "what", "which", "when", "where",
    "how", "why", "who", "whom", "each", "other", "into", "onto", "then", "than",
}


def _tokenize(text: str | None) -> set[str]:
    if not text:
        return set()
    words = re.findall(r"[a-zA-Z]{3,}", text.lower())
    return {w for w in words if w not in _STOP_WORDS}


def find_recovery_candidates(
    raw_label: str | None,
    answer_text: str | None,
    questions: list[Any],
    answer_index: int = 1,
    total_answers: int = 1,
) -> list[RecoveryCandidate]:
    """Find evidence-based candidates when direct normalized label matching fails."""
    candidates: list[RecoveryCandidate] = []
    norm = normalize_question_number(raw_label) if raw_label else None
    ans_tokens = _tokenize(answer_text)

    q_by_norm = {q.normalized_number: q for q in questions if getattr(q, "normalized_number", None)}
    q_by_pos = {getattr(q, "position", i + 1): q for i, q in enumerate(questions)}

    # 1. Handwritten digit confusion recovery (e.g. 17 -> 1, 27 -> 2)
    if norm and norm in _DIGIT_CONFUSIONS:
        alternatives = _DIGIT_CONFUSIONS[norm]
        for alt in alternatives:
            if alt in q_by_norm:
                target_q = q_by_norm[alt]
                score = 0.70
                reasons = [f"OCR digit misread: '{norm}' is commonly misread for '{alt}'"]

                # If sequential position also matches the alternative's position
                q_pos = getattr(target_q, "position", None)
                if q_pos is not None and abs(q_pos - answer_index) <= 1:
                    score += 0.18
                    reasons.append(f"position matches exam sequence (#{q_pos})")

                # Keyword overlap boost
                q_tokens = _tokenize(getattr(target_q, "question_text", None))
                common = ans_tokens & q_tokens
                if len(common) >= 2:
                    score += 0.10
                    reasons.append(f"content keyword overlap ({', '.join(list(common)[:3])})")

                candidates.append(
                    RecoveryCandidate(
                        question_id=target_q.id,
                        normalized_number=alt,
                        score=min(1.0, round(score, 2)),
                        reason="; ".join(reasons),
                    )
                )

    # 2. Content similarity candidate if there is strong text overlap and answer text is substantial
    if ans_tokens and len(ans_tokens) >= 3:
        for q in questions:
            qid = q.id
            if any(c.question_id == qid for c in candidates):
                continue
            q_tokens = _tokenize(getattr(q, "question_text", None))
            common = ans_tokens & q_tokens
            if len(common) >= 3:
                jaccard = len(common) / len(ans_tokens | q_tokens) if (ans_tokens | q_tokens) else 0
                if jaccard >= 0.20:
                    q_norm = getattr(q, "normalized_number", str(getattr(q, "display_number", "")))
                    candidates.append(
                        RecoveryCandidate(
                            question_id=qid,
                            normalized_number=q_norm,
                            score=min(0.85, round(0.50 + jaccard, 2)),
                            reason=f"Significant content match: shared keywords ({', '.join(list(common)[:4])})",
                        )
                    )

    # Sort descending by score
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates
