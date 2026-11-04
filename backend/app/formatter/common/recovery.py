"""OCR Recovery and Evidence-Based Mapping Scorer.

Solves:
- Handwritten question labels misread or containing an extra digit.
- Lack of OCR recovery mechanism.
- Treating raw OCR as authoritative instead of probabilistic evidence.
- Generates evidence-based candidate suggestions with confidence scores and explanations.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Any
from ..tamil import format as tamil_format
from .numbering import normalize_question_number


@dataclass
class RecoveryCandidate:
    question_id: str
    normalized_number: str
    score: float
    reason: str


def _near_label(source: str, target: str) -> bool:
    """One character edit, using only labels present in the uploaded paper."""
    if source == target or not source.isdigit() or not target.isdigit():
        return False
    if len(source) == len(target):
        differences = [i for i, (a, b) in enumerate(zip(source, target)) if a != b]
        return len(differences) == 1 or (len(differences) == 2
            and differences[1] == differences[0] + 1
            and source[differences[0]] == target[differences[1]]
            and source[differences[1]] == target[differences[0]])
    longer, shorter = sorted((source, target), key=len, reverse=True)
    return len(longer) == len(shorter) + 1 and any(
        longer[:i] + longer[i + 1:] == shorter for i in range(len(longer)))

_STOP_WORDS = {
    # English prepositions, pronouns, conjunctions, auxiliaries
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "will", "have", "has", "had", "they", "them", "what", "which", "when", "where",
    "how", "why", "who", "whom", "each", "other", "into", "onto", "then", "than",
    "of", "in", "on", "at", "by", "to", "or", "is", "as", "an", "be", "if", "not",
    "its", "it", "so", "up", "out", "no", "do", "does", "did", "can", "could", "would",
    "should", "may", "might", "must", "per", "we", "he", "she", "you", "your", "my",
    "our", "all", "any", "both", "such", "same", "also", "there", "here", "their",
    "about", "after", "before", "between", "under", "over", "above", "below",
    # LaTeX formatting commands (should not be scored as question content keywords)
    "left", "right", "frac", "times", "div", "cdot", "text", "quad", "begin", "end",
    "sqrt", "circ", "display", "style", "prime", "approx", "sum", "int", "prod",
    # Generic question boilerplate words
    "given", "find", "calculate", "using", "use", "formula", "value", "following",
    "marks", "mark", "ans", "answer", "total", "solve", "evaluate", "express", "show",
}

_SUPERSCRIPT_TRANS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


def _normalize_word(w: str) -> str:
    w = w.lower()
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    return w.rstrip("s")


def _clean_math_text(text: str | None) -> str:
    if not text:
        return ""
    cleaned = text.translate(_SUPERSCRIPT_TRANS)
    # Remove commas inside numbers (e.g. 1,25,000 -> 125000, 80,000 -> 80000)
    cleaned = re.sub(r"(?<=\d),(?=\d)", "", cleaned)
    # Separate units from numbers: e.g. 15m -> 15 m, 7cm -> 7 cm, Rs.80000 -> Rs. 80000
    cleaned = re.sub(r"(?<=\d)([a-zA-Z]+)", r" \1", cleaned)
    cleaned = re.sub(r"([a-zA-Z]+)(?=\d)", r"\1 ", cleaned)
    return cleaned


def _tokenize(text: str | None) -> set[str]:
    if not text:
        return set()
    cleaned = _clean_math_text(text)
    words = re.findall(r"\b[a-zA-Z]+[0-9]*\b", cleaned.lower())
    toks = {_normalize_word(w) for w in words if len(w) >= 2 and w not in _STOP_WORDS}
    return toks | tamil_format.indic_tokens(cleaned)


def _extract_distinct_numbers(text: str | None) -> set[str]:
    if not text:
        return set()
    cleaned = _clean_math_text(text)
    raw_nums = re.findall(r"(?<![a-zA-Z0-9_])\d+(?:\.\d+)?", cleaned)
    cleaned_nums = set()
    for n in raw_nums:
        c = n.rstrip(".")
        if len(c) >= 2 or (c.isdigit() and int(c) >= 4) or "." in c:
            cleaned_nums.add(c)
    return cleaned_nums


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

    exact_q = q_by_norm.get(norm)
    exact_toks = _tokenize(getattr(exact_q, "question_text", None)) if exact_q else set()
    exact_nums = _extract_distinct_numbers(getattr(exact_q, "question_text", None)) if exact_q else set()
    exact_shared_toks = ans_tokens & exact_toks
    exact_shared_nums = ans_nums & exact_nums

    generic_consts = {"100", "0", "1", "2", "3"}

    # Label similarity proposes candidates; student content must support them.
    if norm:
        alternatives = [label for label in q_by_norm if _near_label(norm, label)]
        for alt in alternatives:
            if alt in q_by_norm:
                target_q = q_by_norm[alt]

                # Keyword overlap
                q_tokens = _tokenize(getattr(target_q, "question_text", None))
                common = ans_tokens & q_tokens

                # Distinct numerical constants match
                q_nums = _extract_distinct_numbers(getattr(target_q, "question_text", None))
                shared_nums = ans_nums & q_nums

                other_words = set().union(*(_tokenize(getattr(q, "question_text", None))
                    for label, q in q_by_norm.items() if label != alt))
                if len(common) < 2 and not (common - other_words) and not (shared_nums - generic_consts):
                    continue

                if exact_q:
                    alt_dist_nums = (shared_nums - exact_nums) - generic_consts
                    exact_dist_nums = (exact_shared_nums - q_nums) - generic_consts
                    alt_dist_toks = common - exact_toks
                    # If exact question has distinct constant matches and alt has none, skip alt
                    if exact_dist_nums and not alt_dist_nums:
                        continue
                    # If exact question has equal or stronger keyword overlap than alt, and alt has no unique numbers, skip alt
                    if len(exact_shared_toks) >= len(common) and not alt_dist_nums:
                        continue
                    # Alt must have positive evidence
                    if not (alt_dist_nums or alt_dist_toks or len(common) >= 2 or (shared_nums and len(common) >= 1)):
                        continue

                score = 0.70
                reasons = [f"Similar uploaded label: '{norm}' / '{alt}', supported by student content"]

                # If sequential position also matches the alternative's position
                q_pos = getattr(target_q, "position", None)
                if q_pos is not None and abs(q_pos - answer_index) <= 1:
                    score += 0.15
                    reasons.append(f"position matches exam sequence (#{q_pos})")

                if len(common) >= 2:
                    score += 0.10
                    reasons.append(f"content keyword overlap ({', '.join(list(common)[:3])})")

                if shared_nums:
                    score += 0.10
                    reasons.append(f"shared exam constants ({', '.join(list(shared_nums)[:3])})")

                if exact_q:
                    if alt_dist_nums:
                        score += 0.10
                        reasons.append(f"unique constants for Q{alt} ({', '.join(list(alt_dist_nums)[:3])})")
                    if alt_dist_toks:
                        score += 0.08
                        reasons.append(f"unique keywords for Q{alt} ({', '.join(list(alt_dist_toks)[:3])})")

                candidates.append(
                    RecoveryCandidate(
                        question_id=target_q.id,
                        normalized_number=alt,
                        score=min(1.0, round(score, 2)),
                        reason="; ".join(reasons),
                    )
                )

    # 2. Content similarity candidate if there is strong text overlap and answer text is substantial
    if ans_tokens and len(ans_tokens) >= 2:
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

