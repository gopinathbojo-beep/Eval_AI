from __future__ import annotations
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    url = get_settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL is empty in backend/.env (use the Supabase transaction pooler string).")
    # Supabase hands out postgres:// / postgresql:// URLs; route them to the installed psycopg 3 driver
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg://" + url[len(prefix):]
    # prepare_threshold=None: Supabase's transaction pooler (port 6543) cannot use prepared statements.
    # Small pool: Supabase limits connections per project.
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5,
                         connect_args={"prepare_threshold": None})


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401
    logging.getLogger("adem").info("Database: %s", engine.url.host)
    Base.metadata.create_all(engine)
