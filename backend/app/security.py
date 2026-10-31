"""Sessions. A token names one account, the portal it signed in to, and the account's session version; the role,
status and workspace are re-read from the database on every request, so a suspension, role change or "sign out
everywhere" takes effect immediately.

The web app keeps its session in an HttpOnly cookie (CSRF-checked on writes); the admin and parent apps send the
same token as a Bearer header. Which roles may sign in where is PORTAL_ROLES (checked at sign-in, see routes/auth.py).
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from .config import get_settings
from .database import get_db
from .models import Teacher, Workspace

_bearer = HTTPBearer(auto_error=False)
ALGO = "HS256"
SESSION_COOKIE = "eval_session"

# portal -> the roles that sign in there. "web" is the school and family web app (Version2.0's single app).
PORTAL_ROLES = {"admin": ("ADMIN",), "school": ("MANAGEMENT",), "teacher": ("TEACHER",), "parent": ("PARENT",),
                "web": ("MANAGEMENT", "TEACHER", "PARENT", "UNASSIGNED", "ADMIN")}
# Admin console roles. Anything unknown reads as the least privileged one.
ADMIN_ROLES = ("super_admin", "admin", "viewer")
# What school management may change (everything else it can only read: exams, uploads, grading, finalising)
MANAGEMENT_WRITES = ("/api/classes", "/api/students", "/api/subjects", "/api/school-profile", "/api/report-templates",
                     "/api/management", "/api/school", "/api/credits", "/api/support", "/api/disputes", "/api/auth",
                     "/api/reports")


def require_browser_request(request: Request) -> None:
    """A non-simple header plus an explicit origin check protects cookie mutations from CSRF."""
    origins = {o.strip().rstrip("/") for o in get_settings().cors_origins.split(",") if o.strip()}
    origin = request.headers.get("origin")
    if request.headers.get("x-requested-with") != "EvalAI" or (origin and origin not in origins):
        raise HTTPException(403, detail={"code": "CSRF_REJECTED", "message": "Request origin could not be verified."})


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str | None) -> bool:
    if not hashed or hashed.startswith("!"):  # "!..." marks an account that signs in with Google only
        return False
    try:
        return bcrypt.checkpw(pw.encode()[:72], hashed.encode())
    except ValueError:
        return False


def _is_owner(t: Teacher) -> bool:
    owner = get_settings().admin_email.strip().lower()
    return bool(owner) and t.email.strip().lower() == owner


def is_admin(t: Teacher) -> bool:
    """A platform console account: role ADMIN, or the owner named by ADMIN_EMAIL."""
    return t.role == "ADMIN" or _is_owner(t)


def admin_role(t: Teacher) -> str:
    if _is_owner(t):
        return "super_admin"
    return t.admin_role if t.admin_role in ADMIN_ROLES else "viewer"


def create_token(account: Teacher | str, version: int | None = None, portal: str = "web") -> str:
    s = get_settings()
    sub = account if isinstance(account, str) else account.id
    ver = version if version is not None else (0 if isinstance(account, str) else account.session_version or 0)
    exp = datetime.now(timezone.utc) + timedelta(minutes=s.access_token_minutes)
    return jwt.encode({"sub": sub, "ver": ver, "portal": portal, "exp": exp}, s.jwt_secret, algorithm=ALGO)


def set_session_cookie(response: Response, teacher: Teacher) -> None:
    s = get_settings()
    response.set_cookie(SESSION_COOKIE, create_token(teacher), max_age=s.access_token_minutes * 60,
                        httponly=True, secure=s.cookie_secure, samesite="strict", path="/api")


def _fail(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message}, headers={"WWW-Authenticate": "Bearer"})


def current_account(request: Request, cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
                    token: str | None = None, db: Session = Depends(get_db)) -> Teacher:
    """Any signed-in account, even one that still has to change its password or finish its profile."""
    unauth = _fail(401, "UNAUTHENTICATED", "Sign in to continue.")
    cookie_token = request.cookies.get(SESSION_COOKIE)
    if not cred and cookie_token and request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_browser_request(request)
    # `token` as a query parameter lets <img> and download links authenticate in development; it can leak through
    # logs, so production never accepts it
    raw_token = cred.credentials if cred else cookie_token or (token if get_settings().environment != "production" else None)
    if not raw_token:
        raise unauth
    try:
        payload = jwt.decode(raw_token, get_settings().jwt_secret, algorithms=[ALGO])
    except jwt.ExpiredSignatureError:
        raise _fail(401, "TOKEN_EXPIRED", "Your session expired. Sign in again.")
    except jwt.PyJWTError:
        raise unauth
    t = db.get(Teacher, payload.get("sub"))
    if t is None or t.approval_status == "INVITED":
        raise unauth
    if payload.get("ver", 0) != (t.session_version or 0):
        raise _fail(401, "SESSION_ENDED", "You were signed out. Sign in again.")
    if not t.is_active:
        raise _fail(401, "ACCOUNT_DISABLED", "This account is not active. Contact the administrator.")
    if t.workspace_id:
        ws = db.get(Workspace, t.workspace_id)
        if not ws or not ws.is_active:
            raise _fail(401, "WORKSPACE_DISABLED", "This workspace is disabled.")
    request.state.portal = payload.get("portal", "web")
    request.state.user = t
    return t


current_user = current_account  # our auth routes' name for it


def current_teacher(request: Request, teacher: Teacher = Depends(current_account),
                    db: Session = Depends(get_db)) -> Teacher:
    """An account doing academic work in its workspace (management, teacher or parent)."""
    if teacher.must_change_password:  # the temporary password goes first, then the profile
        raise HTTPException(403, detail={"code": "PASSWORD_CHANGE_REQUIRED", "message": "Change your temporary password to continue."})
    if not is_admin(teacher) and (not teacher.profile_completed_at or not teacher.workspace_id):
        raise HTTPException(403, detail={"code": "PROFILE_REQUIRED", "message": "Complete your profile to continue."})
    ws = db.get(Workspace, teacher.workspace_id) if teacher.workspace_id else None
    if ws and ws.status != "ACTIVE":
        raise HTTPException(403, detail={"code": "SCHOOL_NOT_ACTIVE",
                                         "message": "Your school is not active yet. Contact the platform team."})
    path = request.url.path
    write = request.method not in {"GET", "HEAD", "OPTIONS"}
    roster = path.startswith(("/api/classes", "/api/students", "/api/subjects")) and "report-card" not in path
    branding = path.startswith(("/api/school-profile", "/api/report-templates"))
    if is_admin(teacher) and write and not path.startswith("/api/admin"):
        raise HTTPException(403, detail={"code": "WORKSPACE_REQUIRED", "message": "Use a school or family account for academic work."})
    if write and teacher.role == "TEACHER" and (roster or branding):
        raise HTTPException(403, detail={"code": "MANAGEMENT_REQUIRED", "message": "School management maintains these records."})
    if write and teacher.role == "MANAGEMENT" and not path.startswith(MANAGEMENT_WRITES):
        # spec 04: the School Manager sees every exam, mark and sheet of the school but creates and grades none
        raise HTTPException(403, detail={"code": "MANAGER_READ_ONLY",
                                         "message": "School management can view exams but not change them. Teachers run exams."})
    if teacher.role == "PARENT":
        if path.startswith("/api/students/import") or (write and (path.startswith("/api/classes") or path.startswith("/api/students"))):
            raise HTTPException(403, detail={"code": "ONE_CHILD_ONLY", "message": "Manage your child in the family profile."})
        if write and path.startswith("/api/school-profile"):
            raise HTTPException(403, detail={"code": "SCHOOL_ONLY", "message": "School branding is managed by schools."})
    return teacher


def current_school_manager(t: Teacher = Depends(current_teacher)) -> Teacher:
    if t.role != "MANAGEMENT":
        raise _fail(403, "MANAGEMENT_REQUIRED", "Only school management can do this.")
    return t


def current_parent(t: Teacher = Depends(current_teacher)) -> Teacher:
    if t.role != "PARENT":
        raise _fail(403, "PARENT_REQUIRED", "This is for parent accounts.")
    return t


def current_admin(request: Request, teacher: Teacher = Depends(current_account)) -> Teacher:
    """Any console user. A Viewer may only read: every other method is refused here."""
    if not is_admin(teacher):
        raise HTTPException(403, detail={"code": "ADMIN_REQUIRED", "message": "Administrator access is required."})
    if teacher.must_change_password:
        raise _fail(403, "PASSWORD_CHANGE_REQUIRED", "Set a new password to continue.")
    if request.method not in ("GET", "HEAD", "OPTIONS") and admin_role(teacher) == "viewer":
        raise _fail(403, "READ_ONLY", "Your console role can view but not change anything.")
    return teacher


def current_super_admin(t: Teacher = Depends(current_admin)) -> Teacher:
    if admin_role(t) != "super_admin":
        raise _fail(403, "FORBIDDEN", "Only a Super Admin can do this.")
    return t
