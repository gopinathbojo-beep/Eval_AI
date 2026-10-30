from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from .config import get_settings
from .database import init_db
from .routes import admin, answer_keys, core, documents, evaluations, google_auth, questions, reference_collection, registration, school, management, uploads
from .services.admin_accounts import ensure_owner
from .services.exam_files import start_purge_scheduler
from .services.recovery import recover_interrupted_jobs
from sqlalchemy import text
from .database import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class PrivateAccessLog(logging.Filter):
    def filter(self, record):
        # OAuth authorization codes and other query values must not enter access logs.
        if isinstance(record.args, tuple) and len(record.args) == 5:
            values = list(record.args)
            values[2] = str(values[2]).split("?", 1)[0]
            record.args = tuple(values)
        return True


logging.getLogger("uvicorn.access").addFilter(PrivateAccessLog())


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if get_settings().storage_provider == "supabase":
        from .documents.cloud import SupabaseStorage
        if SupabaseStorage().bucket_info().get("public") is not False:
            raise RuntimeError("The document storage bucket must be private.")
    with SessionLocal() as db:
        ensure_owner(db)
    if get_settings().durable_jobs:
        from .services.persistent_queue import start_recovery
        start_recovery()
    else:
        recover_interrupted_jobs()
    start_purge_scheduler()
    yield


def create_app() -> FastAPI:
    s = get_settings()
    production = s.environment == "production"
    app = FastAPI(title="ADEM API", version="1.0.0", lifespan=lifespan,
                  docs_url=None if production else "/docs", redoc_url=None if production else "/redoc",
                  openapi_url=None if production else "/openapi.json")
    if production:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=[h.strip() for h in s.allowed_hosts.split(",") if h.strip()])
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in s.cors_origins.split(",") if o.strip()],
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(SessionMiddleware, secret_key=s.jwt_secret, session_cookie="eval_oauth", max_age=600,
                       same_site="lax", https_only=s.cookie_secure, path="/api/auth/google")

    @app.middleware("http")
    async def private_responses(request: Request, call_next):
        from .actor import actor_id
        from .security import SESSION_COOKIE, ALGO
        import jwt
        authorization = request.headers.get("authorization", "").split(" ", 1)
        raw = authorization[1] if len(authorization) == 2 and authorization[0].lower() == "bearer" else request.cookies.get(SESSION_COOKIE)
        raw = raw or (request.query_params.get("token") if not production else None)
        actor = None
        if raw:
            try:
                actor = jwt.decode(raw, s.jwt_secret, algorithms=[ALGO]).get("sub")
            except jwt.PyJWTError:
                pass
        context = actor_id.set(actor)
        try:
            response = await call_next(request)
        finally:
            actor_id.reset(context)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_exc(_: Request, exc: StarletteHTTPException):
        d = exc.detail
        body = d if isinstance(d, dict) and "code" in d else {"code": "ERROR", "message": str(d)}
        return JSONResponse(body, status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def val_exc(_: Request, exc: RequestValidationError):
        issues = [{"question": ".".join(str(x) for x in e["loc"][1:]) or "request", "reason": e["msg"]} for e in exc.errors()]
        return JSONResponse({"code": "VALIDATION_ERROR", "message": "Some fields are missing or invalid.", "issues": issues},
                            status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        logging.getLogger("adem").exception("Unhandled error")
        return JSONResponse({"code": "SERVER_ERROR", "message": "Something went wrong on the server. Details are in the server log."},
                            status_code=500)

    from .documents.cloud import StorageError
    @app.exception_handler(StorageError)
    async def storage_error(_: Request, exc: StorageError):
        return JSONResponse({"code": "STORAGE_UNAVAILABLE", "message": str(exc)}, status_code=503)

    for r in (core.router, documents.router, questions.router, answer_keys.router, evaluations.router, reference_collection.router,
              school.router, admin.router, google_auth.router, registration.router, management.router, uploads.router):
        app.include_router(r)

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/ready")
    def ready():
        # AI availability is reported separately: manual review still works without the GPU.
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
            return {"ok": True}
        except Exception:
            return JSONResponse({"ok": False}, status_code=503)

    return app


app = create_app()
