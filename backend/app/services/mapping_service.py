"""DB-aware wrappers around the pure mapping rules."""
from __future__ import annotations
from sqlalchemy.orm import Session
from ..config import get_settings
from ..models import AnswerKey, Evaluation, ExamQuestion, StudentAnswer
from .mapping import MAPPED, NEEDS_REVIEW, UNMAPPED, flag_duplicates, map_label, detect_mapping_anomalies

DUP_NOTE = "DUPLICATE_MAPPING: another answer also maps to this question"
_RECOMPUTABLE = {"UNMAPPED", "NEEDS_REVIEW", "MAPPED"}


def exam_questions(db: Session, exam_id: str) -> list[ExamQuestion]:
    return db.query(ExamQuestion).filter_by(exam_id=exam_id).order_by(ExamQuestion.position).all()


def apply_student_mapping(db: Session, ev: Evaluation) -> None:
    qs = exam_questions(db, ev.exam_id)
    minc = get_settings().min_label_confidence
    answers = db.query(StudentAnswer).filter_by(evaluation_id=ev.id).order_by(StudentAnswer.position).all()
    total_ans = len(answers)
    prev_qid = None
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
            a.raw_question_number,
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
    live = [a for a in answers if a.status != "IGNORED"]
    dups = flag_duplicates(live)
    for a in live:
        if a.exam_question_id in dups and a.status in _RECOMPUTABLE:
            a.status, a.mapping_note = "NEEDS_REVIEW", DUP_NOTE
        elif a.status == "NEEDS_REVIEW" and (a.mapping_note or "").startswith("DUPLICATE_MAPPING"):
            a.status, a.mapping_note = "MAPPED", None
    db.flush()


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
    db.flush()


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
    accounted_q = mapped_q | suggested_q
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
