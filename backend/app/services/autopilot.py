"""Autopilot: the school only uploads the question paper, the answer key and the answer sheets; every review step
in between is settled here, with the AI, so each document moves on by itself.

Each step runs after the app's own reading and checks, and only on what those left unresolved, so a clean paper
costs no extra AI call. The AI tiers (config): the medium model looks at page images (a flagged question, a
question the reading missed) and writes missing answer-key entries; the small model makes short text-only
choices (which question an answer or a key row belongs to). Whatever the AI settles is recorded on the item
(notes, audit) so a teacher can still see it, change it, or reopen a finalized evaluation.

Turned off with AUTOPILOT=false: the manual review screens then work as before.
"""
from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

from fastapi import BackgroundTasks, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import SessionLocal
from ..documents.storage import abs_path
from ..models import (AnswerKey, AnswerKeyDocument, AnswerSheetDocument, Evaluation, EvaluationItem, Exam,
                      ExamQuestion, QuestionPaperDocument, StudentAnswer, Teacher)
from ..ocr.internvl import AIResponseError, AIUnavailable, chat_structured
from .audit import audit
from .job_queue import keyed_lock

log = logging.getLogger("adem.autopilot")

REVIEW_SYSTEM = ("You check the work of an automatic reader of school examination documents against the source. "
                 "Use only what the source shows. Reply with one JSON object and nothing else.")
WRITER_SYSTEM = ("You are an experienced CBSE examiner writing the marking-scheme answer for questions whose scheme "
                 "entry is missing: correct, complete for the marks, in the board's style. Reply with one JSON object "
                 "and nothing else.")
REOPENED = "evaluation_reopened"  # audit action: a teacher reopened the result, so it is never finalized again here


def enabled() -> bool:
    return get_settings().autopilot


def _isolated(step):
    """Run a step in a copy of the context: the request helpers it reuses (get_exam) set the exam's formatter and
    paper format for "the rest of the request", which outside a request would stay on the worker thread."""
    import contextvars
    from functools import wraps

    @wraps(step)
    def run(*args, **kwargs):
        return contextvars.copy_context().run(step, *args, **kwargs)
    return run


def _safely(step, *args):
    """A step that fails leaves the document where it is (the manual screens still work); it never breaks the
    reading or grading that called it."""
    if not enabled():
        return None
    try:
        return step(*args)
    except AIUnavailable as e:
        log.warning("Autopilot %s stopped: AI unavailable (%s)", step.__name__, e.detail)
    except Exception:
        log.exception("Autopilot %s failed", step.__name__)
    return None


def _owner(db: Session, exam: Exam) -> Teacher:
    return db.get(Teacher, exam.teacher_id)


def _note(db, exam, entity_type, entity_id, action, new=None):
    audit(db, exam_id=exam.id, teacher_id=None, entity_type=entity_type, entity_id=entity_id, action=action, new=new)


def _run_background(bg: BackgroundTasks) -> None:
    for task in bg.tasks:
        task.func(*task.args, **task.kwargs)


def _page_image(doc, numbers: list[int]) -> Path | None:
    """The source page(s) as one image: two pages are stacked, so a question cut by a page break is seen whole."""
    from PIL import Image
    files = []
    for n in sorted(set(numbers))[:2]:
        page = next((p for p in doc.pages or [] if p.get("page_number") == n), None)
        if page and page.get("processed_file") and abs_path(page["processed_file"]).is_file():
            files.append(abs_path(page["processed_file"]))
    if not files:
        return None
    if len(files) == 1:
        return files[0]
    images = [Image.open(f).convert("RGB") for f in files]
    width = max(i.width for i in images)
    sheet = Image.new("RGB", (width, sum(i.height for i in images)), "white")
    y = 0
    for image in images:
        sheet.paste(image, (0, y))
        y += image.height
    out = Path(tempfile.mkdtemp(prefix="autopilot-")) / "pages.png"
    sheet.save(out)
    return out


# ---------------------------------------------------------------- question paper

class QuestionFix(BaseModel):
    found: bool = True
    text: str = ""
    marks: float | None = Field(None, ge=0)

    @field_validator("marks", mode="before")
    @classmethod
    def _number(cls, value):
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None


def _fix_prompt(number, text, marks, problems):
    return (f"The page image shows question {number} of a question paper. The automatic reader produced:\n"
            f"--- text ---\n{text or '(nothing)'}\n--- printed marks: {marks if marks is not None else 'unknown'}\n"
            f"--- problems it reported ---\n" + "\n".join(f"- {p}" for p in problems or ["none"]) + "\n\n"
            "Give the complete, correct text of this one question exactly as printed: its stem, every part, every "
            "option and every OR alternative, including any 'For Visually Impaired' version. Leave out page headers, "
            "footers, section headings and instructions to the whole section. Describe a figure in one line as "
            "[Figure: ...]. Give the marks printed for the whole question.\n"
            'Reply: {"found": true, "text": "...", "marks": 3}. If question ' f"{number}" ' is not on the page, '
            'reply {"found": false}.')


@_isolated
def settle_questions(exam_id: str) -> None:
    """After the question paper is read: fix each flagged question against its page, read any question the board
    pattern expects but the reading missed, accept everything and verify the paper (which releases the key)."""
    db = SessionLocal()
    try:
        exam = db.get(Exam, exam_id)
        if exam is None or exam.status not in ("QUESTION_PAPER_UPLOADED", "QUESTIONS_EXTRACTED"):
            return
        doc = (db.query(QuestionPaperDocument).filter_by(exam_id=exam.id, is_active=True)
               .order_by(QuestionPaperDocument.uploaded_at.desc()).first())
        if doc is None or doc.status not in ("READY", "NEEDS_ATTENTION"):
            return
        with keyed_lock(f"exam:{exam.id}"):
            _settle_questions(db, exam, doc)
    finally:
        db.close()
    settle_answer_key(exam_id)  # a key read before the questions were ready goes on now


def _expected_marks(exam):
    from ..cbse.catalog import get_profile
    p = get_profile(exam.standard_profile_id) if exam.standard_profile_id else None
    if not p or p.get("upload_driven"):
        return None, None
    return p, {n + 1: m for n, m in enumerate(p["parent_marks"])}


def _settle_questions(db, exam, doc):
    from ..routes.questions import _validate_for_verified, verify_questions
    profile, expected = _expected_marks(exam)
    qs = db.query(ExamQuestion).filter_by(exam_id=exam.id).order_by(ExamQuestion.position).all()
    model = get_settings().medium_model

    # 1. questions the board pattern has and the reading missed
    if profile:
        present = {int(q.normalized_number) for q in qs if (q.normalized_number or "").isdigit()}
        by_root = {int(q.normalized_number): q for q in qs if (q.normalized_number or "").isdigit()}
        for root in range(1, profile["question_count"] + 1):
            if root in present:
                continue
            before = max((r for r in present if r < root), default=None)
            after = min((r for r in present if r > root), default=None)
            pages = [n for n in ((by_root[before].page_end if before else None),
                                 (by_root[after].page_start if after else None)) if n]
            image = _page_image(doc, pages or [1])
            if image is None:
                continue
            fix = chat_structured(REVIEW_SYSTEM, _fix_prompt(root, "", expected.get(root), [
                "the reader found no question with this number"]), QuestionFix, image, model=model).parsed
            if not fix.found or not fix.text.strip():
                continue
            from ..cbse.catalog import expected_section
            section = expected_section(profile, root)
            marks = expected.get(root) or fix.marks
            q = ExamQuestion(exam_id=exam.id, document_id=doc.id, display_number=str(root), normalized_number=str(root),
                             question_text=fix.text.strip(), raw_ocr_text=fix.text.strip(), max_marks=marks,
                             section=section["key"] if section else None, position=root,
                             page_start=min(pages) if pages else None, page_end=max(pages) if pages else None,
                             structure={"root": root, "issues": [], "source_pages": pages,
                                        "tree": {"id": f"q{root}", "kind": "point", "label": str(root), "marks": marks,
                                                 "text": fix.text.strip()[:200], "children": []},
                                        "notes": ["The reading missed this question; the AI read it from the page."]},
                             verification_status="UNVERIFIED")
            db.add(q)
            qs.append(q)
            present.add(root)
            by_root[root] = q
            _note(db, exam, "question", str(root), "autopilot_question_recovered")
        db.flush()

    # 2. each flagged question checked against its page
    for q in qs:
        problems = list((q.structure or {}).get("issues") or []) + _validate_for_verified(q, qs)
        if q.verification_status != "NEEDS_REVIEW" and not problems:
            continue
        pages = [n for n in (q.page_start, q.page_end) if n]
        image = _page_image(doc, pages) if pages else None
        if image is not None:
            try:
                fix = chat_structured(REVIEW_SYSTEM, _fix_prompt(q.display_number, q.question_text, q.max_marks, problems),
                                      QuestionFix, image, model=model).parsed
            except AIResponseError:
                fix = None
            if fix and fix.found and fix.text.strip():
                q.question_text = fix.text.strip()
                if not expected and fix.marks and (q.max_marks is None or q.max_marks <= 0):
                    q.max_marks = fix.marks
        root = int(q.normalized_number) if (q.normalized_number or "").isdigit() else None
        if expected and root in expected:
            q.max_marks = expected[root]  # the board pattern is the authority for whole-question marks
        structure = dict(q.structure or {})
        if problems:
            structure["notes"] = list(structure.get("notes") or []) + [f"Checked by AI against the page: {p}" for p in problems]
        structure["issues"] = []
        q.structure = structure
        q.verification_status, q.review_reason = "VERIFIED", None
    for q in qs:
        if q.verification_status == "UNVERIFIED" and not _validate_for_verified(q, qs):
            q.verification_status = "VERIFIED"
    db.commit()

    # 3. pages that could not be read at all: one more reading, then the paper goes on with what was read
    extraction = dict(doc.extraction or {})
    if doc.status == "NEEDS_ATTENTION":
        if not extraction.get("autopilot_reread"):
            extraction["autopilot_reread"] = True
            doc.extraction = extraction
            db.commit()
            from .job_queue import submit
            from .pipeline import process_document
            submit(exam.id, process_document, "question-paper", doc.id, True)
            return
        doc.status, doc.stage = "READY", "Ready (some pages could not be read)"
        db.commit()
    if exam.status == "QUESTION_PAPER_UPLOADED":
        from .state import set_state
        set_state(exam, "QUESTIONS_EXTRACTED")
        db.commit()
    bg = BackgroundTasks()
    try:
        verify_questions(exam.id, bg, db, _owner(db, exam))
    except HTTPException as e:
        log.warning("Autopilot could not verify the questions of exam %s: %s", exam.id, e.detail)
        return
    _note(db, exam, "exam", exam.id, "autopilot_questions_verified", len(qs))
    db.commit()
    _run_background(bg)


# ---------------------------------------------------------------- answer key

class RowChoice(BaseModel):
    id: str
    question: str | None = None


class RowChoices(BaseModel):
    rows: list[RowChoice] = Field(default_factory=list)


def _question_list(qs, width=110):
    return "\n".join(f"Q{q.display_number} [{q.max_marks:g} marks]: "
                     + re.sub(r"\s+", " ", q.question_text or "")[:width] for q in qs if q.max_marks is not None)


@_isolated
def settle_answer_key(exam_id: str) -> None:
    """After the key is read (and the questions verified): map rows the reader could not place, merge rows split
    over one question, write an answer for any question the key has none for, align marks to the paper, and
    verify the key. Sheets already read are graded once it is."""
    db = SessionLocal()
    try:
        exam = db.get(Exam, exam_id)
        if exam is None or exam.status != "ANSWER_KEY_UPLOADED":
            return
        doc = (db.query(AnswerKeyDocument).filter_by(exam_id=exam.id, is_active=True)
               .order_by(AnswerKeyDocument.uploaded_at.desc()).first())
        if doc is None or doc.status not in ("READY", "NEEDS_ATTENTION"):
            return
        with keyed_lock(f"exam:{exam.id}"):
            verified = _settle_answer_key(db, exam, doc)
    finally:
        db.close()
    if verified:
        grade_waiting_sheets(exam_id)


def _settle_answer_key(db, exam, doc) -> bool:
    from ..routes.answer_keys import verify_keys
    from .mapping_service import exam_questions, refresh_key_state
    qs = exam_questions(db, exam.id)
    by_number = {q.normalized_number: q for q in qs}
    keys = db.query(AnswerKey).filter_by(exam_id=exam.id, is_active=True).all()

    # 1. rows the reader could not place: one small-model call for all of them
    loose = [k for k in keys if k.mapping_status != "MAPPED" or not k.exam_question_id]
    if loose:
        prompt = ("Each answer-key row below belongs to one question of the paper. Match each row to its question "
                  "number, using the row's printed label first and its content second. A row that is not an answer "
                  "(an instruction, a heading) gets null.\n\nQUESTIONS\n" + _question_list(qs) + "\n\nROWS\n"
                  + "\n".join(f"id={k.id} label={k.raw_question_number or '-'}: "
                              + re.sub(r"\s+", " ", k.answer_text or "")[:300] for k in loose)
                  + '\n\nReply: {"rows": [{"id": "...", "question": "12"}]}')
        try:
            picks = {r.id: r.question for r in chat_structured(REVIEW_SYSTEM, prompt, RowChoices,
                                                               model=get_settings().small_model).parsed.rows}
        except AIResponseError:
            picks = {}
        for k in loose:
            number = re.sub(r"^\s*Q\.?\s*", "", str(picks.get(k.id) or ""), flags=re.I).strip()
            q = by_number.get(number)
            if q is None:
                k.is_active = False
                k.mapping_note = "Not an answer to any question (AI review)."
                continue
            k.exam_question_id, k.normalized_number = q.id, q.normalized_number
            k.mapping_status, k.mapping_note, k.mapping_candidates = "MAPPED", "Mapped by AI review.", []

    # 2. one row per question: rows split over a question are joined into the first
    keys = [k for k in keys if k.is_active]
    seen: dict[str, AnswerKey] = {}
    for k in sorted(keys, key=lambda k: (k.page_number or 0, k.created_at)):
        if not k.exam_question_id:
            continue
        first = seen.get(k.exam_question_id)
        if first is None:
            seen[k.exam_question_id] = k
            continue
        first.answer_text = f"{first.answer_text}\n{k.answer_text}".strip()
        first.criteria = list(first.criteria or []) + [c for c in k.criteria or [] if c not in (first.criteria or [])]
        k.is_active = False
        k.mapping_note = "Joined into the first row for this question (AI review)."

    # 3. questions the key has no answer for: the medium model writes one
    missing = [q for q in qs if q.id not in seen or not (seen[q.id].answer_text or "").strip()]
    if missing:
        from ..ocr import prompts
        from ..ocr.schemas import GeneratedAnswerKeyResult
        prompt = prompts.generate_answer_key_prompt(exam.name, [
            {"id": q.id, "display_number": q.display_number, "max_marks": q.max_marks,
             "question_type": q.question_type, "question_text": q.question_text} for q in missing])
        try:
            written = chat_structured(WRITER_SYSTEM, prompt, GeneratedAnswerKeyResult).parsed.answers
        except AIResponseError:
            written = []
        by_id = {q.id: q for q in missing}
        for answer in written:
            q = by_id.get(getattr(answer, "exam_question_id", None)) or by_number.get(str(getattr(answer, "question_number", "")))
            if q is None or not (answer.answer_text or "").strip():
                continue
            if q.id in seen:
                seen[q.id].answer_text = answer.answer_text
                continue
            row = AnswerKey(exam_id=exam.id, document_id=doc.id, raw_question_number=q.display_number,
                            normalized_number=q.normalized_number, exam_question_id=q.id,
                            answer_text=answer.answer_text, raw_ocr_text="", marks=q.max_marks,
                            criteria=list(answer.criteria or []), accepted_answers=list(answer.accepted_answers or []),
                            keywords=list(answer.keywords or []), mapping_status="MAPPED",
                            mapping_note="The uploaded key had no answer for this question; written by the AI.")
            db.add(row)
            seen[q.id] = row
        _note(db, exam, "answer_key", doc.id, "autopilot_answers_written", len(written))

    # 4. marks follow the question paper
    qmap = {q.id: q for q in qs}
    for k in seen.values():
        q = qmap.get(k.exam_question_id)
        if q is not None and q.max_marks is not None and k.marks != q.max_marks:
            k.marks = q.max_marks
    db.flush()
    refresh_key_state(db, exam.id)
    for k in db.query(AnswerKey).filter_by(exam_id=exam.id, is_active=True):
        k.mark_mismatch = False  # the paper's marks were adopted above
    if doc.status == "NEEDS_ATTENTION":
        doc.status, doc.stage = "READY", "Ready (some pages could not be read)"
    db.commit()
    try:
        verify_keys(exam.id, db, _owner(db, exam))
    except HTTPException as e:
        log.warning("Autopilot could not verify the answer key of exam %s: %s", exam.id, e.detail)
        return False
    _note(db, exam, "exam", exam.id, "autopilot_answer_key_verified")
    db.commit()
    return True


def grade_waiting_sheets(exam_id: str) -> None:
    """Sheets read before the exam was ready for grading are graded now."""
    from .evaluation_service import auto_evaluate_sheet
    db = SessionLocal()
    try:
        ids = [d.id for d in db.query(AnswerSheetDocument).filter_by(exam_id=exam_id, is_active=True, status="READY")
               .filter(AnswerSheetDocument.student_id.isnot(None))]
    finally:
        db.close()
    for doc_id in ids:
        auto_evaluate_sheet(doc_id)


# ---------------------------------------------------------------- answer sheets

def settle_answers(db: Session, ev: Evaluation) -> int:
    """Every answer the mapping rules could not place, settled in one small-model call for the whole sheet: the
    question it answers, or none (rough work, the details box, crossed-out text). Returns how many were settled."""
    if not enabled() or ev.status == "FINALIZED":
        return 0
    from .mapping_service import exam_questions
    answers = db.query(StudentAnswer).filter_by(evaluation_id=ev.id).order_by(StudentAnswer.position).all()
    open_ = [a for a in answers if a.status in ("UNMAPPED", "NEEDS_REVIEW")]
    if not open_:
        return 0
    qs = exam_questions(db, ev.exam_id)
    by_id, by_number = {q.id: q for q in qs}, {q.normalized_number: q for q in qs}

    def placed(a):
        q = by_id.get(a.exam_question_id)
        return f"Q{q.display_number}" if q and a.status not in ("UNMAPPED", "NEEDS_REVIEW") else "?"
    order = " ".join(f"[{a.position}:{placed(a)}]" for a in answers)
    prompt = ("A student's handwritten answers were read from an answer sheet and matched to the questions. The "
              "answers below could not be matched with certainty. For each, give the question it answers. The "
              "number the student wrote is the strongest evidence; then the order of the answers (students mostly "
              "answer in order, and a piece with no number often continues the answer before it); then the content. "
              "Several pieces may answer one question. Give null only for text that answers no question (rough "
              "work, the student details box, a heading).\n\nQUESTIONS\n" + _question_list(qs)
              + f"\n\nORDER OF ALL ANSWERS ON THE SHEET (position:question)\n{order}\n\nANSWERS TO MATCH\n"
              + "\n".join(f"id={a.id} position={a.position} page={a.page_number} written number={a.raw_question_number or '-'}: "
                          + re.sub(r"\s+", " ", a.answer_text or "")[:400] for a in open_)
              + '\n\nReply: {"rows": [{"id": "...", "question": "7"}]}')
    try:
        picks = {r.id: r.question for r in chat_structured(REVIEW_SYSTEM, prompt, RowChoices,
                                                           model=get_settings().small_model).parsed.rows}
    except AIResponseError:
        picks = {}
    settled = 0
    for a in open_:
        number = re.sub(r"^\s*Q\.?\s*", "", str(picks.get(a.id) or ""), flags=re.I).strip()
        q = by_number.get(number)
        if q is None and a.id in picks and picks[a.id] is None:
            a.status, a.mapping_note = "IGNORED", "Not an answer to any question (AI review)."
        elif q is None:
            q = by_id.get((a.mapping_candidates or [None])[0]) or by_id.get(a.exam_question_id)
            if q is None:
                a.status, a.mapping_note = "IGNORED", "Could not be matched to a question (AI review)."
                settled += 1
                continue
        if q is not None:
            a.exam_question_id, a.normalized_number = q.id, q.normalized_number
            a.status, a.mapping_confirmed = "MAPPED", True
            a.mapping_note, a.mapping_candidates = f"Matched to Q{q.display_number} by AI review.", []
        settled += 1
    exam = db.get(Exam, ev.exam_id)
    _note(db, exam, "evaluation", ev.id, "autopilot_answers_mapped", settled)
    db.commit()
    return settled


def settle_roll_mismatch(identity: dict) -> dict:
    """The roll number typed by the uploader and the one read from the sheet differ: the typed one stands (it was
    entered on purpose; handwriting is read with mistakes). Recorded on the sheet."""
    check = dict(identity.get("roll_check") or {})
    check["status"], check["use"], check["settled_by"] = "CONFIRMED", "typed", "autopilot"
    return {**identity, "roll_check": check}


def pick_student(db: Session, exam: Exam, result: dict):
    """A sheet the identity rules held: take the candidate whose roll number matches what was read, when that
    student has no sheet yet. Anything else stays with the school (two sheets for one student is not guessed)."""
    from ..models import Student
    from .student_identity import _roll_key
    roll = (result.get("read") or {}).get("roll_number")
    if not enabled() or not roll:
        return None
    taken = {e.student_id for e in db.query(Evaluation.student_id).filter_by(exam_id=exam.id)}
    for sid in result.get("candidates") or []:
        st = db.get(Student, sid)
        if st and st.id not in taken and _roll_key(st.roll_number) == _roll_key(roll):
            return st
    return None


# ---------------------------------------------------------------- marks

@_isolated
def settle_evaluation(ev_id: str) -> None:
    """After grading: grade again what failed, settle unattempted questions, approve the AI marks and finalize the
    student's result. A teacher can reopen it to change a mark."""
    from .evaluation_service import (approve_clean_items, evaluate_item, finalize, finalize_issues,
                                     refresh_evaluation_status)
    from .mapping_service import exam_questions
    db = SessionLocal()
    try:
        ev = db.get(Evaluation, ev_id)
        if ev is None or ev.status == "FINALIZED" or ev.run_status == "RUNNING":
            return
        exam = db.get(Exam, ev.exam_id)
        if exam.status == "FINALIZED":
            return
        from ..models import AuditLog
        if db.query(AuditLog.id).filter_by(entity_type="evaluation", entity_id=ev.id, action=REOPENED).first():
            return  # a teacher is working on this result
        settle_answers(db, ev)
        qs = {q.id: q for q in exam_questions(db, ev.exam_id)}
        for item in db.query(EvaluationItem).filter_by(evaluation_id=ev.id, status="EVALUATION_ERROR").all():
            if item.exam_question_id in qs:
                evaluate_item(db, ev, qs[item.exam_question_id], item)  # once more; a mark normally comes out now
        for item in db.query(EvaluationItem).filter_by(evaluation_id=ev.id).all():
            if item.status == "EVALUATION_ERROR":  # the grader never gave a readable reply: 0, clearly flagged
                item.status, item.ai_marks, item.final_marks, item.ai_confidence = "EVALUATED", 0.0, 0.0, 0.0
                item.ai_feedback = f"Check this mark: the AI could not grade this answer ({item.error})."
                item.error = None
            elif item.status == "MISSING":
                item.not_attempted_confirmed, item.final_marks = True, item.final_marks or 0.0
            elif item.status == "PENDING" and item.exam_question_id in qs:
                evaluate_item(db, ev, qs[item.exam_question_id], item)
        db.commit()
        refresh_evaluation_status(db, ev)
        approve_clean_items(db, ev)
        db.commit()
        refresh_evaluation_status(db, ev)
        issues = finalize_issues(db, ev)
        if issues:
            log.warning("Autopilot could not finalize evaluation %s: %s", ev.id, issues[:3])
            return
        finalize(db, ev)
        _note(db, exam, "evaluation", ev.id, "autopilot_finalized",
              {"total": ev.total_marks, "max": ev.maximum_marks, "percentage": ev.percentage})
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------- entry points used by the pipeline

def after_document(kind: str, exam_id: str, doc_id: str | None = None) -> None:
    if kind == "question-paper":
        _safely(settle_questions, exam_id)
    elif kind == "answer-key":
        _safely(settle_answer_key, exam_id)
    elif kind == "answer-sheet" and doc_id:
        _safely(grade_uploaded_sheet, doc_id)


@_isolated
def grade_uploaded_sheet(doc_id: str) -> None:
    """A sheet the school uploaded for a named student is graded as soon as it is read (sheets the identity or
    uploader flows handle are graded by those flows, after their own checks)."""
    from .evaluation_service import auto_evaluate_sheet
    from .student_identity import in_flight
    db = SessionLocal()
    try:
        doc = db.get(AnswerSheetDocument, doc_id)
        if doc is None or doc.student_id is None or doc.uploaded_by_code or in_flight(doc_id):
            return
    finally:
        db.close()
    auto_evaluate_sheet(doc_id)


def after_grading(ev_id: str) -> None:
    _safely(settle_evaluation, ev_id)
