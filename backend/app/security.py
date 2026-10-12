from __future__ import annotations
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from .config import get_settings
from .database import get_db
from .models import Teacher

_bearer = HTTPBearer(auto_error=False)
ALGO = "HS256"


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode()[:72], hashed.encode())
    except ValueError:
        return False


def create_token(teacher_id: str) -> str:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=s.access_token_minutes)
    return jwt.encode({"sub": teacher_id, "exp": exp}, s.jwt_secret, algorithm=ALGO)


def current_teacher(cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
                    token: str | None = None,
                    db: Session = Depends(get_db)) -> Teacher:
    unauth = HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "Sign in to continue."},
                           headers={"WWW-Authenticate": "Bearer"})
    raw_token = cred.credentials if cred else token
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
    return t
