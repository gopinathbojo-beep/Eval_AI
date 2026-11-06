"""Build one canonical whole question with an explicit nested scoring tree."""

import re
from collections import defaultdict
from .extraction import choice_signature, merge_nodes, settle_marks, tree_issues, tree_total
from ..models import ExamQuestion, AnswerKey, StudentAnswer, EvaluationItem
from ..services.state import set_state
from ..documents import cropping
from ..documents.storage import abs_path, rel


from .issues import split as split_issues


def review_reason(issues):
    """Keep the summary within the legacy column; full issues remain in structure."""
    value = "; ".join(issues)
    return value if len(value) <= 300 else value[:297].rstrip() + "..."


def crop_visuals(fragments, wd, prefix):
    """Persist every source visual; callers expose paths only through authorized routes."""
    output = []
    for page, fragment in fragments:
        for visual in fragment.visuals:
            bbox = cropping.normalise_bbox(
                visual.bbox,
                page["ocr_width"],
                page["ocr_height"],
                page["width"],
                page["height"],
            )
            if not bbox:
                fragment.issues.append(
                    f"Invalid {visual.kind} crop on page {page['page_number']}; review the source location."
                )
                continue
            try:
                path = cropping.save_crop(
                    abs_path(page["source_file"]),
                    bbox,
                    wd / "crops" / f"{prefix}-visual-{len(output) + 1:02d}.png",
                    pad=0,
                )
                crop_file = rel(path)
            except Exception:
                fragment.issues.append(
                    f"Could not store {visual.kind} crop on page {page['page_number']}."
                )
                continue
            output.append(
                {
                    "kind": visual.kind,
                    "description": visual.description,
                    "labels": visual.labels,
                    "page_number": page["page_number"],
                    "bbox": bbox,
                    "crop_file": crop_file,
                }
            )
    return output


_ALTERNATIVE = "Repeated whole-question label without a confirmed continuation; review source numbering."
_ACCESSIBLE = re.compile(r"^\W*for\s+visually\s+(?:impaired|challenged)", re.I)
_MENTIONS_VI = re.compile(r"visually\s+(?:impaired|challenged)", re.I)


_TABLE_HEAD = re.compile(r"^\s*(Q\.?\s*No\.?.*?Marks|This section comprises\b.*)\s*$", re.I | re.M)
# "Q. No. ANS HINTS/SOLUTION Marks" can share a line with the first answer
_TABLE_HEAD_INLINE = re.compile(r"Q\.?\s*No\.?\s+(?:Question|ANS\b[^\n]*?)\s+Marks\s*", re.I)
_SECTION_LINE = re.compile(r"^\s*section\s*\W{0,3}\s*[A-E]\b(?:\s*\[[^\]]*\])?[^\n]*?(?=\d+\s*[.(]|$)", re.I | re.M)
# a header is a short line; a page read as one run-on line keeps its question text
_PAPER_HEADER = re.compile(r"^[^\n]{0,120}?\b(?:marking\s+scheme|sample\s+question\s+paper|subject\s*:|class\s*-\s*x)\b[^\n]{0,120}$", re.I | re.M)
# the footer itself ("Note: ... Page 8 of 13"): on a run-on line it is cut off and the text before it stays
_FOOTER = re.compile(r"(?:^|[ \t]+)(?:note:[^\n]{0,120}?)?\bPage\s+\d+\s+of\s+\d+\s*$", re.I | re.M)
# "1^st", "1/4^th": a superscript ordinal, printed as 1st
_ORDINAL = re.compile(r"(\d)\s*\^\s*\{?(st|nd|rd|th)\}?\b", re.I)
# CBSE sample papers repeat this note at the foot of every page
_PAPER_NOTE = re.compile(r"^\W*there is no change in the question paper design[^\n]*(?:\n[^\n]*\d{4}-\d{2}\.?\s*)?$", re.I | re.M)
# "Question No. 31 to 33 are long answer type questions carrying 5 marks each." is the section's instruction
_SECTION_RULE = re.compile(r"^\s*questions?\s+no\.?\s*\d+\s*(?:to|-|\u2013)\s*\d+\s+are\b[^\n]*$", re.I | re.M)


_CROP_NOTE = re.compile(r"cropped (?:image|region|page|area|portion)|(?:this|the) crop\b|split(?:-page)? (?:half|region)", re.I)
_NUMBER_TOKEN = re.compile(r"^[-−–+]?\d+(?:\.\d+)?$")


def _drop_axis_labels(text):
    """A chart's axis ticks and data labels copied from the PDF text layer ("0 0.00333 … -0.5 -1 -1.5 … log k …")
    sit just before its "Figure N" caption. The chart is kept as a picture, so drop that run of numbers."""
    out, pos = [], 0
    for caption in re.finditer(r"Figure\s+\d+", text):
        before = text[pos:caption.start()]
        tokens = list(re.finditer(r"\S+", before))
        start, numbers = len(tokens), 0
        while start and (_NUMBER_TOKEN.match(tokens[start - 1].group()) or len(tokens[start - 1].group()) <= 6):
            start -= 1
            numbers += bool(_NUMBER_TOKEN.match(tokens[start].group()))
        if numbers >= 10 and numbers >= .7 * (len(tokens) - start):
            # keep a sentence's closing stop that the walk swallowed, and a space before the caption
            kept = before[:tokens[start].start()].rstrip()
            before = kept + ("." if tokens[start].group() == "." else "") + " "
        out.append(before + caption.group())
        pos = caption.end()
    return "".join(out) + text[pos:]


# printed markers that start a new line: OR, a choice ("17B", "31(B)"), a part ("II.", "(III)", "a)")
_BREAK_BEFORE = re.compile(
    r"\s+(?=(?:OR\b(?!\s*[a-z])|\d{1,3}\s*\(?[AB]\)?[.:]?\s+(?:I\b|\(I\))|\(?\b(?:II|III|IV|V|VI)\b\)?[.)]\s|"
    r"\((?:II|III|IV|V|VI|ii|iii|iv|v|vi)\)\s|\b[b-e]\)\s))")


def break_lines(text):
    """A long answer read as one run-on line ("17A I. … II. … OR 17B I. …") gets a new line at each printed marker.
    Text that already has its own line breaks is left as written."""
    out = []
    for line in text.split("\n"):
        out.append(_BREAK_BEFORE.sub("\n", line) if len(line) > 160 else line)
    return re.sub(r"\n{2,}", "\n", "\n".join(out))


def clean_text(text):
    """Drop the paper header/instructions the model copied into a question, page footers, and the
    one-glyph-per-line column a PDF text layer gives for typeset mathematics (its joined line is kept)."""
    heads = list(_TABLE_HEAD.finditer(text))
    if heads and (re.search(r"general\s+instructions", text, re.I) or heads[-1].start() < 400):
        text = text[heads[-1].end():]
    inline = list(_TABLE_HEAD_INLINE.finditer(text))
    if inline:
        text = text[inline[-1].end():]
    text = _PAPER_HEADER.sub("", text)
    text = _SECTION_LINE.sub("", text)
    text = _FOOTER.sub("", text)
    text = _PAPER_NOTE.sub("", text)
    text = _SECTION_RULE.sub("", text)
    text = _drop_axis_labels(text)
    text = _ORDINAL.sub(r"\1\2", text)
    text = break_lines(text)
    out, run, dropped = [], [], False
    for line in text.split("\n") + [None]:
        if line is not None and 0 < len(line.strip()) <= 4:
            run.append(line)
            continue
        if len(run) < 6:
            out += run
        else:
            dropped = True
        run = []
        if line is None:
            continue
        # the line that started a dropped column is repeated at the start of its joined line
        if dropped and out and out[-1].strip() and line.strip().startswith(out[-1].strip()):
            out.pop()
        dropped = False
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


_LEAD_LABEL = re.compile(r"^\s*(?:Q(?:uestion)?\.?\s*)?\d{1,3}\s*(?:\(\s*[A-Za-z]\s*\))?\s*[.):]?\s*", re.I)


def _key(text):
    return re.sub(r"\W+", "", _LEAD_LABEL.sub("", text or "", count=1).casefold())[:60]


def drop_borrowed_alternatives(results):
    """Remove an OR alternative the model copied from another printed question (e.g. Q23 read as Q22(B))."""
    owners = {}
    for _, result in results:
        for fragment in result.fragments:
            for line in (fragment.text or "").split("\n"):
                if len(_key(line)) >= 30:
                    owners.setdefault(_key(line), set()).add(fragment.root)
    for _, result in results:
        for fragment in result.fragments:
            tree = fragment.tree
            if tree is None or tree.kind != "choose" or len(tree.children) < 2:
                continue
            kept = []
            for child in tree.children:
                key = _key(child.text)
                # a visually impaired version is its own printed text, often sharing phrases with other answers
                vi = bool(child.audience) or _ACCESSIBLE.match(child.text or "") or "vi" in (child.label or "").lower().split()
                borrowed = not vi and len(key) >= 30 and any(
                    other != fragment.root and (key.startswith(k) or k.startswith(key))
                    for k, roots in owners.items() for other in roots
                )
                if borrowed:
                    fragment.issues.append(f"Removed alternative {child.label or child.id}: its text is another printed question.")
                    fragment.text = "\n".join(
                        line for line in fragment.text.split("\n")
                        if not (len(_key(line)) >= 30 and key.startswith(_key(line)[:40]))
                    )
                else:
                    kept.append(child)
            if len(kept) == 1:
                only = kept[0]
                tree.kind, tree.children, tree.limit = only.kind, only.children, None
                tree.text = only.text
                tree.marks = tree.marks if tree.marks is not None else only.marks
            elif kept:
                tree.children = kept


def apply_printed_sections(doc, results):
    """Section and per-question marks come from the printed SECTION headings, not the per-page model read."""
    from .layout import printed_sections

    printed = printed_sections(doc)
    for page, result in results:
        for fragment in result.fragments:
            letter, each = printed.get(fragment.root, (None, None))
            if letter and fragment.section != letter:
                fragment.section = letter
            if each and fragment.marks != each and not fragment.continues:
                # the printed section value is the authority: filling or correcting the model's mark is not a review item
                fragment.marks = each
                if fragment.tree is not None and not fragment.tree.children:
                    fragment.tree.marks = each


# a lone paper title such as "MATHEMATICS BASIC (241)" left after the header is removed
_TITLE_ONLY = re.compile(r"^[A-Z][A-Z &,\-]*(?:\(\d+\))?\s*$")
_ALTERNATIVE_START = re.compile(
    r"^\s*(?:Q(?:uestion)?\.?\s*)?(?:\d{1,3}\s*)?(?:\(\s*B\s*\)|OR\b|\W*for\s+visually\s+(?:impaired|challenged))", re.I)


def mark_answer_continuations(results, printed=None):
    """A question or answer cut by a page break restarts at the top of the next page under the same number.

    printed = {page: numbers the PDF prints there} (layout.printed_by_page): a number printed again on the new page
    is a new printing of that question (an OR alternative or a visually impaired version), never a continuation;
    one the page does not print can only be carried over. Without it (a scan) the piece's own text decides."""
    last = None
    for page, result in results:
        if result.fragments and last is not None:
            first = result.fragments[0]
            if first.root == last and not first.continues:
                on_page = printed.get(page.get("page_number")) if printed is not None else None
                if on_page is not None:
                    first.continues = first.root not in on_page
                else:
                    first.continues = not _ALTERNATIVE_START.match(first.text or "")
        if result.fragments:
            last = result.fragments[-1].root


def fix_false_continuations(results):
    """A visually impaired version is an alternative, never a continuation; a 'continuation' that only repeats
    text already read for the same question (a split-page overlap) is dropped."""
    seen, last = defaultdict(str), None
    for _, result in results:
        kept = []
        for index, fragment in enumerate(result.fragments):
            # a piece continues what comes just before it: the previous page's last question for the first piece,
            # the piece above it on the same page otherwise; never one that opens with its own choice label
            # or a visually impaired heading
            before = kept[-1].root if kept else last
            if fragment.continues and (fragment.root != before or _CHOICE_MARK.match(fragment.text or "")
                                       or _ACCESSIBLE.match(fragment.text or "")):
                fragment.continues = False
                fragment.issues = [x for x in fragment.issues if "continu" not in x.lower()]
            if fragment.continues and len(_key(fragment.text)) >= 12 and _key(fragment.text) in _squash_all(seen[fragment.root]):
                continue
            seen[fragment.root] += "\n" + (fragment.text or "")
            kept.append(fragment)
        result.fragments = kept
        if kept:
            last = kept[-1].root


def _squash_all(text):
    return re.sub(r"\W+", "", (text or "").casefold())


_UNSPLIT_MARKS = re.compile(
    r"(?:individual|separate|per[- ]?(?:part|subpart)|split|breakdown|distribution|allocation)s?\b[^.;]*"
    r"(?:not (?:printed|shown|given|specified|stated|indicated|visible)|unspecified|missing)"
    r"|share[sd]? (?:a |one )?(?:printed |combined |single )?(?:total|mark)"
    # the printed split ("3x1 in the marks column") is the marking scheme's business, not a paper problem
    r"|\ballocation\b|\b\d+\s*[x\u00d7]\s*\d+\b[^.;]*marks?", re.I)
# layout remarks: where a section heading or its instructions sit is not a problem with any question
_LAYOUT_NOTE = re.compile(r"section[- ]?[A-E]?\s+heading|heading and (?:its )?instructions|instructions? (?:is|are) printed", re.I)


# A model note reaches the school only when it says something the school must act on: content that cannot be read,
# is missing or is cut off, or a question number / marks that cannot be read. Transcription remarks ("printed as
# '-6'; retained as visible"), mark-splitting remarks, layout remarks and stray fragments ("BD; bbox2; width") are
# the reader's own business: they never make a question "Needs review".
_ACTIONABLE_NOTE = re.compile(
    r"illegible|unreadable|(?:cannot|can't|could not|couldn't|unable to) (?:be )?(?:read|see|make out|decipher)"
    r"|not (?:legible|readable|clear(?:ly)? visible)|blurr|smudge|faded|obscured|torn|damaged"
    r"|(?:text|question|part|option|options|answer|page|line|figure|diagram|table) (?:is |are )?(?:missing|cut off|truncated|incomplete)"
    r"|(?:missing|cut off|truncated|incomplete) (?:text|question|part|option|options|answer|page|line|figure|diagram|table)"
    r"|question number (?:is )?(?:missing|unclear|unreadable|not visible)"
    r"|marks? (?:is |are )?(?:unreadable|illegible|not legible)", re.I)


def actionable(notes):
    """The model's notes worth showing a teacher; see _ACTIONABLE_NOTE."""
    return [x for x in notes or [] if isinstance(x, str) and _ACTIONABLE_NOTE.search(x)
            and sum(c.isalpha() for c in x) >= 12 and not _CROP_NOTE.search(x)]


_ROMAN_CLASS = {"VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12}


def _metadata_value(name, value):
    """Class 'XII' and 12 are the same class; a code printed as 55 is 055."""
    text = str(value).strip().upper().removeprefix("CLASS").strip()
    if name == "class_level":
        return _ROMAN_CLASS.get(text, int(text) if text.isdigit() else value)
    if name == "subject_code" and text.isdigit():
        return text.zfill(3)
    return value


def _same_metadata(old, new):
    """'Accountancy' and 'ACCOUNTANCY 055' name one subject."""
    a, b = (re.sub(r"[^a-z]", "", str(x).casefold()) for x in (old, new))
    return str(old) == str(new) or (a and b and (a in b or b in a))


# the reader's own remarks sometimes come back as text ("No further numbered questions are visible on this page.")
_READER_REMARK = re.compile(r"^\s*(?:no (?:further|more|other) (?:numbered )?questions?\b|(?:the )?(?:rest|remainder) of "
                            r"(?:this|the) page\b|this page (?:has|contains) no\b)[^\n]*$", re.I | re.M)


def _drop_page_furniture(results):
    """Leave out what is not the question: a line printed on most pages (a running note or footer such as "Note: There
    is no change in the Question Paper Design ...", "Page 3 of 13") and the reader's remarks about the page. A piece left
    with no text and no parts is dropped."""
    def key(line):
        return re.sub(r"\d+", "#", re.sub(r"\s+", " ", line.strip().casefold()))
    pages_with = defaultdict(set)
    for page, result in results:
        # the PDF's own text layer shows a running note on every page even where the reader skipped it
        for line in (page.get("page_text") or "").splitlines():
            if len(line.strip()) >= 12:
                pages_with[key(line)].add(page["page_number"])
        for fragment in result.fragments:
            for line in (fragment.text or "").splitlines():
                if len(line.strip()) >= 12:
                    pages_with[key(line)].add(page["page_number"])
    # printed on (nearly) every page: a running header or footer. An instruction repeated in a few questions
    # ("Attempt either option A or B") is on far fewer pages and stays
    furniture = {k for k, pages in pages_with.items() if len(pages) >= max(3, round(0.8 * len(results)))}
    for _, result in results:
        for fragment in result.fragments:
            lines = [x for x in (fragment.text or "").splitlines() if key(x) not in furniture]
            fragment.text = _READER_REMARK.sub("", "\n".join(lines)).strip()
        result.fragments = [f for f in result.fragments if f.text or (f.tree and f.tree.children)]


def collect(doc, results, kind="question-paper"):
    from .layout import ground_visuals

    # clean first: the printed number of a fragment is read from its text when grounding it
    for _, result in results:
        # only the model's notes are filtered here; the app's own checks add their notes after this point
        result.issues = actionable(result.issues)
        for fragment in result.fragments:
            fragment.text = clean_text(fragment.text or "")
            if kind == "question-paper":
                # a paper printing one mark for several subparts is normal: the marking scheme gives the split
                fragment.issues = [x for x in fragment.issues if not _UNSPLIT_MARKS.search(x)]
            fragment.issues = actionable([x for x in fragment.issues if not _LAYOUT_NOTE.search(x)])
        result.fragments = [f for f in result.fragments
                            if (f.text and not _TITLE_ONLY.match(f.text)) or (f.tree and f.tree.children)]
    ground_visuals(doc, results, answers=kind == "answer-key")
    from .layout import tag_branches
    tag_branches(doc, results)  # after grounding: a re-grounded piece takes the option its printed row sits under
    for _, result in results:  # rows recovered from the PDF text layer need the same clean-up
        for fragment in result.fragments:
            fragment.text = clean_text(fragment.text or "")
            # "23 The values of…": the printed number is shown by the app already
            # "32. Under which …" too; "17 A." keeps its choice letter
            fragment.text = re.sub(rf"^\s*{fragment.root}\s*[.)]?(?=\s+[A-Z(])\s*", "", fragment.text, count=1)
            # notes about one half of a page the app split to re-read it ("cut off at the bottom of the cropped image")
            fragment.issues = [x for x in fragment.issues if not _CROP_NOTE.search(x)]
    _drop_page_furniture(results)
    if kind == "answer-key":
        mark_answer_continuations(results)
    else:
        from .layout import printed_by_page
        mark_answer_continuations(results, printed_by_page(doc))
    # before marks are set: a piece wrongly flagged as a continuation gets no whole-question marks
    fix_false_continuations(results)
    apply_printed_sections(doc, results)
    drop_borrowed_alternatives(results)
    roots = defaultdict(list)
    metadata, instructions, issues = {}, [], []
    for page, result in results:
        for name, value in result.metadata.items():
            if value is None:
                continue
            value = _metadata_value(name, value)
            if name in metadata and _same_metadata(metadata[name], value):
                continue
            if name in metadata and str(metadata[name]) != str(value):
                issues.append(f"Conflicting {name} on page {page['page_number']}")
            else:
                metadata[name] = value
        instructions += [x for x in result.instructions if x not in instructions]
        issues += [f"Page {page['page_number']}: {x}" for x in result.issues]
        for fragment in result.fragments:
            # the same number under the other Part B option is that option's question, not a repeated label
            # a question printed again for visually impaired students repeats its number by design
            if (roots[fragment.root] and not fragment.continues
                    and fragment.branch in {f.branch for _, f in roots[fragment.root]}
                    and not any(_MENTIONS_VI.search(f.text or "") for f in [fragment] + [x for _, x in roots[fragment.root]])):
                fragment.issues.append(_ALTERNATIVE)
            if fragment.tree:

                def node_ids(node):
                    return [node.id] + [
                        value for child in node.children for value in node_ids(child)
                    ]

                ids = node_ids(fragment.tree)
                if len(ids) != len(set(ids)):
                    fragment.issues.append(
                        "Duplicate part or criterion IDs on this source page; review the hierarchy."
                    )
            roots[fragment.root].append((page, fragment))
    doc.extraction = {
        "metadata": metadata,
        "instructions": instructions,
        "issues": issues,
    }
    return roots


# an internal choice starts with its (A)/(B) label; a bare OR also sits between case-study parts, so it is not evidence
# "(A)", "OR (B)" or "25 A."; uppercase only: "(a) Long term Borrowings" opening a page is a part, not an alternative
_CHOICE_MARK = re.compile(r"^\s*(?:[Oo][Rr]\s+)?(?:(?:[Qq]?\s*\d{1,3}\s*\.?\s*)?\(\s*[AB]\s*\)|\d{1,3}\s*[AB]\s*\.)")
# a bare "A." / "B." (the number cut off when the text was cleaned) is a choice only next to a printed OR
_BARE_CHOICE = re.compile(r"^\s*[AB]\s*[.)]\s")
_OR_LINE_END = re.compile(r"(?m)^\s*OR\s*\Z")
_OR_LINE_START = re.compile(r"\A\s*OR\b")
_B_START = re.compile(r"^\s*(?:OR\s+)?(?:\d{1,3}\s*)?\(?\s*B\s*\)?\s*[.)]?\s+\S")  # "B. ...", "OR 31 B. ...", "(B) ..."

_METHOD_HEADING = re.compile(r"^\s*(?:alternative|alternate|another)\s+(?:solution|method|approach)\b", re.I | re.M)
_BRANCH_LABEL = re.compile(r"^\s*(?:Q\.?\s*)?(?:\d+\s*)?\(?([A-D])\)?[.)]?\s*$", re.I)


def mark_solution_methods(fragment):
    """A printed alternative solution is a method choice inside its question branch."""
    if not fragment.tree or not _METHOD_HEADING.search(fragment.text or ""):
        return

    def visit(node):
        for child in node.children:
            visit(child)
        if node.kind != "choose" or node.limit != 1:
            return
        branches = {match[1].upper() for child in node.children
                    if (match := _BRANCH_LABEL.fullmatch(child.label or ""))}
        method_label = any(_METHOD_HEADING.search(child.label or "")
                           or _METHOD_HEADING.match(child.text or "") for child in node.children)
        if method_label and len(branches) <= 1:
            node.choice_type = "method"

    visit(fragment.tree)


def _alternatives(fragments, printed_choice=False):
    """Whole questions printed twice under one number are internal choices (OR) or a visually impaired version.

    A version may itself run onto the next page: its continuation pieces join that version, not a new one."""
    if any(f.tree is None for _, f in fragments) or fragments[0][1].continues:
        return None
    groups = []
    for page, fragment in fragments:
        # a page showing a one-way choice ("A ... OR" with nothing after it) and a next piece opening with "B." or
        # "OR B.": that piece is alternative B, even when the reader flagged it as a continuation
        opens_b = (groups and _B_START.match(fragment.text or "") and groups[-1][0][1].tree is not None
                   and groups[-1][0][1].tree.kind == "choose" and len(groups[-1][0][1].tree.children) == 1)
        if fragment.continues and groups and not opens_b:
            groups[-1].append((page, fragment))
        else:
            groups.append([(page, fragment)])
    if len(groups) < 2:
        return None
    heads = [group[0][1] for group in groups]
    accessible = [_ACCESSIBLE.match(f.text or "") is not None for f in heads]
    # printed evidence of a choice: an (A)/(B) label, an OR line, or a visually impaired version
    bare_or = (len(heads) == 2 and _BARE_CHOICE.match(heads[0].text or "") and _B_START.match(heads[1].text or "")
               and (_OR_LINE_END.search((groups[0][-1][1].text or "").rstrip()) or _OR_LINE_START.match(heads[1].text or "")
                    or (heads[0].tree is not None and heads[0].tree.kind == "choose")))
    if not (printed_choice or bare_or or any(accessible) or any(_CHOICE_MARK.match(f.text or "") for f in heads)):
        return None
    # each copy carries the same whole-question marks (a visually impaired version may print none);
    # unmarked pieces are parts of one question
    # an alternative the PDF prints under the same number may show no marks of its own ("OR 25 B." beside one marks cell)
    marks = {f.marks for f, vi in zip(heads, accessible) if not ((vi or printed_choice or bare_or) and f.marks is None)}
    if len(marks) != 1 or None in marks:
        return None
    root = heads[0].tree.id
    versions = []
    for index, group in enumerate(groups):
        merged, _ = merge_nodes([f.tree for _, f in group])
        child = dict(merged[0]) if len(merged) == 1 else heads[index].tree.model_dump()
        if (child.get("kind") == "choose" and len(child.get("children") or []) == 1
                and not (child["children"][0].get("children") and child["children"][0].get("kind") == "choose")):
            # "A ... OR" with B on the next page: this page's one-way choice is just alternative A
            only = dict(child["children"][0])
            only["marks"] = only.get("marks") if only.get("marks") is not None else child.get("marks")
            child = only
        if (child.get("kind") == "choose" and child.get("limit") == 1
                and child.get("choice_type", "question") == "question" and len(child.get("children") or []) > 1):
            # one page read "VI version OR (B)" as its own choice: those are further alternatives, not one nested version
            versions += [(dict(c), _ACCESSIBLE.match(c.get("text") or "") is not None or c.get("audience") == "accessible")
                         for c in child["children"]]
        else:
            versions.append((child, accessible[index]))
    # a paper prints its visually impaired versions together under one heading, after the standard ones:
    # "For Visually Impaired: Q34 (A) ... OR Q34 (B) ..." - every version after the heading is for that audience
    seen_vi = False
    for index, (child, vi) in enumerate(versions):
        seen_vi = seen_vi or vi
        versions[index] = (child, seen_vi)
    standard = [c for c, vi in versions if not vi]
    accessible_versions = [c for c, vi in versions if vi]
    if len(standard) > 1 and len(accessible_versions) > 1:
        # each audience has its own internal choice: one version per audience, each a one-of-its-alternatives choice
        groups = []
        for key, audience, members in (("std", "standard", standard), ("vi", "accessible", accessible_versions)):
            for index, child in enumerate(members):
                child["id"] = f"{root}-{key}-alt{index + 1}"
                child["label"] = child.get("label") or f"Alternative {index + 1}"
                child["audience"] = None
            groups.append({"id": f"{root}-{key}", "kind": "choose", "label": "For Visually Impaired" if key == "vi" else "",
                           "text": "", "marks": next(iter(marks), None), "limit": 1, "choice_type": "question",
                           "audience": audience, "response_type": "open", "deductions": [], "children": members})
        for _, fragment in fragments:
            fragment.issues = [x for x in fragment.issues if x != _ALTERNATIVE]
        return {"id": root, "kind": "choose", "label": "", "text": "", "marks": next(iter(marks), None),
                "limit": 1, "choice_type": "question", "audience": None, "response_type": "open",
                "deductions": [], "children": groups}
    children = []
    for index, (child, vi) in enumerate(versions):
        child["id"] = f"{root}-alt{index + 1}"
        if child.get("marks") is None:  # every alternative is worth the question's marks
            child["marks"] = next(iter(marks), None)
        child["label"] = child.get("label") or f"Alternative {index + 1}"
        if any(vi for _, vi in versions):
            child["audience"] = "accessible" if vi else "standard"
        children.append(child)
    tree = {"id": root, "kind": "choose", "label": "", "text": "", "marks": next(iter(marks), None),
            "limit": 1, "choice_type": "question", "audience": None, "response_type": "open",
            "deductions": [], "children": children}
    for _, fragment in fragments:
        fragment.issues = [x for x in fragment.issues if x != _ALTERNATIVE]
    return tree


def _is_vi(node):
    return node.get("audience") == "accessible" or _ACCESSIBLE.match(node.get("text") or "") is not None


_OPTION_LABEL = re.compile(r"^\s*\(?\s*[A-Da-d]\s*\)?\s*\.?\s*$")
_CHOICE_LABEL = re.compile(r"^\s*(?:Q?\s*\d{1,3})?\s*\(?\s*([AB])\s*\)?\s*\.?\s*$", re.I)


def shape_choices(node):
    """A visually impaired version read as one more required part is an alternative to the rest, and a
    one-of choice nested directly in another one-of choice is the same choice. Each version is totalled for its own audience."""
    if not isinstance(node, dict):
        return node
    node["children"] = [shape_choices(child) for child in node.get("children") or []]
    children = node["children"]
    if (node.get("kind") == "all" and len(children) >= 2 and all(
            _OPTION_LABEL.match(c.get("label") or "") and not c.get("marks") and not c.get("children") for c in children)):
        # MCQ options (A)-(D) read as parts: they are one answer worth the question's marks
        options = "\n".join(f"{c.get('label')} {c.get('text') or ''}".strip() for c in children)
        node.update(kind="point", response_type="mcq", children=[],
                    text=((node.get("text") or "") + "\n" + options).strip())
        return node
    if node.get("kind") == "all" and len(children) == 2:
        labels = [_CHOICE_LABEL.match(c.get("label") or "") for c in children]
        marks = {c.get("marks") for c in children}
        if all(labels) and {m[1].upper() for m in labels} == {"A", "B"} and len(marks) == 1 and None not in marks \
                and node.get("marks") in (None, *marks):
            # "31 A ... OR ... 31 B" read as two required parts, each carrying the question's marks: one of them is answered
            node.update(kind="choose", limit=1, choice_type="question", marks=next(iter(marks)))
    if node.get("kind") == "all" and len(children) > 1:
        vi = [c for c in children if _is_vi(c)]
        rest = [c for c in children if not _is_vi(c) and c.get("kind") != "context"]
        if len(vi) == 1 and rest:
            whole = node.get("marks") or tree_total(dict(node, kind="all", children=rest), {"accessibility": "standard"})
            if whole and abs(tree_total(vi[0], {"accessibility": "accessible"}) - whole) < 1e-6:
                standard = rest[0] if len(rest) == 1 else {
                    "id": f"{node['id']}.std", "kind": "all", "label": "", "text": node.get("text") or "",
                    "marks": whole, "limit": None, "choice_type": "question", "audience": None,
                    "response_type": "open", "deductions": [], "children": rest}
                standard["audience"], vi[0]["audience"] = "standard", "accessible"
                context = [c for c in children if c.get("kind") == "context"]
                node.update(kind="choose", limit=1, choice_type="question", marks=whole,
                            children=context + [standard, vi[0]])
                children = node["children"]
    if node.get("kind") == "choose" and node.get("limit") == 1 and node.get("choice_type", "question") == "question":
        flat = []
        for child in children:
            if (child.get("kind") == "choose" and child.get("limit") == 1
                    and child.get("choice_type", "question") == "question"
                    and not child.get("audience")):  # an audience's own choice (VI version with its OR) stays nested
                flat += child.get("children") or []
            else:
                flat.append(child)
        node["children"] = flat
    return node


_PAGE_ONLY_NOTE = re.compile(r"(?:next|previous|following|preceding) page|(?:on|in) this page|"
                             r"may continue|continues? (?:on|from)|cut off", re.I)


BRANCH_LABELS = {"financial": "Analysis of Financial Statements", "computerised": "Computerised Accounting"}


def _branch_versions(fragments, options, printed_choice):
    """Accountancy Part B: one printed number per option (27-34). Each option is built as its own question and the
    two become alternatives tagged with their option, so the student's answered option is the one marked."""
    groups = {}
    for page, fragment in fragments:
        groups.setdefault(fragment.branch, []).append((page, fragment))
    if len(groups) < 2 or None in groups:
        return None
    root = fragments[0][1].root
    # the number is printed twice because of the two options; a choice inside one option shows its own (A)/(B)
    parts = {name: combined(group, options) for name, group in groups.items()}
    marks = max((part[3] for part in parts.values() if part[3]), default=None)
    children, texts, problems = [], [], []
    for name, (text, tree, issues, part_marks, _section) in parts.items():
        if tree is None:  # a row read from the PDF text only: one point worth the question's printed marks
            tree = {"id": f"q{root}", "kind": "point", "label": "", "text": text, "marks": part_marks or marks,
                    "limit": None, "choice_type": "question", "audience": None, "response_type": "open",
                    "deductions": [], "children": []}
            issues = [x for x in issues if x != _ONE_ROOT]
        tree = dict(tree, id=f"q{root}-{name}", label=BRANCH_LABELS[name], audience=name)
        if tree.get("marks") is None:
            tree["marks"] = part_marks or marks
        children.append(tree)
        texts.append(f"[Part B - {BRANCH_LABELS[name]}]\n{text}")
        problems += issues
    tree = {"id": f"q{root}", "kind": "choose", "label": "", "text": "", "marks": marks, "limit": 1,
            "choice_type": "question", "audience": None, "response_type": "open", "deductions": [],
            "children": children}
    sections = {part[4] for part in parts.values() if part[4]}
    return "\nOR\n".join(texts), tree, problems, marks, next(iter(sorted(sections)), None)


_ONE_ROOT = "Review the whole-question scoring tree; one root is required."


def combined(fragments, options=None, printed_choice=False):
    for _, fragment in fragments:
        mark_solution_methods(fragment)
    branched = _branch_versions(fragments, options, printed_choice)
    if branched:
        return branched
    alternative = _alternatives(fragments, printed_choice)
    # a continuation's root marks are a part's marks (or a guess where no marks are printed), not the question's
    trees, problems = ([alternative], []) if alternative else merge_nodes(
        [f.tree.model_copy(update={"marks": None}) if f.continues and f.tree is not None else f.tree
         for _, f in fragments])
    if len(trees) != 1:
        problems.append(_ONE_ROOT)
    tree = shape_choices(trees[0]) if len(trees) == 1 else None
    # "OR" only between printed alternatives; a page-break continuation of the same alternative joins with a newline
    text, seen = "", set()
    for _, f in fragments:
        if not f.text.strip() or f.text in seen:
            continue
        seen.add(f.text)
        text += ("" if not text else "\nOR\n" if alternative and not f.continues else "\n") + f.text
    # a page ending on "OR" and the next page opening with it print one OR
    text = re.sub(r"(?m)^(\s*OR\s*\n)(?:\s*OR\s*\n)+", r"\1", text)
    # A split MCQ may be classified differently on its continuation page. Its
    # four printed options still represent a single scored response.
    if (len(fragments) > 1 and all(f.tree and not f.tree.children for _, f in fragments)
            and all(re.search(rf"(?m)^\s*{letter}[.)]\s", text) for letter in "ABCD")
            and tree and all(f"Conflicting kind for {tree['id']}" == p for p in problems)):
        tree.update(kind="point", response_type="mcq", children=[])
        problems = []
    # Reconstruct a whole-question A/B choice when a page break made the
    # continuation look like another question. Keep each branch holistic:
    # the paper does not give the individual allocations.
    choice = re.search(r"(?ms)^\s*A[.)]\s*(.*?)^\s*OR\s*$\s*^\s*B[.)]\s*(.*)", text)
    if (choice and re.search(r"attempt\s+either\s+option\s+A\s+or\s+B", text, re.I)
            and any(_ALTERNATIVE in f.issues for _, f in fragments)):
        starts_for_choice = [f.marks for _, f in fragments if f.marks is not None and not f.continues]
        if starts_for_choice and len(set(starts_for_choice)) == 1:
            mark = starts_for_choice[0]
            root = f"q{fragments[0][1].root}"
            tree = {"id": root, "kind": "choose", "limit": 1, "marks": mark,
                    "children": [{"id": f"{root}.{label}", "kind": "point", "label": label,
                                  "text": choice.group(index).strip(), "marks": mark, "children": []}
                                 for index, label in ((1, "A"), (2, "B"))]}
            for _, fragment in fragments:
                fragment.issues = [issue for issue in fragment.issues if issue != _ALTERNATIVE]
    sections = {f.section for _, f in fragments if f.section}
    # a continuation piece carries step marks, not the whole question's
    starts = [f.marks for _, f in fragments if f.marks is not None and not f.continues]
    marks = set(starts)
    if len(marks) > 1:
        problems.append("Conflicting whole-question marks across pages")
    if len(sections) > 1:
        problems.append("Conflicting section labels across pages")
    issues = [x for _, f in fragments for x in f.issues]
    if len({page["page_number"] for page, _ in fragments}) > 1:
        # page-by-page model notes ("continues on the next page", "not visible on this page") are settled once joined
        issues = [x for x in issues if not _PAGE_ONLY_NOTE.search(x)]
    problems += issues
    # the marks column prints them where the question starts: the first piece in page order, not any of a set
    derived = starts[0] if starts else None
    if derived is None and tree:
        derived = tree_total(tree, options or {}) or None
    return text, tree, problems, derived, next(iter(sections), None)


def build_questions(db, doc, exam, results):
    ids = [q.id for q in db.query(ExamQuestion).filter_by(exam_id=exam.id)]
    if ids:
        db.query(AnswerKey).filter_by(exam_id=exam.id).update(
            {AnswerKey.exam_question_id: None}
        )
        db.query(StudentAnswer).filter(StudentAnswer.exam_question_id.in_(ids)).update(
            {StudentAnswer.exam_question_id: None}, synchronize_session=False
        )
        db.query(EvaluationItem).filter(
            EvaluationItem.exam_question_id.in_(ids)
        ).delete(synchronize_session=False)
        db.query(ExamQuestion).filter_by(exam_id=exam.id).delete()
    from .layout import printed_twice

    choices = printed_twice(doc)
    last_section = None
    for root, fragments in sorted(collect(doc, results).items()):
        visuals = crop_visuals(
            fragments, abs_path(doc.original_file).parent, f"q{root}"
        )
        text, tree, issues, marks, section = combined(fragments, exam.standard_options, root in choices)
        tree = settle_marks(tree, marks)
        issues, notes = split_issues(issues)  # settled ones are kept as notes, never a review
        # sections run in order through the paper (A, B, C ...): a question with none, or one read as an earlier
        # section after a later one has started, belongs to the section it is printed in
        if last_section and (not section or (len(section) == 1 == len(last_section) and section < last_section)):
            section = last_section
        last_section = section or last_section
        db.add(
            ExamQuestion(
                exam_id=exam.id,
                document_id=doc.id,
                display_number=str(root),
                normalized_number=str(root),
                question_text=text,
                raw_ocr_text=text,
                max_marks=marks,
                section=section,
                question_type=fragments[0][1].question_type,
                position=root,
                page_start=fragments[0][0]["page_number"],
                page_end=fragments[-1][0]["page_number"],
                structure={
                    "root": root,
                    "tree": tree,
                    "issues": issues,
                    "notes": notes,
                    "source_pages": [p["page_number"] for p, _ in fragments],
                    "visuals": visuals,
                },
                bbox=visuals[0]["bbox"] if visuals else None,
                crop_file=visuals[0]["crop_file"] if visuals else None,
                verification_status="NEEDS_REVIEW" if issues else "UNVERIFIED",
                review_reason=review_reason(issues) or None,
            )
        )
    set_state(exam, "QUESTIONS_EXTRACTED")
    exam.standard_validation = None
    db.commit()
    from ..services.mapping_service import apply_key_mapping
    from ..models import AnswerKeyDocument

    for key_doc in db.query(AnswerKeyDocument).filter_by(
        exam_id=exam.id, is_active=True
    ):
        apply_key_mapping(db, exam.id, key_doc.id)
    db.commit()


def use_question_marks(fragments, question):
    """A marking scheme prints step marks, not question totals: the whole-question marks are the question paper's."""
    if question is None or question.max_marks is None:
        return
    for _, fragment in fragments:
        if fragment.continues:
            continue
        fragment.marks = float(question.max_marks)
        if fragment.tree is not None and fragment.tree.kind != "choose" and not fragment.tree.children:
            fragment.tree.marks = float(question.max_marks)


def scheme_tree(tree, question, options):
    """The scheme's scoring tree, fitted to the question's printed marks. When it still does not fit the paper
    (another split, or OR alternatives read as parts) the question's own tree scores it: the scheme text is kept
    as printed and the grader reads it against that tree."""
    import copy

    q_tree = (question.structure or {}).get("tree") if question is not None else None
    tree = settle_marks(tree, question.max_marks if question is not None else None)
    if not q_tree or tree is None:
        return tree or (copy.deepcopy(q_tree) if q_tree else None)
    fits = (not tree_issues(tree, options)
            and abs(tree_total(tree, options) - (question.max_marks or 0)) < 1e-7
            and sorted(choice_signature(tree, options)) == sorted(choice_signature(q_tree, options)))
    return tree if fits else copy.deepcopy(q_tree)


def build_keys(db, doc, exam, results, changed_pages=None):
    if changed_pages is None:
        db.query(AnswerKey).filter_by(exam_id=exam.id).update({AnswerKey.is_active: False})
        db.query(AnswerKey).filter_by(document_id=doc.id).delete()
    qs = {
        q.normalized_number: q
        for q in db.query(ExamQuestion).filter_by(exam_id=exam.id)
    }
    from .layout import printed_twice

    choices = printed_twice(doc)
    for root, fragments in sorted(collect(doc, results, kind="answer-key").items()):
        if changed_pages is not None:
            if not any(page["page_number"] in changed_pages for page, _ in fragments):
                continue
            db.query(AnswerKey).filter_by(document_id=doc.id, normalized_number=str(root)).delete()
        visuals = crop_visuals(
            fragments, abs_path(doc.original_file).parent, f"k{root}"
        )
        q = qs.get(str(root))
        use_question_marks(fragments, q)
        text, tree, issues, marks, _ = combined(fragments, exam.standard_options, root in choices)
        tree = scheme_tree(tree, q, exam.standard_options or {})
        # a scheme's section is the question paper's; page-by-page section guesses are not the teacher's concern
        issues, notes = split_issues(issues)  # settled ones are kept as notes, never a review
        criteria = [x for _, f in fragments for x in f.criteria]
        db.add(
            AnswerKey(
                exam_id=exam.id,
                document_id=doc.id,
                raw_question_number=str(root),
                normalized_number=str(root),
                exam_question_id=q.id if q else None,
                answer_text=text,
                raw_ocr_text=text,
                marks=marks,
                criteria=criteria,
                accepted_answers=[x for _, f in fragments for x in f.accepted_answers],
                mapping_status="MAPPED" if q else "UNMAPPED",
                page_number=fragments[0][0]["page_number"],
                bbox=visuals[0]["bbox"] if visuals else None,
                crop_file=visuals[0]["crop_file"] if visuals else None,
                mark_mismatch=bool(q and marks != q.max_marks),
                verification_status="UNVERIFIED",
                rubric_status="UNREVIEWED",
                rubric={
                    "cbse_tree": tree,
                    "problems": issues,
                    "kind": "cbse",
                    "points": [],
                    "deductions": [],
                    "notes": notes,
                    "stated_total": marks,
                    "total": marks,
                    "source_pages": [p["page_number"] for p, _ in fragments],
                    "visuals": visuals,
                },
            )
        )
    exam.standard_validation = None
    db.commit()
