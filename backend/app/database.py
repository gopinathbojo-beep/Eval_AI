from __future__ import annotations
import logging
from sqlalchemy import create_engine, event, inspect, text
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
    _add_missing_columns()


# Columns added after a table first shipped. create_all never alters an existing table, so they are added here.
_ADDED_COLUMNS = {"exam_questions": {"choice_group": "VARCHAR(50)", "answer_any": "INTEGER",
                                     "compulsory": "BOOLEAN NOT NULL DEFAULT 0"}}


def _add_missing_columns() -> None:
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in _ADDED_COLUMNS.items():
            have = {c["name"] for c in insp.get_columns(table)}
            for name, sql_type in cols.items():
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))
                    logging.getLogger("adem").info("Database: added %s.%s", table, name)
