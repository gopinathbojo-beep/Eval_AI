"""Sessions. A token names one user and one portal (scope); the role, status and token version are re-read from the
database on every request, so a suspension, role change or "sign out everywhere" takes effect immediately."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from .config import get_settings
from .database import get_db
from .models import School, User

_bearer = HTTPBearer(auto_error=False)
ALGO = "HS256"

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
