"""Answer sheet photo quality, checked before any credit is charged (spec 6.5): too blurred (variance of the
Laplacian), too dark or washed out, or sideways (a landscape photo of a portrait page). Each page gets its problems;
an empty list means it is fine."""
from __future__ import annotations
import io

BLUR_MIN = 60.0      # variance of the Laplacian below this: too blurred to read
DARK_MAX = 60        # mean brightness (0-255) below this: too dark
BRIGHT_MIN = 245     # above this with little contrast: washed out or blank
CONTRAST_MIN = 12


def page_images(data: bytes, ext: str) -> list:
    """The pages as greyscale arrays: each page of a PDF, or the one image."""
    import cv2
    import numpy as np
    if ext == "pdf":
        import pymupdf
        doc = pymupdf.open(stream=data, filetype="pdf")
        out = []
        for page in doc:
            pix = page.get_pixmap(dpi=110, colorspace=pymupdf.csGRAY)
            out.append(np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width))
        return out
    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    return [img] if img is not None else []


def check_page(gray) -> list[str]:
    import cv2
    problems = []
    if gray is None or gray.size == 0:
        return ["The file could not be opened."]
    h, w = gray.shape[:2]
    if min(h, w) < 400:
        problems.append("The picture is too small to read. Take it closer or at a higher resolution.")
    if cv2.Laplacian(gray, cv2.CV_64F).var() < BLUR_MIN:
        problems.append("The picture is blurred. Hold the camera steady and retake it.")
    mean, std = float(gray.mean()), float(gray.std())
    if mean < DARK_MAX:
        problems.append("The picture is too dark. Retake it in better light.")
    elif mean > BRIGHT_MIN and std < CONTRAST_MIN:
        problems.append("The page looks blank or washed out.")
    if w > h * 1.25:
        problems.append("The page is sideways. Turn it upright and retake it.")
    return problems


def check(data: bytes, ext: str) -> list[dict]:
    """[{page, problems}] for every page; raises ValueError when the file is unreadable."""
    pages = page_images(data, ext)
    if not pages:
        raise ValueError("The file could not be opened. Upload a JPG, PNG or PDF.")
    return [{"page": i + 1, "problems": check_page(p)} for i, p in enumerate(pages)]


def merge_to_pdf(files: list[tuple[bytes, str]]) -> bytes:
    """Photos and PDFs, in the order given, as one PDF: the student's sheet."""
    import pymupdf
    out = pymupdf.open()
    for data, ext in files:
        if ext == "pdf":
            out.insert_pdf(pymupdf.open(stream=data, filetype="pdf"))
        else:
            img = pymupdf.open(stream=data, filetype=ext)
            out.insert_pdf(pymupdf.open("pdf", img.convert_to_pdf()))
    buf = io.BytesIO()
    out.save(buf)
    return buf.getvalue()
