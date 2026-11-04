"""Pages scanned or photographed sideways (a portrait answer sheet fed into the scanner on its side): find them and
the turn that makes them upright, so the vision model reads handwriting the right way up.

Two measurements on the ink (strokes darker than their surroundings) of a small copy of the page:
- Sideways or not: lines of writing make the ink profile across them alternate strongly (line, gap, line ...),
  while the profile along them stays even. Writing that runs down the page gives a stronger column profile than
  row profile.
- Which way to turn: written lines start at a shared margin and end raggedly, so once upright their start
  positions agree much more than their end positions.

The turn is decided once per document (a scanner feeds every sheet the same way); one page alone can mislead,
for instance a page of long lines or struck-out work, so a single page is never turned and pages that disagree
leave the document as it is. Pages without a clear signal are left as they are, unless most of the document is
clearly sideways.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

_WIDTH = 600          # measured on a small copy: fast, and enough for line structure
_CONTRAST = 40        # ink is this much darker than its surroundings (faint notebook rules are not)
_PEN = 160            # and dark in itself: pen strokes, for finding where lines start and end
_MIN_INK = 0.001      # blank (or almost blank) pages carry no signal
# Column/row line strength. Sideways handwritten pages measured 1.9-3.5, upright ones (scans and desk photos)
# at most 1.3; the thresholds sit between.
_CLEAR = 1.6          # marks a page as sideways on its own
_LEANING = 1.35       # accepted only when most of the document is clearly sideways
_MIN_VOTERS = 2       # clearly sideways pages needed to decide the direction


def _ink(img: Image.Image, pen_only: bool = False) -> np.ndarray:
    """Strokes darker than their neighbourhood: a dark desk or shadow around a photographed sheet is not ink.
    pen_only also drops lighter marks (printed rules, show-through from the back of the sheet), which would
    blur where lines start and end."""
    h = max(1, round(_WIDTH * img.height / max(img.width, 1)))
    grey = img.convert("L").resize((_WIDTH, h))
    near = np.asarray(grey.filter(ImageFilter.BoxBlur(12)), dtype=np.int16)
    level = np.asarray(grey, dtype=np.int16)
    ink = level < near - _CONTRAST
    return ink & (level < _PEN) if pen_only else ink


def _line_strength(mask: np.ndarray, axis: int) -> float:
    """How strongly the ink alternates across lines: the spread of the (lightly smoothed) profile."""
    profile = np.convolve(mask.mean(axis=axis), np.ones(3) / 3, mode="same")
    return float(profile.std() / (profile.mean() + 1e-6))


def sideways_ratio(img: Image.Image) -> float | None:
    """Column/row line strength: above 1 the writing runs down the page. None for a page with too little ink."""
    mask = _ink(img)
    if mask.mean() < _MIN_INK:
        return None
    return _line_strength(mask, 0) / max(_line_strength(mask, 1), 1e-6)


def _margin_alignment(upright: Image.Image) -> float:
    """Positive when the page's lines share their start (reads left to right as shown), negative when they share
    their end (the page is upside down)."""
    mask = _ink(upright, pen_only=True)
    height, width = mask.shape
    has_ink = mask.sum(axis=1) > 2
    starts, ends = [], []
    row = 0
    while row < height:
        if not has_ink[row]:
            row += 1
            continue
        end = row
        while end < height and has_ink[end]:
            end += 1
        if end - row >= 3:
            xs = np.flatnonzero(mask[row:end].any(axis=0))
            if len(xs) > 5:
                starts.append(xs[0] / width)
                ends.append(xs[-1] / width)
        row = end
    if len(starts) < 3:
        return 0.0

    def spread(values):
        q75, q25 = np.percentile(values, [75, 25])
        return float(q75 - q25)
    return spread(ends) - spread(starts)


def upright_turns(images: list[Image.Image | None]) -> list[int]:
    """For each page, the counter-clockwise turn in degrees (PIL `rotate`) that makes it upright: 0, 90 or 270.
    None stands for a page not to be measured (a digital page with its own text layer)."""
    ratios = [sideways_ratio(img) if img is not None else None for img in images]
    measured = [r for r in ratios if r is not None]
    clear = [i for i, r in enumerate(ratios) if r is not None and r >= _CLEAR]
    # one page cannot tell which way to turn (a page of full-width lines lines up at both ends): left as it is
    if len(clear) < _MIN_VOTERS:
        return [0] * len(images)
    # 90 turns a page whose top was scanned on the right; 270 one whose top was scanned on the left
    votes = [_margin_alignment(images[i].rotate(90, expand=True)) for i in clear]
    ahead = sum(v > 0 for v in votes) - sum(v < 0 for v in votes)
    if ahead == 0 or (ahead > 0) != (sum(votes) > 0):
        return [0] * len(images)  # the pages disagree: a wrong turn is worse than none
    turn = 90 if ahead > 0 else 270
    mostly_sideways = len(clear) * 2 > len(measured)
    return [turn if r is not None and (r >= _CLEAR or (mostly_sideways and r >= _LEANING)) else 0 for r in ratios]
