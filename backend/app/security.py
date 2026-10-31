"""Sessions. A token names one user and one portal (scope); the role, status and token version are re-read from the
database on every request, so a suspension, role change or "sign out everywhere" takes effect immediately."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
<<<<<<< 7c662e7
from fastapi import Depends, HTTPException, Request
=======
from fastapi import Depends, HTTPException, Request, Response
>>>>>>> kishore/Version2.0
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from .config import get_settings
from .database import get_db
<<<<<<< 7c662e7
from .models import School, User
=======
from .models import Teacher, Workspace
>>>>>>> kishore/Version2.0

_bearer = HTTPBearer(auto_error=False)
ALGO = "HS256"
SESSION_COOKIE = "eval_session"


def require_browser_request(request: Request) -> None:
    """A non-simple header plus an explicit origin check protects cookie mutations from CSRF."""
    origins = {o.strip().rstrip("/") for o in get_settings().cors_origins.split(",") if o.strip()}
    origin = request.headers.get("origin")
    if request.headers.get("x-requested-with") != "EvalAI" or (origin and origin not in origins):
        raise HTTPException(403, detail={"code": "CSRF_REJECTED", "message": "Request origin could not be verified."})

# portal (token scope) -> the role allowed to use it
SCOPE_ROLE = {"admin": "platform_admin", "school": "school_manager", "teacher": "teacher", "parent": "parent"}
ROLE_SCOPE = {v: k for k, v in SCOPE_ROLE.items()}
# Admin console roles. Anything unknown reads as the least privileged one.
ADMIN_ROLES = ("super_admin", "admin", "viewer")


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(pw.encode()[:72], hashed.encode())
    except ValueError:
        return False


<<<<<<< 7c662e7
def create_token(user: User) -> str:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=s.access_token_minutes)
    payload = {"sub": user.id, "scope": ROLE_SCOPE[user.role], "tv": user.token_version or 0, "exp": exp}
    return jwt.encode(payload, s.jwt_secret, algorithm=ALGO)


def _fail(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message}, headers={"WWW-Authenticate": "Bearer"})


def _session_user(raw_token: str | None, db: Session) -> tuple[User, str]:
    """The signed-in user and the token's scope, or 401. Status and school checks are left to the guards."""
    unauth = _fail(401, "UNAUTHENTICATED", "Sign in to continue.")
=======
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
>>>>>>> kishore/Version2.0
    if not raw_token:
        raise unauth
    try:
        payload = jwt.decode(raw_token, get_settings().jwt_secret, algorithms=[ALGO])
    except jwt.ExpiredSignatureError:
        raise _fail(401, "TOKEN_EXPIRED", "Your session expired. Sign in again.")
    except jwt.PyJWTError:
        raise unauth
    user = db.get(User, payload.get("sub"))
    scope = payload.get("scope")
    if user is None or scope not in SCOPE_ROLE or SCOPE_ROLE[scope] != user.role:
        raise unauth
<<<<<<< 7c662e7
    if payload.get("tv", 0) != (user.token_version or 0):
        raise _fail(401, "SESSION_ENDED", "You were signed out. Sign in again.")
    if user.status != "active":
        raise _fail(401, "ACCOUNT_DISABLED", "This account is not active. Contact support.")
    return user, scope


def _raw(cred: HTTPAuthorizationCredentials | None, token: str | None) -> str | None:
    # `token` as a query parameter lets <img> and download links authenticate
    return cred.credentials if cred else token


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer), token: str | None = None,
                 db: Session = Depends(get_db)) -> User:
    """Any signed-in user, even one who still has to change their password (the auth routes use this)."""
    return _session_user(_raw(cred, token), db)[0]


def _guard(scope: str):
    def dep(request: Request, cred: HTTPAuthorizationCredentials | None = Depends(_bearer), token: str | None = None,
            db: Session = Depends(get_db)) -> User:
        user, got = _session_user(_raw(cred, token), db)
        if got != scope:
            raise _fail(403, "WRONG_PORTAL", "This account cannot use this part of ADEM.")
        if user.must_change_password:
            raise _fail(403, "PASSWORD_CHANGE_REQUIRED", "Set a new password to continue.")
        if user.school_id:
            school = db.get(School, user.school_id)
            if school is None or school.status != "ACTIVE":
                raise _fail(403, "SCHOOL_NOT_ACTIVE", "Your school is not active yet. Contact the platform team.")
        request.state.user = user
        return user
    return dep


current_teacher = _guard("teacher")
current_school_manager = _guard("school")
current_parent = _guard("parent")
_current_admin = _guard("admin")


def admin_role(user: User) -> str:
    return user.admin_role if user.admin_role in ADMIN_ROLES else "viewer"


def current_admin(request: Request, user: User = Depends(_current_admin)) -> User:
    """Any console user. A Viewer may only read: every other method is refused here."""
    if request.method not in ("GET", "HEAD", "OPTIONS") and admin_role(user) == "viewer":
        raise _fail(403, "READ_ONLY", "Your console role can view but not change anything.")
    return user


def current_super_admin(user: User = Depends(current_admin)) -> User:
    if admin_role(user) != "super_admin":
        raise _fail(403, "FORBIDDEN", "Only a Super Admin can do this.")
    return user
=======
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
>>>>>>> kishore/Version2.0
