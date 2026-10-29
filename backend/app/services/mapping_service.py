"""DB-aware wrappers around the pure mapping rules."""
from __future__ import annotations
from typing import Any
from sqlalchemy.orm import Session
from .. import formatter
from ..config import get_settings
from ..models import AnswerKey, Evaluation, ExamQuestion, StudentAnswer
from ..formatter.common.mapping import MAPPED, NEEDS_REVIEW, UNMAPPED, flag_duplicates, map_label, detect_mapping_anomalies
from ..formatter.common.numbering import part_labels

DUP_NOTE = "DUPLICATE_MAPPING: another answer also maps to this question"
_RECOMPUTABLE = {"UNMAPPED", "NEEDS_REVIEW", "MAPPED"}


def exam_questions(db: Session, exam_id: str) -> list[ExamQuestion]:
    return db.query(ExamQuestion).filter_by(exam_id=exam_id).order_by(ExamQuestion.position).all()


def apply_student_mapping(db: Session, ev: Evaluation) -> None:
    qs = exam_questions(db, ev.exam_id)
    minc = get_settings().min_label_confidence
    answers = db.query(StudentAnswer).filter_by(evaluation_id=ev.id).order_by(StudentAnswer.position).all()
    total_ans = len(answers)
    in_part = dict(zip((a.id for a in answers), part_labels(answers, qs)))
    prev_qid = None
    suggested: list[tuple[StudentAnswer, list[dict]]] = []  # unlabelled answers placed by content alone
    for a in answers:
        if a.status == "IGNORED" or a.status not in _RECOMPUTABLE:
            if a.exam_question_id:
                prev_qid = a.exam_question_id
            continue
        if a.mapping_confirmed and a.exam_question_id:
            a.status, a.mapping_note, a.mapping_candidates = "MAPPED", None, []
            prev_qid = a.exam_question_id
            continue
        res = map_label(
            in_part.get(a.id) or a.raw_question_number,
            qs,
            a.ocr_confidence,
            minc,
            answer_text=a.answer_text,
            answer_position=a.position,
            total_answers=total_ans,
            prev_question_id=prev_qid,
        )
        a.normalized_number = res.normalized_number
        a.exam_question_id = res.question_id
        a.mapping_note = res.note
        a.mapping_candidates = res.candidates
        a.status = {MAPPED: "MAPPED", NEEDS_REVIEW: "NEEDS_REVIEW", UNMAPPED: "UNMAPPED"}[res.status]
        if res.question_id:
            prev_qid = res.question_id
        if not a.raw_question_number and res.status == NEEDS_REVIEW and res.question_id and res.candidate_details:
            suggested.append((a, res.candidate_details))
    _spread_content_suggestions(answers, qs, suggested)
    live = [a for a in answers if a.status != "IGNORED"]
    dups = flag_duplicates(live)
    for a in live:
        if a.exam_question_id in dups and a.status in _RECOMPUTABLE:
            a.status, a.mapping_note = "NEEDS_REVIEW", DUP_NOTE
        elif a.status == "NEEDS_REVIEW" and (a.mapping_note or "").startswith("DUPLICATE_MAPPING"):
            a.status, a.mapping_note = "MAPPED", None
    _confirm_content_mappings(live, qs, suggested)
    db.flush()


AUTO_MIN_SCORE = 0.75
AUTO_MARGIN = 0.15


def _confirm_content_mappings(answers: list, qs: list, suggested: list[tuple[Any, list[dict]]]) -> None:
    """Map an unlabelled answer without review when every piece of evidence agrees: a strong content match that
    clearly beats any other question, no other answer on that question, and its place in the answer order (between
    the questions confidently answered before and after it). Anything short of that stays NEEDS_REVIEW."""
    qpos = {q.id: q.position for q in qs}
    for a, det in sorted(suggested, key=lambda x: x[0].position or 0):
        if a.status != "NEEDS_REVIEW" or not det or a.exam_question_id != det[0].get("id"):
            continue  # a duplicate, or moved by _spread_content_suggestions: the teacher decides
        top = det[0].get("score") or 0
        runner = max((d.get("score") or 0 for d in det[1:] if d.get("num") != det[0].get("num")), default=0)
        if top < AUTO_MIN_SCORE or top - runner < AUTO_MARGIN:
            continue
        if any(x is not a and x.exam_question_id == a.exam_question_id for x in answers):
            continue
        confident = [x for x in answers if x.status == "MAPPED" and x.exam_question_id in qpos]
        lo = max((qpos[x.exam_question_id] for x in confident if x.position < a.position), default=-1)
        hi = min((qpos[x.exam_question_id] for x in confident if x.position > a.position), default=10**9)
        if lo < qpos.get(a.exam_question_id, -2) < hi:
            a.status = "MAPPED"  # counts as a confident neighbour for the answers after it
            a.mapping_note = f"No readable number: mapped to Q{a.normalized_number} by content and answer order"


SUGGESTION_MARGIN = 0.15


def _spread_content_suggestions(answers: list, qs: list, suggested: list[tuple[Any, list[dict]]]) -> None:
    """Unlabelled answers suggested for the same question: the strongest content match keeps it; each other one
    moves to its next close candidate that is free and fits the answer order (between the questions confidently
    answered before and after it). Results stay NEEDS_REVIEW suggestions."""
    qpos = {q.id: q.position for q in qs}
    by_q: dict[str, list[tuple[Any, list[dict]]]] = {}
    for a, det in suggested:
        by_q.setdefault(a.exam_question_id, []).append((a, det))
    for qid, group in by_q.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda x: -(x[1][0].get("score") or 0))
        for a, det in group[1:]:
            confident = [x for x in answers if x.status == "MAPPED" and x.exam_question_id in qpos]
            lo = max((qpos[x.exam_question_id] for x in confident if x.position < a.position), default=-1)
            hi = min((qpos[x.exam_question_id] for x in confident if x.position > a.position), default=10**9)
            taken = {x.exam_question_id for x in answers if x.exam_question_id and x is not a and x.status != "IGNORED"}
            top = det[0].get("score") or 0
            for cand in sorted(det, key=lambda d: -(d.get("score") or 0)):
                cid = cand.get("id")
                if (cid and cid != qid and cid not in taken and (cand.get("score") or 0) >= top - SUGGESTION_MARGIN
                        and lo < qpos.get(cid, -2) < hi):
                    a.exam_question_id = cid
                    a.normalized_number = cand.get("num")
                    a.mapping_note = f"Suggested Q{cand.get('num')} from content and answer order (please confirm)"
                    break


def apply_key_mapping(db: Session, exam_id: str, doc_id: str) -> None:
    qs = exam_questions(db, exam_id)
    keys = db.query(AnswerKey).filter_by(exam_id=exam_id, document_id=doc_id).order_by(AnswerKey.created_at).all()
    prev_qid = None
    for idx, k in enumerate(keys, 1):
        res = map_label(
            k.raw_question_number,
            qs,
            k.ocr_confidence,
            get_settings().min_label_confidence,
            answer_text=k.answer_text,
            answer_position=idx,
            total_answers=len(keys),
            prev_question_id=prev_qid,
            check_content=False,  # a printed key label is authoritative; content checks are for handwritten labels
        )
        k.normalized_number, k.exam_question_id = res.normalized_number, res.question_id
        k.mapping_status, k.mapping_note, k.mapping_candidates = res.status, res.note, res.candidates
        if res.question_id:
            prev_qid = res.question_id
    db.flush()
    refresh_key_state(db, exam_id)


def refresh_key_state(db: Session, exam_id: str) -> None:
    """Recompute duplicate flags and mark mismatches for active keys (called after any key edit)."""
    qmap = {q.id: q for q in exam_questions(db, exam_id)}
    keys = db.query(AnswerKey).filter_by(exam_id=exam_id, is_active=True).all()
    dups = flag_duplicates(keys)
    for k in keys:
        if k.exam_question_id in dups:
            k.mapping_status, k.mapping_note = "NEEDS_REVIEW", DUP_NOTE
        elif k.mapping_status == "NEEDS_REVIEW" and (k.mapping_note or "").startswith("DUPLICATE_MAPPING"):
            k.mapping_status, k.mapping_note = "MAPPED", None
        q = qmap.get(k.exam_question_id) if k.exam_question_id else None
        # Inherit question max_marks if answer key marks was missing
        if (k.marks is None or k.marks == 0.0) and q and q.max_marks is not None:
            k.marks = q.max_marks
        # Correct section total misattribution (e.g. 10 Marks from Section C header)
        elif k.marks is not None and q and q.max_marks is not None and k.marks > q.max_marks * 1.5:
            k.marks = q.max_marks
        k.mark_mismatch = bool(
            q and k.marks is not None and q.max_marks is not None and abs(k.marks - q.max_marks) > 1e-9
        )
        refresh_rubric(k, q)
    db.flush()


def refresh_rubric(key: AnswerKey, q: ExamQuestion | None) -> None:
    """Rebuild the key's marking rubric with the subject's formatter. A rubric that comes out different from the one
    the teacher confirmed needs confirming again; the same rubric keeps its confirmation."""
    if q is None:
        return
    built = formatter.current().build_rubric(q.question_text, key.answer_text, list(key.criteria or []), q.max_marks)
    new = built.to_dict() if built is not None else None
    if new != key.rubric:
        key.rubric, key.rubric_status = new, "UNREVIEWED"


def mapping_summary(db: Session, ev: Evaluation) -> dict:
    qs = exam_questions(db, ev.exam_id)
    answers = db.query(StudentAnswer).filter_by(evaluation_id=ev.id).all()
    live = [a for a in answers if a.status != "IGNORED"]
    mapped_q = {a.exam_question_id for a in live if a.status not in ("UNMAPPED", "NEEDS_REVIEW") and a.exam_question_id}

    # Questions that have answers with suggested candidates
    suggested_q = set()
    for a in live:
        if a.status == "NEEDS_REVIEW" and a.mapping_candidates:
            for cid in a.mapping_candidates:
                if cid not in mapped_q:
                    suggested_q.add(cid)

    # Questions completely missing an answer
    missing = [q for q in qs if q.id not in {a.exam_question_id for a in live if a.exam_question_id}]

    return {
        "total_questions": len(qs),
        "mapped": len(mapped_q),
        "suggested": len(suggested_q),
        "needs_review": sum(a.status == "NEEDS_REVIEW" for a in live),
        "unmapped": sum(a.status == "UNMAPPED" for a in live),
        "missing": len(missing),
        "ignored": len(answers) - len(live),
        "missing_question_ids": [q.id for q in missing],
        "anomalies": detect_mapping_anomalies(live, qs),
    }
