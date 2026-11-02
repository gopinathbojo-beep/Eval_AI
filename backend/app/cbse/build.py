"""Build one canonical whole question with an explicit nested scoring tree."""

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


def collect(doc, results):
    from .layout import ground_visuals

    ground_visuals(doc, results)
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
                fragment.issues.append(
                    "Repeated whole-question label without a confirmed continuation; review source numbering."
                )
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


def combined(fragments, options=None):
    trees, problems = merge_nodes([f.tree for _, f in fragments])
    if len(trees) != 1:
        problems.append("Review the whole-question scoring tree; one root is required.")
    tree = trees[0] if len(trees) == 1 else None
    text = "\n".join(dict.fromkeys(f.text for _, f in fragments if f.text.strip()))
    sections = {f.section for _, f in fragments if f.section}
    marks = {f.marks for _, f in fragments if f.marks is not None}
    if len(marks) > 1:
        problems.append("Conflicting whole-question marks across pages")
    if len(sections) > 1:
        problems.append("Conflicting section labels across pages")
    problems += [x for _, f in fragments for x in f.issues]
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
    for root, fragments in sorted(collect(doc, results).items()):
        visuals = crop_visuals(
            fragments, abs_path(doc.original_file).parent, f"q{root}"
        )
        text, tree, issues, marks, section = combined(fragments, exam.standard_options)
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


def build_keys(db, doc, exam, results):
    db.query(AnswerKey).filter_by(exam_id=exam.id).update({AnswerKey.is_active: False})
    db.query(AnswerKey).filter_by(document_id=doc.id).delete()
    qs = {
        q.normalized_number: q
        for q in db.query(ExamQuestion).filter_by(exam_id=exam.id)
    }
    for root, fragments in sorted(collect(doc, results).items()):
        visuals = crop_visuals(
            fragments, abs_path(doc.original_file).parent, f"k{root}"
        )
        text, tree, issues, marks, _ = combined(fragments, exam.standard_options)
        q = qs.get(str(root))
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
