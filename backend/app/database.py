from __future__ import annotations
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str | None = None):
    url = url or f"sqlite:///{get_settings().data_path / 'adem.db'}"
    eng = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _fk(dbapi_conn, _):  # enforce FKs and WAL mode in SQLite
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


# Columns added after the first release. create_all() never alters existing tables, so they are added here.
_ADDED_COLUMNS = [
    ("answer_keys", "mapping_candidate_details", "JSON NOT NULL DEFAULT '[]'"),
    ("answer_keys", "mapping_confirmed", "BOOLEAN NOT NULL DEFAULT 0"),
    ("student_answers", "mapping_candidate_details", "JSON NOT NULL DEFAULT '[]'"),
]


def _add_missing_columns(eng) -> None:
    insp = inspect(eng)
    with eng.begin() as conn:
        for table, column, ddl in _ADDED_COLUMNS:
            if insp.has_table(table) and column not in {c["name"] for c in insp.get_columns(table)}:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def init_db():
    from . import models  # noqa: F401
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)
