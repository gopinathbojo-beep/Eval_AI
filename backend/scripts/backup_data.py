"""Offline DATA_DIR backup/restore. Stop the API first so files match the database."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tarfile
import tempfile


def check_database(path: Path) -> None:
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Database integrity check failed")


def backup(source: Path, destination: Path) -> Path:
    source, destination = source.resolve(), destination.resolve()
    if destination == source or source in destination.parents:
        raise ValueError("Backup destination must be outside DATA_DIR")
    if not (source / "adem.db").is_file():
        raise ValueError("No adem.db found in DATA_DIR")
    check_database(source / "adem.db")
    destination.mkdir(parents=True, exist_ok=True)
    name = f"eval-ai-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.tar.gz"
    archive = destination / name
    partial = archive.with_suffix(".partial")
    try:
        with tempfile.TemporaryDirectory() as scratch:
            snapshot = Path(scratch) / "adem.db"
            with closing(sqlite3.connect((source / "adem.db").as_uri() + "?mode=ro", uri=True)) as db:
                with closing(sqlite3.connect(snapshot)) as target:
                    db.backup(target)
            with os.fdopen(os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as output:
                with tarfile.open(fileobj=output, mode="w:gz") as tar:
                    for path in source.rglob("*"):
                        if path.is_symlink():
                            raise ValueError(f"Symlink in DATA_DIR: {path.name}")
                        relative = path.relative_to(source).as_posix()
                        if relative in {"adem.db", "adem.db-wal", "adem.db-shm"}:
                            continue
                        tar.add(path, arcname=relative, recursive=False)
                    tar.add(snapshot, arcname="adem.db")
            partial.replace(archive)
        return archive
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


def restore(archive: Path, target: Path) -> None:
    target = target.resolve()
    target.mkdir(parents=True, exist_ok=True)
    if any(target.iterdir()):
        raise ValueError("Restore requires an empty DATA_DIR; existing data will not be overwritten")
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        seen = set()
        for member in members:
            name = PurePosixPath(member.name)
            if (name.is_absolute() or ".." in name.parts or "\\" in member.name or ":" in member.name
                    or not (member.isfile() or member.isdir()) or member.name in seen):
                raise ValueError("Unsafe or duplicate archive member")
            seen.add(member.name)
        with tempfile.TemporaryDirectory(prefix=".restore-", dir=target) as scratch:
            stage = Path(scratch)
            for member in members:
                output = stage.joinpath(*PurePosixPath(member.name).parts)
                if member.isdir():
                    output.mkdir(parents=True, exist_ok=True)
                else:
                    output.parent.mkdir(parents=True, exist_ok=True)
                    with tar.extractfile(member) as src, output.open("xb") as dst:
                        shutil.copyfileobj(src, dst)
                    output.chmod(0o600)
            check_database(stage / "adem.db")
            for path in stage.iterdir():
                shutil.move(str(path), str(target / path.name))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="Backup directory, or an archive when --restore is set")
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    data = Path(os.environ.get("DATA_DIR", "../data"))
    if args.restore:
        restore(args.path, data)
        print("Restore completed. Verify the application before opening traffic.")
    else:
        archive = backup(data, args.path)
        with archive.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        print(f"{digest}  {archive}")


if __name__ == "__main__":
    main()
