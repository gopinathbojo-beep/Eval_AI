from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from .config import get_settings
from .database import init_db
from .routes import answer_keys, core, documents, evaluations, questions

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="ADEM API", version="1.0.0", lifespan=lifespan)
    s = get_settings()
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in s.cors_origins.split(",") if o.strip()],
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

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

    for r in (core.router, documents.router, questions.router, answer_keys.router, evaluations.router):
        app.include_router(r)

    @app.get("/api/health")
    def health():
        return {"ok": True}

    return app


app = create_app()
