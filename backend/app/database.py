from __future__ import annotations
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    eng = create_engine(f"sqlite:///{get_settings().data_path / 'adem.db'}", connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _pragmas(dbapi_conn, _):  # enforce FKs and WAL mode in SQLite
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    return eng


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
    logging.getLogger("adem").info("Database: %s", engine.url.database)
    Base.metadata.create_all(engine)
