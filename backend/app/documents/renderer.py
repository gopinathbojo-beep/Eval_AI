"""Render uploads to page images. Originals are never touched; page PNGs go to pages/, OCR copies to processed/."""
from __future__ import annotations
import shutil
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
import pymupdf
from PIL import Image, ImageOps
from ..config import get_settings
from .preprocessing import make_ocr_copy
from .storage import rel

Image.MAX_IMAGE_PIXELS = 400_000_000


class RenderError(Exception):
    pass


_SUPERSCRIPT = str.maketrans("0123456789+-−=()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻⁼⁽⁾ⁿ")
_SUBSCRIPT = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


@dataclass
class _Span:
    text: str
    x0: float
    x1: float
    cy: float
    size: float


def _plain(t: str) -> str:
    """Math italic letters (𝑥, 𝜋, ℎ) as ordinary ones (x, π, h); everything else unchanged."""
    return "".join(unicodedata.normalize("NFKC", c) if 0x1D400 <= ord(c) <= 0x1D7FF or c == "ℎ" else c for c in t)


def _wrap(t: str) -> str:
    return f"({t})" if len(t) > 1 and any(c in t for c in " +-−×÷/") else t


def _raised(t: str) -> str:
    return t.translate(_SUPERSCRIPT) if all(c in "0123456789+-−=()n" for c in t) else f"^{_wrap(t)}"


def _lowered(t: str) -> str:
    return t.translate(_SUBSCRIPT) if t.isdigit() else f"_{t}" if t.isalnum() else _wrap(t)


def _linear(spans: list[_Span]) -> str:
    """One visual line as text. Word/PDF equations lay fractions out as a numerator above the line and a
    denominator below it, and exponents as small raised text: these become 'num/den', '²' or '^(...)'."""
    if not spans:
        return ""
    ref = max(spans, key=lambda s: (bool(s.text.strip()), round(s.size, 1), len(s.text.strip())))

    def on_line(s: _Span) -> bool:  # smaller text needs only a slight shift to be a raised/lowered piece
        return (not s.text.strip()  # a space's box says nothing about its level
                or abs(s.cy - ref.cy) <= (0.25 if s.size >= 0.9 * ref.size else 0.15) * ref.size)

    base = [s for s in spans if on_line(s)]
    off = sorted((s for s in spans if not on_line(s)), key=lambda s: s.x0)
    groups: list[list[_Span]] = []  # raised/lowered pieces that touch horizontally belong together
    for s in off:
        if groups and s.x0 <= max(g.x1 for g in groups[-1]) + 0.5:
            groups[-1].append(s)
        else:
            groups.append([s])
    items = [(s.x0, s.x1, s.text, True) for s in base]  # (start, end, text, on the line)
    for g in groups:
        up = [s for s in g if s.cy < ref.cy]
        down = [s for s in g if s.cy > ref.cy]
        num, den = _linear(up).strip(), _linear(down).strip()
        if num and den:
            t = f"{_wrap(num)}/{_wrap(den)}"
        else:
            t = _raised(num) if num else _lowered(den)
        items.append((min(s.x0 for s in g), max(s.x1 for s in g), t, False))
    out, prev = [], None
    for item in sorted(items, key=lambda i: i[0]):
        # words drawn as separate pieces with a gap and no space character ("Marks" "Awarded"): the gap is a space
        if (prev and prev[3] and item[3] and item[0] - prev[1] > 0.2 * ref.size
                and not prev[2].endswith(" ") and not item[2].startswith(" ")):
            out.append(" ")
        out.append(item[2])
        prev = item
    return "".join(out)


def _block_lines(spans: list[_Span]) -> list[str]:
    rows: list[list[_Span]] = []
    for s in sorted(spans, key=lambda s: s.cy):
        if rows and s.cy - rows[-1][0].cy <= 0.3 * max(s.size, rows[-1][0].size):
            rows[-1].append(s)
        else:
            rows.append([s])
    # A short row just above/below a fuller one (numerators, denominators, exponents) belongs to that line;
    # ordinary lines are at least ~1 font size apart.
    # Fuller rows claim them first; a claimed row extends its line, so an exponent above a numerator joins too.
    chars = [sum(len(s.text.strip()) for s in r) for r in rows]
    owner = list(range(len(rows)))
    size = [max(s.size for s in r) for r in rows]
    inked = [[s for s in r if s.text.strip()] or r for r in rows]  # a trailing space says nothing about a row's extent
    x0 = [min(s.x0 for s in r) for r in inked]
    x1 = [max(s.x1 for s in r) for r in inked]
    changed = True
    while changed:
        changed = False
        for i in sorted(range(len(rows)), key=lambda k: chars[k]):
            if owner[i] != i or any(owner[k] == i for k in range(len(rows)) if k != i):
                continue  # already attached, or already owns pieces
            best = None
            for j in range(len(rows)):
                o = owner[j]
                # an exponent may hang past the line's last letter by about one character ("b³")
                if (o != i and chars[o] > chars[i] and abs(rows[j][0].cy - rows[i][0].cy) < 0.85 * size[o]
                        and x0[o] - 2 <= x0[i] and x1[i] <= x1[o] + size[o]
                        and (best is None or abs(rows[j][0].cy - rows[i][0].cy) < best[0])):
                    best = (abs(rows[j][0].cy - rows[i][0].cy), o)
            if best:
                owner[i], changed = best[1], True
    return [_linear([s for k, r in enumerate(rows) if owner[k] == i for s in r])
            for i in range(len(rows)) if owner[i] == i]


def page_text(page) -> str:
    """Plain page text like page.get_text(), but with equations kept readable from their layout: superscripts
    ('2³ + 4³', not '23 + 43') and fractions ('(2/3)^(−2)', '1/x²') instead of numbers stacked on separate lines."""
    try:
        blocks = page.get_text("dict")["blocks"]
    except Exception:
        return page.get_text()
    # Word puts each equation piece in its own block, so lines are rebuilt across the whole page
    spans = [_Span(_plain(s["text"]), s["bbox"][0], s["bbox"][2], (s["bbox"][1] + s["bbox"][3]) / 2, s["size"])
             for b in blocks if b.get("type") == 0
             for line in b.get("lines", []) for s in line.get("spans", []) if s.get("text")]
    return "\n".join(_block_lines(spans)) + "\n"


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

    def finish(n: int, img: Image.Image, page_text: str | None = None):
        name = f"page-{n:03d}.png"
        page_path = pages_dir / name
        img.save(page_path, "PNG")
        ocr_path, info = make_ocr_copy(img, proc_dir / name, s.ocr_max_side)
        entry = {
            "page_number": n, "width": img.width, "height": img.height,
            "source_file": rel(page_path),
            "processed_file": rel(ocr_path),
            "ocr_width": info["ocr_width"], "ocr_height": info["ocr_height"],
            "content_bbox": info["content_bbox"],
            "ocr_status": "PENDING", "ocr_error": None,
        }
        if page_text:
            entry["page_text"] = page_text
        meta.append(entry)

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
            finish(i, img, page_text=page_text(page))
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
