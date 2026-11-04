"""Ground AI visual evidence in printed PDF question boundaries and geometry."""
from __future__ import annotations

import logging
import re

import pymupdf

from ..documents.storage import abs_path
from ..documents.cropping import normalise_bbox
from .extraction import Fragment, Node, VisualEvidence

log = logging.getLogger("adem.layout")
_LABEL = re.compile(r"^(?:Q(?:uestion)?\.?\s*)?(\d{1,3})(?:[.)](?:\(?[A-Za-z]\)?)?|\([A-Za-z]\)[.]?|[A-D])$", re.I)  # "17A": choice A of 17
_BARE = re.compile(r"\d{1,2}")
# "Q23" alone: an internal choice prints its "(A)." on the next line (CBSE Mathematics 2026-27)
_Q_ONLY = re.compile(r"^Q(?:uestion)?\.?\s*(\d{1,3})$", re.I)
_VISUALLY_IMPAIRED = re.compile(r"^\W*for\s+visually\s+(?:impaired|challenged)", re.I)
_TEXT_ROOT = re.compile(r"^\s*(?:Q(?:uestion)?\.?\s*)?(\d{1,3})(?=[.):\s])", re.I)


# the heading can share a text block with "Time: 3 hours ... Max. Marks", so it is searched, not anchored
_INSTRUCTIONS = re.compile(r"general\s+instructions|read\s+the\s+following\s+instructions", re.I)
_SECTION = re.compile(r"^\s*section\b", re.I)


def _instruction_span(page):
    """The numbered General Instructions block (heading to the first SECTION heading): its numbers are not questions."""
    start = end = None
    for block in sorted(page.get_text("blocks"), key=lambda b: b[1]):
        if start is None and _INSTRUCTIONS.search(block[4]):
            start = block[1]
        elif start is not None and _SECTION.match(block[4]):
            end = block[1]
            break
    return (start, end if end is not None else page.rect.height) if start is not None else None


_SECTION_HEADING = re.compile(r"^\s*section\s*\W{0,3}\s*([A-E])\b(?:.*?\(\s*\d+\s*\S\s*(\d+(?:\.\d+)?)\s*=\s*\d+)?", re.I | re.S)


_SECTION_MARKS = re.compile(r"section\s*[-\u2013]?\s*([A-E])\b[^.\n]*?\b(?:carrying|of)\s+0?(\d+)\s+marks?\s+each", re.I)


def printed_sections(doc):
    """Question root -> (section letter, printed marks per question) from the SECTION headings, in page order.

    Pages are read one at a time, so the model cannot see a heading printed on an earlier page; the PDF can.
    """
    source = getattr(doc, "original_file", None)
    if not source or not str(source).lower().endswith(".pdf"):
        return {}  # scans have no text layer; the model's section labels stand
    try:
        pdf = pymupdf.open(abs_path(source))
    except (OSError, RuntimeError, ValueError):
        return {}
    found, current = {}, None
    with pdf:
        # "SECTION B consists of 5 ... carrying 2 marks each": per-question marks when a heading prints none
        each = {letter.upper(): float(marks) for page in list(pdf)[:2]
                for letter, marks in _SECTION_MARKS.findall(page.get_text())}
        for page in pdf:
            skip = _instruction_span(page)
            events = []
            for block in page.get_text("blocks"):
                match = _SECTION_HEADING.match(block[4])
                if match and not (skip and skip[0] <= block[1] < skip[1]):
                    letter = match[1].upper()
                    events.append((block[1], 0, (letter, float(match[2]) if match[2] else each.get(letter))))
            events += [(y, 1, root) for root, y, _x in _anchors(page)]
            for _y, kind, value in sorted(events, key=lambda e: (e[0], e[1])):
                if kind == 0:
                    current = value
                elif current and value not in found:
                    found[value] = current
    return found


def printed_twice(doc):
    """Question numbers the PDF prints more than once: Q30 (A) ... OR ... Q30 (B) is an internal choice."""
    source = getattr(doc, "original_file", None)
    if not source or not str(source).lower().endswith(".pdf"):
        return set()
    try:
        pdf = pymupdf.open(abs_path(source))
    except (OSError, RuntimeError, ValueError):
        return set()
    counts = {}
    with pdf:
        for page in pdf:
            for root, _y, _x in _anchors(page):
                counts[root] = counts.get(root, 0) + 1
    return {root for root, count in counts.items() if count > 1}


def printed_by_page(doc):
    """{page number: question numbers the PDF prints on it}; None for a scan (no text layer to trust)."""
    source = getattr(doc, "original_file", None)
    if not source or not str(source).lower().endswith(".pdf"):
        return None
    try:
        pdf = pymupdf.open(abs_path(source))
    except (OSError, RuntimeError, ValueError):
        return None
    with pdf:
        return {index + 1: {root for root, _y, _x in _anchors(page)} for index, page in enumerate(pdf)}


def _anchors(page):
    found, bare = [], []
    skip = _instruction_span(page)
    for word in page.get_text("words"):
        if skip and skip[0] <= word[1] < skip[1]:
            continue
        match = _LABEL.fullmatch(word[4]) or _Q_ONLY.fullmatch(word[4])
        if match and (word[4].lower().startswith("q") or word[0] < page.rect.width * .2):
            found.append((int(match[1]), float(word[1]), float(word[0])))
        elif (_BARE.fullmatch(word[4]) and word[7] == 0 and word[0] < page.rect.width * .22
              and 0 < int(word[4]) <= 60):
            # a Q.No table column prints a bare "1": first word of its line, in the left-hand column
            bare.append((int(word[4]), float(word[1]), float(word[0])))
    if not bare:
        return sorted(found, key=lambda item: item[1])
    kept = []
    marks = [(root, y, x, True) for root, y, x in found] + [(root, y, x, False) for root, y, x in bare]
    for root, y, x, labelled in sorted(marks, key=lambda item: item[1]):
        # question numbers run in order; digits inside a question's own table or a fraction do not
        last = kept[-1][0] if kept else None
        if last is not None and root < last:
            continue  # a numbered list inside a question: printed question numbers never go back on a page
        if labelled or last is None or root in (last, last + 1):
            kept.append((root, y, x))
    return kept


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


def _recovered_parts(page, root, top, bottom):
    """Recover clearly aligned, separately marked roman-numbered parts from a PDF row."""
    words = [w for w in page.get_text("words") if top - 2 <= w[1] < bottom]
    labels = sorted((w for w in words if re.fullmatch(r"\((?:i|ii|iii|iv)\)", w[4], re.I)), key=lambda w: w[1])
    if len(labels) < 2 or [w[4].lower() for w in labels] != [f"({s})" for s in ("i", "ii", "iii", "iv")[:len(labels)]]:
        return None
    if any(re.search(r"\b(?:or|either)\b", w[4], re.I) for w in words if w[1] >= labels[0][1]):
        return None
    children = []
    for index, label in enumerate(labels):
        end = labels[index + 1][1] if index + 1 < len(labels) else bottom
        marks = [w for w in words if w[0] >= page.rect.width * .85 and label[1] - 2 <= w[1] < end
                 and re.fullmatch(r"[1-9](?:\.\d+)?", w[4])]
        if len(marks) != 1 or marks[0][1] > label[1] + 24:
            return None
        text = page.get_textbox(pymupdf.Rect(label[0], label[1] - 2, page.rect.width * .85, end)).strip()
        part = label[4][1:-1].lower()
        start = re.search(r"\(" + re.escape(part) + r"\)", text, re.I)
        if not start:
            return None
        text = text[start.start():].strip()
        children.append(Node(id=f"q{root}.{part}", kind="point", label=f"{root}({part})", text=text,
                             marks=float(marks[0][4])))
    return Node(id=f"q{root}", kind="all", label=str(root), marks=sum(c.marks for c in children), children=children)


def _reconcile_fragments(page, meta, result, anchors, lead=None):
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
        # model boxes can be on another scale (DeepSeek); a root the page prints is only overruled by the text's own label
        grounded = text_root or (layout_root if fragment.root not in printed else None)
        if grounded is not None and grounded != fragment.root:
            old = fragment.root
            fragment.root = grounded
            _rename_root(fragment.tree, old, grounded)
            if grounded != text_root:  # the text printing its own number settles it; a layout guess is worth a look
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
        # the model read this row inside a piece filed under a number the page does not print: re-file it, don't copy it
        head = _squash(text)[:40]
        misfiled = next((f for f in result.fragments if f.root not in printed and len(head) >= 20
                         and head in _squash(f.text)), None)
        if misfiled is not None:
            old = misfiled.root
            misfiled.root = root
            _rename_root(misfiled.tree, old, root)
            present.add(root)
            continue
        tree = _recovered_parts(page, root, top, bottom)
        result.fragments.append(Fragment(
            root=root,
            text=text,
            tree=tree,
            bbox={"x": 0, "y": max(0, top - 2) * sy, "width": meta["ocr_width"],
                  "height": min(page.rect.height, bottom) * sy - max(0, top - 2) * sy},
            issues=[] if tree else [
                "The AI omitted this printed question row; its text and visual boundary were recovered "
                "from the PDF source. Review its parts and marks."
            ],
        ))
        present.add(root)
    # a question continued from the previous page (lead) is printed above this page's first number
    result.fragments.sort(key=lambda fragment: (-1 if fragment.root == lead and fragment.root not in printed else next(
        (top for candidate, top, _bottom in bands if candidate == fragment.root), page.rect.height
    ), fragment.root))


def _keep_with(fragment, root, tag):
    """Move a piece onto question `root` as a part of it: its own whole-question marks are dropped and its part ids
    made unique, so pieces numbered alike by the model ("q1.i" on every page) do not clash."""
    if fragment.root != root:
        old = fragment.root
        fragment.root = root
        _rename_root(fragment.tree, old, root)
    fragment.marks = None
    if fragment.tree is not None:
        fragment.tree.marks = None if fragment.tree.children else fragment.tree.marks

        def tag_ids(node):
            for child in node.children:
                child.id = f"{child.id}@{tag}"
                tag_ids(child)
        tag_ids(fragment.tree)


def _squash(text):
    return re.sub(r"[^a-z0-9]+", "", (text or "").casefold())


def _carry_page_top(page, result, anchors, previous):
    """Text printed above a page's first question number continues the previous page's last question.

    Models without position boxes (Qwen3-VL) label it with the next number; the PDF text layer settles it.
    """
    if not (result.fragments and anchors and previous):
        return
    carry = previous[-1][0]
    top = _squash(page.get_textbox(pymupdf.Rect(0, 0, page.rect.width, max(0, anchors[0][1] - 12))))
    for fragment in result.fragments:
        head = _squash(fragment.text)[:20]
        if fragment.root == carry or len(head) < 12 or head not in top:
            continue
        old = fragment.root
        fragment.root, fragment.continues = carry, True
        _rename_root(fragment.tree, old, carry)
        fragment.issues.append(f"Text above printed question {anchors[0][0]} continues question {carry} from the previous page.")


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


def ground_visuals(doc, results, answers=False):
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
        last_printed = None
        for meta, result in results:
            number = meta["page_number"] - 1
            if number >= len(pdf):
                continue
            page = pdf[number]
            anchors = _anchors(page)
            if not anchors:
                # no printed question number on this page: all of it belongs to the last printed question.
                # The model may number its parts (I), (II) as questions 1, 2: they are parts, not new copies.
                if last_printed is not None:
                    for index, fragment in enumerate(result.fragments):
                        _keep_with(fragment, last_printed, f"p{meta['page_number']}-{index + 1}")
                        # a visually impaired version starts its own alternative; every other piece continues
                        fragment.continues = not _VISUALLY_IMPAIRED.match(fragment.text or "")
                continue
            lead, last_printed = last_printed, anchors[-1][0]
            if lead is not None:
                printed_here = {root for root, _y, _x in anchors}
                for index, fragment in enumerate(result.fragments):
                    # a question that already ended on an earlier page cannot reappear here unprinted:
                    # the piece continues the last question printed before this page
                    if fragment.root not in printed_here and fragment.root < lead:
                        _keep_with(fragment, lead, f"p{meta['page_number']}-{index + 1}")
                        fragment.continues = not _VISUALLY_IMPAIRED.match(fragment.text or "")
            previous = _anchors(pdf[number - 1]) if number else []
            if answers:  # a question paper may print a case-study passage above its number
                # before reconciling, so a printed row the model skipped is then recovered from the PDF
                _carry_page_top(page, result, anchors, previous)
            _reconcile_fragments(page, meta, result, anchors, lead)
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
                    return carry or lead  # above the first printed number: the previous page's question
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
                own = [m for m in matches if m[2] == fragment.root and m[0] >= 2]
                if len(own) > 1 and matches[0][0] - matches[1][0] <= .15:
                    # several drawings inside this question's printed band and model boxes too rough to choose:
                    # the model lists visuals in reading order, so take the band's next one from the top
                    matches = [min(own, key=lambda m: (m[3].y0, m[3].x0))]
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
            # A printed equation or structure drawn from many small pieces (arrows, bonds, sub/superscripts):
            # one picture of the whole printed area reads far better than the pieces or a garbled transcription.
            pieces = {}
            for index, (kind, rect) in enumerate(candidates):
                if kind == "image" and rect.get_area() < page.rect.get_area() * .01:
                    root = owner(rect)
                    if root is not None:
                        pieces.setdefault(root, []).append(index)
            for root, indexes in pieces.items():
                target = next((f for f in result.fragments if f.root == root), None)
                if target is None or len(indexes) < 3:
                    continue
                area = pymupdf.Rect(candidates[indexes[0]][1])
                for index in indexes[1:]:
                    area |= candidates[index][1]
                area = pymupdf.Rect(page.rect.width * .12, max(0, area.y0 - 14),
                                    page.rect.width * .9, min(page.rect.height, area.y1 + 14))
                target.visuals = [VisualEvidence(
                    kind="formula", description="The printed answer, shown as in the uploaded document.", labels=[],
                    bbox={"x": area.x0 * meta["ocr_width"] / page.rect.width,
                          "y": area.y0 * meta["ocr_height"] / page.rect.height,
                          "width": area.width * meta["ocr_width"] / page.rect.width,
                          "height": area.height * meta["ocr_height"] / page.rect.height},
                )]
                # the picture is authoritative for this part; doubts about its garbled text layer no longer matter
                garbled = any(re.search(r"garbled|text layer", x, re.I) for x in target.issues)
                target.issues = [x for x in target.issues if not re.search(r"garbled|text layer|ownership", x, re.I)]
                if garbled:
                    # the typed-out working is the unreadable part: keep the short answer, the picture shows the rest
                    parts = re.split(r"(?<=\.)\s+(?=\((?:i|1|a)\)|\(?I\.)", target.text or "")
                    short, rest = parts[0].strip(), parts[1:]
                    while len(short) < 8 and rest:  # "D." alone is the option letter; keep "D. (i) and (ii)."
                        short = f"{short} {rest.pop(0).strip()}"
                    if 0 < len(short) < len(target.text or ""):
                        target.text = short + "\n[Working shown in the picture below, as printed in the marking scheme.]"
                used.update(i for i, (kind, _r) in enumerate(candidates) if kind == "image" and owner(_r) == root)
            # A "visual" that is only a rule or an empty box (no text, no image, a few strokes) shows nothing
            drawings = page.get_drawings()
            for fragment in result.fragments:
                kept = []
                for visual in fragment.visuals:
                    b = visual.bbox or {}
                    rect = pymupdf.Rect(b.get("x", 0) * page.rect.width / meta["ocr_width"],
                                        b.get("y", 0) * page.rect.height / meta["ocr_height"],
                                        (b.get("x", 0) + b.get("width", 0)) * page.rect.width / meta["ocr_width"],
                                        (b.get("y", 0) + b.get("height", 0)) * page.rect.height / meta["ocr_height"])
                    strokes = [d for d in drawings if d["rect"].intersects(rect)]
                    empty = (not page.get_textbox(rect).strip()
                             and not any(pymupdf.Rect(i["bbox"]).intersects(rect) for i in page.get_image_info())
                             and len(strokes) <= 4
                             # only straight rules and boxes; a circle or curve is a real drawing
                             and all(item[0] in ("l", "re") for d in strokes for item in d["items"]))
                    if not empty or visual.kind == "table":
                        kept.append(visual)
                fragment.visuals = kept
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
