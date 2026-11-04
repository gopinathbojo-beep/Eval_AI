from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import err
from ..login_limiter import LoginLimiter
from ..models import Exam, SchoolClass, SchoolProfile, Student, Teacher, Workspace
from ..security import (
    current_account,
    hash_password,
    is_admin,
    require_browser_request,
    set_session_cookie,
    verify_password,
)
from ..services.audit import audit
from ..actor import actor_id
from .. import validation as valid
from .core import teacher_view

router = APIRouter(prefix="/api/auth")
register_limiter = LoginLimiter()


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(max_length=72)
    role: Literal["MANAGEMENT", "PARENT"]  # teachers never self-register

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        return valid.person_name(value)

    @field_validator("email", mode="before")
    @classmethod
    def email_format(cls, value):
        return valid.email(str(value))

    @field_validator("password")
    @classmethod
    def password_bytes(cls, value):
        if len(value.encode()) > 72:
            raise ValueError("Password cannot exceed 72 UTF-8 bytes")
        # Same rule as frontend/src/utils/validation.ts passwordRules
        if len(value) < 8:
            raise ValueError("Use at least 8 characters for your password.")
        if not value[0].isupper():
            raise ValueError("Start your password with a capital letter.")
        if not any(c.isdigit() for c in value):
            raise ValueError("Add at least one number to your password.")
        if all(c.isalnum() for c in value):
            raise ValueError("Add at least one special character (like @, # or !) to your password.")
        return value


@router.post("/register", status_code=201)
def register(
    body: RegisterIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    require_browser_request(request)
    register_limiter.check(request.client.host if request.client else "unknown", 10)
    user = Teacher(
        name=body.name,
        email=str(body.email).lower(),
        password_hash=hash_password(body.password),
        role=body.role,
        approval_status="APPROVED",
        registration_source="PUBLIC",
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise err(
            409,
            "EMAIL_EXISTS",
            "An account with this email already exists. Sign in instead.",
        )
    audit(
        db,
        exam_id=None,
        teacher_id=user.id,
        entity_type="user",
        entity_id=user.id,
        action="account_registered",
    )
    db.commit()
    set_session_cookie(response, user)
    return {"teacher": teacher_view(user)}


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: Literal["MANAGEMENT", "PARENT"] | None = None
    phone: str = Field(min_length=1, max_length=30)
    school_name: str = Field("", max_length=200)
    address: str = Field("", max_length=600)
    # structured school address (registration chat); address is then the formatted whole
    building: str = Field("", max_length=200)
    locality: str = Field("", max_length=200)
    city: str = Field("", max_length=100)
    state: str = Field("", max_length=100)
    postcode: str = Field("", max_length=20)
    principal_name: str = Field("", max_length=200)
    affiliation_number: str = Field("", max_length=50)
    total_students: int | None = Field(None, ge=1, le=100000)
    child_name: str = Field("", max_length=200)
    child_class: Literal["10", "12"] | None = None

    @field_validator("name")
    @classmethod
    def required(cls, value):
        return valid.person_name(value)

    @field_validator("phone")
    @classmethod
    def phone_format(cls, value):
        return valid.phone(value)

    @field_validator("principal_name", "child_name")
    @classmethod
    def optional_person(cls, value, info):
        what = {"principal_name": "Principal's name", "child_name": "Child's name"}[info.field_name]
        return valid.person_name(value, what) if value.strip() else ""

    @field_validator("school_name")
    @classmethod
    def school(cls, value):
        return valid.place_name(value, "School name") if value.strip() else ""

    @field_validator("city", "state")
    @classmethod
    def place(cls, value, info):
        return valid.place_name(value, info.field_name.capitalize()) if value.strip() else ""

    @field_validator("postcode")
    @classmethod
    def pin(cls, value):
        return valid.pin_code(value) if value.strip() else ""


def format_address(body: "ProfileIn") -> str:
    """Building, Locality, City, State - PIN: the one-line address shown on reports and in the review."""
    place = ", ".join(x.strip() for x in (body.building, body.locality, body.city, body.state) if x.strip())
    return f"{place} - {body.postcode.strip()}" if body.postcode.strip() else place


@router.get("/affiliation/{number}")
def affiliation_lookup(number: str, user: Teacher = Depends(current_account)):
    """School details CBSE publishes for an affiliation number, to pre-fill the profile chat for review."""
    from ..services import cbse_affiliation

    if not cbse_affiliation.NUMBER.fullmatch(number.strip()):
        raise err(400, "INVALID_AFFILIATION_NUMBER", "A CBSE affiliation number has only digits, like 1930001.")
    try:
        school = cbse_affiliation.lookup(number)
    except cbse_affiliation.LookupFailed:
        raise err(502, "CBSE_LOOKUP_UNAVAILABLE", "CBSE records could not be reached. Please enter the details yourself.")
    if not school:
        raise err(404, "AFFILIATION_NOT_FOUND", "No school with this affiliation number was found in CBSE records.")
    return school


@router.get("/school-search")
def school_search(q: str = Query(..., min_length=2), user: Teacher = Depends(current_account)):
    """Search CBSE SARAS directory by school name/keyword to pre-fill the profile chat."""
    from ..services import cbse_affiliation

    return cbse_affiliation.search_by_name(q)


@router.put("/profile")
def complete_profile(
    body: ProfileIn,
    response: Response,
    db: Session = Depends(get_db),
    user: Teacher = Depends(current_account),
):
    if is_admin(user) or user.role == "TEACHER":
        raise err(
            403, "MANAGED_ACCOUNT", "This profile is managed by your administrator."
        )
    role = body.role or user.role
    if body.building.strip() or body.locality.strip():
        body.address = format_address(body)
    if user.role not in {"UNASSIGNED", role}:
        raise err(409, "ROLE_FIXED", "Account role cannot be changed.")
    # the principal's name is optional (the sign-up chat lets it be skipped): report cards print "Principal" alone
    # until it is added in School Settings
    if role == "MANAGEMENT" and not all(
        (
            body.school_name.strip(),
            body.address.strip(),
            body.city.strip(),
            body.state.strip(),
            body.postcode.strip(),
        )
    ):
        raise err(
            400,
            "SCHOOL_DETAILS_REQUIRED",
            "Complete the school name, address, city, state and postcode.",
        )
    if role == "PARENT" and (not body.child_name.strip() or not body.child_class):
        raise err(400, "CHILD_REQUIRED", "Enter your child's name and Class 10 or 12.")
    user.role = role
    ws = db.get(Workspace, user.workspace_id) if user.workspace_id else None
    if not ws:
        ws = Workspace(
            kind="SCHOOL" if role == "MANAGEMENT" else "FAMILY",
            name=body.school_name.strip()
            if role == "MANAGEMENT"
            else body.child_name.strip(),
            owner_id=user.id,
        )
        db.add(ws)
        db.flush()
        user.workspace_id = ws.id
    user.name = body.name.strip()
    user.profile = body.model_dump(exclude={"name", "role"})
    user.profile_completed_at = datetime.now(timezone.utc)
    user.approval_status = "APPROVED"
    if role == "MANAGEMENT":
        ws.name = body.school_name.strip()
        profile = db.query(SchoolProfile).filter_by(teacher_id=user.id).first()
        if not profile:
            profile = SchoolProfile(teacher_id=user.id)
            db.add(profile)
        profile.name, profile.address, profile.principal_name = (
            ws.name,
            body.address.strip(),
            body.principal_name.strip(),
        )
    else:
        cls = db.query(SchoolClass).filter_by(teacher_id=user.id).first()
        child = (
            db.query(Student)
            .join(SchoolClass)
            .filter(SchoolClass.teacher_id == user.id)
            .first()
        )
        if (
            child
            and cls.name != body.child_class
            and db.query(Exam).filter_by(workspace_id=ws.id).count()
        ):
            raise err(
                409,
                "CLASS_HAS_EXAMS",
                "The child's class cannot change while exams exist.",
            )
        if not cls:
            cls = SchoolClass(
                teacher_id=user.id, workspace_id=ws.id, name=body.child_class
            )
            db.add(cls)
            db.flush()
        cls.name = body.child_class
        if not child:
            child = Student(
                class_id=cls.id, name=body.child_name.strip(), roll_number="1"
            )
            db.add(child)
        child.name = body.child_name.strip()
        ws.name = child.name
    audit(
        db,
        exam_id=None,
        teacher_id=actor_id.get() or user.id,
        entity_type="workspace",
        entity_id=ws.id,
        action="profile_updated",
    )
    db.commit()
    set_session_cookie(response, user)
    return {"teacher": teacher_view(user)}


class PasswordIn(BaseModel):
    current_password: str = Field("", max_length=1024)
    password: str = Field(min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def password_bytes(cls, value):
        return RegisterIn.password_bytes(value)


@router.post("/password")
def change_password(
    body: PasswordIn,
    response: Response,
    user: Teacher = Depends(current_account),
    db: Session = Depends(get_db),
):
    if not user.password_hash.startswith("!") and not verify_password(
        body.current_password, user.password_hash
    ):
        raise err(400, "INVALID_PASSWORD", "Current password is incorrect.")
    user.password_hash = hash_password(body.password)
    user.must_change_password = False
    user.session_version += 1
    audit(
        db,
        exam_id=None,
        teacher_id=user.id,
        entity_type="user",
        entity_id=user.id,
        action="password_changed",
    )
    db.commit()
    set_session_cookie(response, user)
    return {"teacher": teacher_view(user)}
