from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import shutil
from ..config import AI_UNAVAILABLE_MESSAGE, get_settings
from ..database import get_db
from ..deps import err, get_exam
from ..models import (AnswerKey, AnswerKeyDocument, AnswerSheetDocument, AuditLog, Evaluation,
                      EvaluationItem, Exam, ExamQuestion, QuestionPaperDocument, SchoolClass,
                      Student, StudentAnswer, Subject, Teacher)
from ..ocr.internvl import AIUnavailable, check_model
from ..security import create_token, current_teacher, verify_password
from ..serializers import doc_view, evaluation_view, student_view
from ..services.audit import audit

router = APIRouter(prefix="/api")


# ---------- auth ----------
class LoginIn(BaseModel):
    email: str
    password: str


def teacher_view(t: Teacher) -> dict:
    return {"id": t.id, "name": t.name, "email": t.email}


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    t = db.query(Teacher).filter_by(email=body.email.strip().lower()).first()
    if not t or not verify_password(body.password, t.password_hash):
        raise err(401, "INVALID_CREDENTIALS", "Email or password is incorrect.")
    return {"access_token": create_token(t.id), "token_type": "bearer", "teacher": teacher_view(t)}


@router.get("/auth/me")
def me(t: Teacher = Depends(current_teacher)):
    return teacher_view(t)


# ---------- system ----------
@router.get("/system/ai-status")
def ai_status(_: Teacher = Depends(current_teacher)):
    s = get_settings()
    try:
        info = check_model()
        return {**info, "message": "InternVL3.5 4B is ready."}
    except AIUnavailable as e:
        return {"available": False, "model": s.internvl_model, "url": s.internvl_api_url,
                "message": AI_UNAVAILABLE_MESSAGE, "detail": e.detail}


# ---------- dashboard ----------
@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    exam_ids = [e.id for e in db.query(Exam.id).filter_by(teacher_id=t.id)]
    class_ids = [c.id for c in db.query(SchoolClass.id).filter_by(teacher_id=t.id)]
    evs = db.query(Evaluation).filter(Evaluation.exam_id.in_(exam_ids)).all() if exam_ids else []
    recent_exams = db.query(Exam).filter_by(teacher_id=t.id).order_by(Exam.created_at.desc()).limit(5).all()
    recent_evs = sorted(evs, key=lambda e: e.created_at, reverse=True)[:5]
    return {
        "total_classes": len(class_ids),
        "total_subjects": db.query(Subject).filter_by(teacher_id=t.id).count(),
        "total_exams": len(exam_ids),
        "total_students": db.query(Student).filter(Student.class_id.in_(class_ids)).count() if class_ids else 0,
        "pending_evaluations": sum(e.status != "FINALIZED" for e in evs),
        "completed_evaluations": sum(e.status == "FINALIZED" for e in evs),
        "recent_exams": [exam_view(e) for e in recent_exams],
        "recent_evaluations": [evaluation_view(e) for e in recent_evs],
    }


# ---------- cascade delete helpers ----------
def cascade_delete_exam_records(db: Session, exam_id: str):
    """Safely cascades deletion of all dependent records and files for an exam."""
    evals = db.query(Evaluation).filter_by(exam_id=exam_id).all()
    eval_ids = [ev.id for ev in evals]
    if eval_ids:
        db.query(EvaluationItem).filter(EvaluationItem.evaluation_id.in_(eval_ids)).delete(synchronize_session=False)
        db.query(StudentAnswer).filter(StudentAnswer.evaluation_id.in_(eval_ids)).delete(synchronize_session=False)
        db.query(Evaluation).filter_by(exam_id=exam_id).delete(synchronize_session=False)

    db.query(AnswerKey).filter_by(exam_id=exam_id).delete(synchronize_session=False)
    db.query(AnswerSheetDocument).filter_by(exam_id=exam_id).delete(synchronize_session=False)
    db.query(AnswerKeyDocument).filter_by(exam_id=exam_id).delete(synchronize_session=False)
    db.query(QuestionPaperDocument).filter_by(exam_id=exam_id).delete(synchronize_session=False)
    db.query(ExamQuestion).filter_by(exam_id=exam_id).delete(synchronize_session=False)
    db.query(AuditLog).filter_by(exam_id=exam_id).delete(synchronize_session=False)
    db.query(Exam).filter_by(id=exam_id).delete(synchronize_session=False)

    try:
        exam_dir = get_settings().data_path / "exams" / exam_id
        if exam_dir.exists():
            shutil.rmtree(exam_dir, ignore_errors=True)
    except Exception:
        pass


def cascade_delete_student_records(db: Session, student_id: str):
    """Safely cascades deletion of evaluations and answer sheets for a student."""
    evals = db.query(Evaluation).filter_by(student_id=student_id).all()
    eval_ids = [ev.id for ev in evals]
    if eval_ids:
        db.query(EvaluationItem).filter(EvaluationItem.evaluation_id.in_(eval_ids)).delete(synchronize_session=False)
        db.query(StudentAnswer).filter(StudentAnswer.evaluation_id.in_(eval_ids)).delete(synchronize_session=False)
        db.query(Evaluation).filter_by(student_id=student_id).delete(synchronize_session=False)
    db.query(AnswerSheetDocument).filter_by(student_id=student_id).delete(synchronize_session=False)
    db.query(Student).filter_by(id=student_id).delete(synchronize_session=False)


# ---------- classes / subjects / students ----------
class NameIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: str | None = None


@router.get("/classes")
def list_classes(db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    return [{"id": c.id, "name": c.name,
             "student_count": db.query(Student).filter_by(class_id=c.id).count()}
            for c in db.query(SchoolClass).filter_by(teacher_id=t.id).order_by(SchoolClass.name)]


@router.post("/classes", status_code=201)
def create_class(body: NameIn, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    c = SchoolClass(teacher_id=t.id, name=body.name.strip())
    db.add(c)
    db.commit()
    return {"id": c.id, "name": c.name, "student_count": 0}


@router.patch("/classes/{class_id}")
def update_class(class_id: str, body: NameIn, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    c = db.get(SchoolClass, class_id)
    if not c or c.teacher_id != t.id:
        raise err(404, "NOT_FOUND", "Class not found.")
    c.name = body.name.strip()
    db.commit()
    return {"id": c.id, "name": c.name, "student_count": db.query(Student).filter_by(class_id=c.id).count()}


@router.delete("/classes/{class_id}")
def delete_class(class_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    c = db.get(SchoolClass, class_id)
    if not c or c.teacher_id != t.id:
        raise err(404, "NOT_FOUND", "Class not found.")

    # 1. Cascade delete all exams assigned to this class
    exams = db.query(Exam).filter_by(class_id=c.id).all()
    for ex in exams:
        cascade_delete_exam_records(db, ex.id)

    # 2. Cascade delete all students enrolled in this class
    students = db.query(Student).filter_by(class_id=c.id).all()
    for st in students:
        cascade_delete_student_records(db, st.id)

    # 3. Delete the class itself
    db.delete(c)
    db.commit()
    return {"deleted": True, "id": class_id}


@router.get("/subjects")
def list_subjects(db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    return [{"id": s.id, "name": s.name, "code": s.code}
            for s in db.query(Subject).filter_by(teacher_id=t.id).order_by(Subject.name)]


@router.post("/subjects", status_code=201)
def create_subject(body: NameIn, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    s = Subject(teacher_id=t.id, name=body.name.strip(), code=body.code)
    db.add(s)
    db.commit()
    return {"id": s.id, "name": s.name, "code": s.code}


@router.patch("/subjects/{subject_id}")
def update_subject(subject_id: str, body: NameIn, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    s = db.get(Subject, subject_id)
    if not s or s.teacher_id != t.id:
        raise err(404, "NOT_FOUND", "Subject not found.")
    s.name = body.name.strip()
    if body.code is not None:
        s.code = body.code
    db.commit()
    return {"id": s.id, "name": s.name, "code": s.code}


@router.delete("/subjects/{subject_id}")
def delete_subject(subject_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    s = db.get(Subject, subject_id)
    if not s or s.teacher_id != t.id:
        raise err(404, "NOT_FOUND", "Subject not found.")

    # Cascade delete all exams assigned to this subject
    exams = db.query(Exam).filter_by(subject_id=s.id).all()
    for ex in exams:
        cascade_delete_exam_records(db, ex.id)

    db.delete(s)
    db.commit()
    return {"deleted": True, "id": subject_id}


class StudentIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    roll_number: str = Field(min_length=1, max_length=50)
    class_id: str


class StudentPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    roll_number: str | None = Field(None, min_length=1, max_length=50)
    class_id: str | None = None


@router.get("/students")
def list_students(class_id: str | None = Query(None), db: Session = Depends(get_db),
                  t: Teacher = Depends(current_teacher)):
    class_ids = [c.id for c in db.query(SchoolClass.id).filter_by(teacher_id=t.id)]
    q = db.query(Student).filter(Student.class_id.in_(class_ids or [""]))
    if class_id:
        q = q.filter(Student.class_id == class_id)
    return [student_view(s) for s in q.order_by(Student.roll_number)]


@router.post("/students", status_code=201)
def create_student(body: StudentIn, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    c = db.get(SchoolClass, body.class_id)
    if not c or c.teacher_id != t.id:
        raise err(404, "NOT_FOUND", "Class not found.")
    s = Student(class_id=c.id, name=body.name.strip(), roll_number=body.roll_number.strip())
    db.add(s)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise err(409, "DUPLICATE_ROLL", f"Roll number {body.roll_number} already exists in {c.name}.")
    db.refresh(s)
    return student_view(s)


@router.patch("/students/{student_id}")
def update_student(student_id: str, body: StudentPatch, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    s = db.get(Student, student_id)
    if not s:
        raise err(404, "NOT_FOUND", "Student not found.")
    orig_c = db.get(SchoolClass, s.class_id)
    if not orig_c or orig_c.teacher_id != t.id:
        raise err(404, "NOT_FOUND", "Student not found.")

    target_class_id = s.class_id
    if body.class_id and body.class_id != s.class_id:
        new_c = db.get(SchoolClass, body.class_id)
        if not new_c or new_c.teacher_id != t.id:
            raise err(404, "NOT_FOUND", "Target class not found.")
        s.class_id = new_c.id
        target_class_id = new_c.id

    if body.name is not None and body.name.strip():
        s.name = body.name.strip()
    if body.roll_number is not None and body.roll_number.strip():
        s.roll_number = body.roll_number.strip()

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        target_c_name = db.get(SchoolClass, target_class_id).name
        raise err(409, "DUPLICATE_ROLL", f"Roll number {s.roll_number} already exists in {target_c_name}.")
    db.refresh(s)
    return student_view(s)


@router.delete("/students/{student_id}")
def delete_student(student_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    s = db.get(Student, student_id)
    if not s:
        raise err(404, "NOT_FOUND", "Student not found.")
    c = db.get(SchoolClass, s.class_id)
    if not c or c.teacher_id != t.id:
        raise err(404, "NOT_FOUND", "Student not found.")
    cascade_delete_student_records(db, s.id)
    db.commit()
    return {"deleted": True, "id": student_id}


# ---------- reports ----------
@router.get("/reports/marksheet")
def download_marksheet(db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    import traceback
    import logging
    from fastapi import Response
    from fastapi.responses import JSONResponse
    try:
        from ..services.marksheet import generate_marksheet_bytes, sync_root_marksheet_file
        stream = generate_marksheet_bytes(db, teacher_id=t.id)
        sync_root_marksheet_file(db, teacher_id=t.id, stream=stream)
        return Response(
            content=stream.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=ADEM_Student_Marksheet.xlsx"}
        )
    except Exception as e:
        logging.getLogger("adem").exception("Marksheet generation error")
        return JSONResponse(
            {"code": "MARKSHEET_ERROR", "detail": str(e), "trace": traceback.format_exc()},
            status_code=500,
        )


# ---------- exams ----------
class ExamIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    academic_year: str | None = None
    class_id: str
    subject_id: str
    exam_type: str
    exam_date: str | None = None
    duration_minutes: int | None = Field(None, gt=0)
    total_marks: float = Field(gt=0)
    instructions: str | None = None


class ExamPatch(BaseModel):
    name: str | None = None
    academic_year: str | None = None
    exam_type: str | None = None
    exam_date: str | None = None
    duration_minutes: int | None = Field(None, gt=0)
    total_marks: float | None = Field(None, gt=0)
    instructions: str | None = None


def exam_view(e: Exam) -> dict:
    return {"id": e.id, "name": e.name, "academic_year": e.academic_year, "class_id": e.class_id,
            "class_name": e.school_class.name, "subject_id": e.subject_id, "subject_name": e.subject.name,
            "exam_type": e.exam_type, "exam_date": e.exam_date, "duration_minutes": e.duration_minutes,
            "total_marks": e.total_marks, "instructions": e.instructions, "status": e.status,
            "created_at": e.created_at.isoformat()}


@router.get("/exams")
def list_exams(db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    return [exam_view(e) for e in db.query(Exam).filter_by(teacher_id=t.id).order_by(Exam.created_at.desc())]


@router.post("/exams", status_code=201)
def create_exam(body: ExamIn, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    c, s = db.get(SchoolClass, body.class_id), db.get(Subject, body.subject_id)
    if not c or c.teacher_id != t.id or not s or s.teacher_id != t.id:
        raise err(400, "INVALID_REFERENCE", "Choose a class and subject that exist.")
    data = body.model_dump()
    if not data.get("academic_year"):
        from datetime import datetime
        now = datetime.now()
        data["academic_year"] = f"{now.year}-{str(now.year + 1)[-2:]}"
    e = Exam(teacher_id=t.id, status="DRAFT", **data)
    db.add(e)
    db.flush()
    audit(db, exam_id=e.id, teacher_id=t.id, entity_type="exam", entity_id=e.id, action="exam_created")
    db.commit()
    db.refresh(e)
    return exam_view(e)


@router.get("/exams/{exam_id}")
def get_exam_detail(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    e = get_exam(db, t, exam_id)
    qp = db.query(QuestionPaperDocument).filter_by(exam_id=e.id, is_active=True).order_by(QuestionPaperDocument.uploaded_at.desc()).first()
    ak = db.query(AnswerKeyDocument).filter_by(exam_id=e.id, is_active=True).order_by(AnswerKeyDocument.uploaded_at.desc()).first()
    evs = db.query(Evaluation).filter_by(exam_id=e.id).all()
    return {**exam_view(e),
            "question_paper": doc_view(qp, "question-paper"), "answer_key_document": doc_view(ak, "answer-key"),
            "question_count": db.query(ExamQuestion).filter_by(exam_id=e.id).count(),
            "verified_question_count": db.query(ExamQuestion).filter_by(exam_id=e.id, verification_status="VERIFIED").count(),
            "evaluation_count": len(evs), "finalized_count": sum(x.status == "FINALIZED" for x in evs)}


@router.patch("/exams/{exam_id}")
def patch_exam(exam_id: str, body: ExamPatch, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    e = get_exam(db, t, exam_id)
    if e.status == "FINALIZED":
        raise err(409, "EXAM_FINALIZED", "A finalized exam cannot be edited.")
    for k, v in body.model_dump(exclude_unset=True).items():
        old = getattr(e, k)
        if v != old:
            audit(db, exam_id=e.id, teacher_id=t.id, entity_type="exam", entity_id=e.id,
                  action=f"exam_{k}_changed", old=old, new=v)
            setattr(e, k, v)
    db.commit()
    return exam_view(e)


@router.delete("/exams/{exam_id}")
def delete_exam(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    e = get_exam(db, t, exam_id)
    cascade_delete_exam_records(db, e.id)
    db.commit()
    try:
        from ..services.marksheet import sync_root_marksheet_file
        sync_root_marksheet_file(db, t.id)
    except Exception:
        pass
    return {"ok": True}

