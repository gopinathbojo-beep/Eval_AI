"""Non-destructive OCR copy: RGB, aspect-preserving downscale only. No thresholding/binarisation/denoise."""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageChops


def content_bbox(img: Image.Image) -> list[int] | None:
    """Bounding box of non-background pixels (metadata only; the image is NOT cropped)."""
    g = img.convert("L")
    bg = Image.new("L", g.size, 255)
    diff = ImageChops.difference(g, bg).point(lambda v: 255 if v > 30 else 0)
    box = diff.getbbox()
    return list(box) if box else None


def make_ocr_copy(img: Image.Image, dest: Path, max_side: int) -> tuple[Path, dict]:
    w, h = img.size
    scale = min(1.0, max_side / max(w, h))
    out = img if scale == 1.0 else img.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    out.save(dest, "PNG")
    return dest, {"ocr_width": out.width, "ocr_height": out.height, "content_bbox": content_bbox(img)}
