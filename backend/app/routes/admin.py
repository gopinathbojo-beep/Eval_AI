from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import err
from ..models import AuditLog, SchoolClass, Teacher, Workspace
from ..security import current_admin, hash_password, is_admin, set_session_cookie
from ..services.audit import audit
from .core import teacher_view
from .management import TeacherPatch
from .registration import ProfileIn, complete_profile

router = APIRouter(prefix="/api/admin", dependencies=[Depends(current_admin)])


def stamp(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


UPLOADS = {
    "question_paper_uploaded",
    "answer_key_uploaded",
    "answer_sheet_uploaded",
    "answer_sheets_bulk_uploaded",
}


def events_query(db, start=None, end=None):
    q = db.query(AuditLog)
    if start:
        q = q.filter(AuditLog.created_at >= datetime.combine(start, time.min))
    if end:
        q = q.filter(AuditLog.created_at <= datetime.combine(end, time.max))
    return q


def metrics(db, user_id=None, workspace_id=None, start=None, end=None):
    q = events_query(db, start, end)
    if user_id:
        q = q.filter(AuditLog.teacher_id == user_id)
    if workspace_id:
        q = q.filter(AuditLog.workspace_id == workspace_id)
    rows = q.all()
    counts = {
        key: sum(r.action == action for r in rows)
        for key, action in {
            "exams": "exam_created",
            "ai_runs": "ai_evaluation_started",
            "ai_completed": "ai_evaluation_completed",
            "ai_failed": "ai_evaluation_failed",
            "ai_requests": "ai_grading_request",
        }.items()
    }
    counts["uploads"] = sum(
        len(r.new_value)
        if r.action == "answer_sheets_bulk_uploaded" and isinstance(r.new_value, list)
        else 1
        for r in rows
        if r.action in UPLOADS
    )
    counts["classes"] = (
        db.query(SchoolClass).filter_by(workspace_id=workspace_id).count()
        if workspace_id
        else db.query(SchoolClass).filter_by(teacher_id=user_id).count()
        if user_id
        else db.query(SchoolClass).count()
    )
    return counts


def view(db, user, start=None, end=None):
    ws = db.get(Workspace, user.workspace_id) if user.workspace_id else None
    return {
        **teacher_view(user),
        "is_active": user.is_active,
        "workspace_name": ws.name if ws else None,
        "workspace_active": ws.is_active if ws else True,
        "google_connected": bool(user.google_sub),
        "password_enabled": not user.password_hash.startswith("!"),
        "created_at": stamp(user.created_at),
        "last_login_at": stamp(user.last_login_at),
        **metrics(db, user_id=user.id, start=start, end=end),
    }


@router.get("/summary")
def summary(
    start: date | None = None, end: date | None = None, db: Session = Depends(get_db)
):
    return {
        "users": db.query(Teacher).count(),
        "schools": db.query(Workspace).filter_by(kind="SCHOOL").count(),
        "parents": db.query(Teacher).filter_by(role="PARENT").count(),
        "teachers": db.query(Teacher).filter_by(role="TEACHER").count(),
        **metrics(db, start=start, end=end),
    }


@router.get("/users")
def users(
    q: str = "",
    role: str | None = None,
    workspace_id: str | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Teacher)
    if q.strip():
        query = query.filter(
            or_(
                Teacher.name.icontains(q.strip(), autoescape=True),
                Teacher.email.icontains(q.strip(), autoescape=True),
                Teacher.workspace_id.in_(
                    db.query(Workspace.id).filter(
                        Workspace.name.icontains(q.strip(), autoescape=True)
                    )
                ),
            )
        )
    if role:
        query = query.filter_by(role=role)
    if workspace_id:
        query = query.filter_by(workspace_id=workspace_id)
    return {
        "total": query.count(),
        "users": [
            view(db, u, start, end)
            for u in query.order_by(Teacher.created_at.desc())
            .offset(offset)
            .limit(limit)
        ],
    }


@router.patch("/users/{user_id}")
def patch_user(
    user_id: str,
    body: TeacherPatch,
    response: Response,
    db: Session = Depends(get_db),
    admin: Teacher = Depends(current_admin),
):
    user = db.get(Teacher, user_id)
    if not user:
        raise err(404, "NOT_FOUND", "User not found.")
    if is_admin(user) and (
        body.is_active is False or body.email and str(body.email).lower() != user.email
    ):
        raise err(
            400,
            "OWNER_PROTECTED",
            "The owner cannot be disabled or assigned another email.",
        )
    if body.assignments is not None:
        raise err(
            400,
            "USE_SCHOOL_ASSIGNMENTS",
            "Manage assignments from the school management account.",
        )
    if body.name is not None:
        if not body.name.strip():
            raise err(400, "NAME_REQUIRED", "Name cannot be blank.")
        user.name = body.name.strip()
    if body.email and str(body.email).lower() != user.email:
        if user.google_sub:
            raise err(409, "GOOGLE_LINKED", "Disconnect Google before changing email.")
        user.email = str(body.email).lower()
    if body.phone is not None:
        user.profile = {**(user.profile or {}), "phone": body.phone}
    if body.is_active is not None:
        user.is_active = body.is_active
        if user.role == "MANAGEMENT":
            ws = db.get(Workspace, user.workspace_id)
            if ws:
                ws.is_active = body.is_active
                for member in db.query(Teacher).filter_by(workspace_id=ws.id):
                    member.session_version += 1
    if body.password:
        user.password_hash = hash_password(body.password)
        user.must_change_password = user.role == "TEACHER"
    user.session_version += 1
    audit(
        db,
        exam_id=None,
        teacher_id=admin.id,
        entity_type="user",
        entity_id=user.id,
        action="user_updated",
        new=list(body.model_dump(exclude_unset=True, exclude={"password"})),
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise err(409, "EMAIL_EXISTS", "This email already has an account.")
    if user.id == admin.id:
        set_session_cookie(response, user)
    return view(db, user)


@router.get("/workspaces")
def workspaces(
    q: str = "",
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Workspace)
        .filter(Workspace.name.icontains(q, autoescape=True))
        .order_by(Workspace.name)
        .all()
    )
    return [
        {
            "id": w.id,
            "kind": w.kind,
            "name": w.name,
            "is_active": w.is_active,
            "owner_id": w.owner_id,
            **metrics(db, workspace_id=w.id, start=start, end=end),
        }
        for w in rows
    ]


@router.put("/users/{user_id}/profile")
def edit_profile(
    user_id: str,
    body: ProfileIn,
    db: Session = Depends(get_db),
    admin: Teacher = Depends(current_admin),
):
    user = db.get(Teacher, user_id)
    if not user:
        raise err(404, "NOT_FOUND", "User not found.")
    result = complete_profile(body, Response(), db, user)
    audit(
        db,
        exam_id=None,
        teacher_id=admin.id,
        entity_type="user",
        entity_id=user.id,
        action="user_profile_updated",
    )
    db.commit()
    return result


class WorkspacePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    is_active: bool | None = None


@router.patch("/workspaces/{workspace_id}")
def patch_workspace(
    workspace_id: str,
    body: WorkspacePatch,
    db: Session = Depends(get_db),
    admin: Teacher = Depends(current_admin),
):
    ws = db.get(Workspace, workspace_id)
    if not ws:
        raise err(404, "NOT_FOUND", "Workspace not found.")
    if body.name:
        ws.name = body.name.strip()
    if body.is_active is not None:
        ws.is_active = body.is_active
        for member in db.query(Teacher).filter_by(workspace_id=ws.id):
            member.session_version += 1
    audit(
        db,
        exam_id=None,
        teacher_id=admin.id,
        entity_type="workspace",
        entity_id=ws.id,
        action="workspace_updated",
    )
    db.commit()
    return {"id": ws.id, "name": ws.name, "is_active": ws.is_active}


@router.get("/activity")
def activity(
    user_id: str | None = None,
    workspace_id: str | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = events_query(db, start, end)
    if user_id:
        query = query.filter(AuditLog.teacher_id == user_id)
    if workspace_id:
        query = query.filter(AuditLog.workspace_id == workspace_id)
    actors = {u.id: u for u in db.query(Teacher)}
    return {
        "total": query.count(),
        "events": [
            {
                "id": a.id,
                "action": a.action,
                "created_at": stamp(a.created_at),
                "teacher_name": actors[a.teacher_id].name
                if a.teacher_id in actors
                else "System",
                "actor_id": a.teacher_id,
                "workspace_id": a.workspace_id,
                "entity_type": a.entity_type,
                "entity_id": a.entity_id,
                "exam_id": a.exam_id,
            }
            for a in query.order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(limit)
        ],
    }
