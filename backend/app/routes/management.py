"""School-owned teacher provisioning and assignment management."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import err
from ..models import SchoolClass, Subject, Teacher, TeacherAssignment
from ..security import current_teacher, hash_password
from ..services.audit import audit
from .core import teacher_view
from .registration import RegisterIn


def management(user: Teacher = Depends(current_teacher)):
    if user.role != "MANAGEMENT":
        raise err(403, "MANAGEMENT_REQUIRED", "School management access is required.")
    return user


router = APIRouter(prefix="/api/management", dependencies=[Depends(management)])


class AssignmentIn(BaseModel):
    class_id: str
    subject_id: str


class TeacherIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=10, max_length=72)
    phone: str = Field("", max_length=30)
    assignments: list[AssignmentIn] = Field(default_factory=list, max_length=200)

    @field_validator("name")
    @classmethod
    def name_valid(cls, value):
        return RegisterIn.clean_name(value)

    @field_validator("password")
    @classmethod
    def password_valid(cls, value):
        return RegisterIn.password_bytes(value)


class TeacherPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30)
    password: str | None = Field(None, min_length=10, max_length=72)
    is_active: bool | None = None
    assignments: list[AssignmentIn] | None = Field(None, max_length=200)

    @field_validator("password")
    @classmethod
    def password_valid(cls, value):
        return RegisterIn.password_bytes(value) if value else value


def teacher_record(db, user, target):
    row = db.get(Teacher, target)
    if not row or row.role != "TEACHER" or row.workspace_id != user.workspace_id:
        raise err(404, "NOT_FOUND", "Teacher not found.")
    return row


def set_assignments(db, user, teacher, assignments):
    pairs = {(a.class_id, a.subject_id) for a in assignments}
    for cid, sid in pairs:
        c, s = db.get(SchoolClass, cid), db.get(Subject, sid)
        if (
            not c
            or not s
            or c.workspace_id != user.workspace_id
            or s.workspace_id != user.workspace_id
        ):
            raise err(404, "NOT_FOUND", "Class or subject not found.")
    db.query(TeacherAssignment).filter_by(teacher_id=teacher.id).delete()
    for cid, sid in pairs:
        db.add(TeacherAssignment(teacher_id=teacher.id, class_id=cid, subject_id=sid))


def view(db, teacher):
    return {
        **teacher_view(teacher),
        "is_active": teacher.is_active,
        "assignments": [
            {"class_id": a.class_id, "subject_id": a.subject_id}
            for a in db.query(TeacherAssignment).filter_by(teacher_id=teacher.id)
        ],
    }


@router.get("/teachers")
def teachers(db: Session = Depends(get_db), user: Teacher = Depends(management)):
    return [
        view(db, row)
        for row in db.query(Teacher)
        .filter_by(workspace_id=user.workspace_id, role="TEACHER")
        .order_by(Teacher.name)
    ]


@router.post("/teachers", status_code=201)
def create(
    body: TeacherIn, db: Session = Depends(get_db), user: Teacher = Depends(management)
):
    row = Teacher(
        name=body.name.strip(),
        email=str(body.email).lower(),
        role="TEACHER",
        workspace_id=user.workspace_id,
        password_hash=hash_password(body.password),
        must_change_password=True,
        profile={"phone": body.phone},
        profile_completed_at=datetime.now(timezone.utc),
        approval_status="APPROVED",
    )
    db.add(row)
    try:
        db.flush()
        set_assignments(db, user, row, body.assignments)
        audit(
            db,
            exam_id=None,
            teacher_id=user.id,
            entity_type="user",
            entity_id=row.id,
            action="teacher_created",
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise err(409, "EMAIL_EXISTS", "This email already has an account.")
    return view(db, row)


@router.patch("/teachers/{teacher_id}")
def patch(
    teacher_id: str,
    body: TeacherPatch,
    db: Session = Depends(get_db),
    user: Teacher = Depends(management),
):
    row = teacher_record(db, user, teacher_id)
    if body.name is not None:
        row.name = RegisterIn.clean_name(body.name)
    if body.phone is not None:
        row.profile = {**(row.profile or {}), "phone": body.phone}
    if body.email and str(body.email).lower() != row.email:
        if row.google_sub:
            raise err(
                409, "GOOGLE_LINKED", "Disconnect Google before changing this email."
            )
        row.email = str(body.email).lower()
    if body.is_active is not None:
        row.is_active = body.is_active
    if body.password:
        row.password_hash = hash_password(body.password)
        row.must_change_password = True
    if body.assignments is not None:
        set_assignments(db, user, row, body.assignments)
    row.session_version += 1
    audit(
        db,
        exam_id=None,
        teacher_id=user.id,
        entity_type="user",
        entity_id=row.id,
        action="teacher_updated",
        new=list(body.model_dump(exclude_unset=True, exclude={"password"})),
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise err(409, "EMAIL_EXISTS", "This email already has an account.")
    return view(db, row)
