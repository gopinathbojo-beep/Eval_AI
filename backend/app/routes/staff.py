"""School management's teachers: invite by email, resend or cancel an invitation, suspend and reactivate.

Like a shop owner and their staff: the school manager signs up, then invites each teacher, who joins from the emailed
link and signs in on the same page as the manager. Every query is limited to the manager's own school."""
from __future__ import annotations
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ..config import get_settings
from ..database import get_db
from ..deps import err
from ..models import AuthToken, User
from ..security import current_school_manager
from ..services import mailer
from ..services.accounts import issue_link, normalize_email
from ..services.audit import audit

router = APIRouter(prefix="/api/school")


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _view(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "phone": u.phone, "status": u.status,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "created_at": u.created_at.isoformat() if u.created_at else None}


def _teacher(db: Session, manager: User, tid: str) -> User:
    u = db.get(User, tid)
    if u is None or u.role != "teacher" or u.school_id != manager.school_id:
        raise err(404, "NOT_FOUND", "Teacher not found.")
    return u


def _send_invite(db: Session, manager: User, u: User) -> None:
    raw = issue_link(db, "invite", user_id=u.id)
    db.commit()
    school = manager.school.name if manager.school else "your school"
    mailer.send(u.email, f"{school} invited you to ADEM", "You are invited to ADEM",
                [f"Hello {u.name},", f"{manager.name} added you as a teacher at {school} on ADEM, "
                 "where you set exams and mark answer sheets with AI.",
                 "Accept the invitation to choose a password, or continue with Google. The link works for 7 days."],
                ("Accept invitation", f"{get_settings().web_url}/accept-invite?token={raw}"))


@router.get("/teachers")
def list_teachers(db: Session = Depends(get_db), m: User = Depends(current_school_manager)):
    rows = (db.query(User).filter(User.school_id == m.school_id, User.role == "teacher", User.status != "removed")
            .order_by(User.created_at.desc()).all())
    return [_view(u) for u in rows]


class InviteIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: str
    phone: str = ""


@router.post("/teachers", status_code=201)
def invite_teacher(body: InviteIn, request: Request, db: Session = Depends(get_db),
                   m: User = Depends(current_school_manager)):
    email = normalize_email(body.email)
    if "@" not in email:
        raise err(422, "EMAIL_REQUIRED", "Enter a valid email address.")
    if db.query(User).filter_by(email=email).first() is not None:
        # one email = one account and one role, at this school or any other
        raise err(409, "EMAIL_TAKEN", "This email already has an ADEM account. Use a different email.")
    u = User(name=body.name.strip(), email=email, phone=body.phone.strip(), role="teacher", school_id=m.school_id,
             status="invited", created_by=m.id)
    db.add(u)
    db.flush()
    audit(db, exam_id=None, teacher_id=m.id, entity_type="user", entity_id=u.id, action="TEACHER_INVITED", ip=_ip(request))
    _send_invite(db, m, u)
    return _view(u)


@router.post("/teachers/{tid}/resend")
def resend_invite(tid: str, request: Request, db: Session = Depends(get_db), m: User = Depends(current_school_manager)):
    u = _teacher(db, m, tid)
    if u.status != "invited":
        raise err(409, "NOT_INVITED", "This teacher has already joined.")
    audit(db, exam_id=None, teacher_id=m.id, entity_type="user", entity_id=u.id, action="TEACHER_INVITE_RESENT", ip=_ip(request))
    _send_invite(db, m, u)
    return {"ok": True, "message": f"Invitation sent again to {u.email}."}


@router.delete("/teachers/{tid}/invite")
def cancel_invite(tid: str, request: Request, db: Session = Depends(get_db), m: User = Depends(current_school_manager)):
    u = _teacher(db, m, tid)
    if u.status != "invited":
        raise err(409, "NOT_INVITED", "This teacher has already joined. Suspend the account instead.")
    # never joined, so owns nothing: delete it, which kills the emailed link and frees the email for a new invite
    db.query(AuthToken).filter_by(user_id=u.id).delete()
    audit(db, exam_id=None, teacher_id=m.id, entity_type="user", entity_id=u.id, action="TEACHER_INVITE_CANCELLED",
          old={"email": u.email}, ip=_ip(request))
    db.delete(u)
    db.commit()
    return {"ok": True}


class StatusIn(BaseModel):
    status: str  # active | suspended


@router.put("/teachers/{tid}/status")
def set_status(tid: str, body: StatusIn, request: Request, db: Session = Depends(get_db),
               m: User = Depends(current_school_manager)):
    u = _teacher(db, m, tid)
    if body.status not in ("active", "suspended") or u.status not in ("active", "suspended"):
        raise err(409, "BAD_STATUS", "Only a teacher who has joined can be suspended or reactivated.")
    if u.status != body.status:
        old = u.status
        u.status = body.status
        if body.status == "suspended":
            u.token_version = (u.token_version or 0) + 1  # signed out everywhere at once
        audit(db, exam_id=None, teacher_id=m.id, entity_type="user", entity_id=u.id, action="TEACHER_STATUS",
              old={"status": old}, new={"status": body.status}, ip=_ip(request))
        db.commit()
    return _view(u)
