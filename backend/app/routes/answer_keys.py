from __future__ import annotations
import re
from typing import Literal
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ..database import get_db
from ..deps import err, get_exam
from ..models import (AnswerKey, AnswerKeyDocument, Evaluation, EvaluationItem, Exam, ExamQuestion,
                      Teacher)
from ..security import current_teacher
from ..serializers import key_view
from ..services.audit import audit
from ..formatter.common.mapping import map_label
from ..services.mapping_service import exam_questions, refresh_key_state, refresh_rubric
from ..services.state import set_state
from ..reference.search import subject_of
from ..reference.verify import find_board_answer, find_references, label_sources, verify_answers

router = APIRouter(prefix="/api")


def _verification_rubric_problems(key: AnswerKey):
    rubric = key.rubric or {}
    # CBSE extraction notes are retained as evidence, not workflow gates.
    if rubric.get("kind") == "cbse" or "cbse_tree" in rubric:
        return []
    return rubric.get("problems") or []


def _editable(exam: Exam):
    # open while questions are still being reviewed too: the key is read in parallel with the question paper
    if exam.status not in ("QUESTION_PAPER_UPLOADED", "QUESTIONS_EXTRACTED", "QUESTIONS_VERIFIED", "ANSWER_KEY_UPLOADED"):
        raise err(409, "ANSWER_KEY_LOCKED", "The answer key is not open for editing.")


def _get_key(db: Session, t: Teacher, kid: str) -> AnswerKey:
    k = db.get(AnswerKey, kid)
    if not k:
        raise err(404, "NOT_FOUND", "Answer key row not found.")
    get_exam(db, t, k.exam_id)
    return k


@router.get("/exams/{exam_id}/answer-keys")
def list_keys(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    exam = get_exam(db, t, exam_id)
    qs = exam_questions(db, exam.id)
    keys = db.query(AnswerKey).filter_by(exam_id=exam.id, is_active=True).order_by(AnswerKey.created_at).all()
    doc = db.query(AnswerKeyDocument).filter_by(exam_id=exam.id, is_active=True).order_by(AnswerKeyDocument.uploaded_at.desc()).first()
    covered = {k.exam_question_id for k in keys if k.mapping_status == "MAPPED" and k.exam_question_id}
    is_locked = exam.status in ("ANSWER_KEY_VERIFIED", "READY_FOR_EVALUATION", "EVALUATING", "REVIEW_REQUIRED", "FINALIZED")
    qmap = {q.id: q for q in qs}
    missing_rubric = [k for k in keys if k.rubric is None and k.exam_question_id in qmap]
    for k in missing_rubric:  # keys from before rubrics existed: build theirs now
        refresh_rubric(k, qmap[k.exam_question_id])
        if k.verification_status == "VERIFIED" and k.rubric is not None:
            k.rubric_status = "CONFIRMED"  # the teacher already reviewed this key
    if missing_rubric:
        db.commit()
    return {"keys": [key_view(k) for k in keys], "document_id": doc.id if doc else None,
            "questions": [{"id": q.id, "display_number": q.display_number, "max_marks": q.max_marks,
                           "question_text": q.question_text} for q in qs],
            "missing_question_ids": [q.id for q in qs if q.id not in covered],
            "locked": is_locked}


@router.get("/exams/{exam_id}/answer-keys/export.pdf")
def export_answer_keys_pdf(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    from ..services.extracted_pdf import answer_keys_pdf

    exam = get_exam(db, t, exam_id)
    questions = exam_questions(db, exam.id)
    qmap = {q.id: q for q in questions}
    rows = db.query(AnswerKey).filter_by(exam_id=exam.id, is_active=True).all()
    rows.sort(key=lambda key: (qmap[key.exam_question_id].position if key.exam_question_id in qmap else 10**9,
                               key.created_at))
    if not rows:
        raise err(409, "NO_EXTRACTED_ANSWER_KEY", "There is no extracted answer key to download.")
    filename = re.sub(r"[^A-Za-z0-9_-]+", "_", exam.name).strip("_") or "Exam"
    return Response(answer_keys_pdf(exam, rows, qmap), media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{filename}_Extracted_Answer_Key.pdf"',
    })


class KeyPatch(BaseModel):
    raw_question_number: str | None = None      # re-run deterministic mapping from this label
    exam_question_id: str | None = None         # teacher chooses the question explicitly
    answer_text: str | None = None
    marks: float | None = Field(None, ge=0)
    criteria: list[str] | None = None
    accepted_answers: list[str] | None = None
    keywords: list[str] | None = None
    verification_status: Literal["UNVERIFIED", "VERIFIED"] | None = None
    mismatch_resolution: Literal["keep_question_marks", "use_key_marks"] | None = None
    reason: str | None = None


@router.patch("/answer-keys/{kid}")
def patch_key(kid: str, body: KeyPatch, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    k = _get_key(db, t, kid)
    exam = db.get(Exam, k.exam_id)
    _editable(exam)
    d = body.model_dump(exclude_unset=True)
    reason = d.pop("reason", None)
    qs = exam_questions(db, exam.id)

    def log(action, old, new):
        audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="answer_key", entity_id=k.id, action=action, old=old, new=new, reason=reason)

    content_changed = False
    if "exam_question_id" in d and d["exam_question_id"]:
        q = next((x for x in qs if x.id == d["exam_question_id"]), None)
        if not q:
            raise err(400, "INVALID_QUESTION", "That question does not belong to this exam.")
        log("answer_key_mapping_changed", k.exam_question_id, q.id)
        k.exam_question_id, k.normalized_number = q.id, q.normalized_number
        k.mapping_status, k.mapping_note, k.mapping_candidates = "MAPPED", "Confirmed by teacher", []
        content_changed = True
    elif "raw_question_number" in d:
        log("answer_key_label_changed", k.raw_question_number, d["raw_question_number"])
        k.raw_question_number = d["raw_question_number"]
        res = map_label(k.raw_question_number, qs)
        k.normalized_number, k.exam_question_id = res.normalized_number, res.question_id
        k.mapping_status, k.mapping_note, k.mapping_candidates = res.status, res.note, res.candidates
        content_changed = True
    for f in ("answer_text", "marks", "criteria", "accepted_answers", "keywords"):
        if f in d and d[f] != getattr(k, f):
            log(f"answer_key_{f}_changed", getattr(k, f), d[f])
            setattr(k, f, d[f])
            content_changed = True
    db.flush()
    refresh_key_state(db, exam.id)
    res_choice = d.get("mismatch_resolution")
    if res_choice:
        q = next((x for x in qs if x.id == k.exam_question_id), None)
        if not q or not k.mark_mismatch:
            raise err(400, "NO_MISMATCH", "There is no marks mismatch to resolve for this row.")
        if res_choice == "keep_question_marks":
            log("answer_key_marks_aligned_to_question", k.marks, q.max_marks)
            k.marks = q.max_marks
        else:
            if not reason:
                raise err(400, "REASON_REQUIRED", "Give a reason for changing the question's maximum marks.")
            log("question_max_marks_changed_from_answer_key", q.max_marks, k.marks)
            q.max_marks = k.marks
        db.flush()
        refresh_key_state(db, exam.id)

    if "verification_status" in d and d["verification_status"] is not None:
        v_choice = d["verification_status"]
        if v_choice == "VERIFIED":
            if k.mapping_status != "MAPPED" or not k.exam_question_id:
                raise err(400, "CANNOT_VERIFY", "Cannot verify answer: it must be mapped to a question first.")
            if not (k.answer_text or "").strip():
                raise err(400, "CANNOT_VERIFY", "Cannot verify answer: solution text is empty.")
            if k.mark_mismatch:
                raise err(400, "CANNOT_VERIFY", "Cannot verify answer: marks mismatch must be resolved first.")
        if k.verification_status != v_choice:
            log("answer_key_verification_status_changed", k.verification_status, v_choice)
            k.verification_status = v_choice
    elif content_changed and k.verification_status == "VERIFIED":
        log("answer_key_verification_status_changed", k.verification_status, "UNVERIFIED")
        k.verification_status = "UNVERIFIED"

    db.commit()
    return key_view(k)


class KeyCreate(BaseModel):
    exam_question_id: str
    answer_text: str = Field(min_length=1)
    marks: float | None = Field(None, ge=0)
    criteria: list[str] = []
    accepted_answers: list[str] = []
    keywords: list[str] = []


@router.post("/exams/{exam_id}/answer-keys", status_code=201)
def add_key(exam_id: str, body: KeyCreate, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    exam = get_exam(db, t, exam_id)
    _editable(exam)
    q = db.get(ExamQuestion, body.exam_question_id)
    if not q or q.exam_id != exam.id:
        raise err(400, "INVALID_QUESTION", "That question does not belong to this exam.")
    doc = db.query(AnswerKeyDocument).filter_by(exam_id=exam.id, is_active=True).order_by(AnswerKeyDocument.uploaded_at.desc()).first()
    k = AnswerKey(exam_id=exam.id, document_id=doc.id if doc else None, raw_question_number=q.display_number,
                  normalized_number=q.normalized_number, exam_question_id=q.id, answer_text=body.answer_text,
                  raw_ocr_text="", marks=body.marks, criteria=body.criteria, accepted_answers=body.accepted_answers,
                  keywords=body.keywords, mapping_status="MAPPED", mapping_note="Entered by teacher")
    db.add(k)
    db.flush()
    if exam.status == "QUESTIONS_VERIFIED":
        set_state(exam, "ANSWER_KEY_UPLOADED")
    refresh_key_state(db, exam.id)
    audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="answer_key", entity_id=k.id, action="answer_key_added_manually", new=q.display_number)
    db.commit()
    return key_view(k)


@router.delete("/answer-keys/{kid}")
def delete_key(kid: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    k = _get_key(db, t, kid)
    exam = db.get(Exam, k.exam_id)
    _editable(exam)
    audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="answer_key", entity_id=k.id, action="answer_key_row_deleted", old=key_view(k))
    db.delete(k)
    db.flush()
    refresh_key_state(db, exam.id)
    db.commit()
    return {"ok": True}


@router.post("/exams/{exam_id}/answer-keys/generate-ai")
def generate_answer_keys_ai(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    exam = get_exam(db, t, exam_id)
    if exam.status in ("DRAFT", "QUESTION_PAPER_UPLOADED", "QUESTIONS_EXTRACTED"):
        raise err(409, "QUESTIONS_NOT_VERIFIED", "Verify the questions before generating the answer key.")
    if db.query(EvaluationItem).join(Evaluation, Evaluation.id == EvaluationItem.evaluation_id).filter(Evaluation.exam_id == exam.id).first():
        raise err(409, "ANSWER_KEY_LOCKED", "Evaluation has started, so the answer key can no longer be changed.")

    qs = exam_questions(db, exam.id)
    if not qs:
        raise err(400, "NO_QUESTIONS", "There are no verified questions in this exam to generate answers for.")

    # Keys come only from the shared reference library; the AI is not used here (it reads sheets and grades).
    # A question that is a CBSE sample-paper question gets its marking-scheme answer exactly as printed.
    # Any other question is left for the teacher, with the NCERT passages for it shown as printed.
    scope = subject_of(exam)
    answers = []
    for q in qs:
        refs = find_references(db, *scope, q.question_text or "") if scope else []
        board = find_board_answer(db, *scope, q.question_text or "") if scope else None
        if board:
            note = (f"From {board['source']}, question {board['question_number']} (p.{board['pages']}), "
                    "exactly as printed.")
        elif refs:
            note = "Not a board question: write the answer from the textbook passages shown."
        else:
            note = "No source found in the reference library: write the answer yourself."
        answers.append({
            "exam_question_id": q.id,
            "question_number": q.display_number,
            "question_text": q.question_text,
            "max_marks": q.max_marks,
            "answer_text": board["answer"] if board else "",
            "marks": q.max_marks,
            "criteria": [],
            "keywords": [],
            "accepted_answers": [],
            "origin": "BOARD_MARKING_SCHEME" if board else "NONE",
            "board": {k: board[k] for k in ("source", "question_number", "marks", "pages", "question")} if board else None,
            "sources": label_sources(refs),
            "note": note,
        })
    return {"answers": answers, "source": "REFERENCE_LIBRARY", "can_save_as_scheme": not bool(exam.standard_profile_id),
            "reference_subject": scope[1] if scope else None}


@router.post("/exams/{exam_id}/answer-keys/check-references")
def check_answer_key_references(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    """Checks the exam's saved answer key against the NCERT / CBSE reference library. Advice only: nothing is changed."""
    exam = get_exam(db, t, exam_id)
    scope = subject_of(exam)
    by_q = {q.id: q for q in exam_questions(db, exam.id)}
    keys = db.query(AnswerKey).filter_by(exam_id=exam.id, is_active=True).all()
    out, todo = [], []
    for k in keys:
        q = by_q.get(k.exam_question_id)
        row = {"answer_key_id": k.id, "exam_question_id": k.exam_question_id,
               "question_number": q.display_number if q else k.raw_question_number, "verification": None}
        out.append(row)
        if scope and (k.answer_text or "").strip():
            todo.append((row, {"question": (q.question_text if q else "") or "", "answer": k.answer_text}))
    if todo:
        for (row, _), v in zip(todo, verify_answers(db, *scope, [item for _, item in todo])):
            row["verification"] = v.as_dict()
    order = {qid: i for i, qid in enumerate(by_q)}
    out.sort(key=lambda x: order.get(x["exam_question_id"], 999))
    return {"reference_subject": scope[1] if scope else None, "answers": out}


class SaveGeneratedItem(BaseModel):
    exam_question_id: str
    answer_text: str = ""
    marks: float | None = None
    criteria: list[str] = []
    keywords: list[str] = []
    accepted_answers: list[str] = []


class SaveGeneratedIn(BaseModel):
    answers: list[SaveGeneratedItem]


@router.post("/exams/{exam_id}/answer-keys/save-ai", status_code=201)
def save_generated_answer_keys(exam_id: str, body: SaveGeneratedIn, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    exam = get_exam(db, t, exam_id)
    if exam.standard_profile_id:
        raise err(409,"UPLOADED_SCHEME_REQUIRED","Generated answers are drafts. Upload the matching marking scheme for a CBSE board-pattern exam.")
    if exam.status in ("DRAFT", "QUESTION_PAPER_UPLOADED", "QUESTIONS_EXTRACTED"):
        raise err(409, "QUESTIONS_NOT_VERIFIED", "Verify the questions before saving an answer key.")
    if db.query(EvaluationItem).join(Evaluation, Evaluation.id == EvaluationItem.evaluation_id).filter(Evaluation.exam_id == exam.id).first():
        raise err(409, "ANSWER_KEY_LOCKED", "Evaluation has started, so the answer key can no longer be replaced.")

    qs = exam_questions(db, exam.id)
    q_map = {q.id: q for q in qs}

    for old_k in db.query(AnswerKey).filter_by(exam_id=exam.id, is_active=True):
        old_k.is_active = False
    for old_doc in db.query(AnswerKeyDocument).filter_by(exam_id=exam.id, is_active=True):
        old_doc.is_active = False

    saved_keys = []
    for item in body.answers:
        q = q_map.get(item.exam_question_id)
        if not q:
            continue
        k = AnswerKey(
            exam_id=exam.id,
            document_id=None,
            raw_question_number=q.display_number,
            normalized_number=q.normalized_number,
            exam_question_id=q.id,
            answer_text=item.answer_text,
            raw_ocr_text=item.answer_text,
            marks=item.marks if item.marks is not None else q.max_marks,
            criteria=item.criteria,
            keywords=item.keywords,
            accepted_answers=item.accepted_answers,
            mapping_status="MAPPED",
            mapping_note="Generated with AI and approved by teacher",
            verification_status="UNVERIFIED",
        )
        db.add(k)
        saved_keys.append(k)

    db.flush()
    refresh_key_state(db, exam.id)
    set_state(exam, "ANSWER_KEY_UPLOADED")
    audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="answer_key", entity_id=exam.id,
          action="answer_keys_generated_with_ai", new=len(saved_keys))
    db.commit()

    return list_keys(exam.id, db, t)


def _collect_answer_key_validation(db: Session, exam: Exam) -> dict:
    doc = db.query(AnswerKeyDocument).filter_by(exam_id=exam.id, is_active=True).order_by(AnswerKeyDocument.uploaded_at.desc()).first()
    qs = exam_questions(db, exam.id)
    keys = db.query(AnswerKey).filter_by(exam_id=exam.id, is_active=True).order_by(AnswerKey.created_at).all()
    refresh_key_state(db, exam.id)

    blocking_issues = []
    verified_keys = []
    needs_review_keys = []

    if doc is not None and doc.status != "READY":
        blocking_issues.append({
            "key_id": None,
            "question": "Answer Key Document",
            "reason": "Some pages could not be read. Retry them before verifying.",
            "issue_type": "ocr_failed",
        })

    by_q: dict[str, list[AnswerKey]] = {}
    for k in keys:
        label = k.raw_question_number or (f"Q{k.normalized_number}" if k.normalized_number else "(no number)")
        has_issue = False

        if k.mapping_status != "MAPPED" or not k.exam_question_id:
            reason = (k.mapping_note or "Not mapped to a question") + ". Map it to a question or delete the row."
            blocking_issues.append({
                "key_id": k.id,
                "question": label,
                "reason": reason,
                "issue_type": "unmapped" if k.mapping_status == "UNMAPPED" else "needs_review",
            })
            has_issue = True

        if not (k.answer_text or "").strip():
            blocking_issues.append({
                "key_id": k.id,
                "question": label,
                "reason": "Answer text is empty",
                "issue_type": "empty_solution",
            })
            has_issue = True

        if k.mark_mismatch:
            blocking_issues.append({
                "key_id": k.id,
                "question": label,
                "reason": "MARK MISMATCH: key marks differ from the question's maximum marks",
                "issue_type": "mark_mismatch",
            })
            has_issue = True

        if k.verification_status != "VERIFIED":
            needs_review_keys.append(k.id)
            if not has_issue:
                blocking_issues.append({
                    "key_id": k.id,
                    "question": label,
                    "reason": "Pending individual teacher verification. Tap Verify Answer to approve.",
                    "issue_type": "unapproved",
                })
        else:
            if not has_issue:
                verified_keys.append(k.id)

        if k.mapping_status == "MAPPED" and k.exam_question_id:
            by_q.setdefault(k.exam_question_id, []).append(k)

    for q in qs:
        mapped_rows = by_q.get(q.id, [])
        if len(mapped_rows) == 0:
            blocking_issues.append({
                "key_id": None,
                "question": f"Question {q.display_number}",
                "reason": "No answer key for this question",
                "issue_type": "missing_key",
            })
        elif len(mapped_rows) > 1:
            for row in mapped_rows:
                blocking_issues.append({
                    "key_id": row.id,
                    "question": f"Question {q.display_number}",
                    "reason": "More than one answer key row maps to this question",
                    "issue_type": "duplicate_mapping",
                })

    return {
        "valid": len(blocking_issues) == 0,
        "summary": {
            "total_processed": len(keys),
            "total_keys": len(keys),
            "total_questions": len(qs),
            "verified_count": len(verified_keys),
            "needs_review_count": len(needs_review_keys),
            "failed_count": 0,
            "blocking_issues_count": len(blocking_issues),
        },
        "blocking_issues": blocking_issues,
        "issues": [{"question": b["question"], "reason": b["reason"]} for b in blocking_issues],
    }


@router.post("/exams/{exam_id}/answer-keys/validate")
def validate_keys(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    exam = get_exam(db, t, exam_id)
    return _collect_answer_key_validation(db, exam)


@router.post("/exams/{exam_id}/answer-keys/verify-all")
def verify_all_keys(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    exam = get_exam(db, t, exam_id)
    _editable(exam)

    doc = db.query(AnswerKeyDocument).filter_by(exam_id=exam.id, is_active=True).order_by(AnswerKeyDocument.uploaded_at.desc()).first()
    qs = exam_questions(db, exam.id)
    qmap = {q.id: q for q in qs}
    keys = db.query(AnswerKey).filter_by(exam_id=exam.id, is_active=True).order_by(AnswerKey.created_at).all()

    # Recompute deterministic duplicate flags and mark mismatches first
    refresh_key_state(db, exam.id)

    # Count occurrences of mapped exam_question_ids to detect duplicates
    by_q: dict[str, list[AnswerKey]] = {}
    for k in keys:
        if k.mapping_status == "MAPPED" and k.exam_question_id:
            by_q.setdefault(k.exam_question_id, []).append(k)

    blocking_issues: list[dict] = []
    verified_keys: list[str] = []
    needs_review_keys: list[str] = []
    failed_keys: list[str] = []
    newly_verified = 0

    doc_failed = doc is not None and doc.status == "FAILED"
    if doc is not None and doc.status != "READY":
        blocking_issues.append({
            "key_id": None,
            "question": "Answer Key Document",
            "reason": "Some pages could not be read. Retry them before verifying.",
            "issue_type": "ocr_failed",
        })

    for k in keys:
        label = k.raw_question_number or (f"Q{k.normalized_number}" if k.normalized_number else "(no number)")
        reasons = []
        primary_issue_type = None

        if doc_failed:
            reasons.append("Document reading failed")
            primary_issue_type = "ocr_failed"

        # Check question mapping
        if k.mapping_status != "MAPPED" or not k.exam_question_id:
            reason = (k.mapping_note or "Not mapped to a question") + ". Map it to a question or delete the row."
            reasons.append(reason)
            if not primary_issue_type:
                primary_issue_type = "unmapped" if k.mapping_status == "UNMAPPED" else "needs_review"
        elif k.exam_question_id not in qmap:
            reasons.append("Mapped question does not exist in this exam")
            if not primary_issue_type:
                primary_issue_type = "needs_review"
        elif len(by_q.get(k.exam_question_id, [])) > 1:
            mapped_q = qmap.get(k.exam_question_id)
            q_disp = mapped_q.display_number if mapped_q else "?"
            reasons.append(f"Duplicate mapping: more than one answer key row maps to question {q_disp}")
            if not primary_issue_type:
                primary_issue_type = "duplicate_mapping"

        # Check solution text
        if not (k.answer_text or "").strip():
            reasons.append("Answer text is empty / missing solution")
            if not primary_issue_type:
                primary_issue_type = "empty_solution"

        # Check marks and mark mismatch
        if k.marks is None or k.marks < 0:
            reasons.append("Invalid marks assigned")
            if not primary_issue_type:
                primary_issue_type = "needs_review"
        elif k.mark_mismatch:
            mapped_q = qmap.get(k.exam_question_id)
            q_marks = mapped_q.max_marks if mapped_q else "?"
            reasons.append(f"MARK MISMATCH: key has {k.marks} marks, but Question {mapped_q.display_number if mapped_q else '?'} is worth {q_marks} marks")
            if not primary_issue_type:
                primary_issue_type = "mark_mismatch"

        for problem in _verification_rubric_problems(k):
            reasons.append(f"Rubric: {problem}")
            if not primary_issue_type:
                primary_issue_type = "rubric"

        if reasons:
            if doc_failed:
                failed_keys.append(k.id)
            else:
                needs_review_keys.append(k.id)

            # Never verify problematic answers; revert if previously marked VERIFIED
            if k.verification_status == "VERIFIED":
                k.verification_status = "UNVERIFIED"
                audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="answer_key", entity_id=k.id,
                      action="answer_key_verification_status_changed", old="VERIFIED", new="UNVERIFIED",
                      reason="reverted_due_to_unresolved_issue")

            for r in reasons:
                blocking_issues.append({
                    "key_id": k.id,
                    "question": label,
                    "reason": r,
                    "issue_type": primary_issue_type or "needs_review",
                })
        else:
            # All validation rules satisfied & unambiguous mapping
            if k.verification_status != "VERIFIED":
                k.verification_status = "VERIFIED"
                audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="answer_key", entity_id=k.id,
                      action="answer_key_verification_status_changed", old="UNVERIFIED", new="VERIFIED",
                      reason="auto_verified_eligible_answer")
                newly_verified += 1
            if k.rubric is not None:
                k.rubric_status = "CONFIRMED"
            verified_keys.append(k.id)

    # Check for questions lacking answer keys
    covered = {k.exam_question_id for k in keys if k.mapping_status == "MAPPED" and k.exam_question_id}
    missing_q_ids = [q.id for q in qs if q.id not in covered]
    for q in qs:
        if q.id not in covered:
            blocking_issues.append({
                "key_id": None,
                "question": f"Question {q.display_number}",
                "reason": "No answer key for this question",
                "issue_type": "missing_key",
            })

    if newly_verified > 0:
        audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="exam", entity_id=exam.id,
              action="answer_keys_auto_verified", new=newly_verified,
              reason=f"auto_verified_{len(verified_keys)}_of_{len(keys)}")

    db.commit()

    is_locked = exam.status in ("ANSWER_KEY_VERIFIED", "READY_FOR_EVALUATION", "EVALUATING", "REVIEW_REQUIRED", "FINALIZED")
    summary = {
        "total_processed": len(keys),
        "total_keys": len(keys),
        "total_questions": len(qs),
        "verified_count": len(verified_keys),
        "needs_review_count": len(needs_review_keys),
        "failed_count": len(failed_keys),
        "blocking_issues_count": len(blocking_issues),
    }

    return {
        "summary": summary,
        "keys": [key_view(k) for k in keys],
        "questions": [{"id": q.id, "display_number": q.display_number, "max_marks": q.max_marks,
                       "question_text": q.question_text} for q in qs],
        "missing_question_ids": missing_q_ids,
        "blocking_issues": blocking_issues,
        "issues": [{"question": b["question"], "reason": b["reason"]} for b in blocking_issues],
        "valid": len(blocking_issues) == 0,
        "locked": is_locked,
        "all_verified": len(verified_keys) == len(keys) and len(blocking_issues) == 0,
    }


@router.post("/exams/{exam_id}/answer-keys/verify")
def verify_keys(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    exam = get_exam(db, t, exam_id)
    if exam.status != "ANSWER_KEY_UPLOADED":
        raise err(409, "INVALID_EXAM_STATE", "The answer key can only be verified after it has been uploaded.")
    doc = db.query(AnswerKeyDocument).filter_by(exam_id=exam.id, is_active=True).order_by(AnswerKeyDocument.uploaded_at.desc()).first()
    qs = exam_questions(db, exam.id)
    keys = db.query(AnswerKey).filter_by(exam_id=exam.id, is_active=True).all()
    refresh_key_state(db, exam.id)
    issues = []
    if doc is not None and doc.status != "READY":
        issues.append({"question": "Answer key", "reason": "Some pages could not be read. Retry them before verifying."})
    for k in keys:
        label = k.raw_question_number or "(no number)"
        if k.mapping_status != "MAPPED":
            issues.append({"question": label, "reason": (k.mapping_note or "Not mapped to a question") + ". Map it to a question or delete the row."})
        if not (k.answer_text or "").strip():
            issues.append({"question": label, "reason": "Answer text is empty"})
        if k.mark_mismatch:
            issues.append({"question": label, "reason": "MARK MISMATCH: key marks differ from the question's maximum marks"})
        for problem in _verification_rubric_problems(k):
            issues.append({"question": label, "reason": f"Rubric: {problem}"})
    by_q: dict[str, int] = {}
    for k in keys:
        if k.mapping_status == "MAPPED" and k.exam_question_id:
            by_q[k.exam_question_id] = by_q.get(k.exam_question_id, 0) + 1
    for q in qs:
        n = by_q.get(q.id, 0)
        if n == 0:
            issues.append({"question": q.display_number, "reason": "No answer key for this question"})
        elif n > 1:
            issues.append({"question": q.display_number, "reason": "More than one answer key row maps to this question"})
    if issues:
        raise err(400, "ANSWER_KEY_NOT_READY", f"{len(issues)} issue(s) must be resolved before the answer key can be verified.", issues)
    for k in keys:
        k.verification_status = "VERIFIED"
        if k.rubric is not None:
            k.rubric_status = "CONFIRMED"  # the teacher's one-time review of the marking rubric
    set_state(exam, "ANSWER_KEY_VERIFIED")
    if db.query(Evaluation).filter_by(exam_id=exam.id).first():
        set_state(exam, "READY_FOR_EVALUATION")
    audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="exam", entity_id=exam.id, action="answer_key_verified", new=len(keys))
    db.commit()
    return {"verified": len(keys)}
