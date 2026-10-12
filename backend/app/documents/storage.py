"""Controlled file storage + upload validation. Client filenames are never used as paths."""
from __future__ import annotations
import zipfile
from io import BytesIO
from pathlib import Path
from fastapi import HTTPException, UploadFile
from ..config import get_settings

ALLOWED = {
    "pdf": ("application/pdf",),
    "png": ("image/png",),
    "jpg": ("image/jpeg",),
    "jpeg": ("image/jpeg",),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document",
             "application/octet-stream", "application/zip"),
}


def data_root() -> Path:
    return get_settings().data_path


def safe_join(base: Path, *parts: str) -> Path:
    base = base.resolve()
    p = base.joinpath(*parts).resolve()
    if base != p and base not in p.parents:
        raise HTTPException(400, "Invalid path")
    return p


def rel(path: Path) -> str:
    return str(Path(path).resolve().relative_to(data_root()))


def abs_path(relative: str) -> Path:
    return safe_join(data_root(), relative)


def doc_dir(kind: str, exam_id: str, doc_id: str, student_id: str | None = None) -> Path:
    if kind == "question-paper":
        parts = ("exams", exam_id, "question-paper", doc_id)
    elif kind == "answer-key":
        parts = ("exams", exam_id, "answer-key", doc_id)
    elif kind == "answer-sheet":
        parts = ("exams", exam_id, "answer-sheets", student_id or "unknown", doc_id)
    else:
        raise ValueError(kind)
    p = safe_join(data_root(), *parts)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _sniff(data: bytes) -> str | None:
    if data.startswith(b"%PDF"):
        return "pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(BytesIO(data)) as z:
                if "word/document.xml" in z.namelist():
                    return "docx"
        except zipfile.BadZipFile:
            return None
    return None


async def read_validated_upload(file: UploadFile, allowed: set[str]) -> tuple[bytes, str, str]:
    """Returns (bytes, extension, mime). Validates name, extension, size, MIME and magic bytes."""
    s = get_settings()
    name = (file.filename or "").strip()
    if not name or "/" in name or "\\" in name or ".." in name or "\x00" in name:
        raise HTTPException(400, "Invalid file name.")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in allowed:
        raise HTTPException(400, f"File type .{ext or '?'} is not accepted. Allowed: {', '.join(sorted(allowed)).upper()}.")
    limit = s.max_upload_mb * 1024 * 1024
    buf = bytearray()
    while chunk := await file.read(1024 * 1024):
        buf.extend(chunk)
        if len(buf) > limit:
            raise HTTPException(413, f"File is larger than {s.max_upload_mb} MB.")
    if not buf:
        raise HTTPException(400, "The uploaded file is empty.")
    if file.content_type and file.content_type not in ALLOWED[ext]:
        raise HTTPException(400, f"MIME type {file.content_type} does not match .{ext}.")
    kind = _sniff(bytes(buf[:4096]) if ext != "docx" else bytes(buf))
    canon = "jpg" if ext == "jpeg" else ext
    if kind != canon:
        raise HTTPException(400, f"File content does not look like a real .{ext} file.")
    mime = ALLOWED[ext][0]
    return bytes(buf), canon, mime
