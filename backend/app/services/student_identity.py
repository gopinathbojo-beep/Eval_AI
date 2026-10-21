"""Identify which student an uploaded answer sheet belongs to, from the details written in its header.

Matching is strict: a registration number or roll number must point at exactly one student of the exam's class,
and the other details read must not contradict it. A name alone never assigns a sheet (many students share names).
Anything uncertain is held for the teacher (status NEEDS_STUDENT) with the details read and likely candidates.
"""
from __future__ import annotations
import logging
import re
import threading
from difflib import SequenceMatcher
from PIL import Image
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..documents.renderer import RenderError, render_document
from ..documents.storage import abs_path
from ..models import AnswerSheetDocument, Evaluation, Exam, Student
from ..ocr import prompts
from ..ocr.internvl import AIResponseError, AIUnavailable, chat_structured, check_model
from ..ocr.schemas import StudentIdentityResult
from .audit import audit
from .pipeline import process_document

log = logging.getLogger("adem.identity")

# One sheet at a time: identification and OCR share the single local model, and a bulk upload of 40 sheets
# must not start 40 model calls at once.
_SHEETS_LOCK = threading.Lock()
HEADER_FRACTION = 0.4
MIN_NAME_SIMILARITY = 0.5


def norm_id(v: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (v or "").upper())


def _roll_key(v: str | None) -> str:
    n = norm_id(v)
    return n.lstrip("0") or n


def name_similarity(a: str | None, b: str | None) -> float:
    ta = sorted(re.findall(r"[a-z]+", (a or "").lower()))
    tb = sorted(re.findall(r"[a-z]+", (b or "").lower()))
    if not ta or not tb:
        return 0.0
    return max(SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio(),
               SequenceMatcher(None, "".join(ta), "".join(tb)).ratio())


def _hold(note: str, read: dict, candidates: list[Student]) -> dict:
    ids = list(dict.fromkeys(s.id for s in candidates))
    return {"match": "HOLD", "student_id": None, "note": note, "read": read, "candidates": ids[:5]}


def match_student(db: Session, exam: Exam, read: dict) -> dict:
    """read: {name, roll_number, registration_number, class_name, section} -> {match, student_id, note, read, candidates}."""
    students = db.query(Student).filter_by(class_id=exam.class_id).all()
    taken = {e.student_id for e in db.query(Evaluation.student_id).filter_by(exam_id=exam.id)}
    reg, roll, name, section = read.get("registration_number"), read.get("roll_number"), read.get("name"), read.get("section")

    def score(s: Student) -> float:  # ranks candidates shown to the teacher when a sheet is held
        sc = name_similarity(name, s.name)
        if reg and s.registration_number and norm_id(reg) in norm_id(s.registration_number):
            sc += 1
        if roll and _roll_key(roll) == _roll_key(s.roll_number):
            sc += 1
        return sc
    ranked = sorted(students, key=score, reverse=True)

    by_reg = [s for s in students if reg and s.registration_number and norm_id(s.registration_number) == norm_id(reg)]
    by_roll = [s for s in students if roll and _roll_key(s.roll_number) == _roll_key(roll)]

    if not (reg or roll):
        return _hold("No roll number or registration number could be read from the sheet.", read, ranked)

    if len(by_reg) == 1:
        st = by_reg[0]
        if by_roll and st not in by_roll:
            return _hold(f"Registration number matches {st.name} ({st.roll_number}) but roll number {roll} "
                         f"belongs to {by_roll[0].name}.", read, [st, by_roll[0], *ranked])
        how = "registration number" + (" and roll number" if by_roll else "")
    elif len(by_roll) == 1:
        st = by_roll[0]
        if reg and st.registration_number:
            return _hold(f"Roll number {roll} is {st.name}, but registration number {reg} does not match "
                         f"theirs ({st.registration_number}).", read, [st, *ranked])
        if name and name_similarity(name, st.name) < MIN_NAME_SIMILARITY:
            return _hold(f"Roll number {roll} is {st.name}, but the name on the sheet reads '{name}'.", read, [st, *ranked])
        how = "roll number"
    else:
        what = " / ".join(x for x in (f"reg. no. {reg}" if reg else "", f"roll no. {roll}" if roll else "") if x)
        return _hold(f"No student in this class matches {what}.", read, ranked)

    if section and st.section and norm_id(section) != norm_id(st.section):
        return _hold(f"Matched {st.name} by {how}, but the sheet says section {section} and the record says "
                     f"{st.section}.", read, [st, *ranked])
    if st.id in taken:
        return _hold(f"Matched {st.name} ({st.roll_number}) by {how}, but they already have an answer sheet "
                     f"in this exam.", read, [st, *ranked])
    return {"match": "AUTO", "student_id": st.id, "note": f"Matched by {how}.", "read": read, "candidates": []}


def _read_header(doc: AnswerSheetDocument) -> dict:
    page1 = abs_path(doc.pages[0]["processed_file"])
    crop = page1.parent / f"identity-{page1.name}"
    with Image.open(page1) as img:
        img.crop((0, 0, img.width, max(1, int(img.height * HEADER_FRACTION)))).save(crop)
    try:
        res = chat_structured(prompts.IDENTITY_SYSTEM, prompts.student_identity_prompt(), StudentIdentityResult, crop)
        read = res.parsed.model_dump()
        if not (read["roll_number"] or read["registration_number"]):  # details may sit lower on the page
            res = chat_structured(prompts.IDENTITY_SYSTEM, prompts.student_identity_prompt(), StudentIdentityResult, page1)
            read = {k: read.get(k) or v for k, v in res.parsed.model_dump().items()}
        return read
    finally:
        crop.unlink(missing_ok=True)


def assign_student(db: Session, doc: AnswerSheetDocument, student: Student, teacher_id: str | None, how: str) -> Evaluation:
    """Link a sheet to its student and open the evaluation; the caller then queues OCR with run_sheet()."""
    doc.student_id = student.id
    doc.status, doc.stage, doc.error_message = "UPLOADED", "Queued", None
    ev = Evaluation(exam_id=doc.exam_id, student_id=student.id, answer_sheet_id=doc.id, status="DRAFT")
    db.add(ev)
    db.flush()
    audit(db, exam_id=doc.exam_id, teacher_id=teacher_id, entity_type="answer_sheet", entity_id=doc.id,
          action="answer_sheet_student_assigned", new={"student": student.name, "roll": student.roll_number, "how": how})
    return ev


def run_sheet(doc_id: str) -> None:
    """OCR an already-assigned sheet with the regular pipeline, one sheet at a time."""
    with _SHEETS_LOCK:
        process_document("answer-sheet", doc_id, True)


def identify_sheets(doc_ids: list[str], teacher_id: str | None) -> None:
    for doc_id in doc_ids:
        with _SHEETS_LOCK:
            try:
                assigned = _identify(doc_id, teacher_id)
            except Exception:
                log.exception("Identification crashed for sheet %s", doc_id)
                _set_hold(doc_id, "Reading the student details failed unexpectedly. Pick the student or retry.")
                assigned = False
            if assigned:
                # pages are already rendered, so the pipeline only has to read them
                process_document("answer-sheet", doc_id, True)


def _set_hold(doc_id: str, note: str, read: dict | None = None, candidates: list[str] | None = None) -> None:
    db = SessionLocal()
    try:
        doc = db.get(AnswerSheetDocument, doc_id)
        if doc and doc.student_id is None:
            doc.status, doc.stage = "NEEDS_STUDENT", "Pick the student"
            doc.identity = {"match": "HOLD", "student_id": None, "note": note, "read": read or (doc.identity or {}).get("read") or {},
                            "candidates": candidates or []}
            db.commit()
    finally:
        db.close()


def _identify(doc_id: str, teacher_id: str | None) -> bool:
    db = SessionLocal()
    try:
        doc = db.get(AnswerSheetDocument, doc_id)
        if doc is None or not doc.is_active or doc.student_id is not None:
            return False
        exam = db.get(Exam, doc.exam_id)
        doc.status, doc.stage, doc.error_message = "IDENTIFYING", "Reading student details", None
        db.commit()
        if not doc.pages:
            try:
                original = abs_path(doc.original_file)
                doc.pages = render_document(original, original.suffix.lstrip(".").lower(), original.parent)
            except RenderError as e:
                doc.status, doc.stage, doc.error_message = "FAILED", "Could not open file", str(e)
                db.commit()
                return False
            db.commit()
        try:
            check_model()
            read = _read_header(doc)
        except AIUnavailable:
            db.rollback()
            _set_hold(doc_id, "The AI model is not available, so the student details could not be read. "
                              "Pick the student or retry once the model is running.")
            return False
        except AIResponseError:
            db.rollback()
            _set_hold(doc_id, "The student details on this sheet could not be read. Pick the student or retry.")
            return False
        result = match_student(db, exam, read)
        doc.identity = result
        if result["match"] != "AUTO":
            doc.status, doc.stage = "NEEDS_STUDENT", "Pick the student"
            db.commit()
            return False
        assign_student(db, doc, db.get(Student, result["student_id"]), teacher_id, result["note"])
        db.commit()
        return True
    finally:
        db.close()
