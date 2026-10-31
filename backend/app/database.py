from __future__ import annotations
import logging
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url
from .config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    settings = get_settings()
<<<<<<< 7c662e7
    if settings.database_url:  # e.g. Postgres on RDS
        return create_engine(settings.database_url, pool_pre_ping=True, pool_size=10, max_overflow=10)
    eng = create_engine(f"sqlite:///{settings.data_path / 'adem.db'}", connect_args={"check_same_thread": False})
=======
    url = make_url(settings.database_url or f"sqlite:///{settings.data_path / 'adem.db'}")
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    if url.get_backend_name() == "postgresql":
        connect_args = {"connect_timeout": 10}
        # Supabase/Prisma examples include this URL hint; libpq does not accept it.
        # Transaction poolers also require prepared statements to be disabled.
        pooled = url.query.get("pgbouncer", "").lower() == "true" or url.port == 6543
        url = url.difference_update_query(["pgbouncer"])
        if pooled:
            connect_args["prepare_threshold"] = None
        if "sslmode" not in url.query:
            connect_args["sslmode"] = settings.database_sslmode
        return create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=2,
                             pool_recycle=300, connect_args=connect_args, hide_parameters=True)
    if url.get_backend_name() != "sqlite":
        raise ValueError("DATABASE_URL must use PostgreSQL or SQLite.")
    eng = create_engine(url, connect_args={"check_same_thread": False})
>>>>>>> kishore/Version2.0

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
    logging.getLogger("adem").info("Database driver: %s", engine.dialect.name)
    if get_settings().auto_migrate:
        migrate_database()
    elif engine.dialect.name == "sqlite":
        Base.metadata.create_all(engine)
        _add_missing_columns()
    else:
        # Cloud schemas are versioned; never silently mutate them with create_all.
        with engine.connect() as connection:
            connection.execute(text("SELECT version_num FROM alembic_version"))


def migrate_database():
    from alembic.config import Config
    from alembic import command
    from pathlib import Path
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(786230014)"))
            inspector = inspect(connection)
            if inspector.has_table("teachers") and not inspector.has_table("alembic_version"):
                raise RuntimeError("Existing unversioned application tables require a reviewed migration. They were not modified.")
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


# Columns added after a table first shipped. create_all never alters an existing table, so they are added here.
<<<<<<< 7c662e7
_ADDED_COLUMNS = {"exam_questions": {"choice_group": "VARCHAR(50)", "answer_any": "INTEGER",
                                     "compulsory": "BOOLEAN NOT NULL DEFAULT FALSE"},
=======
_ADDED_COLUMNS = {"teachers": {"role": "VARCHAR(20) NOT NULL DEFAULT 'TEACHER'", "workspace_id": "VARCHAR(36)", "must_change_password": "BOOLEAN NOT NULL DEFAULT 0", "is_active": "BOOLEAN NOT NULL DEFAULT 1", "google_sub": "VARCHAR(255)",
                                "session_version": "INTEGER NOT NULL DEFAULT 0", "last_login_at": "DATETIME",
                                "approval_status": "VARCHAR(20) NOT NULL DEFAULT 'APPROVED'",
                                "registration_source": "VARCHAR(20) NOT NULL DEFAULT 'ADMIN'", "profile": "JSON",
                                "profile_completed_at": "DATETIME", "rejection_reason": "VARCHAR(500)"},
                 "exam_questions": {"choice_group": "VARCHAR(50)", "answer_any": "INTEGER",
                                     "compulsory": "BOOLEAN NOT NULL DEFAULT 0"},
>>>>>>> kishore/Version2.0
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
