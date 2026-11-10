"""Answer-sheet routes: upload (one, photos, bulk), sheets waiting for their student, roll numbers, listing and
deleting. Shared upload helpers live in documents.py."""
from __future__ import annotations
import re
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db
from ..deps import err, get_exam
from ..documents.storage import read_validated_upload
from ..models import (
    AnswerSheetDocument,
    Evaluation,
    EvaluationItem,
    Student,
    StudentAnswer,
    Teacher,
)
from ..security import current_teacher
from ..serializers import EVALUATION_VIEW_LOAD, doc_view, evaluation_view
from ..services.audit import audit
from ..services.job_queue import submit
from ..services.student_identity import assign_student, identify_sheets, run_sheet
from ..services.student_io import split_class_name
from .documents import BUSY, EXT, ROLL_FORMAT, _save


router = APIRouter(prefix="/api")


@router.post("/exams/{exam_id}/answer-sheets", status_code=202)
async def upload_answer_sheet(
    exam_id: str,
    bg: BackgroundTasks,
    file: UploadFile = File(...),
    student_id: str | None = Form(None),
    student_name: str | None = Form(None),
    roll_number: str | None = Form(None),
    db: Session = Depends(get_db),
    t: Teacher = Depends(current_teacher),
):
    exam = get_exam(db, t, exam_id)
    _require_sheet_state(exam)
    roll_number = (roll_number or "").strip() or None
    if t.role == "PARENT":
        child = db.query(Student).filter_by(class_id=exam.class_id).one()
        if student_id and student_id != child.id:
            raise err(404, "NOT_FOUND", "Student not found.")
        student_id = child.id
    if not (student_id or student_name or roll_number):
        docs = await _save_unassigned(db, t, exam, [file])
        for d in docs:
            bg.add_task(submit, exam.id, identify_sheets, [d.id], t.id)
        return _unassigned_view(db, docs[0])
    typed_roll = None
    if student_id:
        st = db.get(Student, student_id)
        if not st or st.class_id != exam.class_id:
            raise err(
                400, "INVALID_STUDENT", "Choose a student from this exam's class."
            )
    elif roll_number and not student_name:
        # only a roll number, as in the uploader app: it decides the student and is checked against the sheet
        typed_roll = roll_number.upper()
        if not ROLL_FORMAT.fullmatch(typed_roll):
            raise err(
                400,
                "INVALID_ROLL",
                "Enter the student's roll number (letters and digits only).",
            )
        st = (
            db.query(Student)
            .filter_by(class_id=exam.class_id, roll_number=typed_roll)
            .first()
        )
        if st is None:
            section = (
                split_class_name(exam.school_class.name)[1]
                if exam.school_class
                else None
            )
            st = Student(
                class_id=exam.class_id,
                name=f"Roll {typed_roll}",
                roll_number=typed_roll,
                section=section,
            )
            db.add(st)
            db.flush()
    else:
        if not student_name or not roll_number:
            raise err(
                400,
                "STUDENT_REQUIRED",
                "Select a student, or enter a name and roll number.",
            )
        st = (
            db.query(Student)
            .filter_by(class_id=exam.class_id, roll_number=roll_number.strip())
            .first()
        )
        if st is None:
            st = Student(
                class_id=exam.class_id,
                name=student_name.strip(),
                roll_number=roll_number.strip(),
            )
            db.add(st)
            db.flush()
    if db.query(Evaluation).filter_by(exam_id=exam.id, student_id=st.id).first():
        raise err(
            409,
            "ANSWER_SHEET_EXISTS",
            f"{st.name} ({st.roll_number}) already has an answer sheet for this exam. Delete it first to upload again.",
        )
    data, ext, mime = await read_validated_upload(file, EXT["answer-sheet"])
    doc = _save(
        db,
        "answer-sheet",
        exam.id,
        data,
        ext,
        mime,
        file.filename or "upload",
        student_id=st.id,
        **({"identity": {"typed_roll": typed_roll}} if typed_roll else {}),
    )
    # the roll number given at upload is checked against the one written on the sheet once it is read
    doc.identity = {**(doc.identity or {}), "typed_roll": st.roll_number}
    db.flush()
    ev = Evaluation(
        exam_id=exam.id, student_id=st.id, answer_sheet_id=doc.id, status="DRAFT"
    )
    db.add(ev)
    db.flush()
    audit(
        db,
        exam_id=exam.id,
        teacher_id=t.id,
        entity_type="answer_sheet",
        entity_id=doc.id,
        action="answer_sheet_uploaded",
        new={"student": st.name, "roll": st.roll_number},
    )
    db.commit()
    bg.add_task(submit, exam.id, run_sheet, doc.id)  # read, check the roll number, then grade
    db.refresh(ev)
    return {**evaluation_view(ev), "document": doc_view(doc, "answer-sheet")}


@router.post("/exams/{exam_id}/answer-sheets/photos", status_code=202)
async def upload_answer_sheet_photos(
    exam_id: str,
    bg: BackgroundTasks,
    files: list[UploadFile] = File(...),
    roll_number: str | None = Form(None),
    db: Session = Depends(get_db),
    t: Teacher = Depends(current_teacher),
):
    """Photos of one student's sheet, one per page in order, become one answer sheet."""
    from .uploader import _pages_to_pdf

    _require_sheet_state(get_exam(db, t, exam_id))
    sheet = await _pages_to_pdf(files)
    return await upload_answer_sheet(
        exam_id, bg, sheet, None, None, roll_number, db, t
    )


SHEET_STATES = (
    "ANSWER_KEY_VERIFIED",
    "READY_FOR_EVALUATION",
    "EVALUATING",
    "REVIEW_REQUIRED",
)
MAX_BULK_FILES = 200


def _require_sheet_state(exam) -> None:
    if exam.status not in SHEET_STATES:
        raise err(
            409,
            "ANSWER_KEY_NOT_VERIFIED",
            "Verify the answer key before uploading student answer sheets."
            if exam.status != "FINALIZED"
            else "This exam is finalized.",
        )


BULK_EXT = {"pdf", "docx"}  # bulk upload is one file per student; photos of one student's pages go through /photos


async def _save_unassigned(
    db: Session, t: Teacher, exam, files: list[UploadFile], allowed: set[str] | None = None
) -> list:
    _require_sheet_state(exam)
    if not files:
        raise err(400, "NO_FILES", "Choose at least one answer sheet.")
    if len(files) > MAX_BULK_FILES:
        raise err(
            400,
            "TOO_MANY_FILES",
            f"Upload at most {MAX_BULK_FILES} answer sheets at a time.",
        )
    validated = []
    for f in files:  # validate every file first, so one bad file rejects the batch before anything is stored
        try:
            validated.append(
                (
                    f.filename or "upload",
                    *await read_validated_upload(f, allowed or EXT["answer-sheet"]),
                )
            )
        except HTTPException as e:
            msg = e.detail.get("message") if isinstance(e.detail, dict) else e.detail
            raise err(400, "INVALID_FILE", f"{f.filename}: {msg}")
    docs = []
    for name, data, ext, mime in validated:
        doc = _save(db, "answer-sheet", exam.id, data, ext, mime, name)
        doc.stage = "Waiting to read student details"
        docs.append(doc)
    db.flush()
    audit(
        db,
        exam_id=exam.id,
        teacher_id=t.id,
        entity_type="exam",
        entity_id=exam.id,
        action="answer_sheets_bulk_uploaded",
        new=[d.original_filename for d in docs],
    )
    db.commit()
    return docs


def _unassigned_view(db: Session, doc) -> dict:
    ident = doc.identity or {}
    cands = [db.get(Student, sid) for sid in ident.get("candidates") or []]
    return {
        **doc_view(doc, "answer-sheet"),
        "identity": ident,
        "candidates": [
            {
                "id": s.id,
                "name": s.name,
                "roll_number": s.roll_number,
                "registration_number": s.registration_number,
                "section": s.section,
            }
            for s in cands
            if s
        ],
    }


@router.post("/exams/{exam_id}/answer-sheets/bulk", status_code=202)
async def upload_answer_sheets_bulk(
    exam_id: str,
    bg: BackgroundTasks,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    t: Teacher = Depends(current_teacher),
):
    """Many sheets at once. Each is matched to its student from the details written on it, then read as usual."""
    exam = get_exam(db, t, exam_id)
    if t.role == "PARENT":
        if len(files) != 1:
            raise err(
                400,
                "ONE_CHILD_ONLY",
                "Upload one answer sheet for your child per exam.",
            )
        result = await upload_answer_sheet(
            exam_id, bg, files[0], None, None, None, db, t
        )
        return {"uploaded": 1, "documents": [result["document"]]}
    docs = await _save_unassigned(db, t, exam, files, BULK_EXT)
    for d in docs:  # one job per sheet, so sheets are identified and read in parallel
        bg.add_task(submit, exam.id, identify_sheets, [d.id], t.id)
    return {"uploaded": len(docs), "documents": [_unassigned_view(db, d) for d in docs]}


@router.get("/exams/{exam_id}/answer-sheets/unassigned")
def list_unassigned_sheets(
    exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)
):
    """Sheets not yet linked to a student: being identified, held for the teacher, or unreadable."""
    exam = get_exam(db, t, exam_id)
    docs = (
        db.query(AnswerSheetDocument)
        .filter_by(exam_id=exam.id, is_active=True, student_id=None)
        .filter(AnswerSheetDocument.status != "CAPTURING")  # an uploader is still photographing its pages
        .order_by(AnswerSheetDocument.uploaded_at)
        .all()
    )
    # fetch every candidate in one query; held in a variable so the per-sheet lookups below find them in the session
    ids = {sid for d in docs for sid in (d.identity or {}).get("candidates") or []}
    candidates = db.query(Student).filter(Student.id.in_(ids or [""])).all()  # noqa: F841
    return [_unassigned_view(db, d) for d in docs]


def _unassigned_doc(db: Session, t: Teacher, doc_id: str):
    doc = db.get(AnswerSheetDocument, doc_id)
    if doc is None or not doc.is_active:
        raise err(404, "NOT_FOUND", "Answer sheet not found.")
    exam = get_exam(db, t, doc.exam_id)
    if doc.student_id is not None:
        raise err(
            409, "ALREADY_ASSIGNED", "This answer sheet is already linked to a student."
        )
    return doc, exam


class AssignBody(BaseModel):
    student_id: str


@router.post("/answer-sheets/{doc_id}/assign")
def assign_sheet_student(
    doc_id: str,
    body: AssignBody,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    t: Teacher = Depends(current_teacher),
):
    doc, exam = _unassigned_doc(db, t, doc_id)
    _require_sheet_state(exam)
    if doc.status in BUSY:
        raise err(
            409,
            "PROCESSING_IN_PROGRESS",
            "The student details are still being read. Wait a moment.",
        )
    if not doc.pages:
        raise err(
            409,
            "SHEET_UNREADABLE",
            "This file could not be opened. Delete it and upload it again.",
        )
    st = db.get(Student, body.student_id)
    if not st or st.class_id != exam.class_id:
        raise err(400, "INVALID_STUDENT", "Choose a student from this exam's class.")
    if db.query(Evaluation).filter_by(exam_id=exam.id, student_id=st.id).first():
        raise err(
            409,
            "ANSWER_SHEET_EXISTS",
            f"{st.name} ({st.roll_number}) already has an answer sheet for this exam. Delete it first to assign this one.",
        )
    ev = assign_student(db, doc, st, t.id, "Picked by teacher")
    db.commit()
    bg.add_task(submit, exam.id, run_sheet, doc.id)
    db.refresh(ev)
    return {**evaluation_view(ev), "document": doc_view(doc, "answer-sheet")}


@router.post("/answer-sheets/{doc_id}/identify", status_code=202)
def retry_identify(
    doc_id: str,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    t: Teacher = Depends(current_teacher),
):
    doc, exam = _unassigned_doc(db, t, doc_id)
    _require_sheet_state(exam)
    if doc.status in BUSY:
        raise err(
            409,
            "PROCESSING_IN_PROGRESS",
            "This answer sheet is already being processed.",
        )
    doc.status, doc.stage, doc.error_message = (
        "UPLOADED",
        "Waiting to read student details",
        None,
    )
    db.commit()
    bg.add_task(submit, exam.id, identify_sheets, [doc.id], t.id)
    return _unassigned_view(db, doc)


ROLL_RE = re.compile(r"^[A-Z0-9/-]{1,20}$")  # same rule as the uploader app


def _move_sheet_to_roll(db: Session, exam, doc: AnswerSheetDocument, roll: str) -> None:
    """Link the sheet (and its evaluation) to the student with this roll number, adding the roll if it is new."""
    from ..services.student_io import split_class_name

    ev = db.query(Evaluation).filter_by(answer_sheet_id=doc.id).first()
    student = db.query(Student).filter_by(class_id=exam.class_id, roll_number=roll).first()
    if student is None:
        section = split_class_name(exam.school_class.name)[1] if exam.school_class else None
        student = Student(class_id=exam.class_id, roll_number=roll, section=section, name=f"Roll {roll}")
        db.add(student)
        db.flush()
    other = db.query(Evaluation).filter_by(exam_id=exam.id, student_id=student.id).first()
    if other is not None and other.id != (ev.id if ev else None):
        raise err(409, "ANSWER_SHEET_EXISTS", f"Roll number {roll} already has an answer sheet in this exam.")
    doc.student_id = student.id
    if ev is not None:
        ev.student_id = student.id


class RollNumberBody(BaseModel):
    roll_number: str


@router.post("/answer-sheets/{doc_id}/roll-number")
def edit_roll_number(doc_id: str, body: RollNumberBody, bg: BackgroundTasks,
                     db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    """The school types the right roll number for a sheet (the typed or the read one was wrong).

    Works on any linked sheet. A sheet held on a roll number mismatch counts as settled and goes for grading."""
    from ..services.evaluation_service import auto_evaluate_sheet

    doc = db.get(AnswerSheetDocument, doc_id)
    if doc is None or not doc.is_active or doc.student_id is None:
        raise err(404, "NOT_FOUND", "Answer sheet not found.")
    exam = get_exam(db, t, doc.exam_id)
    roll = re.sub(r"\s+", "", body.roll_number or "").upper()
    if not ROLL_RE.match(roll):
        raise err(400, "INVALID_ROLL_NUMBER", "Enter a roll number (letters, digits, / or -, up to 20).")
    old = db.get(Student, doc.student_id).roll_number
    _move_sheet_to_roll(db, exam, doc, roll)
    identity = dict(doc.identity or {})
    check = dict(identity.get("roll_check") or {})
    was_held = check.get("status") == "MISMATCH"
    if check:
        check["status"], check["chosen"], check["edited"] = "CONFIRMED", "edited", roll
        identity["roll_check"] = check
        doc.identity = identity
    if was_held:
        doc.stage = "Ready for review" if doc.status == "READY" else doc.stage
    audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="answer_sheet", entity_id=doc.id,
          action="roll_number_edited", old={"roll_number": old}, new={"roll_number": roll})
    db.commit()
    if was_held:
        bg.add_task(submit, exam.id, auto_evaluate_sheet, doc.id)
    return {"roll_number": roll}


class RollCheckBody(BaseModel):
    use: str  # "typed": the uploader's roll number is right; "written": the roll number on the sheet is right


@router.post("/answer-sheets/{doc_id}/roll-check", status_code=202)
def settle_roll_check(doc_id: str, body: RollCheckBody, bg: BackgroundTasks,
                      db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    """The typed and the written roll number differ: the school says which is right, then the sheet is graded."""
    from ..services.evaluation_service import auto_evaluate_sheet

    doc = db.get(AnswerSheetDocument, doc_id)
    if doc is None or not doc.is_active:
        raise err(404, "NOT_FOUND", "Answer sheet not found.")
    exam = get_exam(db, t, doc.exam_id)
    identity = dict(doc.identity or {})
    check = dict(identity.get("roll_check") or {})
    if check.get("status") != "MISMATCH":
        raise err(409, "NO_ROLL_MISMATCH", "This sheet has no roll number to check.")
    if body.use not in ("typed", "written"):
        raise err(400, "INVALID_CHOICE", "Choose the typed or the written roll number.")
    if body.use == "written":
        _move_sheet_to_roll(db, exam, doc, check["written"])
    check["status"], check["chosen"] = "CONFIRMED", body.use
    identity["roll_check"] = check
    doc.identity = identity
    doc.stage = "Ready for review" if doc.status == "READY" else doc.stage
    audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="answer_sheet", entity_id=doc.id,
          action="roll_number_settled", new={"use": body.use, "typed": check.get("typed"), "written": check.get("written")})
    db.commit()
    bg.add_task(submit, exam.id, auto_evaluate_sheet, doc.id)
    return {"roll_number": check["written"] if body.use == "written" else check["typed"]}


@router.delete("/answer-sheets/{doc_id}")
def delete_unassigned_sheet(
    doc_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)
):
    doc, exam = _unassigned_doc(db, t, doc_id)
    if doc.status == "IDENTIFYING":
        raise err(
            409,
            "PROCESSING_IN_PROGRESS",
            "Wait for the student details to be read before deleting.",
        )
    doc.is_active = False  # original file stays on disk
    audit(
        db,
        exam_id=exam.id,
        teacher_id=t.id,
        entity_type="answer_sheet",
        entity_id=doc.id,
        action="unassigned_answer_sheet_deleted",
        old=doc.original_filename,
    )
    db.commit()
    return {"ok": True}


@router.get("/exams/{exam_id}/answer-sheets")
def list_answer_sheets(
    exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)
):
    exam = get_exam(db, t, exam_id)
    evs = (
        db.query(Evaluation)
        .options(*EVALUATION_VIEW_LOAD)
        .filter_by(exam_id=exam.id)
        .order_by(Evaluation.created_at)
        .all()
    )
    # the database is remote: load each kind of row once for the whole list instead of once per sheet
    docs = {
        d.id: d
        for d in db.query(AnswerSheetDocument).filter(
            AnswerSheetDocument.id.in_([ev.answer_sheet_id for ev in evs] or [""])
        )
    }
    counts: dict[str, list[int]] = {ev.id: [0, 0] for ev in evs}
    for ev_id, status in db.query(
        StudentAnswer.evaluation_id, StudentAnswer.status
    ).filter(StudentAnswer.evaluation_id.in_(list(counts) or [""])):
        counts[ev_id][0] += 1
        counts[ev_id][1] += status in ("UNMAPPED", "NEEDS_REVIEW")
    return [
        {
            **evaluation_view(ev),
            "document": doc_view(docs[ev.answer_sheet_id], "answer-sheet"),
            "detected_answers": counts[ev.id][0],
            "unresolved_answers": counts[ev.id][1],
        }
        for ev in evs
    ]


@router.delete("/evaluations/{ev_id}")
def delete_answer_sheet(
    ev_id: str,
    confirm_finalized: bool = False,
    db: Session = Depends(get_db),
    t: Teacher = Depends(current_teacher),
):
    """Remove a student's answer sheet with its answers and marks. A finalized one only when the teacher confirms
    it (confirm_finalized): its locked marks leave the results and reports."""
    from ..deps import get_evaluation

    ev = get_evaluation(db, t, ev_id)
    if ev.status == "FINALIZED" and not confirm_finalized:
        raise err(
            409,
            "EVALUATION_FINALIZED",
            "This evaluation is finalized. Confirm to delete it and remove its marks from the results.",
        )
    if ev.run_status == "RUNNING" or (
        db.query(AnswerSheetDocument)
        .filter(AnswerSheetDocument.id == ev.answer_sheet_id,
                AnswerSheetDocument.status.in_(("RENDERING", "OCR_PROCESSING", "EXTRACTING", "IDENTIFYING")))
        .first()
    ):
        raise err(
            409,
            "PROCESSING_IN_PROGRESS",
            "Wait for processing to finish before deleting.",
        )
    audit(
        db,
        exam_id=ev.exam_id,
        teacher_id=t.id,
        entity_type="evaluation",
        entity_id=ev.id,
        action="answer_sheet_deleted",
        old={"student": ev.student.name, "status": ev.status, "total_marks": ev.total_marks},
    )
    db.query(EvaluationItem).filter_by(evaluation_id=ev.id).delete()
    db.query(StudentAnswer).filter_by(evaluation_id=ev.id).delete()
    doc = db.get(AnswerSheetDocument, ev.answer_sheet_id)
    db.delete(ev)
    if doc:
        doc.is_active = False  # original file stays on disk
    db.commit()
    return {"ok": True}
