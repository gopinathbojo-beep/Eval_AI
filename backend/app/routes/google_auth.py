"""Google OIDC authorization code flow with state, nonce and PKCE managed by Authlib."""
from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import urlsplit

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Teacher
from ..security import is_admin, set_session_cookie, current_account
from ..services.audit import audit

router = APIRouter(prefix="/api/auth")


@lru_cache
def google_client():
    s = get_settings()
    oauth = OAuth()
    return oauth.register("google", client_id=s.google_client_id, client_secret=s.google_client_secret,
                          server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
                          client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256", "timeout": 15})


def public_origin() -> str:
    uri = urlsplit(get_settings().google_redirect_uri)
    return f"{uri.scheme}://{uri.netloc}"


def login_error(code: str):
    return RedirectResponse(f"{public_origin()}/login?oauth_error={code}", status_code=303)


@router.get("/providers")
def providers():
    s = get_settings()
    return {"google": bool(s.google_client_id and s.google_client_secret),
            "google_start_url": f"{public_origin()}/api/auth/google/start"}


@router.get("/google/start")
async def google_start(request: Request):
    s = get_settings()
    if not s.google_client_id or not s.google_client_secret:
        return login_error("not_configured")
    # Always set the OAuth cookie on the callback hostname, including when opened via 127.0.0.1.
    if request.headers.get("host") != urlsplit(s.google_redirect_uri).netloc:
        return RedirectResponse(f"{public_origin()}/api/auth/google/start", status_code=303)
    request.session.clear()
    try:
        return await google_client().authorize_redirect(request, s.google_redirect_uri, prompt="select_account")
    except Exception:
        request.session.clear()
        return login_error("unavailable")


@router.get("/google/link")
async def google_link(request: Request, user: Teacher = Depends(current_account)):
    request.session.clear()
    request.session["link_user_id"] = user.id
    request.session["link_version"] = user.session_version
    return await google_client().authorize_redirect(request, get_settings().google_redirect_uri, prompt="select_account")


def teacher_for_google(db: Session, claims: dict) -> Teacher | None:
    # Only verified OIDC claims are supplied by authorize_access_token(), never client-submitted email.
    if claims.get("email_verified") is not True or not claims.get("sub"):
        return None
    email = str(claims.get("email", "")).strip().lower()
    teacher = db.query(Teacher).filter_by(email=email).first()
    if not teacher:
        teacher = Teacher(name=str(claims.get("name") or email.split("@")[0])[:200], email=email,
                          password_hash="!google-login-required", role="UNASSIGNED", approval_status="APPROVED", registration_source="PUBLIC")
        db.add(teacher)
        db.flush()
        audit(db, exam_id=None, teacher_id=teacher.id, entity_type="teacher", entity_id=teacher.id, action="teacher_registered")
    if not teacher.is_active:
        return None
    if teacher.google_sub and teacher.google_sub != claims["sub"]:
        return None
    bound = db.query(Teacher).filter_by(google_sub=claims["sub"]).first()
    if bound and bound.id != teacher.id:
        return None
    if not teacher.google_sub and not teacher.password_hash.startswith("!"):
        return None  # Password accounts must link Google from their authenticated account settings.
    teacher.google_sub = claims["sub"]
    return teacher


@router.get("/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    try:
        token = await google_client().authorize_access_token(request)
        claims = dict(token.get("userinfo") or {})
        link_id = request.session.pop("link_user_id", None)
        link_version = request.session.pop("link_version", None)
        if link_id:
            teacher = db.get(Teacher, link_id)
            if (not teacher or not teacher.is_active or teacher.session_version != link_version
                    or claims.get("email_verified") is not True or not claims.get("sub")
                    or str(claims.get("email", "")).lower() != teacher.email):
                return login_error("not_allowed")
            teacher.google_sub = claims["sub"]
        else:
            teacher = teacher_for_google(db, claims)
        if not teacher:
            db.rollback()
            return login_error("not_allowed")
        if teacher.workspace_id:
            from ..models import Workspace
            workspace = db.get(Workspace, teacher.workspace_id)
            if not workspace or not workspace.is_active:
                db.rollback()
                return login_error("not_allowed")
        teacher.last_login_at = datetime.now(timezone.utc)
        audit(db, exam_id=None, teacher_id=teacher.id, entity_type="teacher", entity_id=teacher.id, action="google_login")
        db.commit()
        destination = "/admin" if is_admin(teacher) else "/account" if teacher.must_change_password else "/onboarding" if not teacher.profile_completed_at else "/dashboard"
        response = RedirectResponse(f"{public_origin()}{destination}", status_code=303)
        set_session_cookie(response, teacher)
        return response
    except Exception:
        # Never log provider exceptions: they can include credentials, codes or tokens.
        db.rollback()
        return login_error("failed")
    finally:
        request.session.clear()
