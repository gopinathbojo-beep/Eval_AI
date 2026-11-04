"""Build one canonical whole question with an explicit nested scoring tree."""

import re
from collections import defaultdict
from .extraction import merge_nodes, tree_total
from ..models import ExamQuestion, AnswerKey, StudentAnswer, EvaluationItem
from ..services.state import set_state
from ..documents import cropping
from ..documents.storage import abs_path, rel


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


_TABLE_HEAD = re.compile(r"^\s*(Q\.?\s*No\.?.*?Marks|This section comprises\b.*)\s*$", re.I | re.M)
# "Q. No. ANS HINTS/SOLUTION Marks" can share a line with the first answer
_TABLE_HEAD_INLINE = re.compile(r"Q\.?\s*No\.?\s+(?:Question|ANS\b[^\n]*?)\s+Marks\s*", re.I)
_SECTION_LINE = re.compile(r"^\s*section\s*\W{0,3}\s*[A-E]\b(?:\s*\[[^\]]*\])?[^\n]*?(?=\d+\s*[.(]|$)", re.I | re.M)
_PAPER_HEADER = re.compile(r"^[^\n]*\b(?:marking\s+scheme|sample\s+question\s+paper|subject\s*:|class\s*-\s*x)\b[^\n]*$", re.I | re.M)
_FOOTER = re.compile(r"^.*\bPage\s+\d+\s+of\s+\d+\s*$", re.I | re.M)


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
_ALTERNATIVE_START = re.compile(r"^\s*(?:\d{1,3}\s*)?(?:\(\s*B\s*\)|OR\b|\W*for\s+visually\s+(?:impaired|challenged))", re.I)


def mark_answer_continuations(results):
    """An answer cut by a page break restarts at the top of the next page under the same number."""
    last = None
    for _, result in results:
        if result.fragments and last is not None:
            first = result.fragments[0]
            if first.root == last and not first.continues and not _ALTERNATIVE_START.match(first.text or ""):
                first.continues = True
        if result.fragments:
            last = result.fragments[-1].root


def fix_false_continuations(results):
    """A visually impaired version is an alternative, never a continuation; a 'continuation' that only repeats
    text already read for the same question (a split-page overlap) is dropped."""
    seen, last = defaultdict(str), None
    for _, result in results:
        kept = []
        for index, fragment in enumerate(result.fragments):
            # only the first piece of a page, under the previous page's last number, can continue it,
            # and never one that opens with its own choice label or a visually impaired heading
            if fragment.continues and (index > 0 or fragment.root != last or _CHOICE_MARK.match(fragment.text or "")
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
    r"|share[sd]? (?:a |one )?(?:printed |combined |single )?(?:total|mark)", re.I)


def collect(doc, results, kind="question-paper"):
    from .layout import ground_visuals

    # clean first: the printed number of a fragment is read from its text when grounding it
    for _, result in results:
        for fragment in result.fragments:
            fragment.text = clean_text(fragment.text or "")
            if kind == "question-paper":
                # a paper printing one mark for several subparts is normal: the marking scheme gives the split
                fragment.issues = [x for x in fragment.issues if not _UNSPLIT_MARKS.search(x)]
        result.fragments = [f for f in result.fragments
                            if (f.text and not _TITLE_ONLY.match(f.text)) or (f.tree and f.tree.children)]
    ground_visuals(doc, results, answers=kind == "answer-key")
    for _, result in results:  # rows recovered from the PDF text layer need the same clean-up
        for fragment in result.fragments:
            fragment.text = clean_text(fragment.text or "")
    if kind == "answer-key":
        mark_answer_continuations(results)
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
            if name in metadata and str(metadata[name]) != str(value):
                issues.append(f"Conflicting {name} on page {page['page_number']}")
            else:
                metadata[name] = value
        instructions += [x for x in result.instructions if x not in instructions]
        issues += [f"Page {page['page_number']}: {x}" for x in result.issues]
        for fragment in result.fragments:
            if roots[fragment.root] and not fragment.continues:
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
_CHOICE_MARK = re.compile(r"^\s*(?:Q?\s*\d{1,3}\s*\.?\s*)?\(\s*[AB]\s*\)", re.I)


def _alternatives(fragments, printed_choice=False):
    """Whole questions printed twice under one number are internal choices (OR) or a visually impaired version.

    A version may itself run onto the next page: its continuation pieces join that version, not a new one."""
    if any(f.tree is None for _, f in fragments) or fragments[0][1].continues:
        return None
    groups = []
    for page, fragment in fragments:
        if fragment.continues and groups:
            groups[-1].append((page, fragment))
        else:
            groups.append([(page, fragment)])
    if len(groups) < 2:
        return None
    heads = [group[0][1] for group in groups]
    accessible = [_ACCESSIBLE.match(f.text or "") is not None for f in heads]
    # printed evidence of a choice: an (A)/(B) label, an OR line, or a visually impaired version
    if not (printed_choice or any(accessible) or any(_CHOICE_MARK.match(f.text or "") for f in heads)):
        return None
    # each copy carries the same whole-question marks (a visually impaired version may print none);
    # unmarked pieces are parts of one question
    marks = {f.marks for f, vi in zip(heads, accessible) if not (vi and f.marks is None)}
    if len(marks) != 1 or None in marks:
        return None
    root = heads[0].tree.id
    versions = []
    for index, group in enumerate(groups):
        merged, _ = merge_nodes([f.tree for _, f in group])
        child = dict(merged[0]) if len(merged) == 1 else heads[index].tree.model_dump()
        if child.get("kind") == "choose" and child.get("limit") == 1 and len(child.get("children") or []) > 1:
            # one page read "VI version OR (B)" as its own choice: those are further alternatives, not one nested version
            versions += [(dict(c), _ACCESSIBLE.match(c.get("text") or "") is not None or c.get("audience") == "accessible")
                         for c in child["children"]]
        else:
            versions.append((child, accessible[index]))
    children = []
    for index, (child, vi) in enumerate(versions):
        child["id"] = f"{root}-alt{index + 1}"
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


def shape_choices(node):
    """A visually impaired version read as one more required part is an alternative to the rest, and a
    one-of choice nested directly in another one-of choice is the same choice. Each version is totalled for its own audience."""
    if not isinstance(node, dict):
        return node
    node["children"] = [shape_choices(child) for child in node.get("children") or []]
    children = node["children"]
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
                    and child.get("choice_type", "question") == "question"):
                flat += child.get("children") or []
            else:
                flat.append(child)
        node["children"] = flat
    return node


_PAGE_ONLY_NOTE = re.compile(r"(?:next|previous|following|preceding) page|not visible on this page|"
                             r"may continue|continues? (?:on|from)|cut off", re.I)


def combined(fragments, options=None, printed_choice=False):
    alternative = _alternatives(fragments, printed_choice)
    trees, problems = ([alternative], []) if alternative else merge_nodes([f.tree for _, f in fragments])
    if len(trees) != 1:
        problems.append("Review the whole-question scoring tree; one root is required.")
    tree = shape_choices(trees[0]) if len(trees) == 1 else None
    text = ("\nOR\n" if alternative else "\n").join(dict.fromkeys(f.text for _, f in fragments if f.text.strip()))
    # a page ending on "OR" and the next page opening with it print one OR
    text = re.sub(r"(?m)^(\s*OR\s*\n)(?:\s*OR\s*\n)+", r"\1", text)
    sections = {f.section for _, f in fragments if f.section}
    # a continuation piece carries step marks, not the whole question's
    marks = {f.marks for _, f in fragments if f.marks is not None and not f.continues}
    if len(marks) > 1:
        problems.append("Conflicting whole-question marks across pages")
    if len(sections) > 1:
        problems.append("Conflicting section labels across pages")
    issues = [x for _, f in fragments for x in f.issues]
    if len({page["page_number"] for page, _ in fragments}) > 1:
        # page-by-page model notes ("continues on the next page", "not visible on this page") are settled once joined
        issues = [x for x in issues if not _PAGE_ONLY_NOTE.search(x)]
    problems += issues
    derived = next(iter(marks), None)
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
    for root, fragments in sorted(collect(doc, results).items()):
        visuals = crop_visuals(
            fragments, abs_path(doc.original_file).parent, f"q{root}"
        )
        text, tree, issues, marks, section = combined(fragments, exam.standard_options, root in choices)
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


def build_keys(db, doc, exam, results):
    db.query(AnswerKey).filter_by(exam_id=exam.id).update({AnswerKey.is_active: False})
    db.query(AnswerKey).filter_by(document_id=doc.id).delete()
    qs = {
        q.normalized_number: q
        for q in db.query(ExamQuestion).filter_by(exam_id=exam.id)
    }
    from .layout import printed_twice

    choices = printed_twice(doc)
    for root, fragments in sorted(collect(doc, results, kind="answer-key").items()):
        visuals = crop_visuals(
            fragments, abs_path(doc.original_file).parent, f"k{root}"
        )
        q = qs.get(str(root))
        use_question_marks(fragments, q)
        text, tree, issues, marks, _ = combined(fragments, exam.standard_options, root in choices)
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
                    "notes": [],
                    "stated_total": marks,
                    "total": marks,
                    "source_pages": [p["page_number"] for p, _ in fragments],
                    "visuals": visuals,
                },
            )
        )
    exam.standard_validation = None
    db.commit()
