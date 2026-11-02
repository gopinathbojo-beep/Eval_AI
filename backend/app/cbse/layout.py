"""Ground AI visual evidence in printed PDF question boundaries and geometry."""
from __future__ import annotations

import logging
import re

import pymupdf

from ..documents.storage import abs_path
from ..documents.cropping import normalise_bbox
from .extraction import Fragment, VisualEvidence

log = logging.getLogger("adem.layout")
_LABEL = re.compile(r"^(?:Q(?:uestion)?\.?\s*)?(\d{1,3})(?:[.)](?:\(?[A-Za-z]\)?)?|\([A-Za-z]\)[.]?)$", re.I)
_TEXT_ROOT = re.compile(r"^\s*(?:Q(?:uestion)?\.?\s*)?(\d{1,3})(?=[.):\s])", re.I)


def _anchors(page):
    found = []
    for word in page.get_text("words"):
        match = _LABEL.fullmatch(word[4])
        if match and (word[4].lower().startswith("q") or word[0] < page.rect.width * .2):
            found.append((int(match[1]), float(word[1]), float(word[0])))
    return sorted(found, key=lambda item: item[1])


def _bands(page, anchors):
    """Return one vertical source band per printed whole-question root."""
    unique = []
    for root, y, x in anchors:
        if unique and unique[-1][0] == root:
            continue
        unique.append((root, y, x))
    return [
        (root, y, unique[index + 1][1] if index + 1 < len(unique) else page.rect.height)
        for index, (root, y, _x) in enumerate(unique)
    ]


def _bbox_rect(fragment, meta, page):
    bbox = normalise_bbox(
        fragment.bbox, meta["ocr_width"], meta["ocr_height"], page.rect.width, page.rect.height
    )
    if not bbox:
        return None
    return pymupdf.Rect(bbox["x"], bbox["y"], bbox["x"] + bbox["width"], bbox["y"] + bbox["height"])


def _band_root(rect, bands):
    if rect is None:
        return None
    scored = []
    for root, top, bottom in bands:
        overlap = max(0, min(rect.y1, bottom) - max(rect.y0, top))
        if overlap:
            scored.append((overlap / max(1, rect.height), root))
    scored.sort(reverse=True)
    if not scored or scored[0][0] < .5:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < .15:
        return None
    return scored[0][1]


def _reconcile_fragments(page, meta, result, anchors):
    """Ground model roots in printed row labels and recover omitted PDF-text rows.

    This is deliberately layout-driven: it never assumes particular question
    numbers or that every question owns a visual.
    """
    bands = _bands(page, anchors)
    printed = {root for root, _top, _bottom in bands}
    for fragment in result.fragments:
        label = _TEXT_ROOT.match(fragment.text or "")
        text_root = int(label.group(1)) if label and int(label.group(1)) in printed else None
        layout_root = _band_root(_bbox_rect(fragment, meta, page), bands)
        grounded = text_root or layout_root
        if grounded is not None and grounded != fragment.root:
            old = fragment.root
            fragment.root = grounded
            _rename_root(fragment.tree, old, grounded)
            fragment.issues.append(
                f"Model root {old} was corrected to printed question {grounded} from the source row boundary."
            )

    present = {fragment.root for fragment in result.fragments}
    sy = meta["ocr_height"] / page.rect.height
    for root, top, bottom in bands:
        if root in present:
            continue
        text = page.get_textbox(pymupdf.Rect(0, max(0, top - 2), page.rect.width, bottom)).strip()
        if not text:
            continue
        result.fragments.append(Fragment(
            root=root,
            text=text,
            bbox={"x": 0, "y": max(0, top - 2) * sy, "width": meta["ocr_width"],
                  "height": min(page.rect.height, bottom) * sy - max(0, top - 2) * sy},
            issues=[
                "The AI omitted this printed question row; its text and visual boundary were recovered "
                "from the PDF source. Review its parts and marks."
            ],
        ))
        present.add(root)
    result.fragments.sort(key=lambda fragment: (next(
        (top for candidate, top, _bottom in bands if candidate == fragment.root), page.rect.height
    ), fragment.root))


def _tokens(text):
    return set(re.findall(r"\w+", text.casefold()))


def _candidates(page):
    candidates = [("image", pymupdf.Rect(item["bbox"])) for item in page.get_image_info()]
    # An illustration can be stored as adjoining image tiles. Treat touching,
    # vertically aligned tiles as one visual instead of ambiguous competitors.
    changed = True
    while changed:
        changed = False
        for i, (_, first) in enumerate(candidates):
            for j in range(i + 1, len(candidates)):
                second = candidates[j][1]
                overlap = min(first.y1, second.y1) - max(first.y0, second.y0)
                gap = max(first.x0, second.x0) - min(first.x1, second.x1)
                if overlap >= .9 * max(first.height, second.height) and abs(gap) <= 2:
                    candidates[i] = ("image", first | second)
                    candidates.pop(j)
                    changed = True
                    break
            if changed:
                break
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
    """Use source layout once per build; recover only source-confirmed visuals.

    A missing/ambiguous match is retained as a review issue, not guessed from
    the nearest question. Raster uploads retain their existing extraction path.
    """
    if not getattr(doc, "original_file", None):
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
        placeholders = []
        for meta, result in results:
            number = meta["page_number"] - 1
            if number >= len(pdf):
                continue
            page = pdf[number]
            anchors = _anchors(page)
            if not anchors:
                continue
            _reconcile_fragments(page, meta, result, anchors)
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
                        score = 0
                        if bbox:
                            predicted = pymupdf.Rect(bbox["x"], bbox["y"], bbox["x"] + bbox["width"], bbox["y"] + bbox["height"])
                            score = (predicted & rect).get_area() / max(1, min(predicted.get_area(), rect.get_area()))
                        if root == fragment.root:
                            # Printed ownership is stronger evidence than an AI
                            # coordinate estimate. Multiple matches still need
                            # geometric disambiguation below.
                            score += 2
                        elif score < .5:
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
                issue = f"Visual ownership or bounds could not be confirmed on page {meta['page_number']}; review source layout."
                fragment.issues.append(issue)
                if not normalise_bbox(visual.bbox, meta["ocr_width"], meta["ocr_height"], page.rect.width, page.rect.height):
                    placeholders.append((fragment, issue))
            # Recover native images the AI omitted, but only inside a confirmed
            # question band. Never manufacture an image for a text-only question.
            for index, (kind, rect) in enumerate(candidates):
                if index in used or kind != "image" or rect.get_area() > page.rect.get_area() * .25:
                    continue
                root = owner(rect)
                target = next((f for f in result.fragments if f.root == root), None)
                if target is None or rect.width < 20 or rect.height < 8:
                    continue
                target.visuals.append(VisualEvidence(
                    kind="image", description="Embedded source image from the uploaded document.",
                    labels=[], bbox={"x": rect.x0 * meta["ocr_width"] / page.rect.width,
                                     "y": rect.y0 * meta["ocr_height"] / page.rect.height,
                                     "width": rect.width * meta["ocr_width"] / page.rect.width,
                                     "height": rect.height * meta["ocr_height"] / page.rect.height},
                ))
            # A missing-location warning can be resolved by confirmed evidence
            # on a continuation page; keep unrelated extraction/marking issues.
        confirmed = {f.root for _, result in results for f in result.fragments if f.visuals}
        for fragment, issue in placeholders:
            if fragment.root in confirmed:
                fragment.issues = [value for value in fragment.issues if value != issue]
        location_issue = re.compile(r"(?:diagram|figure|bbox).*(?:not visible|unavailable|omitted)", re.I)
        for _, result in results:
            for fragment in result.fragments:
                if fragment.root in confirmed:
                    fragment.issues = [issue for issue in fragment.issues if not location_issue.search(issue)]
            def resolved_location(issue):
                refs = {int(value) for value in re.findall(r"\bQ\s*(\d+)\b", issue, re.I)}
                return bool(refs and refs <= confirmed and location_issue.search(issue))
            result.issues = [issue for issue in result.issues if not resolved_location(issue)]
