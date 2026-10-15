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
# '8' <-> '9' (closed loop in 9 or incomplete loop in 8)
# '6' <-> '10' (1 and 0 touching or slant misread)
_DIGIT_CONFUSIONS: dict[str, list[str]] = {
    "17": ["1"],
    "27": ["2"],
    "71": ["1", "7"],
    "8": ["9", "3"],
    "9": ["8"],
    "6": ["10", "5"],
    "10": ["6"],
    "3": ["8"],
    "5": ["6"],
}

_STOP_WORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "will", "have", "has", "had", "they", "them", "what", "which", "when", "where",
    "how", "why", "who", "whom", "each", "other", "into", "onto", "then", "than",
    # LaTeX formatting commands (should not be scored as question content keywords)
    "left", "right", "frac", "times", "div", "cdot", "text", "quad", "begin", "end",
    "sqrt", "circ", "over", "display", "style", "prime", "approx",
}

_SUPERSCRIPT_TRANS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


def _normalize_word(w: str) -> str:
    w = w.lower()
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    return w.rstrip("s")


def _tokenize(text: str | None) -> set[str]:
    if not text:
        return set()
    cleaned_text = text.translate(_SUPERSCRIPT_TRANS)
    words = re.findall(r"\b[0-9]*[a-zA-Z]+[0-9]*\b", cleaned_text.lower())
    return {_normalize_word(w) for w in words if len(w) >= 2 and w not in _STOP_WORDS}


def _extract_distinct_numbers(text: str | None) -> set[str]:
    if not text:
        return set()
    cleaned_text = text.translate(_SUPERSCRIPT_TRANS)
    # Distinct numeric constants with 2+ digits or specific values (handles 16x, 14cm, etc.)
    raw_nums = re.findall(r"(?<![a-zA-Z])\d+(?:[\.,]\d+)?", cleaned_text)
    cleaned = set()
    for n in raw_nums:
        c = n.replace(",", "")
        if len(c) >= 2 or (c.isdigit() and int(c) >= 4):
            cleaned.add(c)
    return cleaned


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
    ans_nums = _extract_distinct_numbers(answer_text)

    q_by_norm = {q.normalized_number: q for q in questions if getattr(q, "normalized_number", None)}
    q_by_pos = {getattr(q, "position", i + 1): q for i, q in enumerate(questions)}

    # 1. Handwritten digit confusion recovery (e.g. 17 -> 1, 27 -> 2, 8 <-> 9)
    # Only evaluate digit confusion if norm is not in this exam OR exact question has no content match
    exact_q = q_by_norm.get(norm)
    exact_has_content = False
    if exact_q:
        exact_toks = _tokenize(getattr(exact_q, "question_text", None))
        exact_nums = _extract_distinct_numbers(getattr(exact_q, "question_text", None))
        if len(ans_tokens & exact_toks) >= 2 or (ans_nums & exact_nums):
            exact_has_content = True

    if norm and norm in _DIGIT_CONFUSIONS and not exact_has_content:
        alternatives = _DIGIT_CONFUSIONS[norm]
        for alt in alternatives:
            if alt in q_by_norm:
                target_q = q_by_norm[alt]
                score = 0.70
                reasons = [f"OCR digit misread: '{norm}' is commonly misread for '{alt}'"]

                # If sequential position also matches the alternative's position
                q_pos = getattr(target_q, "position", None)
                if q_pos is not None and abs(q_pos - answer_index) <= 1:
                    score += 0.15
                    reasons.append(f"position matches exam sequence (#{q_pos})")

                # Keyword overlap boost
                q_tokens = _tokenize(getattr(target_q, "question_text", None))
                common = ans_tokens & q_tokens
                if len(common) >= 2:
                    score += 0.10
                    reasons.append(f"content keyword overlap ({', '.join(list(common)[:3])})")

                # Distinct numerical constants match
                q_nums = _extract_distinct_numbers(getattr(target_q, "question_text", None))
                shared_nums = ans_nums & q_nums
                if shared_nums:
                    score += 0.12
                    reasons.append(f"shared exam constants ({', '.join(list(shared_nums)[:3])})")

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
            q_nums = _extract_distinct_numbers(getattr(q, "question_text", None))
            shared_nums = ans_nums & q_nums

            if len(common) >= 2 or shared_nums:
                jaccard = len(common) / len(ans_tokens | q_tokens) if (ans_tokens | q_tokens) else 0
                recall = len(common) / len(ans_tokens) if ans_tokens else 0
                num_boost = 0.15 if shared_nums else 0.0
                if len(common) >= 3 or jaccard >= 0.15 or recall >= 0.20 or shared_nums:
                    q_norm = getattr(q, "normalized_number", str(getattr(q, "display_number", "")))
                    reasons_list = []
                    if common:
                        reasons_list.append(f"shared keywords ({', '.join(list(common)[:4])})")
                    if shared_nums:
                        reasons_list.append(f"constants ({', '.join(list(shared_nums)[:3])})")
                    candidates.append(
                        RecoveryCandidate(
                            question_id=qid,
                            normalized_number=q_norm,
                            score=min(0.95, round(0.50 + max(jaccard, recall * 0.4) + (0.10 if len(common) >= 3 else 0.05) + num_boost, 2)),
                            reason=f"Significant content match: {'; '.join(reasons_list)}",
                        )
                    )

    # Sort descending by score
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates
