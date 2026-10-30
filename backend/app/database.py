from __future__ import annotations
import logging
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.orm import Session
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


@event.listens_for(Session, "before_flush")
def _workspace_ownership(db, _context, _instances):
    from .models import Exam, SchoolClass, Subject, Teacher
    for row in db.new:
        if isinstance(row, (Exam, SchoolClass, Subject)) and not row.workspace_id:
            creator = db.get(Teacher, row.teacher_id)
            if creator:
                row.workspace_id = creator.workspace_id


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
_ADDED_COLUMNS = {"teachers": {"role": "VARCHAR(20) NOT NULL DEFAULT 'TEACHER'", "workspace_id": "VARCHAR(36)", "must_change_password": "BOOLEAN NOT NULL DEFAULT 0", "is_active": "BOOLEAN NOT NULL DEFAULT 1", "google_sub": "VARCHAR(255)",
                                "session_version": "INTEGER NOT NULL DEFAULT 0", "last_login_at": "DATETIME",
                                "approval_status": "VARCHAR(20) NOT NULL DEFAULT 'APPROVED'",
                                "registration_source": "VARCHAR(20) NOT NULL DEFAULT 'ADMIN'", "profile": "JSON",
                                "profile_completed_at": "DATETIME", "rejection_reason": "VARCHAR(500)"},
                 "exam_questions": {"choice_group": "VARCHAR(50)", "answer_any": "INTEGER",
                                     "compulsory": "BOOLEAN NOT NULL DEFAULT 0"},
                 "answer_keys": {"rubric": "JSON", "rubric_status": "VARCHAR(20) NOT NULL DEFAULT 'UNREVIEWED'"}}
for _table in ("classes", "subjects", "exams", "audit_logs", "verified_reference_examples"):
    _ADDED_COLUMNS.setdefault(_table, {})["workspace_id"] = "VARCHAR(36)"


def _add_missing_columns() -> None:
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in _ADDED_COLUMNS.items():
            if not insp.has_table(table):
                continue  # created later with all its columns
            have = {c["name"] for c in insp.get_columns(table)}
            for name, sql_type in cols.items():
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))
                    logging.getLogger("adem").info("Database: added %s.%s", table, name)
        if insp.has_table("teachers"):
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_teachers_google_sub ON teachers (google_sub)"))
