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


def require_browser_request(request: Request) -> None:
    """A non-simple header plus an explicit origin check protects cookie mutations from CSRF."""
    origins = {o.strip().rstrip("/") for o in get_settings().cors_origins.split(",") if o.strip()}
    origin = request.headers.get("origin")
    if request.headers.get("x-requested-with") != "EvalAI" or (origin and origin not in origins):
        raise HTTPException(403, detail={"code": "CSRF_REJECTED", "message": "Request origin could not be verified."})


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode()[:72], hashed.encode())
    except ValueError:
        return False


def is_admin(teacher: Teacher) -> bool:
    return teacher.email.strip().lower() == get_settings().admin_email.strip().lower()


def set_session_cookie(response: Response, teacher: Teacher) -> None:
    s = get_settings()
    response.set_cookie(SESSION_COOKIE, create_token(teacher.id, teacher.session_version), max_age=s.access_token_minutes * 60,
                        httponly=True, secure=s.cookie_secure, samesite="strict", path="/api")


def create_token(teacher_id: str, version: int = 0) -> str:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=s.access_token_minutes)
    return jwt.encode({"sub": teacher_id, "exp": exp, "ver": version}, s.jwt_secret, algorithm=ALGO)


def current_account(request: Request, cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
                    token: str | None = None,
                    db: Session = Depends(get_db)) -> Teacher:
    unauth = HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "Sign in to continue."},
                           headers={"WWW-Authenticate": "Bearer"})
    cookie_token = request.cookies.get(SESSION_COOKIE)
    if not cred and cookie_token and request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_browser_request(request)
    # Query-string bearer tokens can leak through logs; keep legacy support only during development.
    raw_token = cred.credentials if cred else cookie_token or (token if get_settings().environment != "production" else None)
    if not raw_token:
        raise unauth
    try:
        payload = jwt.decode(raw_token, get_settings().jwt_secret, algorithms=[ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, detail={"code": "TOKEN_EXPIRED", "message": "Your session expired. Sign in again."},
                            headers={"WWW-Authenticate": "Bearer"})
    except jwt.PyJWTError:
        raise unauth
    t = db.get(Teacher, payload.get("sub"))
    if t is None:
        raise unauth
    if not t.is_active:
        raise HTTPException(401, detail={"code": "ACCOUNT_DISABLED", "message": "Your account has been disabled. Contact the administrator."})
    if payload.get("ver", 0) != t.session_version:
        raise unauth
    if t.workspace_id:
        ws = db.get(Workspace, t.workspace_id)
        if not ws or not ws.is_active:
            raise HTTPException(401, detail={"code": "WORKSPACE_DISABLED", "message": "This workspace is disabled."})
    return t


def current_teacher(request: Request, teacher: Teacher = Depends(current_account)) -> Teacher:
    if not is_admin(teacher) and (not teacher.profile_completed_at or not teacher.workspace_id):
        raise HTTPException(403, detail={"code": "PROFILE_REQUIRED", "message": "Complete your profile to continue."})
    if teacher.must_change_password:
        raise HTTPException(403, detail={"code": "PASSWORD_CHANGE_REQUIRED", "message": "Change your temporary password to continue."})
    path = request.url.path
    write = request.method not in {"GET", "HEAD", "OPTIONS"}
    roster = path.startswith(("/api/classes", "/api/students", "/api/subjects")) and "report-card" not in path
    branding = path.startswith(("/api/school-profile", "/api/report-templates"))
    if is_admin(teacher) and write and not path.startswith("/api/admin"):
        raise HTTPException(403, detail={"code": "WORKSPACE_REQUIRED", "message": "Use a school or family account for academic work."})
    if write and teacher.role == "TEACHER" and (roster or branding):
        raise HTTPException(403, detail={"code": "MANAGEMENT_REQUIRED", "message": "School management maintains these records."})
    if teacher.role == "PARENT":
        if path.startswith("/api/students/import") or (write and (path.startswith("/api/classes") or path.startswith("/api/students"))):
            raise HTTPException(403, detail={"code": "ONE_CHILD_ONLY", "message": "Manage your child in the family profile."})
        if write and path.startswith("/api/school-profile"):
            raise HTTPException(403, detail={"code": "SCHOOL_ONLY", "message": "School branding is managed by schools."})
    return teacher


def current_admin(teacher: Teacher = Depends(current_teacher)) -> Teacher:
    if not is_admin(teacher):
        raise HTTPException(403, detail={"code": "ADMIN_REQUIRED", "message": "Administrator access is required."})
    return teacher
