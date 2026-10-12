from __future__ import annotations
from pathlib import Path
from PIL import Image


def normalise_bbox(bbox: dict | None, ocr_w: int, ocr_h: int, page_w: int, page_h: int) -> dict | None:
    """Model bbox (pixels of the OCR image, or 0-1 fractions) -> pixels of the full-res page. None if implausible."""
    if not bbox:
        return None
    try:
        x, y, w, h = (float(bbox[k]) for k in ("x", "y", "width", "height"))
    except (KeyError, TypeError, ValueError):
        return None
    if w <= 0 or h <= 0 or x < 0 or y < 0:
        return None
    if max(x, y, w, h) <= 1.0:      # fractions of the page
        x, w, y, h = x * page_w, w * page_w, y * page_h, h * page_h
    else:                           # pixels of the OCR image -> full-res page
        sx, sy = page_w / ocr_w, page_h / ocr_h
        x, w, y, h = x * sx, w * sx, y * sy, h * sy
    tol = 1.02
    if x + w > page_w * tol or y + h > page_h * tol:
        return None
    w, h = min(w, page_w - x), min(h, page_h - y)
    if w < 5 or h < 5:
        return None
    return {"x": round(x), "y": round(y), "width": round(w), "height": round(h)}


def save_crop(page_png: Path, bbox: dict, dest: Path, pad: int = 12) -> Path:
    with Image.open(page_png) as im:
        x0, y0 = max(0, bbox["x"] - pad), max(0, bbox["y"] - pad)
        x1, y1 = min(im.width, bbox["x"] + bbox["width"] + pad), min(im.height, bbox["y"] + bbox["height"] + pad)
        dest.parent.mkdir(parents=True, exist_ok=True)
        im.crop((x0, y0, x1, y1)).save(dest, "PNG")
    return dest
