"""DB-aware wrappers around the pure mapping rules."""
from __future__ import annotations
from sqlalchemy.orm import Session
from ..config import get_settings
from ..models import AnswerKey, Evaluation, ExamQuestion, StudentAnswer
from .mapping import MAPPED, NEEDS_REVIEW, UNMAPPED, flag_duplicates, map_label
from .numbering import is_sub_question, parent_number

DUP_NOTE = "DUPLICATE_MAPPING: another answer also maps to this question"
_RECOMPUTABLE = {"UNMAPPED", "NEEDS_REVIEW", "MAPPED"}


def exam_questions(db: Session, exam_id: str) -> list[ExamQuestion]:
    return db.query(ExamQuestion).filter_by(exam_id=exam_id).order_by(ExamQuestion.position).all()


def apply_student_mapping(db: Session, ev: Evaluation) -> None:
    qs = exam_questions(db, ev.exam_id)
    minc = get_settings().min_label_confidence
    answers = db.query(StudentAnswer).filter_by(evaluation_id=ev.id).order_by(StudentAnswer.position).all()
    total_ans = len(answers)
    for a in answers:
        if a.status == "IGNORED" or a.status not in _RECOMPUTABLE:
            continue
        if a.mapping_confirmed and a.exam_question_id:
            a.status, a.mapping_note = "MAPPED", None
            a.mapping_candidates, a.mapping_candidate_details = [], []
            continue
        res = map_label(
            a.raw_question_number,
            qs,
            a.ocr_confidence,
            minc,
            answer_text=a.answer_text,
            answer_position=a.position,
            total_answers=total_ans,
        )
        a.normalized_number = res.normalized_number
        a.exam_question_id = res.question_id
        a.mapping_note = res.note
        a.mapping_candidates = res.candidates
        a.mapping_candidate_details = res.candidate_details
        a.status = {MAPPED: "MAPPED", NEEDS_REVIEW: "NEEDS_REVIEW", UNMAPPED: "UNMAPPED"}[res.status]
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
    qmap = {q.id: q for q in qs}
    keys = (db.query(AnswerKey).filter_by(exam_id=exam_id, document_id=doc_id, is_active=True)
            .order_by(AnswerKey.created_at).all())
    for idx, k in enumerate(keys, 1):
        if k.mapping_confirmed and k.exam_question_id in qmap:
            continue  # a teacher's choice is never overwritten by re-mapping
        res = map_label(
            k.raw_question_number,
            qs,
            k.ocr_confidence,
            get_settings().min_label_confidence,
            answer_text=k.answer_text,
            answer_position=idx,
            total_answers=len(keys),
        )
        k.normalized_number, k.exam_question_id = res.normalized_number, res.question_id
        k.mapping_status, k.mapping_note, k.mapping_candidates = res.status, res.note, res.candidates
        k.mapping_candidate_details = res.candidate_details
    _merge_key_parts(db, [k for k in keys if k.mapping_status == MAPPED], qmap)
    for k in keys:
        if k.is_active:
            _correct_extracted_marks(k, qmap.get(k.exam_question_id) if k.exam_question_id else None)
    db.flush()
    refresh_key_state(db, exam_id)


def _merge_key_parts(db: Session, keys: list[AnswerKey], qmap: dict[str, ExamQuestion]) -> None:
    """Key rows for different parts of one question ("9(a)", "9(b)" -> question 9, or "Q5" holding the stem and
    part (a) then "5(b)") become a single key row, since a question has exactly one answer key. Part answers,
    criteria and marks are combined in order, each part keeping its label so it is marked against its own part."""
    groups: dict[str, list[AnswerKey]] = {}
    for k in keys:
        q = qmap.get(k.exam_question_id)
        if q and q.normalized_number and not is_sub_question(q.normalized_number) and k.normalized_number \
                and parent_number(k.normalized_number) == q.normalized_number:
            groups.setdefault(q.id, []).append(k)
    for qid, parts in groups.items():
        whole = qmap[qid].normalized_number
        if len(parts) < 2 or len({k.normalized_number for k in parts}) != len(parts) \
                or not any(is_sub_question(k.normalized_number) for k in parts):
            continue  # a single row, or repeated labels: leave for the teacher (duplicate check flags them)
        head = parts[0]

        def label(k: AnswerKey) -> str:
            return k.normalized_number[len(whole):]  # "9(b)" -> "(b)", "9" -> ""

        head.answer_text = "\n".join(f"{label(k)} {k.answer_text.strip()}".strip() for k in parts)
        head.raw_ocr_text = "\n".join(f"{label(k)} {(k.raw_ocr_text or '').strip()}".strip() for k in parts)
        head.criteria = [f"{label(k)} {c}".strip() for k in parts for c in (k.criteria or [])]
        head.accepted_answers = [a for k in parts for a in (k.accepted_answers or [])]
        head.keywords = list(dict.fromkeys(w for k in parts for w in (k.keywords or [])))
        head.marks = _combined_marks([k.marks for k in parts], is_sub_question(head.normalized_number),
                                     qmap[qid].max_marks)
        head.normalized_number = whole
        head.mapping_note = f"Parts {', '.join(label(k) or whole for k in parts)} combined into one answer"
        for k in parts[1:]:
            db.delete(k)
            k.is_active = False


def _combined_marks(marks: list[float | None], head_is_part: bool, q_max: float | None) -> float | None:
    """Marks of a key combined from its parts: the sum of the part marks. A first row labelled with the whole
    number ("Q5") may carry the question's total instead of part (a)'s marks; when adding it would go past the
    question's maximum, its own figure is that total."""
    if any(m is None for m in marks):
        return None
    total = sum(marks)
    if not head_is_part and q_max is not None and total > q_max + 1e-9 and abs(marks[0] - q_max) < 1e-9:
        return marks[0]
    return total


def _correct_extracted_marks(k: AnswerKey, q: ExamQuestion | None) -> None:
    """OCR-time repair of key marks. Runs only on freshly extracted rows, never on teacher edits."""
    if q is None or q.max_marks is None:
        return
    # Missing marks: inherit the question's maximum
    if k.marks is None or k.marks == 0.0:
        k.marks = q.max_marks
    # Section total misattribution (e.g. 10 Marks from a Section C header)
    elif k.marks > q.max_marks * 1.5:
        k.marks = q.max_marks


def refresh_key_state(db: Session, exam_id: str) -> None:
    """Recompute duplicate flags and mark mismatches for active keys (called after any key edit)."""
    qmap = {q.id: q for q in exam_questions(db, exam_id)}
    keys = db.query(AnswerKey).filter_by(exam_id=exam_id, is_active=True).all()
    dups = flag_duplicates(keys, allow_parts=False)
    for k in keys:
        if k.exam_question_id in dups:
            k.mapping_status, k.mapping_note = "NEEDS_REVIEW", DUP_NOTE
        elif k.mapping_status == "NEEDS_REVIEW" and (k.mapping_note or "").startswith("DUPLICATE_MAPPING"):
            k.mapping_status, k.mapping_note = "MAPPED", None
        q = qmap.get(k.exam_question_id) if k.exam_question_id else None
        # Inherit question max_marks only when the key has no marks at all. Explicit values
        # (including 0 or a teacher-entered figure) are kept and surfaced as a mismatch instead.
        if k.marks is None and q and q.max_marks is not None:
            k.marks = q.max_marks
        k.mark_mismatch = bool(
            q and k.marks is not None and q.max_marks is not None and abs(k.marks - q.max_marks) > 1e-9
        )
    db.flush()


def mapping_summary(db: Session, ev: Evaluation) -> dict:
    qs = exam_questions(db, ev.exam_id)
    answers = db.query(StudentAnswer).filter_by(evaluation_id=ev.id).all()
    live = [a for a in answers if a.status != "IGNORED"]
    q_ids = {q.id for q in qs}
    # Every question falls in exactly one bucket, so mapped + suggested + missing == total_questions.
    mapped_q = {a.exam_question_id for a in live
                if a.status not in ("UNMAPPED", "NEEDS_REVIEW") and a.exam_question_id} & q_ids

    # Questions an unresolved answer points at (a duplicate's own target, or a candidate suggestion)
    suggested_q: set[str] = set()
    for a in live:
        if a.status == "NEEDS_REVIEW":
            suggested_q.update(a.mapping_candidates or [])
            if a.exam_question_id:
                suggested_q.add(a.exam_question_id)
    suggested_q = (suggested_q & q_ids) - mapped_q

    # Questions no answer maps to or is suggested for
    missing = [q for q in qs if q.id not in mapped_q and q.id not in suggested_q]

    return {
        "total_questions": len(qs),
        "mapped": len(mapped_q),
        "suggested": len(suggested_q),
        "needs_review": sum(a.status == "NEEDS_REVIEW" for a in live),
        "unmapped": sum(a.status == "UNMAPPED" for a in live),
        "missing": len(missing),
        "ignored": len(answers) - len(live),
        "missing_question_ids": [q.id for q in missing],
    }
