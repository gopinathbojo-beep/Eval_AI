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
        _rename_legacy_account_tables()
        Base.metadata.create_all(engine)
        _add_missing_columns()
        _adopt_legacy_accounts()
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
_ADDED_COLUMNS = {"teachers": {"role": "VARCHAR(20) NOT NULL DEFAULT 'TEACHER'", "workspace_id": "VARCHAR(36)",
                              "must_change_password": "BOOLEAN NOT NULL DEFAULT FALSE",
                              "is_active": "BOOLEAN NOT NULL DEFAULT TRUE", "google_sub": "VARCHAR(255)",
                              "session_version": "INTEGER NOT NULL DEFAULT 0", "last_login_at": "DATETIME",
                              "approval_status": "VARCHAR(20) NOT NULL DEFAULT 'APPROVED'",
                              "registration_source": "VARCHAR(20) NOT NULL DEFAULT 'ADMIN'", "profile": "JSON",
                              "profile_completed_at": "DATETIME", "rejection_reason": "VARCHAR(500)",
                              "phone": "VARCHAR(30) NOT NULL DEFAULT ''", "admin_role": "VARCHAR(20)",
                              "email_verified_at": "DATETIME", "failed_attempts": "INTEGER NOT NULL DEFAULT 0",
                              "locked_until": "DATETIME", "created_by": "VARCHAR(36)"},
                 "workspaces": {"kind": "VARCHAR(10) NOT NULL DEFAULT 'SCHOOL'", "owner_id": "VARCHAR(36)",
                                "is_active": "BOOLEAN NOT NULL DEFAULT TRUE", "status": "VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'", "board": "VARCHAR(20) NOT NULL DEFAULT 'CBSE'",
                                "address": "TEXT NOT NULL DEFAULT ''", "city": "VARCHAR(100) NOT NULL DEFAULT ''",
                                "state": "VARCHAR(100) NOT NULL DEFAULT ''", "phone": "VARCHAR(30) NOT NULL DEFAULT ''",
                                "approved_at": "DATETIME", "approved_by": "VARCHAR(36)"},
                 "exam_questions": {"choice_group": "VARCHAR(50)", "answer_any": "INTEGER",
                                    "compulsory": "BOOLEAN NOT NULL DEFAULT FALSE"},
                 "exams": {"origin": "VARCHAR(20) NOT NULL DEFAULT 'TEACHER'"},
                 "audit_logs": {"ip": "VARCHAR(64) NOT NULL DEFAULT ''"},
                 "answer_keys": {"rubric": "JSON", "rubric_status": "VARCHAR(20) NOT NULL DEFAULT 'UNREVIEWED'"}}
for _table in ("classes", "subjects", "exams", "audit_logs", "verified_reference_examples"):
    _ADDED_COLUMNS.setdefault(_table, {})["workspace_id"] = "VARCHAR(36)"
_ADDED_COLUMNS["exams"].update({"standard_profile_id": "VARCHAR(40)", "standard_version": "VARCHAR(30)",
    "standard_options": "JSON", "standard_validation": "JSON"})
_ADDED_COLUMNS["exam_questions"]["structure"] = "JSON"
for _table in ("question_paper_documents", "answer_key_documents"):
    _ADDED_COLUMNS[_table] = {"extraction": "JSON"}


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


# ---------- local databases from before the account merge (users + schools) ----------
_ROLE = {"platform_admin": "ADMIN", "school_manager": "MANAGEMENT", "teacher": "TEACHER", "parent": "PARENT"}


def _rename_legacy_account_tables() -> None:
    """A local database made before the account merge keeps its accounts in users and schools. They become teachers
    and workspaces by renaming, which also points every foreign key at the new names (SQLite 3.26+)."""
    insp = inspect(engine)
    with engine.begin() as conn:
        if insp.has_table("users") and not insp.has_table("teachers"):
            conn.execute(text("ALTER TABLE users RENAME TO teachers"))
            logging.getLogger("adem").info("Database: users renamed to teachers")
        if insp.has_table("schools") and not insp.has_table("workspaces"):
            conn.execute(text("ALTER TABLE schools RENAME TO workspaces"))
            logging.getLogger("adem").info("Database: schools renamed to workspaces")


def _adopt_legacy_accounts() -> None:
    """Rows from the old users and schools tables in the merged columns: role names, active and approval status, the
    session version, the school as workspace (owned by its manager), a family workspace for each parent, and the
    workspace of every class, subject and exam. Idempotent: only rows still in the old form are touched."""
    insp = inspect(engine)
    if not insp.has_table("teachers") or "token_version" not in {c["name"] for c in insp.get_columns("teachers")}:
        return
    log = logging.getLogger("adem")
    with engine.begin() as conn:
        for old, new in _ROLE.items():
            conn.execute(text("UPDATE teachers SET role = :new, session_version = COALESCE(token_version, 0), "
                              "workspace_id = COALESCE(workspace_id, school_id), "
                              "is_active = CASE WHEN status IN ('suspended', 'removed') THEN FALSE ELSE TRUE END, "
                              "approval_status = CASE WHEN status = 'invited' THEN 'INVITED' ELSE 'APPROVED' END, "
                              # a parent's profile also needs the child (a class of their own); without one the web
                              # app asks for it
                              "profile_completed_at = COALESCE(profile_completed_at, CASE WHEN :new != 'PARENT' OR EXISTS "
                              "(SELECT 1 FROM classes c WHERE c.teacher_id = teachers.id) THEN created_at END) "
                              "WHERE role = :old"), {"old": old, "new": new})
        conn.execute(text("UPDATE teachers SET admin_role = COALESCE(admin_role, 'viewer') WHERE role = 'ADMIN'"))
        if "school_id" in {c["name"] for c in insp.get_columns("teachers")}:
            conn.execute(text("UPDATE workspaces SET kind = 'SCHOOL', owner_id = (SELECT t.id FROM teachers t "
                              "WHERE t.school_id = workspaces.id AND t.role = 'MANAGEMENT' ORDER BY t.created_at LIMIT 1) "
                              "WHERE owner_id IS NULL"))
        import uuid
        parents = conn.execute(text("SELECT id, name, created_at FROM teachers WHERE role = 'PARENT' AND workspace_id IS NULL")).all()
        for pid, name, created in parents:
            wid = str(uuid.uuid4())
            conn.execute(text("INSERT INTO workspaces (id, kind, name, owner_id, is_active, status, board, address, city, "
                              "state, phone, created_at) VALUES (:id, 'FAMILY', :name, :owner, TRUE, 'ACTIVE', 'CBSE', '', "
                              "'', '', '', :created)"), {"id": wid, "name": name, "owner": pid, "created": created})
            conn.execute(text("UPDATE teachers SET workspace_id = :w WHERE id = :p"), {"w": wid, "p": pid})
        for table in ("classes", "subjects", "exams"):
            conn.execute(text(f"UPDATE {table} SET workspace_id = (SELECT t.workspace_id FROM teachers t "
                              f"WHERE t.id = {table}.teacher_id) WHERE workspace_id IS NULL"))
        if parents:
            log.info("Database: %d parent account(s) given a family workspace", len(parents))

