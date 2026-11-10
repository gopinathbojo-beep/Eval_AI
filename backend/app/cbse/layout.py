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
# the instructions end at the first SECTION heading, or a "Part - A" / "PART B" heading (Accountancy, Economics)
_SECTION = re.compile(r"^\s*(?:section\b|part\s*[-–:]?\s*[A-E]\b)", re.I)


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


# "SECTION C (8x3=24)": the two factors of the section total, printed in either order (questions x marks or
# marks x questions); printed_sections tells them apart by counting the section's questions
_SECTION_HEADING = re.compile(r"^\s*section\s*\W{0,3}\s*([A-E])\b"
                              r"(?:.*?\(\s*(\d+(?:\.\d+)?)\s*\S\s*(\d+(?:\.\d+)?)\s*=\s*\d+)?", re.I | re.S)


_SECTION_MARKS = re.compile(r"section\s*[-\u2013]?\s*([A-E])\b[^.\n]*?\b(?:carrying|of)\s+0?(\d+)\s+marks?\s+each", re.I)


def _marks_each(first, second, questions):
    """Marks per question from a heading's "first x second = total": the factor that is not the number of
    questions printed under it ("(21x1=21)" over 21 questions is 1; "(8x3=24)" over 3 questions is 8)."""
    if first is None or second is None:
        return None
    if questions == second and questions != first:
        return first
    return second


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
    found, current, headings = {}, None, []
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
                    factors = (float(match[2]), float(match[3])) if match[3] else (None, None)
                    headings.append((match[1].upper(), *factors))
                    events.append((block[1], 0, len(headings) - 1))
            events += [(y, 1, root) for root, y, _x in _anchors(page)]
            for _y, kind, value in sorted(events, key=lambda e: (e[0], e[1])):
                if kind == 0:
                    current = value
                elif current is not None and value not in found:
                    found[value] = current
    counts = {}
    for heading in found.values():
        counts[heading] = counts.get(heading, 0) + 1
    out = {}
    for root, heading in found.items():
        letter, first, second = headings[heading]
        marks = _marks_each(first, second, counts[heading])
        out[root] = (letter, marks if marks is not None else each.get(letter))
    return out


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


_COLUMN_SLACK = 15  # points: a question number sits in the paper's number column; list/table numbers are indented
_by_doc: dict = {}


def _paper_anchors(doc):
    """Question numbers for every page, read with the whole paper in view.

    A numbered list inside a question ("1. Goodwill is valued...", a Notes to Accounts table) prints small numbers
    indented from the paper's question-number column, after the paper has already passed those question numbers.
    Such a number is dropped; a number in the column itself is kept even when it goes back (Accountancy Part B
    restarts at 27 for its second option), and an indented number that moves forward is kept (some papers indent
    their numbers on some pages)."""
    raw, last = [], 0
    for p in doc:  # each page knows the last question number the pages before it printed
        page_anchors = _raw_anchors(p, last)
        raw.append(page_anchors)
        last = max([last] + [root for root, _y, _x in page_anchors])
    xs = [round(x / 5) * 5 for page in raw for _root, _y, x in page]
    # the column is the leftmost position used often (an indented list never outnumbers the questions)
    common = sorted({x for x in xs if xs.count(x) >= max(2, len(xs) // 10)})
    column = common[0] if common else None
    out, seen = [], 0
    for page in raw:
        kept = [(root, y, x) for root, y, x in page
                if column is None or x <= column + _COLUMN_SLACK or root >= seen]
        out.append(kept)
        seen = max([seen] + [root for root, _y, _x in kept])
    return out


def _anchors(page):
    doc = page.parent
    if doc is None or len(doc) < 2:
        return _raw_anchors(page)
    key = (id(doc), getattr(doc, "name", ""), len(doc))
    if key not in _by_doc:
        _by_doc.clear()  # one paper at a time
        _by_doc[key] = _paper_anchors(doc)
    return _by_doc[key][page.number]


_MAX_SKIP = 2  # a bare number may skip one question (a page the text layer could not read)


def _raw_anchors(page, seen=None):
    """Printed question numbers on a page. `seen` (the last number the earlier pages printed, when the whole paper
    is in view) keeps a bare number only when it continues the paper: "21" in "...उप प्रश्नों की संख्या 21 है" or the
    date "27 जून 2025" opening a passage line is not question 21 or 27."""
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
    if not seen:  # the paper starts here: its sequence starts at the smallest number the page prints (not always 1)
        seen = min(root for root, _y, _x, _l in marks)
    for root, y, x, labelled in sorted(marks, key=lambda item: item[1]):
        # question numbers run in order; digits inside a question's own table or a fraction do not
        last = kept[-1][0] if kept else seen
        if not labelled and last is not None and not last <= root <= last + _MAX_SKIP:
            continue  # a bare number that does not continue the question sequence is a number in the text
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


def printed_text(doc, root: int) -> str | None:
    """The text a PDF prints for whole question `root` (its first band, from its number to the next question's), or
    None when the number is not printed or the text layer is mis-encoded. The document's own words: nothing is
    added or rewritten."""
    for page in doc:
        if garbled_text_layer(page.get_text()):
            return None
        for number, top, bottom in _bands(page, _anchors(page)):
            if number == root:
                text = page.get_textbox(pymupdf.Rect(0, max(0, top - 2), page.rect.width, bottom)).strip()
                return text or None
    return None


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


# A PDF made with a legacy Hindi font maps its glyphs to the wrong Unicode: "खंड" comes out "िांि", "पाठ्य" as
# "प़ाठ््". Nukta on a vowel sign and doubled viramas never occur in real Devanagari text.
_GARBLED = re.compile("[ा-ौ]़|़[ाी]|््")


def garbled_text_layer(text: str) -> bool:
    """The page's PDF text is mis-encoded (see _GARBLED), so it must not be copied into questions."""
    devanagari = len(re.findall("[ऀ-ॿ]", text or ""))
    return devanagari >= 40 and len(_GARBLED.findall(text)) * 100 >= devanagari  # 1 in 100 letters or more


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
    if garbled_text_layer(page.get_text()):
        return  # nothing can be recovered from a mis-encoded text layer; the AI reading stands as it is
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
        tree = _recovered_parts(page, root, top, bottom)  # clearly printed (i), (ii)... parts with their marks
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
    _recover_page_top(page, meta, result, bands, lead, present, sy)
    # a question continued from the previous page (lead) is printed above this page's first number
    result.fragments.sort(key=lambda fragment: (-1 if fragment.root == lead and fragment.root not in printed else next(
        (top for candidate, top, _bottom in bands if candidate == fragment.root), page.rect.height
    ), fragment.root))


_HEADING_ONLY = re.compile(r"^\s*(?:SECTION|PART)\s*[-\u2013:]?\s*[A-E]\b[^\n]*$", re.I)


def _only_transcribed_tables(page, candidates, owner, fragment):
    """This question's printed area holds no image or drawing other than tables, and each table's words are in
    the text the model read for it."""
    if len(fragment.text or "") < 40:
        return False
    read = set(re.findall(r"[a-z0-9]{3,}", fragment.text.casefold()))
    for kind, rect in candidates:
        if owner(rect) != fragment.root:
            continue
        if kind != "table":
            return False
        words = set(re.findall(r"[a-z0-9]{3,}", page.get_textbox(rect).casefold()))
        if len(words & read) < .7 * max(1, len(words)):
            return False
    return True


_INSTRUCTION_START = re.compile(
    r"^\s*(?:directions?|instructions?|note)\s*[:\-]"
    r"|\bquestions?\s+(?:no\.?|numbers?)\s*\d+\s*(?:and|to|-|–)\s*\d+"
    r"|\bassertion\s*[-–]?\s*(?:and\s+)?reason\s+(?:based|type)"
    r"|^\s*(?:this|the following)\s+section\b", re.I)


def _recover_page_top(page, meta, result, bands, lead, present, sy):
    """The printed text above a page's first question number continues the previous question (lead). When the AI
    read none of it, it is recovered from the PDF text layer, as omitted numbered rows are. Lines the previous page
    also prints (a running header or footer) and lone section headings are not question text. Text the AI read on
    this page under any number (e.g. instructions leading into the next question) is left where the AI put it."""
    if not bands or not page.number:
        return
    previous = page.parent[page.number - 1]
    # the question this text continues is the last one the previous source page prints: when an earlier page failed
    # to read, the last number among the pages that were read (lead) is not it
    printed_before = _anchors(previous)
    carry = printed_before[-1][0] if printed_before else lead
    if carry is None or carry in present or carry in {root for root, _t, _b in bands}:
        return
    first_top = bands[0][1]
    if first_top <= 0:
        return
    above = page.get_textbox(pymupdf.Rect(0, 0, page.rect.width, max(0, first_top - 2)))
    repeated = {_squash(line) for line in previous.get_text().splitlines() if _squash(line)}
    lines = [line.strip() for line in above.splitlines()
             if line.strip() and _squash(line) not in repeated and not _HEADING_ONLY.match(line)
             and not re.fullmatch(r"\d{1,2}(?:\.\d)?", line.strip())]  # a stray marks-column value
    # instructions leading into the next questions ("Assertion-Reason Based Questions / Directions: ...") end it
    cut = next((i for i, line in enumerate(lines) if _INSTRUCTION_START.search(line)), len(lines))
    text = "\n".join(lines[:cut])
    if len(_squash(text)) < 30:
        return
    read = _squash(" ".join(fragment.text or "" for fragment in result.fragments))
    if _squash(text)[:40] in read:
        return
    lead = carry
    result.fragments.append(Fragment(
        root=lead,
        text=text,
        continues=True,
        bbox={"x": 0, "y": 0, "width": meta["ocr_width"], "height": max(0, first_top - 2) * sy},
        # the PDF's own text, past the checks above: a record of what was added, not a question to review
        notes=[f"Text continuing question {lead} at the top of source page {meta['page_number']} was added from the "
               "PDF text (the AI reading skipped it)."],
    ))
    present.add(lead)


# a part label in Roman numerals at the start of a piece: "VII The given question has an error..."
_ROMAN_PART = re.compile(r"^\s*\(?((?=[IVX])X{0,3}(?:IX|IV|V?I{0,3}))\)?[.)]?\s+\S")
_ROMAN = {"I": 1, "V": 5, "X": 10}


def _roman(label: str) -> int:
    total = 0
    for a, b in zip(label, label[1:] + " "):
        total += -_ROMAN[a] if b != " " and _ROMAN[b] > _ROMAN[a] else _ROMAN[a]
    return total


def _keep_roman_parts(result, printed_here, lead, page_number):
    """A question's parts numbered I, II ... XII ("Complete any ten of the twelve tasks") can come back from the model
    as whole questions 7, 8 ... 12. A piece labelled with the Roman numeral of its own number, on a page that does not
    print that number as a question, is a part of the question printed before it (in reading order) on this page, or
    of the previous page's last question."""
    owner = lead
    for index, fragment in enumerate(result.fragments):
        if fragment.root in printed_here:
            owner = fragment.root
            continue
        label = _ROMAN_PART.match(fragment.text or "")
        if owner is None or not label or _roman(label[1]) != fragment.root or fragment.root == owner:
            continue
        part = label[1]
        if fragment.tree is not None and not fragment.tree.children:  # the part itself: a child of the question
            leaf = fragment.tree
            leaf.id, leaf.label = f"q{fragment.root}.{part.lower()}", f"{owner}({part})"
            fragment.tree = Node(id=f"q{fragment.root}", kind="all", label=str(fragment.root), children=[leaf])
        _keep_with(fragment, owner, f"p{page_number}-r{index + 1}")
        fragment.continues = True


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
            _keep_roman_parts(result, {root for root, _y, _x in anchors}, lead, meta["page_number"])
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
                if _only_transcribed_tables(page, candidates, owner, fragment):
                    # no picture in this question's printed area, only text or a ruled table the model has already
                    # transcribed (a match-the-columns block it called a diagram): nothing is missing
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
