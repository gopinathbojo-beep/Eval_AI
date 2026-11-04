"""Deterministic board-pattern gates; called by APIs AND durable workers."""

from __future__ import annotations
from datetime import datetime, timezone
import math
from .catalog import get_profile, expected_section, grade_for, VERSION
from .extraction import tree_issues, tree_total, choice_signature
from ..models import ExamQuestion, QuestionPaperDocument, AnswerKeyDocument, AnswerKey


def active_doc(db, model, exam_id):
    return (
        db.query(model)
        .filter_by(exam_id=exam_id, is_active=True)
        .order_by(model.uploaded_at.desc())
        .first()
    )


def validate(db, exam, phase="evaluation"):
    if not exam.standard_profile_id:
        return {"legacy": True, "valid": True, "issues": []}
    db.flush()
    p = get_profile(exam.standard_profile_id)
    issues = []

    def add(
        code,
        message,
        *,
        question=None,
        document=None,
        page=None,
        expected=None,
        detected=None,
    ):
        issues.append(
            {
                "severity": "error",
                "code": code,
                "message": message,
                "question_id": getattr(question, "id", None),
                "question": getattr(question, "display_number", None),
                "document_id": getattr(document, "id", None),
                "page": page or getattr(question, "page_start", None),
                "expected": expected,
                "detected": detected,
            }
        )

    if not p or exam.standard_version != VERSION:
        add(
            "PROFILE_UNAVAILABLE",
            "This exam's standard version is unavailable; it cannot be silently upgraded.",
        )
        result = {"valid": False, "issues": issues}
        exam.standard_validation = result
        return result
    if grade_for(exam.school_class) != p["class_level"]:
        add("CLASS_MISMATCH", "The class does not match the selected profile.")
    from .routes import candidates

    if p["id"] not in {x["id"] for x in candidates(exam.subject, p["class_level"])}:
        add(
            "SUBJECT_PROFILE",
            "The subject identity no longer matches this exam's profile.",
        )
    if (
        exam.total_marks != p["total_marks"]
        or exam.duration_minutes != p["duration_minutes"]
    ):
        add("EXAM_PATTERN", "Exam total and duration must match the board profile.")
    options = exam.standard_options or {}
    if options.get("accessibility") not in {"standard", "accessible"}:
        add("AUDIENCE_REQUIRED", "Select the standard or accessible paper version.")
    if p["code"] == "055" and options.get("accountancy_option") not in {
        None,
        "financial",
        "computerised",
    }:
        add("BRANCH_REQUIRED", "Select the Accountancy Part B option.")
    docs = [("question-paper", active_doc(db, QuestionPaperDocument, exam.id))]
    if phase != "paper":
        docs.append(("answer-key", active_doc(db, AnswerKeyDocument, exam.id)))
    for kind, doc in docs:
        if not doc:
            add("DOCUMENT_REQUIRED", f"Upload the {kind}.")
            continue
        if (
            doc.status != "READY"
            or not doc.pages
            or any(x.get("ocr_status") != "OK" for x in doc.pages)
        ):
            add(
                "PAGES_INCOMPLETE",
                f"All {kind} pages must finish processing successfully.",
                document=doc,
            )
        extraction = doc.extraction or {}
        meta = extraction.get("metadata", {})
        if not extraction:
            add(
                "SOURCE_EVIDENCE_MISSING",
                f"Reprocess the {kind} with the CBSE extractor.",
                document=doc,
            )
        if p.get("upload_driven"):
            # These language profiles define only class, duration and maximum marks.
            # Their uploaded paper and scheme are authoritative for sections and choices.
            continue
        for field, required in (
            ("class_level", p["class_level"]),
            ("subject_code", p["code"]),
        ):
            actual = meta.get(field)
            same = (
                str(actual).zfill(3) == required
                if field == "subject_code"
                else str(actual) == str(required)
            )
            if not same:
                add(
                    "METADATA_MISMATCH",
                    f"Check the {kind} {field.replace('_', ' ')} against its source.",
                    document=doc,
                    expected=required,
                    detected=actual,
                )
        for field, expected in (
            ("maximum_marks", p["total_marks"]),
            ("duration_minutes", p["duration_minutes"]),
            ("stated_question_count", p["question_count"]),
        ):
            actual = meta.get(field)
            if actual is not None and actual != expected:
                add(
                    "PRINTED_PATTERN_MISMATCH",
                    f"Printed {field.replace('_', ' ')} does not match this profile.",
                    document=doc,
                    expected=expected,
                    detected=actual,
                )
        raw_text = "\n".join(page.get("page_text", "") for page in doc.pages)
        if (
            kind == "answer-key"
            and ("general instructions" in raw_text.casefold() or "सामान्य" in raw_text)
            and not any(str(x).strip() for x in extraction.get("instructions", []))
        ):
            add(
                "EXAMINER_INSTRUCTIONS_MISSING",
                "The source contains general instructions that have not been captured. Review the scheme details.",
                document=doc,
            )
        if kind == "question-paper" and meta.get("maximum_marks") is None:
            add(
                "MAXIMUM_UNREAD",
                "Confirm the printed paper maximum from source.",
                document=doc,
            )
        if meta.get("printed_page_count") and meta["printed_page_count"] != len(
            doc.pages
        ):
            add(
                "PAGE_COUNT_MISMATCH",
                "The uploaded page count differs from the printed page count.",
                document=doc,
                expected=meta["printed_page_count"],
                detected=len(doc.pages),
            )
        for item in extraction.get("issues", []):
            add("EXTRACTION_REVIEW", str(item), document=doc)
    if p.get("upload_driven"):
        result = {"valid": not issues, "issues": issues, "profile": p, "detected": {}}
        exam.standard_validation = result
        return result
    qs = (
        db.query(ExamQuestion)
        .filter_by(exam_id=exam.id)
        .order_by(ExamQuestion.position)
        .all()
    )
    roots, totals, counts, choice_counts = {}, {}, {}, {}
    for q in qs:
        structure = q.structure or {}
        root = structure.get("root")
        if not isinstance(root, int) or root < 1 or root > p["question_count"]:
            add(
                "ROOT_NUMBER",
                "Set a valid whole-question number and hierarchy.",
                question=q,
            )
            continue
        if root in roots:
            add(
                "DUPLICATE_ROOT",
                "Merge duplicate whole-question fragments; keep subparts inside their root.",
                question=q,
            )
        roots[root] = q
        if q.normalized_number != str(root):
            add(
                "ROOT_IDENTITY",
                "The visible question number and hierarchy root must agree.",
                question=q,
                expected=root,
                detected=q.normalized_number,
            )
        sec = expected_section(p, root)
        if q.section != sec["key"]:
            add(
                "SECTION_MISMATCH",
                "Question is in the wrong board-pattern section.",
                question=q,
                expected=sec["key"],
                detected=q.section,
            )
        if (
            not q.max_marks
            or not math.isfinite(q.max_marks)
            or not q.question_text.strip()
        ):
            add(
                "QUESTION_INCOMPLETE",
                "Question text and positive maximum marks are required.",
                question=q,
            )
        if sec["each"] is not None and q.max_marks != sec["each"]:
            add(
                "QUESTION_ALLOCATION",
                "Whole-question marks do not match the profile.",
                question=q,
                expected=sec["each"],
                detected=q.max_marks,
            )
        if p.get("parent_marks") and q.max_marks != p["parent_marks"][root - 1]:
            add(
                "QUESTION_ALLOCATION",
                "Whole-question marks do not match the language-paper pattern.",
                question=q,
                expected=p["parent_marks"][root - 1],
                detected=q.max_marks,
            )
        tree = structure.get("tree")
        if not tree:
            add(
                "HIERARCHY_REQUIRED",
                "Review the question's parts and choices.",
                question=q,
            )
        else:
            signatures = choice_signature(tree, options)
            required = p.get("choice_rules", {}).get(root, [])
            if required and sorted(signatures) != sorted(required):
                add(
                    "CHOICE_PATTERN",
                    "The question's permitted choices differ from the board pattern.",
                    question=q,
                    expected=required,
                    detected=signatures,
                )
            if signatures:
                choice_counts[sec["key"]] = choice_counts.get(sec["key"], 0) + 1
            for problem in tree_issues(tree, options):
                add("QUESTION_TREE", problem, question=q)
            if abs(tree_total(tree, options) - (q.max_marks or 0)) > 1e-7:
                add(
                    "QUESTION_TOTAL",
                    "Choice-aware subpart marks disagree with the question maximum.",
                    question=q,
                )
        for problem in structure.get("issues", []):
            add("QUESTION_REVIEW", str(problem), question=q)
        totals[sec["key"]] = totals.get(sec["key"], 0) + (q.max_marks or 0)
        counts[sec["key"]] = counts.get(sec["key"], 0) + 1
    missing = sorted(set(range(1, p["question_count"] + 1)) - roots.keys())
    if missing:
        add(
            "MISSING_QUESTIONS",
            "Whole questions are missing from the extracted paper.",
            expected=missing,
        )
    for sec in p["sections"]:
        if (
            sec["internal_choices"] is not None
            and choice_counts.get(sec["key"], 0) != sec["internal_choices"]
        ):
            add(
                "SECTION_CHOICES",
                f"Section {sec['key']} has a different number of internal-choice questions.",
                expected=sec["internal_choices"],
                detected=choice_counts.get(sec["key"], 0),
            )
        if abs(totals.get(sec["key"], 0) - sec["marks"]) > 1e-7:
            add(
                "SECTION_TOTAL",
                f"Section {sec['key']} marks do not match the board pattern.",
                expected=sec["marks"],
                detected=totals.get(sec["key"], 0),
            )
    if phase != "paper":
        keys = db.query(AnswerKey).filter_by(exam_id=exam.id, is_active=True).all()
        for k in keys:
            if k.mapping_status != "MAPPED" or k.exam_question_id not in {
                q.id for q in qs
            }:
                add(
                    "UNMAPPED_KEY",
                    "An uploaded scheme entry is unmatched or ambiguous.",
                    document=docs[-1][1],
                    page=k.page_number,
                )
        for q in qs:
            matched = [
                k
                for k in keys
                if k.exam_question_id == q.id and k.mapping_status == "MAPPED"
            ]
            if len(matched) != 1:
                add(
                    "KEY_COVERAGE",
                    "Each whole question needs exactly one mapped scheme entry.",
                    question=q,
                    detected=len(matched),
                )
                continue
            k = matched[0]
            scheme_doc = docs[-1][1]
            rubric = k.rubric or {}
            if (
                not k.document_id
                or not rubric.get("cbse_tree")
                or not k.answer_text.strip()
            ):
                add(
                    "UPLOADED_SCHEME_REQUIRED",
                    "A source-grounded uploaded marking scheme is required.",
                    question=q,
                    document=scheme_doc,
                    page=k.page_number,
                )
                continue
            if (
                k.marks != q.max_marks
                or abs(tree_total(rubric["cbse_tree"], options) - (q.max_marks or 0))
                > 1e-7
            ):
                add(
                    "SCHEME_TOTAL",
                    "Scheme allocations differ from the question maximum.",
                    question=q,
                    document=scheme_doc,
                    page=k.page_number,
                )
            if (
                q.structure
                and q.structure.get("tree")
                and sorted(choice_signature(q.structure["tree"], options))
                != sorted(choice_signature(rubric["cbse_tree"], options))
            ):
                add(
                    "SCHEME_CHOICES",
                    "Scheme scoring groups do not preserve the question's permitted choices.",
                    question=q,
                    document=scheme_doc,
                    page=k.page_number,
                )
            for problem in tree_issues(rubric["cbse_tree"], options) + rubric.get(
                "problems", []
            ):
                add(
                    "SCHEME_REVIEW",
                    problem,
                    question=q,
                    document=scheme_doc,
                    page=k.page_number,
                )
            if phase == "evaluation" and (
                k.verification_status != "VERIFIED" or k.rubric_status != "CONFIRMED"
            ):
                add(
                    "SCHEME_UNVERIFIED",
                    "Review and verify the uploaded marking scheme.",
                    question=q,
                )
        if phase == "evaluation" and any(
            q.verification_status != "VERIFIED" for q in qs
        ):
            add("PAPER_UNVERIFIED", "Verify the question paper before evaluation.")
    result = {
        "profile": p,
        "legacy": False,
        "phase": phase,
        "valid": not issues,
        "issues": issues,
        "detected": {
            "question_count": len(qs),
            "section_totals": totals,
            "section_counts": counts,
        },
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    exam.standard_validation = result
    return result
