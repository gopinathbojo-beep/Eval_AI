"""Back up and optionally remove every exam while preserving account/workspace data.

Run from ``backend`` only after the API and every worker have been stopped.  Deletion
is deliberately gated by two explicit switches; the default operation is backup-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.database import SessionLocal, engine
from app.documents.cloud import SupabaseStorage
from app.models import BackgroundJob, Evaluation, Exam
from app.routes.core import cascade_delete_exam_records


CONFIRMATION = "DELETE-ALL-EXAMS"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_postgres_tools() -> tuple[str, str]:
    dump = shutil.which("pg_dump")
    restore = shutil.which("pg_restore")
    if not dump or not restore:
        raise RuntimeError("pg_dump and pg_restore must be installed and on PATH before backup or deletion.")
    return dump, restore


def database_backup(directory: Path, dump: str, restore: str) -> Path:
    settings = get_settings()
    if engine.dialect.name != "postgresql":
        raise RuntimeError("The production reset requires a PostgreSQL DATABASE_URL.")
    destination = directory / "database.dump"
    subprocess.run([dump, "--format=custom", "--file", str(destination), settings.database_url], check=True)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError("pg_dump did not create a non-empty backup.")
    # Parsing the archive proves that pg_restore can read its catalog before deletion.
    listing = subprocess.run([restore, "--list", str(destination)], check=True, capture_output=True, text=True)
    (directory / "database-archive.list").write_text(listing.stdout, encoding="utf-8")
    return destination


def storage_backup(directory: Path) -> list[dict]:
    storage = SupabaseStorage()
    objects = storage.keys("exams")
    root = directory / "storage" / "exams"
    manifest: list[dict] = []
    for key in objects:
        data = storage.get(key)
        if data is None:
            raise RuntimeError(f"Storage object disappeared during backup: {key}")
        relative = key.removeprefix("exams/")
        destination = root / Path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        digest = sha256(data)
        if sha256(destination.read_bytes()) != digest:
            raise RuntimeError(f"Backup checksum verification failed: {key}")
        manifest.append({"key": key, "bytes": len(data), "sha256": digest})
    (directory / "storage-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def write_record(directory: Path, exam_ids: list[str], objects: list[dict]) -> None:
    settings = get_settings()
    record = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "database_archive": str((directory / "database.dump").resolve()),
        "storage_archive": str((directory / "storage").resolve()),
        "storage_bucket": settings.supabase_storage_bucket,
        "exam_ids": exam_ids,
        "storage_objects": len(objects),
    }
    (directory / "backup-record.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    (directory / "RESTORE.txt").write_text(
        "PostgreSQL (restore into a reviewed empty/recovery database):\n"
        f'pg_restore --clean --if-exists --no-owner --dbname "$RECOVERY_DATABASE_URL" "{record["database_archive"]}"\n\n'
        "Supabase Storage: upload each file under storage/exams/ to the private bucket using its key from "
        "storage-manifest.json, then verify the recorded SHA-256 checksum.\n",
        encoding="utf-8",
    )


def delete_exams(exam_ids: list[str]) -> None:
    with SessionLocal() as db:
        active_jobs = db.query(BackgroundJob).filter(BackgroundJob.status.in_(["QUEUED", "RUNNING"])).count()
        running_evaluations = db.query(Evaluation).filter_by(run_status="RUNNING").count()
        if active_jobs or running_evaluations:
            raise RuntimeError("Queued/running work still exists. Stop API/workers and drain or cancel jobs first.")
        try:
            for exam_id in exam_ids:
                cascade_delete_exam_records(db, exam_id)
            db.commit()
        except Exception:
            db.rollback()
            raise
        if db.query(Exam).count() != 0:
            raise RuntimeError("Exam reset verification failed: exams remain in the database.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--delete", action="store_true", help="Delete after both backups pass verification.")
    parser.add_argument("--maintenance-confirmed", action="store_true", help="Confirm API and workers are stopped.")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    if args.delete and (not args.maintenance_confirmed or args.confirm != CONFIRMATION):
        raise SystemExit(f"Deletion requires --maintenance-confirmed --confirm {CONFIRMATION}")

    directory = args.backup_dir.resolve()
    if directory.exists() and any(directory.iterdir()):
        raise SystemExit("Backup directory must be new or empty.")
    directory.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        exam_ids = [row[0] for row in db.query(Exam.id).order_by(Exam.created_at).all()]
    dump, restore = require_postgres_tools()
    database_backup(directory, dump, restore)
    objects = storage_backup(directory)
    write_record(directory, exam_ids, objects)
    print(f"Verified backup: {len(exam_ids)} exams, {len(objects)} storage objects -> {directory}")
    if args.delete:
        delete_exams(exam_ids)
        print("Exam reset complete. Account, workspace, roster and profile data were preserved.")
    else:
        print("Backup-only mode: no records or files were deleted.")


if __name__ == "__main__":
    main()
