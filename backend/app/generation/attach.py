"""Puts a generated paper into an exam directly, without reading its PDFs back.

The paper is already structured (numbers, sections, marks, OR alternatives, answers, marking points), so the
exam's questions and answer key are written from it as verified and the exam opens for answer sheets. The PDFs
are stored as the exam's question paper and answer key documents for viewing and printing.

A board-pattern paper keeps the exam's CBSE profile and gets CBSE scoring trees; a custom paper (or a language
paper, whose CBSE choice rules a generated paper does not follow) makes the exam a school exam with its own pattern."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..cbse.catalog import VERSION, get_profile
from ..models import (AnswerKey, AnswerKeyDocument, Evaluation, EvaluationItem, Exam, ExamQuestion, GeneratedPaper,
                      QuestionPaperDocument, StudentAnswer)
from ..services.audit import audit
from .render import key_pdf, paper_pdf

# any setup state: until answer sheets arrive, a generated paper may replace the exam's paper and key
EDITABLE = ("DRAFT", "QUESTION_PAPER_UPLOADED", "QUESTIONS_EXTRACTED", "QUESTIONS_VERIFIED", "ANSWER_KEY_UPLOADED",
            "ANSWER_KEY_VERIFIED", "READY_FOR_EVALUATION")


def question_text(item: dict) -> str:
    lines = [item["text"]]
    lines += [f"({chr(97 + i)}) {o}" for i, o in enumerate(item.get("options") or [])]
    return "\n".join(lines)


def _version_tree(item: dict, node_id: str, marks: float) -> dict:
    """One version of a question: its marking points as criteria (one point = a single criterion)."""
    mcq = bool(item.get("options")) and marks <= 1
    points = item.get("marking_points") or [{"point": item.get("answer") or "", "marks": marks}]
    base = {"label": "", "limit": None, "choice_type": "question", "audience": None, "deductions": []}
    if len(points) == 1:
        return {**base, "id": node_id, "kind": "point", "text": points[0]["point"], "marks": marks,
                "response_type": "mcq" if mcq else "open", "children": []}
    return {**base, "id": node_id, "kind": "all", "text": "", "marks": marks, "response_type": "open",
            "children": [{**base, "id": f"{node_id}.{i}", "kind": "point", "text": p["point"], "marks": p["marks"],
                          "response_type": "open", "children": []} for i, p in enumerate(points, 1)]}


def scoring_tree(q: dict) -> dict:
    n, marks = str(q["number"]), float(q["marks"])
    if not q.get("or"):
        return _version_tree(q, n, marks)
    alts = [_version_tree(q, f"{n}-alt1", marks), _version_tree(q["or"], f"{n}-alt2", marks)]
    for i, a in enumerate(alts, 1):
        a["label"] = f"Alternative {i}"
    return {"id": n, "kind": "choose", "label": "", "text": "", "marks": marks, "limit": 1, "choice_type": "question",
            "audience": None, "response_type": "open", "deductions": [], "children": alts}


def _criteria(item: dict) -> list[str]:
    return [f"{p['marks']:g} marks: {p['point']}" for p in item.get("marking_points") or []]


def _advance(exam: Exam) -> None:
    """The paper and key were written verified: every setup step (upload, extract, verify paper, upload key,
    verify key) is complete, so the exam opens for answer sheets."""
    exam.status = "READY_FOR_EVALUATION"


def _clear(db: Session, exam: Exam) -> None:
    ids = [q.id for q in db.query(ExamQuestion).filter_by(exam_id=exam.id)]
    db.query(AnswerKey).filter_by(exam_id=exam.id).delete()
    if ids:
        db.query(StudentAnswer).filter(StudentAnswer.exam_question_id.in_(ids)).update(
            {StudentAnswer.exam_question_id: None}, synchronize_session=False)
        db.query(EvaluationItem).filter(EvaluationItem.exam_question_id.in_(ids)).delete(synchronize_session=False)
        db.query(ExamQuestion).filter_by(exam_id=exam.id).delete()
    for model in (QuestionPaperDocument, AnswerKeyDocument):
        for old in db.query(model).filter_by(exam_id=exam.id, is_active=True):
            old.is_active = False


def _store_docs(db: Session, exam: Exam, paper: dict, profile: dict | None) -> tuple:
    """The PDFs as the exam's documents, already 'read': pages rendered for viewing (no AI) and the paper's own
    facts recorded as the extraction, so nothing is left to process or review."""
    from ..documents.renderer import render_document
    from ..documents.storage import abs_path
    from ..routes.documents import _save
    meta = {"generated": True, "class_level": paper.get("standard"), "maximum_marks": paper.get("total_marks"),
            "duration_minutes": paper.get("duration_minutes"),
            "stated_question_count": len(paper.get("questions", []))}
    if profile:
        meta["subject_code"] = profile["code"]
    docs = []
    for kind, data, name in (("question-paper", paper_pdf(paper), "generated-question-paper.pdf"),
                             ("answer-key", key_pdf(paper), "generated-answer-key.pdf")):
        d = _save(db, kind, exam.id, data, "pdf", "application/pdf", name)
        db.flush()
        original = abs_path(d.original_file)
        pages = render_document(original, "pdf", original.parent)
        for page in pages:
            page["ocr_status"] = "OK"
        d.pages = pages
        d.status, d.stage, d.progress_current, d.progress_total = "READY", "Generated by AI", len(pages), len(pages)
        d.extraction = {"metadata": meta, "instructions": paper.get("instructions", []), "issues": []}
        docs.append(d)
    return tuple(docs)


def attach_to_exam(db: Session, gp: GeneratedPaper) -> None:
    exam = db.get(Exam, gp.exam_id)
    if exam is None or exam.status not in EDITABLE:
        gp.error = "Evaluation has started for this exam, so the generated paper was not attached."
        db.commit()
        return
    if db.query(Evaluation.id).filter_by(exam_id=exam.id).first():
        gp.error = "Answer sheets were already uploaded to this exam, so the generated paper was not attached."
        db.commit()
        return
    paper, req = gp.paper or {}, gp.request or {}
    profile = get_profile(req.get("profile_id")) if req.get("pattern") == "board" else None
    cbse = bool(profile and not profile.get("upload_driven") and not profile.get("choice_rules"))
    if cbse:
        exam.standard_profile_id, exam.standard_version = profile["id"], VERSION
    else:  # the paper's own pattern: a school exam
        exam.standard_profile_id = exam.standard_version = None
        exam.standard_options = None
    exam.standard_validation = None
    exam.total_marks = float(paper.get("total_marks") or exam.total_marks)
    exam.duration_minutes = int(paper.get("duration_minutes") or exam.duration_minutes or 180)
    exam.instructions = "\n".join(paper.get("instructions") or []) or exam.instructions

    from ..services import paper_format
    from .. import formatter
    paper_format.set_for_exam(exam)
    formatter.set_for_exam(exam)
    _clear(db, exam)
    qp, ak = _store_docs(db, exam, paper, profile if cbse else None)
    db.flush()

    pos = 0
    for q in paper.get("questions", []):
        marks = float(q["marks"])
        mcq = bool(q.get("options")) and marks <= 1
        if cbse:
            tree = scoring_tree(q)
            text = question_text(q) + (f"\nOR\n{question_text(q['or'])}" if q.get("or") else "")
            answer = q["answer"] + (f"\nOR\n{q['or']['answer']}" if q.get("or") else "")
            pos += 1
            row = ExamQuestion(exam_id=exam.id, document_id=qp.id, display_number=str(q["number"]),
                               normalized_number=str(q["number"]), question_text=text, raw_ocr_text=text,
                               question_type="mcq" if mcq else "descriptive", max_marks=marks, section=q["section"],
                               position=pos, page_start=1, page_end=1, verification_status="VERIFIED",
                               structure={"root": q["number"], "tree": tree, "issues": [], "source_pages": [],
                                          "visuals": [], "generated": gp.id})
            db.add(row)
            db.flush()
            db.add(AnswerKey(exam_id=exam.id, document_id=ak.id, raw_question_number=str(q["number"]),
                             normalized_number=str(q["number"]), exam_question_id=row.id, answer_text=answer,
                             raw_ocr_text=answer, marks=marks,
                             criteria=_criteria(q) + (_criteria(q["or"]) if q.get("or") else []),
                             mapping_status="MAPPED", page_number=1, verification_status="VERIFIED",
                             rubric_status="CONFIRMED",
                             rubric={"kind": "cbse", "cbse_tree": tree, "problems": [], "points": [], "deductions": [],
                                     "notes": [], "stated_total": marks, "total": marks, "source_pages": [],
                                     "visuals": []}))
            continue
        # school exam: an OR question is two questions sharing a choice group (formatter/common/choices.py)
        versions = [("", q)] if not q.get("or") else [("(a)", q), ("(b)", q["or"])]
        for suffix, item in versions:
            pos += 1
            number = f"{q['number']}{suffix}"
            row = ExamQuestion(exam_id=exam.id, document_id=qp.id, display_number=number, normalized_number=number,
                               question_text=question_text(item), raw_ocr_text=question_text(item),
                               question_type="mcq" if mcq else "descriptive", max_marks=marks, section=q["section"],
                               choice_group=str(q["number"]) if suffix else None, position=pos, page_start=1,
                               page_end=1, verification_status="VERIFIED")
            db.add(row)
            db.flush()
            db.add(AnswerKey(exam_id=exam.id, document_id=ak.id, raw_question_number=number,
                             normalized_number=number, exam_question_id=row.id, answer_text=item["answer"],
                             raw_ocr_text=item["answer"], marks=marks, criteria=_criteria(item),
                             accepted_answers=[], keywords=[], mapping_status="MAPPED", page_number=1,
                             verification_status="VERIFIED"))
    db.flush()
    if not cbse:
        from ..services.mapping_service import refresh_key_state
        refresh_key_state(db, exam.id)  # builds each key's marking rubric from its marking points
        for k in db.query(AnswerKey).filter_by(exam_id=exam.id, is_active=True):
            k.rubric_status = "CONFIRMED"
    _advance(exam)
    audit(db, exam_id=exam.id, teacher_id=gp.teacher_id, entity_type="exam", entity_id=exam.id,
          action="generated_paper_attached", new=gp.id)
    db.commit()
