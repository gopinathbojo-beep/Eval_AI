from __future__ import annotations
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str | None = None):
    url = url or get_settings().database_url or f"sqlite:///{get_settings().data_path / 'adem.db'}"
    if not url.startswith("sqlite"):
        # Supabase hands out postgres:// / postgresql:// URLs; route them to the installed psycopg 3 driver
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                url = "postgresql+psycopg://" + url[len(prefix):]
        # prepare_threshold=None: Supabase's transaction pooler (port 6543) cannot use prepared statements.
        # Small pool: Supabase limits connections per project.
        return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5,
                             connect_args={"prepare_threshold": None})

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


def init_db():
    from . import models  # noqa: F401
    Base.metadata.create_all(engine)
    _migrate()


def _migrate():
    """create_all() never alters existing tables, so bring older databases up to the current models in place."""
    import sqlite3
    if engine.url.get_backend_name() != "sqlite" or not engine.url.database:
        return
    con = sqlite3.connect(engine.url.database, isolation_level=None)  # autocommit: PRAGMAs only apply outside a transaction
    try:
        cols = lambda t: {r[1]: r for r in con.execute(f"PRAGMA table_info({t})")}  # noqa: E731
        for table, new_cols in (("students", (("registration_number", "VARCHAR(50)"), ("section", "VARCHAR(20)"))),
                                ("exam_questions", (("k_level", "VARCHAR(2)"), ("k_level_source", "VARCHAR(10)"),
                                                    ("course_outcome", "VARCHAR(20)"))),
                                ("exams", (("files_purge_at", "DATETIME"), ("files_purged_at", "DATETIME"))),
                                ("school_profiles", (("active_report_template", "VARCHAR(60) NOT NULL DEFAULT 'preset:classic'"),
                                                     ("active_card_template", "VARCHAR(60) NOT NULL DEFAULT 'preset:classic'")))):
            have = cols(table)
            for name, ddl in new_cols:
                if name not in have:
                    con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        con.execute("CREATE INDEX IF NOT EXISTS ix_students_registration_number ON students (registration_number)")

        # answer sheets: student_id became nullable (sheets are uploaded before the student is known) and gained
        # `identity`. SQLite cannot relax NOT NULL, so rebuild the table, keeping every row and every id.
        old = "_answer_sheet_documents_old"
        has_old = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (old,)).fetchone()
        asd = cols("answer_sheet_documents")
        if not has_old and asd["student_id"][3] == 0 and "identity" in asd:
            return
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("PRAGMA legacy_alter_table=ON")  # keep evaluations' FK pointing at the table name, not the renamed copy
        if not has_old:
            con.execute("BEGIN")
            for idx in con.execute("PRAGMA index_list(answer_sheet_documents)").fetchall():
                if idx[3] == "c":  # explicitly created index; auto-indexes go with the table
                    con.execute(f"DROP INDEX {idx[1]}")
            con.execute(f"ALTER TABLE answer_sheet_documents RENAME TO {old}")
            con.execute("COMMIT")
            Base.metadata.tables["answer_sheet_documents"].create(engine)
        common = [c for c in cols(old) if c in cols("answer_sheet_documents")]
        col_list = ", ".join(common)
        con.execute("BEGIN")
        con.execute(f"INSERT INTO answer_sheet_documents ({col_list}) SELECT {col_list} FROM {old}")
        con.execute(f"DROP TABLE {old}")
        con.execute("COMMIT")
    finally:
        con.close()
