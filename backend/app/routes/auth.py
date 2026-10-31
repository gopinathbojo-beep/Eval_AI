"""Sign-in, signup and account links for every portal.

The portal is part of every sign-in: a parent's account cannot open the school app, and so on. Answers never reveal
whether an email has an account (forgot-password, signup) until the password has been checked."""
from __future__ import annotations
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ..config import get_settings
from ..database import get_db
from ..deps import err
from ..models import Consent, School, SignupRequest, User
from ..security import ROLE_SCOPE, SCOPE_ROLE, create_token, current_user, hash_password, verify_password
from ..services import credits, mailer
from ..services.accounts import (PORTAL_LABEL, check_password, consume_link, issue_link, locked_minutes, normalize_email,
                                 now, phone_key, rate_limit, record_failure, record_success, school_active, user_view,
                                 verify_google)
from ..services.audit import audit

router = APIRouter(prefix="/api")
Portal = str  # "admin" | "school" | "teacher" | "parent" | "web"
# The roles each sign-in page accepts. The web app has one sign-in for school management and their invited teachers;
# the session's scope still comes from the role (see create_token).
PORTAL_ROLES = {**{p: (r,) for p, r in SCOPE_ROLE.items()}, "web": ("school_manager", "teacher")}


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def portal_url(portal: str) -> str:
    s = get_settings()
    return {"admin": s.admin_url, "parent": s.parent_url}.get(portal, s.web_url)


def _check_portal(portal: str) -> str:
    if portal not in PORTAL_ROLES:
        raise err(422, "BAD_PORTAL", "Unknown portal.")
    return portal


def _role_label(role: str) -> str:
    return PORTAL_LABEL[ROLE_SCOPE[role]]


def _session(db: Session, u: User, request: Request, how: str) -> dict:
    record_success(u)
    audit(db, exam_id=None, teacher_id=u.id, entity_type="user", entity_id=u.id, action=f"LOGIN_{how}", ip=_ip(request))
    db.commit()
    view = user_view(u)
    # `teacher` keeps the teacher web app's existing login response working
    return {"access_token": create_token(u), "token_type": "bearer", "user": view, "teacher": view}


def _admit(db: Session, u: User, portal: str) -> None:
    """Checks after the identity is proven: right portal, account usable, school live (teachers)."""
    if u.role not in PORTAL_ROLES[portal]:
        raise err(403, "WRONG_PORTAL", f"This account signs in to the {_role_label(u.role)} app.")
    if u.status == "invited":
        raise err(403, "INVITE_PENDING", "Accept the invitation in your email first.")
    if u.status != "active":
        raise err(403, "ACCOUNT_DISABLED", "This account is not active. Contact support.")
    if u.role == "teacher" and not school_active(db, u):
        raise err(403, "SCHOOL_NOT_ACTIVE", "Your school is not active yet.")


# ---------- sign in ----------
class LoginIn(BaseModel):
    email: str
    password: str
    portal: Portal = "teacher"


@router.post("/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    portal = _check_portal(body.portal)
    rate_limit("login", _ip(request), 30, 15 * 60)
    u = db.query(User).filter_by(email=normalize_email(body.email)).first()
    bad = err(401, "INVALID_CREDENTIALS", "Email or password is incorrect.")
    if u is None:
        raise bad
    if mins := locked_minutes(u):
        raise err(423, "ACCOUNT_LOCKED", f"Too many wrong passwords. Try again in {mins} minute(s) or reset your password.")
    if not verify_password(body.password, u.password_hash):
        record_failure(u)
        audit(db, exam_id=None, teacher_id=u.id, entity_type="user", entity_id=u.id, action="LOGIN_FAILED", ip=_ip(request))
        db.commit()
        raise bad
    _admit(db, u, portal)
    return _session(db, u, request, "PASSWORD")


class GoogleIn(BaseModel):
    id_token: str
    portal: Portal


@router.post("/auth/google")
def google_login(body: GoogleIn, request: Request, db: Session = Depends(get_db)):
    portal = _check_portal(body.portal)
    rate_limit("login", _ip(request), 30, 15 * 60)
    g = verify_google(body.id_token)
    u = db.query(User).filter_by(google_sub=g["sub"]).first() or db.query(User).filter_by(email=g["email"]).first()
    if u is None:
        if portal in ("school", "web", "parent"):
            # the app shows the signup form filled in and finishes with /public/signup/google
            raise err(404, "NEEDS_SIGNUP", "No account yet for this Google address. Complete the signup to continue.")
        raise err(404, "NO_ACCOUNT", "No account for this email. Ask your administrator for an invitation.")
    if u.status == "invited" and u.role in PORTAL_ROLES[portal]:
        raise err(403, "INVITE_PENDING", "Accept the invitation in your email first.")
    _admit(db, u, portal)
    if u.google_sub is None:
        u.google_sub = g["sub"]  # first Google sign-in links the account
    u.email_verified_at = u.email_verified_at or now()
    return _session(db, u, request, "GOOGLE")


@router.get("/auth/me")
def me(u: User = Depends(current_user)):
    return user_view(u)


@router.post("/auth/logout")
def logout(request: Request, u: User = Depends(current_user), db: Session = Depends(get_db)):
    audit(db, exam_id=None, teacher_id=u.id, entity_type="user", entity_id=u.id, action="LOGOUT", ip=_ip(request))
    db.commit()
    return {"ok": True}


@router.post("/auth/logout-all")
def logout_all(request: Request, u: User = Depends(current_user), db: Session = Depends(get_db)):
    u.token_version = (u.token_version or 0) + 1
    audit(db, exam_id=None, teacher_id=u.id, entity_type="user", entity_id=u.id, action="LOGOUT_ALL", ip=_ip(request))
    db.commit()
    return {"ok": True}


class ChangePasswordIn(BaseModel):
    current_password: str = ""
    new_password: str


@router.post("/auth/change-password")
def change_password(body: ChangePasswordIn, request: Request, u: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    if u.password_hash and not verify_password(body.current_password, u.password_hash):
        raise err(400, "WRONG_PASSWORD", "Your current password is incorrect.")
    check_password(body.new_password)
    u.password_hash = hash_password(body.new_password)
    u.must_change_password = False
    u.token_version = (u.token_version or 0) + 1  # other sessions end; this one gets a fresh token
    audit(db, exam_id=None, teacher_id=u.id, entity_type="user", entity_id=u.id, action="PASSWORD_CHANGED", ip=_ip(request))
    db.commit()
    return {"access_token": create_token(u), "token_type": "bearer", "user": user_view(u)}


# ---------- password reset ----------
class ForgotIn(BaseModel):
    email: str
    portal: Portal


@router.post("/auth/forgot-password")
def forgot_password(body: ForgotIn, request: Request, db: Session = Depends(get_db)):
    portal = _check_portal(body.portal)
    rate_limit("forgot", _ip(request), 10, 60 * 60)
    u = db.query(User).filter_by(email=normalize_email(body.email)).first()
    if u is not None and u.role in PORTAL_ROLES[portal] and u.status == "active":
        raw = issue_link(db, "reset", user_id=u.id)
        db.commit()
        mailer.send(u.email, "Reset your ADEM password", "Reset your password",
                    [f"Hello {u.name},", "Someone asked to reset the password for your ADEM account. "
                     "If it was you, choose a new password with the button below. The link works for one hour.",
                     "If it was not you, ignore this email; your password stays the same."],
                    ("Choose a new password", f"{portal_url(portal)}/reset-password?token={raw}"))
    return {"ok": True, "message": "If that email has an account, a reset link is on its way."}


class ResetIn(BaseModel):
    token: str
    new_password: str


@router.post("/auth/reset-password")
def reset_password(body: ResetIn, request: Request, db: Session = Depends(get_db)):
    rate_limit("reset", _ip(request), 20, 15 * 60)
    check_password(body.new_password)
    link = consume_link(db, "reset", body.token)
    u = db.get(User, link.user_id)
    u.password_hash = hash_password(body.new_password)
    u.must_change_password = False
    u.failed_attempts, u.locked_until = 0, None
    u.token_version = (u.token_version or 0) + 1
    audit(db, exam_id=None, teacher_id=u.id, entity_type="user", entity_id=u.id, action="PASSWORD_RESET", ip=_ip(request))
    db.commit()
    return {"ok": True, "message": "Password changed. Sign in with your new password."}


# ---------- invitations (teachers, console users) ----------
@router.get("/auth/invite")
def invite_info(token: str, db: Session = Depends(get_db)):
    u = db.get(User, consume_link(db, "invite", token, peek=True).user_id)
    return {"name": u.name, "email": u.email, "role": u.role,
            "school": u.school.name if u.school else None}


class AcceptInviteIn(BaseModel):
    token: str
    password: str | None = None
    id_token: str | None = None  # accept with Google instead of a password


@router.post("/auth/invite/accept")
def accept_invite(body: AcceptInviteIn, request: Request, db: Session = Depends(get_db)):
    link = consume_link(db, "invite", body.token, peek=True)
    u = db.get(User, link.user_id)
    if body.id_token:
        g = verify_google(body.id_token)
        if g["email"] != u.email:
            raise err(400, "GOOGLE_EMAIL_MISMATCH", f"Sign in with the Google account for {u.email}.")
        u.google_sub = g["sub"]
    elif body.password:
        check_password(body.password)
        u.password_hash = hash_password(body.password)
    else:
        raise err(422, "PASSWORD_REQUIRED", "Choose a password or continue with Google.")
    consume_link(db, "invite", body.token)
    u.status = "active"
    u.email_verified_at = now()
    if u.role == "teacher" and not school_active(db, u):
        db.commit()
        raise err(403, "SCHOOL_NOT_ACTIVE", "Your account is ready, but your school is not active yet.")
    return _session(db, u, request, "INVITE")


# ---------- public signup (schools and parents) ----------
@router.get("/public/config")
def public_config():
    s = get_settings()
    return {"google_client_id": s.google_client_id or None, "privacy_version": s.privacy_version,
            "terms_version": s.terms_version}


class SchoolSignupIn(BaseModel):
    school_name: str = Field(min_length=2, max_length=200)
    address: str = ""
    city: str = ""
    state: str = ""
    phone: str = Field(min_length=6, max_length=30)
    manager_name: str = Field(min_length=2, max_length=200)
    email: str = ""  # not needed with Google, which supplies the address
    password: str | None = None
    accept_terms: bool
    accept_privacy: bool


class ParentSignupIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: str = ""  # not needed with Google, which supplies the address
    phone: str = Field(min_length=6, max_length=30)
    password: str | None = None
    accept_terms: bool
    accept_privacy: bool
    accept_child_data: bool


def _require_consent(body) -> None:
    missing = [k for k in ("accept_terms", "accept_privacy", "accept_child_data") if getattr(body, k, True) is False]
    if missing:
        raise err(422, "CONSENT_REQUIRED", "Please accept the terms and privacy policy to continue.")


def _create_account(db: Session, req: SignupRequest, ip: str, google_sub: str | None = None) -> User:
    """Turn a confirmed signup into the school (pending approval) or parent account."""
    p = req.payload
    s = get_settings()
    if req.kind == "school":
        school = School(name=p["school_name"], address=p.get("address", ""), city=p.get("city", ""),
                        state=p.get("state", ""), phone=p["phone"], status="PENDING")
        db.add(school)
        db.flush()
        u = User(name=p["manager_name"], email=req.email, phone=p["phone"], role="school_manager", school_id=school.id,
                 password_hash=p.get("password_hash"), google_sub=google_sub, email_verified_at=now())
        db.add(u)
        db.flush()
        credits.wallet_for(db, "school", school.id)  # the signup credits follow approval
    else:
        u = User(name=p["name"], email=req.email, phone=p["phone"], role="parent",
                 password_hash=p.get("password_hash"), google_sub=google_sub, email_verified_at=now())
        db.add(u)
        db.flush()
        credits.grant_signup_bonus(db, "parent", u.id, req.phone_key)
    kinds = ["terms", "privacy"] + (["child_data"] if req.kind == "parent" else [])
    for k in kinds:
        db.add(Consent(user_id=u.id, kind=k, version=s.terms_version if k == "terms" else s.privacy_version, ip=ip))
    req.status, req.created_user_id, req.completed_at = "COMPLETED", u.id, now()
    audit(db, exam_id=None, teacher_id=u.id, entity_type="user", entity_id=u.id, action=f"SIGNUP_{req.kind.upper()}", ip=ip)
    return u


def _start_signup(db: Session, kind: str, body, request: Request) -> dict:
    rate_limit("signup", _ip(request), 20, 60 * 60)
    _require_consent(body)
    email = normalize_email(body.email)
    if "@" not in email:
        raise err(422, "EMAIL_REQUIRED", "Enter a valid email address.")
    portal = "school" if kind == "school" else "parent"
    if not body.password:
        raise err(422, "PASSWORD_REQUIRED", "Choose a password, or use Continue with Google.")
    check_password(body.password)
    done = {"ok": True, "message": f"Check {email} for a link to confirm your email address."}
    existing = db.query(User).filter_by(email=email).first()
    if existing is not None:
        # same answer as a new signup; the owner of the address is told by email instead
        mailer.send(email, "You already have an ADEM account", "You already have an account",
                    [f"Someone tried to sign up to ADEM with {email}, which already has an account.",
                     "If it was you, sign in instead, or reset your password from the sign-in page."],
                    ("Sign in", f"{portal_url(portal)}/login"))
        return done
    payload = body.model_dump(exclude={"password", "email"})
    payload["password_hash"] = hash_password(body.password)
    req = SignupRequest(kind=kind, email=email, phone_key=phone_key(body.phone), payload=payload)
    db.add(req)
    db.flush()
    raw = issue_link(db, "verify", signup_id=req.id)
    db.commit()
    mailer.send(email, "Confirm your email for ADEM", "Confirm your email address",
                ["Thanks for signing up to ADEM. Confirm your email address to finish creating your account. "
                 "The link works for 24 hours."],
                ("Confirm email", f"{portal_url(portal)}/verify-email?token={raw}"))
    return done


@router.post("/public/signup/school")
def signup_school(body: SchoolSignupIn, request: Request, db: Session = Depends(get_db)):
    return _start_signup(db, "school", body, request)


@router.post("/public/signup/parent")
def signup_parent(body: ParentSignupIn, request: Request, db: Session = Depends(get_db)):
    return _start_signup(db, "parent", body, request)


class VerifyIn(BaseModel):
    token: str


@router.post("/public/signup/verify-email")
def verify_email(body: VerifyIn, request: Request, db: Session = Depends(get_db)):
    link = consume_link(db, "verify", body.token)
    req = db.get(SignupRequest, link.signup_id)
    if db.query(User).filter_by(email=req.email).first() is not None:
        db.commit()
        raise err(409, "ALREADY_REGISTERED", "This email already has an account. Sign in instead.")
    u = _create_account(db, req, _ip(request))
    if req.kind == "school":
        _notify_school_pending(u)
    return _session(db, u, request, "SIGNUP")


class GoogleSignupIn(BaseModel):
    id_token: str
    kind: str  # school | parent
    school: SchoolSignupIn | None = None
    parent: ParentSignupIn | None = None


@router.post("/public/signup/google")
def signup_google(body: GoogleSignupIn, request: Request, db: Session = Depends(get_db)):
    """Signup with Google: the address is already verified, so the account is created at once."""
    rate_limit("signup", _ip(request), 20, 60 * 60)
    if body.kind not in ("school", "parent") or getattr(body, body.kind) is None:
        raise err(422, "BAD_SIGNUP", "Signup details are missing.")
    form = getattr(body, body.kind)
    _require_consent(form)
    g = verify_google(body.id_token)
    if db.query(User).filter((User.email == g["email"]) | (User.google_sub == g["sub"])).first() is not None:
        raise err(409, "ALREADY_REGISTERED", "This Google account already has an ADEM account. Sign in instead.")
    payload = form.model_dump(exclude={"password", "email"})
    req = SignupRequest(kind=body.kind, email=g["email"], phone_key=phone_key(form.phone), payload=payload)
    db.add(req)
    db.flush()
    u = _create_account(db, req, _ip(request), google_sub=g["sub"])
    if body.kind == "school":
        _notify_school_pending(u)
    return _session(db, u, request, "SIGNUP")


def _notify_school_pending(u: User) -> None:
    mailer.send(u.email, "Your school is registered with ADEM", "Thanks for registering",
                [f"Hello {u.name},", f"{u.school.name} is registered. Our team will review and approve it shortly; "
                 "we will email you as soon as it is active. You can sign in meanwhile to see its status."],
                ("Open ADEM", f"{portal_url('school')}/login"))
