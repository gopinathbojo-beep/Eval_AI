"""Render uploads to page images. Originals are never touched; page PNGs go to pages/, OCR copies to processed/."""
from __future__ import annotations
import shutil
import subprocess
import tempfile
from pathlib import Path
import pymupdf
from PIL import Image, ImageOps
from ..config import get_settings
from .preprocessing import make_ocr_copy

Image.MAX_IMAGE_PIXELS = 400_000_000


class RenderError(Exception):
    pass


def _docx_to_pdf(src: Path, out_dir: Path) -> Path:
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe:
        raise RenderError("DOCX files need LibreOffice (soffice) installed on this machine to be rendered. "
                          "Install LibreOffice or upload the document as PDF.")
    with tempfile.TemporaryDirectory() as td:
        try:
            subprocess.run([exe, "--headless", "--convert-to", "pdf", "--outdir", td, str(src)],
                           check=True, capture_output=True, timeout=180)
        except (subprocess.SubprocessError, OSError) as e:
            raise RenderError(f"DOCX conversion failed: {e}") from e
        produced = list(Path(td).glob("*.pdf"))
        if not produced:
            raise RenderError("DOCX conversion produced no PDF.")
        dest = out_dir / "converted-from-docx.pdf"
        shutil.copy(produced[0], dest)
        return dest


def render_document(src: Path, ext: str, work_dir: Path) -> list[dict]:
    """Returns page metadata list. `src` is the untouched original."""
    s = get_settings()
    pages_dir = work_dir / "pages"
    proc_dir = work_dir / "processed"
    pages_dir.mkdir(parents=True, exist_ok=True)
    proc_dir.mkdir(parents=True, exist_ok=True)
    meta: list[dict] = []

    def finish(n: int, img: Image.Image):
        name = f"page-{n:03d}.png"
        page_path = pages_dir / name
        img.save(page_path, "PNG")
        ocr_path, info = make_ocr_copy(img, proc_dir / name, s.ocr_max_side)
        meta.append({
            "page_number": n, "width": img.width, "height": img.height,
            "source_file": str(page_path.relative_to(s.data_path)),
            "processed_file": str(ocr_path.relative_to(s.data_path)),
            "ocr_width": info["ocr_width"], "ocr_height": info["ocr_height"],
            "content_bbox": info["content_bbox"],
            "ocr_status": "PENDING", "ocr_error": None,
        })

    if ext == "docx":
        src = _docx_to_pdf(src, work_dir)
        ext = "pdf"
    if ext == "pdf":
        try:
            doc = pymupdf.open(src)
        except Exception as e:
            raise RenderError(f"Cannot open PDF: {e}") from e
        if doc.is_encrypted:
            raise RenderError("PDF is password protected.")
        if doc.page_count == 0:
            raise RenderError("PDF has no pages.")
        zoom = s.pdf_render_dpi / 72.0
        for i, page in enumerate(doc, start=1):
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            finish(i, img)
        doc.close()
    elif ext in ("png", "jpg"):
        try:
            img = Image.open(src)
            img = ImageOps.exif_transpose(img).convert("RGB")  # honours camera orientation only
        except Exception as e:
            raise RenderError(f"Cannot open image: {e}") from e
        finish(1, img)
    else:
        raise RenderError(f"Unsupported type {ext}")
    return meta
