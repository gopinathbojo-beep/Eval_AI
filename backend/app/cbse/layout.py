"""Ground AI visual evidence in printed PDF question boundaries and geometry."""
from __future__ import annotations

import logging
import re

import pymupdf

from ..documents.storage import abs_path
from ..documents.cropping import normalise_bbox

log = logging.getLogger("adem.layout")
_LABEL = re.compile(r"^(?:Q(?:uestion)?\.?\s*)?(\d{1,3})[.)](?:\(?[A-Za-z]\)?)?$", re.I)


def _anchors(page):
    found = []
    for word in page.get_text("words"):
        match = _LABEL.fullmatch(word[4])
        if match and (word[4].lower().startswith("q") or word[0] < page.rect.width * .2):
            found.append((int(match[1]), float(word[1]), float(word[0])))
    return sorted(found, key=lambda item: item[1])


def _tokens(text):
    return set(re.findall(r"\w+", text.casefold()))


def _candidates(page):
    candidates = [("image", pymupdf.Rect(item["bbox"])) for item in page.get_image_info()]
    drawings = page.get_drawings()
    # Exclude long page rules before grouping local table grids. Some PDFs
    # encode grid lines as thin filled rectangles rather than stroked lines.
    local = [d for d in drawings if d["rect"].width < page.rect.width * .65
             and d["rect"].height < page.rect.height * .45]
    for rect in page.cluster_drawings(drawings=local):
        if rect.width < 30 or rect.height < 15 or rect.height > page.rect.height * .4:
            continue
        members = [d["rect"] for d in local if rect.contains(d["rect"])]
        horizontal = {round(r.y0) for r in members if r.height <= 2 and r.width > 10}
        vertical = {round(r.x0) for r in members if r.width <= 2 and r.height > 10}
        if len(horizontal) >= 2 and len(vertical) >= 3:
            candidates.append(("table", rect))
        elif any(
            item[0] == "c" or (item[0] == "l" and item[1].x != item[2].x and item[1].y != item[2].y)
            for drawing in local if rect.contains(drawing["rect"])
            for item in drawing["items"]
        ):
            candidates.append(("diagram", rect))
    return candidates


def _rename_root(node, old, new):
    if node is None:
        return
    node.id = re.sub(rf"^q{old}(?=$|[.])", f"q{new}", node.id)
    node.label = re.sub(rf"^{old}(?=$|[.(])", str(new), node.label)
    for child in node.children:
        _rename_root(child, old, new)


def ground_visuals(doc, results):
    """Use source layout once per build; never create visuals for empty questions.

    A missing/ambiguous match is retained as a review issue, not guessed from
    the nearest question. Raster uploads retain their existing extraction path.
    """
    if not any(f.visuals for _, result in results for f in result.fragments):
        return
    source = abs_path(doc.original_file)
    if source.suffix.lower() != ".pdf":
        return
    try:
        pdf = pymupdf.open(source)
    except (OSError, RuntimeError):
        log.warning("Could not open source PDF for visual layout checks")
        return
    with pdf:
        for meta, result in results:
            number = meta["page_number"] - 1
            if number >= len(pdf):
                continue
            page = pdf[number]
            anchors = _anchors(page)
            if not anchors:
                continue
            previous = _anchors(pdf[number - 1]) if number else []
            # Repeated printed root at the page start confirms its continuation.
            carry = previous[-1][0] if previous and previous[-1][0] == anchors[0][0] else None
            printed = {root for root, _, _ in anchors}
            if carry:
                for fragment in result.fragments:
                    if fragment.continues and fragment.root not in printed and fragment.root != carry:
                        old = fragment.root
                        fragment.root = carry
                        _rename_root(fragment.tree, old, carry)

            def owner(rect):
                # Reject columns with competing labels instead of selecting by y.
                preceding = [(root, y, x) for root, y, x in anchors if y <= rect.y0 + 3]
                if not preceding:
                    return carry
                root, y, x = preceding[-1]
                if any(other != root and abs(oy - y) < 12 and abs(ox - x) > page.rect.width * .25
                       for other, oy, ox in preceding):
                    return None
                # A crop crossing the next whole question is not owned by either.
                if any(other != root and y + 3 < oy < rect.y1 - 3 for other, oy, _ in anchors):
                    return None
                return root

            candidates = _candidates(page)
            proposed = [(f, v) for f in result.fragments for v in f.visuals]
            for fragment in result.fragments:
                fragment.visuals = []
            used = set()
            for fragment, visual in proposed:
                labels = _tokens(" ".join(visual.labels))
                matches = []
                for index, (kind, rect) in enumerate(candidates):
                    if index in used or (visual.kind == "table") != (kind == "table"):
                        continue
                    root = owner(rect)
                    if root is None:
                        continue
                    if kind == "table":
                        text = _tokens(page.get_textbox(rect + (-1, -1, 1, 1)))
                        score = len(labels & text) / max(1, len(labels))
                        if root != fragment.root or not labels or score < .5:
                            continue
                    else:
                        bbox = normalise_bbox(visual.bbox, meta["ocr_width"], meta["ocr_height"], page.rect.width, page.rect.height)
                        if not bbox:
                            continue
                        predicted = pymupdf.Rect(bbox["x"], bbox["y"], bbox["x"] + bbox["width"], bbox["y"] + bbox["height"])
                        score = (predicted & rect).get_area() / max(1, min(predicted.get_area(), rect.get_area()))
                        if score < .5:
                            continue
                    matches.append((score, index, root, rect))
                matches.sort(reverse=True, key=lambda match: match[0])
                if matches and (len(matches) == 1 or matches[0][0] - matches[1][0] > .15):
                    _, index, root, rect = matches[0]
                    target = next((f for f in result.fragments if f.root == root), None)
                    if target is not None:
                        visual.bbox = {"x": rect.x0 * meta["ocr_width"] / page.rect.width,
                                       "y": rect.y0 * meta["ocr_height"] / page.rect.height,
                                       "width": rect.width * meta["ocr_width"] / page.rect.width,
                                       "height": rect.height * meta["ocr_height"] / page.rect.height}
                        target.visuals.append(visual)
                        used.add(index)
                        continue
                fragment.issues.append(
                    f"Visual ownership or bounds could not be confirmed on page {meta['page_number']}; review source layout."
                )
