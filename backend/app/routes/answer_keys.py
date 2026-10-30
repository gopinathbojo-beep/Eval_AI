from __future__ import annotations
import logging
from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ..database import get_db
from ..deps import err, get_exam
from ..documents.storage import abs_path
from ..models import (AnswerKey, AnswerKeyDocument, Evaluation, EvaluationItem, Exam, ExamQuestion,
                      QuestionPaperDocument, Teacher)
from ..ocr import prompts
from ..ocr.internvl import chat_structured, check_model
from ..ocr.indic import text_model_for
from ..ocr.schemas import GeneratedAnswerKeyResult
from ..security import current_teacher
from ..serializers import key_view
from ..services.audit import audit
from ..cbse.formatter.common.mapping import map_label
from ..services.mapping_service import exam_questions, refresh_key_state, refresh_rubric
from ..cbse.formatter.common.numbering import normalize_question_number
from ..services.state import set_state

router = APIRouter(prefix="/api")


def _editable(exam: Exam):
    if exam.status not in ("QUESTIONS_VERIFIED", "ANSWER_KEY_UPLOADED"):
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


class SplitKeyIn(BaseModel):
    at_char: int = Field(gt=0)
    new_label: str
    new_marks: float | None = Field(None, ge=0)


@router.post("/answer-keys/{kid}/split")
def split_key(kid: str, body: SplitKeyIn, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    k = _get_key(db, t, kid)
    exam = db.get(Exam, k.exam_id)
    _editable(exam)
    if body.at_char >= len(k.answer_text):
        raise err(400, "INVALID_SPLIT", "Split position is beyond the end of the text.")
    norm = normalize_question_number(body.new_label)
    head, tail = k.answer_text[:body.at_char].rstrip(), k.answer_text[body.at_char:].lstrip()

    qs = exam_questions(db, exam.id)
    res = map_label(body.new_label, qs)

    new_k = AnswerKey(
        exam_id=exam.id,
        document_id=k.document_id,
        raw_question_number=body.new_label,
        normalized_number=norm,
        exam_question_id=res.question_id,
        answer_text=tail,
        raw_ocr_text=tail,
        marks=body.new_marks,
        page_number=k.page_number,
        mapping_status=res.status,
        mapping_note=res.note,
        mapping_candidates=res.candidates,
    )
    k.answer_text = head
    db.add(new_k)
    db.flush()
    refresh_key_state(db, exam.id)
    audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="answer_key", entity_id=k.id,
          action="answer_key_split", old=k.raw_ocr_text, new={"head": head, "tail": tail, "new_label": body.new_label})
    db.commit()
    return {"original": key_view(k), "new": key_view(new_k)}


class MergeKeyIn(BaseModel):
    other_id: str


@router.post("/answer-keys/{kid}/merge")
def merge_key(kid: str, body: MergeKeyIn, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    k = _get_key(db, t, kid)
    exam = db.get(Exam, k.exam_id)
    _editable(exam)
    o = _get_key(db, t, body.other_id)
    if o.exam_id != k.exam_id or o.id == k.id:
        raise err(400, "INVALID_MERGE", "Choose a different answer key row from the same exam.")

    audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="answer_key", entity_id=k.id,
          action="answer_key_merged", old={"kept": key_view(k), "absorbed": key_view(o)})
    k.answer_text = (k.answer_text.rstrip() + "\n" + o.answer_text.lstrip()).strip()
    k.raw_ocr_text = (k.raw_ocr_text.rstrip() + "\n" + o.raw_ocr_text.lstrip()).strip()
    if not k.criteria and o.criteria:
        k.criteria = o.criteria
    if not k.accepted_answers and o.accepted_answers:
        k.accepted_answers = o.accepted_answers
    if not k.keywords and o.keywords:
        k.keywords = o.keywords
    db.delete(o)
    db.flush()
    refresh_key_state(db, exam.id)
    db.commit()
    return key_view(k)


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

    model = text_model_for(exam.subject.name if exam.subject else None)
    check_model(model)

    q_dicts = [
        {
            "id": q.id,
            "display_number": q.display_number,
            "normalized_number": q.normalized_number,
            "question_text": q.question_text,
            "max_marks": q.max_marks or 0.0,
            "question_type": q.question_type or "descriptive",
        }
        for q in qs
    ]

    img_path = None
    # Only supply heavy image to Ollama if some questions have empty or very short text (e.g. diagrams/figures)
    if any(len((q.question_text or "").strip()) < 10 for q in qs):
        qp = db.query(QuestionPaperDocument).filter_by(exam_id=exam.id, is_active=True).first()
        if qp and qp.pages and qp.pages[0].get("processed_file"):
            try:
                cand = abs_path(qp.pages[0]["processed_file"])
                if cand.is_file():
                    img_path = cand
            except Exception:
                pass

    by_id = {q.id: q for q in qs}
    by_norm = {q.normalized_number: q for q in qs}
    by_disp = {q.display_number: q for q in qs}

    matched_answers: list[dict] = []
    accounted_qids = set()

    # Batch questions in chunks of up to 3 to prevent token exhaustion and JSON truncation
    batch_size = 3
    for i in range(0, len(q_dicts), batch_size):
        chunk = q_dicts[i:i + batch_size]
        prompt = prompts.generate_answer_key_prompt(exam.name, chunk)
        try:
            call = chat_structured(prompts.GEN_ANSWER_KEY_SYSTEM, prompt, GeneratedAnswerKeyResult, image_path=img_path,
                                   model=model)
            for ans in call.parsed.answers:
                target_q = None
                if ans.exam_question_id and ans.exam_question_id in by_id:
                    target_q = by_id[ans.exam_question_id]
                elif ans.question_number:
                    target_q = by_disp.get(ans.question_number) or by_norm.get(normalize_question_number(ans.question_number))
                    if not target_q:
                        res = map_label(ans.question_number, qs)
                        if res.question_id and res.question_id in by_id:
                            target_q = by_id[res.question_id]

                if target_q and target_q.id not in accounted_qids:
                    accounted_qids.add(target_q.id)
                    matched_answers.append({
                        "exam_question_id": target_q.id,
                        "question_number": target_q.display_number,
                        "question_text": target_q.question_text,
                        "max_marks": target_q.max_marks,
                        "answer_text": ans.answer_text,
                        "marks": ans.marks if ans.marks is not None else target_q.max_marks,
                        "criteria": ans.criteria,
                        "keywords": ans.keywords,
                        "accepted_answers": ans.accepted_answers,
                    })
        except Exception:
            # If a chunk fails, log and continue so subsequent chunks can succeed
            logging.getLogger("adem").exception("AI answer-key generation failed for a chunk")

    for q in qs:
        if q.id not in accounted_qids:
            accounted_qids.add(q.id)
            matched_answers.append({
                "exam_question_id": q.id,
                "question_number": q.display_number,
                "question_text": q.question_text,
                "max_marks": q.max_marks,
                "answer_text": "",
                "marks": q.max_marks,
                "criteria": [],
                "keywords": [],
                "accepted_answers": [],
            })

    q_order = {q.id: idx for idx, q in enumerate(qs)}
    matched_answers.sort(key=lambda x: q_order.get(x["exam_question_id"], 999))

    return {"answers": matched_answers}


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

        for problem in (k.rubric or {}).get("problems") or []:
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
        for problem in (k.rubric or {}).get("problems") or []:
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
