"""Account rules shared by the auth, admin and school routes: password policy, lockout, emailed links, Google tokens."""
from __future__ import annotations
import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import jwt
from sqlalchemy.orm import Session
from ..config import get_settings
from ..deps import err
from ..models import AuthToken, School, User
from ..security import admin_role

LINK_TTL = {"invite": timedelta(days=7), "reset": timedelta(hours=1), "verify": timedelta(hours=24)}
PORTAL_LABEL = {"admin": "Admin", "school": "School", "teacher": "Teacher", "parent": "Parents"}


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(dt: datetime | None) -> datetime | None:
    # SQLite hands back naive datetimes; everything is stored in UTC
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def phone_key(phone: str) -> str:
    return "".join(c for c in phone or "" if c.isdigit())[-10:]


def password_problem(pw: str) -> str | None:
    if len(pw or "") < 8:
        return "Use at least 8 characters."
    if not any(c.isalpha() for c in pw) or not any(c.isdigit() for c in pw):
        return "Use both letters and numbers."
    return None


def check_password(pw: str) -> None:
    problem = password_problem(pw)
    if problem:
        raise err(422, "WEAK_PASSWORD", problem)


def user_view(u: User) -> dict:
    school = u.school
    return {"id": u.id, "name": u.name, "email": u.email, "phone": u.phone, "role": u.role,
            "admin_role": admin_role(u) if u.role == "platform_admin" else None,
            "school": {"id": school.id, "name": school.name, "status": school.status} if school else None,
            "status": u.status, "must_change_password": u.must_change_password,
            "has_password": bool(u.password_hash), "google_linked": bool(u.google_sub),
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None}


# ---------- lockout ----------
def locked_minutes(u: User) -> int:
    until = aware(u.locked_until)
    if until and until > now():
        return max(1, int((until - now()).total_seconds() // 60) + 1)
    return 0


def record_failure(u: User) -> None:
    s = get_settings()
    u.failed_attempts = (u.failed_attempts or 0) + 1
    if u.failed_attempts >= s.login_max_failures:
        u.locked_until = now() + timedelta(minutes=s.login_lock_minutes)
        u.failed_attempts = 0


def record_success(u: User) -> None:
    u.failed_attempts = 0
    u.locked_until = None
    u.last_login_at = now()


# ---------- emailed links ----------
def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_link(db: Session, kind: str, *, user_id: str | None = None, signup_id: str | None = None) -> str:
    """A new single-use token; earlier unused tokens of the same kind for the same user stop working."""
    q = db.query(AuthToken).filter_by(kind=kind, used_at=None)
    q = q.filter_by(user_id=user_id) if user_id else q.filter_by(signup_id=signup_id)
    for old in q:
        old.used_at = now()
    raw = secrets.token_urlsafe(32)
    db.add(AuthToken(kind=kind, user_id=user_id, signup_id=signup_id, token_hash=_hash(raw),
                     expires_at=now() + LINK_TTL[kind]))
    return raw


def consume_link(db: Session, kind: str, raw: str, *, peek: bool = False) -> AuthToken:
    t = db.query(AuthToken).filter_by(token_hash=_hash(raw or ""), kind=kind).first()
    if t is None or t.used_at is not None:
        raise err(400, "LINK_INVALID", "This link is not valid or was already used. Ask for a new one.")
    if aware(t.expires_at) < now():
        raise err(400, "LINK_EXPIRED", "This link has expired. Ask for a new one.")
    if not peek:
        t.used_at = now()
    return t


# ---------- Google ----------
_jwks: jwt.PyJWKClient | None = None


def verify_google(id_token: str) -> dict:
    """The verified Google identity {sub, email, name}, or 401. Signature, audience, issuer and expiry are checked."""
    global _jwks
    client_id = get_settings().google_client_id
    if not client_id:
        raise err(503, "GOOGLE_DISABLED", "Google sign-in is not set up yet. Use your email and password.")
    if _jwks is None:
        _jwks = jwt.PyJWKClient("https://www.googleapis.com/oauth2/v3/certs", cache_keys=True)
    try:
        key = _jwks.get_signing_key_from_jwt(id_token).key
        claims = jwt.decode(id_token, key, algorithms=["RS256"], audience=client_id,
                            issuer=["https://accounts.google.com", "accounts.google.com"])
    except jwt.PyJWTError:
        raise err(401, "GOOGLE_INVALID", "Google sign-in could not be verified. Try again.")
    if not claims.get("email_verified"):
        raise err(401, "GOOGLE_EMAIL_UNVERIFIED", "Your Google email address is not verified.")
    return {"sub": claims["sub"], "email": normalize_email(claims["email"]), "name": claims.get("name") or ""}


# ---------- rate limits ----------
_hits: dict[tuple[str, str], deque] = defaultdict(deque)
_hits_lock = threading.Lock()


def rate_limit(bucket: str, key: str, limit: int, per_seconds: int) -> None:
    """Sliding-window limit per process. Enough for one server; a shared store is needed once there are several."""
    t = time.monotonic()
    with _hits_lock:
        q = _hits[(bucket, key)]
        while q and q[0] < t - per_seconds:
            q.popleft()
        if len(q) >= limit:
            raise err(429, "TOO_MANY_REQUESTS", "Too many attempts. Wait a few minutes and try again.")
        q.append(t)


def school_active(db: Session, u: User) -> bool:
    if not u.school_id:
        return True
    s = db.get(School, u.school_id)
    return s is not None and s.status == "ACTIVE"
