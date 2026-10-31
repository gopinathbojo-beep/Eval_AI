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


def _block_rows(spans: list[_Span]) -> list[tuple[float, list[_Span]]]:
    """The visual lines of some text, each as (its height on the page, its spans): a fraction's numerator and
    denominator and an exponent belong to the line they sit on."""
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
    # a row that is only the word "OR" (between a part's alternatives) is a line of its own, never a fraction piece
    alone = {k for k, r in enumerate(rows) if "".join(s.text for s in r).strip().upper() == "OR"}
    x0 = [min(s.x0 for s in r) for r in inked]
    x1 = [max(s.x1 for s in r) for r in inked]
    cy = [sum(s.cy for s in r) / len(r) for r in inked]  # where its ink sits (a stray space may sit higher)
    # Fractions stacked over each other just above and just below a line, at the same distance, are that line's
    # numerators and denominators, even when they start before the line's first symbol ("sinθ/cosθ = 4/3") or are
    # longer than it ("√5 = (p − 2q)/3q"); ordinary lines are further apart than this
    for j in range(len(rows)):
        if owner[j] != j or not chars[j]:  # a row of spaces is no line
            continue
        for a in range(j):
            for b in range(j + 1, len(rows)):
                da, db = cy[j] - cy[a], cy[b] - cy[j]
                if (not {a, b, j} & alone and chars[a] and chars[b] and owner[a] == a and owner[b] == b and 0.3 * size[j] < da < 0.85 * size[j]
                        and 0.3 * size[j] < db < 0.85 * size[j] and abs(da - db) < 0.35 * size[j]
                        and max(size[a], size[b]) <= size[j] * 1.05
                        and x0[a] < x1[b] and x0[b] < x1[a]  # one over the other
                        and x1[a] >= x0[j] - 2 * size[j] and x0[a] <= x1[j] + size[j]):
                    owner[a] = owner[b] = j
    changed = True
    while changed:
        changed = False
        for i in sorted(range(len(rows)), key=lambda k: chars[k]):
            if i in alone or owner[i] != i or any(owner[k] == i for k in range(len(rows)) if k != i):
                continue  # already attached, or already owns pieces
            best = None
            for j in range(len(rows)):
                o = owner[j]
                # an exponent may hang past the line's last letter by about one character ("b³")
                if (o != i and o not in alone and chars[o] > chars[i] and abs(rows[j][0].cy - rows[i][0].cy) < 0.85 * size[o]
                        and x0[o] - 2 <= x0[i] and x1[i] <= x1[o] + size[o]
                        and (best is None or abs(rows[j][0].cy - rows[i][0].cy) < best[0])):
                    best = (abs(rows[j][0].cy - rows[i][0].cy), o)
            if best:
                owner[i], changed = best[1], True
    return [(sum(x.cy for x in rows[i]) / len(rows[i]), [s for k, r in enumerate(rows) if owner[k] == i for s in r])
            for i in range(len(rows)) if owner[i] == i]


def _block_lines(spans: list[_Span]) -> list[str]:
    return [_linear(line) for _, line in _block_rows(spans)]


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


def _tables(page):
    """The page's ruled tables of three or more columns, the tables drawn inside another's cell (a question's data
    table: "Class | 0-5 | 5-10 ..."), and the page's text spans."""
    try:
        found = [t for t in page.find_tables().tables if t.col_count >= 3]
        blocks = page.get_text("dict")["blocks"] if found else []
    except Exception:
        return [], [], []
    tables = [t for t in found if not any(_inside(t.bbox, other.bbox) for other in found if other is not t)]
    nested = [t for t in found if not any(t is k for k in tables)]
    spans = [_Span(_plain(s["text"]), s["bbox"][0], s["bbox"][2], (s["bbox"][1] + s["bbox"][3]) / 2, s["size"])
             for b in blocks if b.get("type") == 0
             for line in b.get("lines", []) for s in line.get("spans", []) if s.get("text")]
    return tables, nested, spans


def _inside(a, b, tol: float = 2) -> bool:
    return a[0] >= b[0] - tol and a[1] >= b[1] - tol and a[2] <= b[2] + tol and a[3] <= b[3] + tol


def _in_box(spans: list[_Span], box) -> list[_Span]:
    if not box:
        return []
    x0, y0, x1, y1 = box
    return [s for s in spans if x0 - 1 <= (s.x0 + s.x1) / 2 <= x1 + 1 and y0 - 1 <= s.cy <= y1 + 1]


def _table_lines(t, spans: list[_Span]) -> list[str]:
    """A data table as "| Class | 0-5 | 5-10 |" rows under a "|---|" rule after the first, so it stays a table."""
    rows = [[" ".join(" ".join(_block_lines(_in_box(spans, box))).split()).replace("|", "/") for box in row.cells]
            for row in t.rows]
    rows = [r for r in rows if any(r)]
    if not rows:
        return []
    lines = ["| " + " | ".join(r) + " |" for r in rows]
    lines.insert(1, "|" + "---|" * len(rows[0]))
    return lines


def _cell_text(spans: list[_Span], box, nested) -> str:
    """A cell's text rebuilt like page_text, with a data table inside it kept as table rows at its place."""
    mine = _in_box(spans, box)
    inner = sorted((t for t in nested if box and _inside(t.bbox, box)), key=lambda t: t.bbox[1])
    lines, top = [], float("-inf")
    for t in inner:
        lines += _block_lines([s for s in mine if top <= s.cy < t.bbox[1] and not _in_box([s], t.bbox)])
        lines += _table_lines(t, spans)
        top = t.bbox[3]
    lines += _block_lines([s for s in mine if s.cy >= top and not any(_in_box([s], t.bbox) for t in inner)])
    return "\n".join(lines).strip()


def table_rows(page) -> list[list[str]]:
    """The rows of the page's ruled tables, each cell's text rebuilt like page_text (superscripts, fractions): the
    CBSE question paper table "Q.No. | Question | Marks". A cell spanning the row (a section heading) comes back as
    the first cell with the others empty; a data table inside a cell as "| a | b |" lines. [] when the page has no
    ruled table of three or more columns."""
    tables, nested, spans = _tables(page)
    return [[_cell_text(spans, box, nested) for box in row.cells] for t in tables for row in t.rows]


_FIGURE_MIN = 30  # points: smaller pictures are an equation or a symbol set in the line ("0° < θ < 90°")


def _figure_parts(page) -> list[tuple]:
    """Pictures on the page: embedded images, and drawings with curves or slanted lines (a circle and its
    tangents). Straight ruled lines and boxes are table borders and fills, not figures."""
    parts = []
    try:
        parts += [tuple(im["bbox"]) for im in page.get_image_info()]
        for d in page.get_drawings():
            if any(it[0] in ("c", "qu") or (it[0] == "l" and abs(it[1].x - it[2].x) > 1 and abs(it[1].y - it[2].y) > 1)
                   for it in d["items"]):
                parts.append(tuple(d["rect"]))
    except Exception:
        return []
    return [p for p in parts if p[2] > p[0] and p[3] > p[1]]


def _clusters(boxes: list[tuple], gap: float = 12) -> list[tuple]:
    """Boxes that touch or nearly touch merged into one: a figure drawn as many pieces is one picture."""
    out = [list(b) for b in boxes]
    merged = True
    while merged:
        merged = False
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                a, b = out[i], out[j]
                if a[0] - gap <= b[2] and b[0] - gap <= a[2] and a[1] - gap <= b[3] and b[1] - gap <= a[3]:
                    out[i] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    del out[j]
                    merged = True
                    break
            if merged:
                break
    return [tuple(b) for b in out]


def table_figures(page) -> list[list[dict]]:
    """Like table_rows, but each row's figures (the circle of Q24, the fan of Q36) as boxes in fractions of the page
    {"x", "y", "width", "height"}, to be cut from the page image: the text layer has no picture in it. Data tables
    inside a cell are text (table_rows), not figures."""
    tables, nested, _ = _tables(page)
    if not tables:
        return []
    parts = [p for p in _figure_parts(page) if not any(_inside(p, t.bbox) for t in nested)]
    w, h = page.rect.width, page.rect.height
    rows = []
    for t in tables:
        for row in t.rows:
            box = row.bbox
            mine = [p for p in parts if box and box[0] - 1 <= (p[0] + p[2]) / 2 <= box[2] + 1
                    and box[1] - 1 <= (p[1] + p[3]) / 2 <= box[3] + 1]
            rows.append([{"x": c[0] / w, "y": c[1] / h, "width": (c[2] - c[0]) / w, "height": (c[3] - c[1]) / h}
                         for c in _clusters(mine)
                         if c[2] - c[0] >= _FIGURE_MIN and c[3] - c[1] >= _FIGURE_MIN])
    return rows


def table_cell_lines(page) -> list[list[list[tuple[float, str]]]]:
    """Like table_rows, but each cell as its visual lines with their height on the page: (y, text). A marking
    scheme's marks column ("½", "1", "½+½") then lines up with the solution step each mark belongs to."""
    tables, _, spans = _tables(page)
    rows = []
    for t in tables:
        for row in t.rows:
            cells = []
            for box in row.cells:  # the lines as page_text builds them (fractions on their line), with their height
                lines = [(round(y, 1), _linear(ln).strip()) for y, ln in _block_rows(_in_box(spans, box))]
                cells.append([ln for ln in lines if ln[1]])
            rows.append(cells)
    return rows


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
