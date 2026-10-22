"""
Copy every row from the SQLite database (data/adem.db) into the PostgreSQL database named by DATABASE_URL.
Tables are created if missing; the target tables must be empty.
Usage:
    python backend/scripts/migrate_sqlite_to_postgres.py [path/to/adem.db]
"""

from __future__ import annotations
import os
import sys

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from sqlalchemy import create_engine, func, select

from app.config import get_settings
from app.database import Base, _make_engine
from app import models  # noqa: F401


def main():
    settings = get_settings()
    if not settings.database_url.startswith(("postgres://", "postgresql")):
        sys.exit("Set DATABASE_URL to your Supabase/Postgres connection string first (in backend/.env or the environment).")

    sqlite_path = sys.argv[1] if len(sys.argv) > 1 else str(settings.data_path / "adem.db")
    src = create_engine(f"sqlite:///{sqlite_path}")
    dst = _make_engine(settings.database_url)
    Base.metadata.create_all(dst)

    with src.connect() as s, dst.begin() as d:
        for table in Base.metadata.sorted_tables:          # parents before children, so FKs resolve
            if d.execute(select(func.count()).select_from(table)).scalar():
                sys.exit(f"Target table {table.name} is not empty; aborting.")
            src_cols = {c["name"] for c in src.dialect.get_columns(s, table.name)} if src.dialect.has_table(s, table.name) else set()
            if not src_cols:
                print(f"{table.name}: not in SQLite, skipped")
                continue
            cols = [c for c in table.columns if c.name in src_cols]
            rows = [dict(r._mapping) for r in s.execute(select(*cols))]
            # String(n) limits are enforced by Postgres but not SQLite; report overflows instead of failing mid-copy
            for c in cols:
                n = getattr(c.type, "length", None)
                if n and any(isinstance(r[c.name], str) and len(r[c.name]) > n for r in rows):
                    sys.exit(f"{table.name}.{c.name} has values longer than {n}; widen the column before migrating.")
            if rows:
                d.execute(table.insert(), rows)
            print(f"{table.name}: {len(rows)} rows")
    print("Done.")


if __name__ == "__main__":
    main()
