"""Background processing: render pages -> InternVL per page -> store raw+parsed -> build app-owned entities."""
from __future__ import annotations
import copy
import json
import logging
import shutil
from pathlib import Path
from sqlalchemy.orm import Session
from ..config import AI_BAD_RESPONSE_MESSAGE, AI_UNAVAILABLE_MESSAGE, get_settings
from ..database import SessionLocal
from ..documents import cropping
from ..documents.renderer import RenderError, render_document
from ..documents.storage import abs_path, rel
from ..models import (AnswerKey, AnswerKeyDocument, AnswerSheetDocument, Evaluation, Exam, ExamQuestion,
                      QuestionPaperDocument, StudentAnswer)
from ..ocr import prompts
from ..ocr.internvl import AIResponseError, AIUnavailable, chat_structured, check_model
from ..ocr.schemas import AnswerKeyPageResult, QuestionPageResult, StudentPageResult
from .doc_structure import parse_question_paper_structure, StructuredQuestion
from .key_segmentation import segment_answer_keys
from .student_segmentation import segment_student_answers
from .mapping_service import apply_key_mapping, apply_student_mapping, refresh_key_state
from .numbering import is_sub_question, normalize_question_number, parent_number
from .state import set_state

log = logging.getLogger("adem.pipeline")

KINDS = {
    "question-paper": (QuestionPaperDocument, prompts.question_paper_prompt, QuestionPageResult),
    "answer-key": (AnswerKeyDocument, prompts.answer_key_prompt, AnswerKeyPageResult),
    "answer-sheet": (AnswerSheetDocument, prompts.student_answer_prompt, StudentPageResult),
}
LOW_CONF = 0.6


def _set_pages(db: Session, doc, idx: int, **kw) -> None:
    pages = copy.deepcopy(doc.pages)
    pages[idx].update(kw)
    doc.pages = pages
    db.commit()


def _progress(db: Session, doc, stage: str, cur: int | None = None, total: int | None = None, status: str | None = None):
    doc.stage = stage
    if cur is not None:
        doc.progress_current = cur
    if total is not None:
        doc.progress_total = total
    if status:
        doc.status = status
    db.commit()


def process_document(kind: str, doc_id: str, only_failed: bool = False) -> None:
    db = SessionLocal()
    try:
        _run(db, kind, doc_id, only_failed)
    except Exception as e:  # never leak a trace to the teacher; keep it in the developer log
        log.exception("Pipeline crashed for %s %s", kind, doc_id)
        db.rollback()
        model_cls = KINDS[kind][0]
        doc = db.get(model_cls, doc_id)
        if doc:
            doc.status, doc.error_message = "FAILED", "Processing failed unexpectedly. See the server log for details."
            db.commit()
    finally:
        db.close()


def _run(db: Session, kind: str, doc_id: str, only_failed: bool) -> None:
    model_cls, prompt_fn, schema = KINDS[kind]
    doc = db.get(model_cls, doc_id)
    exam = db.get(Exam, doc.exam_id)
    original = abs_path(doc.original_file)
    wd = original.parent
    ext = original.suffix.lstrip(".").lower()
    doc.error_message = None

    if not (only_failed and doc.pages):
        _progress(db, doc, "Rendering pages", 0, 0, "RENDERING")
        try:
            doc.pages = render_document(original, ext, wd)
        except RenderError as e:
            doc.status, doc.error_message = "FAILED", str(e)
            db.commit()
            return
        doc.progress_total = len(doc.pages)
        db.commit()

    try:
        check_model()
    except AIUnavailable as e:
        log.error("AI unavailable: %s", e.detail)
        doc.status, doc.error_message, doc.stage = "AI_ERROR", AI_UNAVAILABLE_MESSAGE, "AI service unavailable"
        db.commit()
        return

    (wd / "ocr").mkdir(exist_ok=True)
    total = len(doc.pages)
    # Exam labels help the model read ambiguous handwritten numbers (it is told to copy what is written).
    labels = [q.display_number for q in _exam_questions(db, exam.id)] if kind == "answer-sheet" else None
    _progress(db, doc, f"OCR: page 1 of {total}", 0, total, "OCR_PROCESSING")
    for i, p in enumerate(list(doc.pages)):
        if only_failed and p.get("ocr_status") == "OK":
            continue
        _progress(db, doc, f"OCR: processing page {p['page_number']} of {total}", i)
        img = abs_path(p["processed_file"])
        out = wd / "ocr" / f"page-{p['page_number']:03d}.json"
        try:
            prompt = prompt_fn(p["page_number"], p["ocr_width"], p["ocr_height"],
                               page_text=p.get("page_text"), canonical_questions=labels)
            call = chat_structured(prompts.OCR_SYSTEM, prompt, schema, img)
            out.write_text(json.dumps({"status": "OK", "raw": call.raw, "parsed": call.parsed.model_dump(),
                                       "attempts": call.attempts, "dropped_items": call.dropped_items},
                                      ensure_ascii=False, indent=1), encoding="utf-8")
            partial = (f"{call.dropped_items} item(s) on this page could not be read and were left out. "
                       "Compare with the original and add them by hand, or retry the page.") if call.dropped_items else None
            _set_pages(db, doc, i, ocr_status="OK", ocr_error=partial, ocr_file=rel(out))
        except AIUnavailable as e:
            log.error("AI became unavailable mid-run: %s", e.detail)
            doc.status, doc.error_message = "AI_ERROR", AI_UNAVAILABLE_MESSAGE
            db.commit()
            return
        except AIResponseError as e:
            log.error("Page %s: %s | raw=%r", p["page_number"], e.detail, e.raw[:500])
            out.write_text(json.dumps({"status": e.kind, "raw": e.raw, "parsed": None, "error": e.detail},
                                      ensure_ascii=False, indent=1), encoding="utf-8")
            _set_pages(db, doc, i, ocr_status=e.kind, ocr_error=AI_BAD_RESPONSE_MESSAGE, ocr_file=rel(out))
    doc.progress_current = total

    _progress(db, doc, "Extracting and validating", None, None, "EXTRACTING")
    results = _load_results(db, doc, schema)
    if not results:
        # Nothing was read: keep whatever was built from an earlier run instead of replacing it with nothing.
        doc.status, doc.stage = "FAILED", "No pages could be read"
        doc.error_message = f"{AI_BAD_RESPONSE_MESSAGE} No page of this document could be read; retry it."
        db.commit()
        return
    if kind == "question-paper":
        _build_questions(db, doc, exam, wd, results)
    elif kind == "answer-key":
        _build_answer_key(db, doc, exam, wd, results)
    else:
        _build_student_answers(db, doc, exam, wd, results)

    failed = [p["page_number"] for p in doc.pages if p.get("ocr_status") != "OK"]
    if failed:
        doc.status = "NEEDS_ATTENTION"
        doc.error_message = f"{AI_BAD_RESPONSE_MESSAGE} Page(s) affected: {', '.join(map(str, failed))}."
        doc.stage = "Needs attention"
    else:
        doc.status, doc.stage = "READY", "Ready for review"
        partial = [p["page_number"] for p in doc.pages if p.get("ocr_error")]
        if partial:  # readable, but something on these pages was dropped
            doc.stage = "Ready for review (check flagged pages)"
            doc.error_message = (f"Some items could not be read on page(s) {', '.join(map(str, partial))}. "
                                 "Check them against the original.")
    db.commit()


def _exam_questions(db: Session, exam_id: str) -> list[ExamQuestion]:
    return db.query(ExamQuestion).filter_by(exam_id=exam_id).order_by(ExamQuestion.position).all()


def _load_results(db: Session, doc, schema):
    out = []
    pdf_doc = None
    try:
        orig = abs_path(doc.original_file)
        if orig.exists() and orig.suffix.lower() == ".pdf":
            import pymupdf
            pdf_doc = pymupdf.open(orig)
    except Exception:
        pdf_doc = None

    for p in list(doc.pages):
        if p.get("ocr_status") != "OK":
            continue
        p_dict = dict(p)
        if pdf_doc and "page_text" not in p_dict:
            p_num = p_dict.get("page_number", 1)
            if 1 <= p_num <= len(pdf_doc):
                try:
                    p_dict["page_text"] = pdf_doc[p_num - 1].get_text()
                except Exception:
                    pass
        try:
            data = json.loads(abs_path(p["ocr_file"]).read_text(encoding="utf-8"))
            parsed = schema.model_validate(data["parsed"])
        except Exception:
            log.exception("Stored OCR output for page %s is unreadable", p.get("page_number"))
            _set_pages(db, doc, doc.pages.index(p), ocr_status="FAILED_PARSE", ocr_error=AI_BAD_RESPONSE_MESSAGE)
            continue
        out.append((p_dict, parsed))

    if pdf_doc:
        try:
            pdf_doc.close()
        except Exception:
            pass
    return out



def _bbox_and_crop(p: dict, bbox, wd: Path, name: str):
    bbox_dict = bbox.model_dump() if hasattr(bbox, "model_dump") else (bbox if isinstance(bbox, dict) else None)
    nb = cropping.normalise_bbox(bbox_dict, p["ocr_width"], p["ocr_height"], p["width"], p["height"])
    crop = None
    if nb:
        try:
            crop = rel(cropping.save_crop(abs_path(p["source_file"]), nb, wd / "crops" / f"{name}.png"))
        except Exception:
            log.exception("crop failed")
    return nb, crop


def _build_questions(db: Session, doc, exam: Exam, wd: Path, results) -> None:
    db.query(AnswerKey).filter_by(exam_id=exam.id).update(
        {AnswerKey.exam_question_id: None, AnswerKey.mapping_status: "UNMAPPED", AnswerKey.mapping_confirmed: False,
         AnswerKey.mapping_note: "Question paper was re-extracted", AnswerKey.mapping_candidates: [],
         AnswerKey.mapping_candidate_details: []}, synchronize_session=False)
    db.query(ExamQuestion).filter_by(exam_id=exam.id).delete()
    struct = parse_question_paper_structure(results)

    # Safety Net: If 0 questions were parsed, check if OCR captured any non-empty text blocks
    if not struct.questions:
        fallback_texts = []
        for p, pres in results:
            raw_qs = getattr(pres, "questions", [])
            for q in raw_qs:
                t = (getattr(q, "question_text", None) or "").strip()
                if t:
                    fallback_texts.append((p.get("page_number", 1), getattr(q, "bbox", None), t, getattr(q, "marks", None)))
        if not fallback_texts and struct.instructions:
            for inst in struct.instructions:
                if len(inst.strip()) > 3:
                    fallback_texts.append((1, None, inst.strip(), None))

        for idx, (p_num, bbox, fb_text, fb_marks) in enumerate(fallback_texts, 1):
            bbox_dict = bbox.model_dump() if hasattr(bbox, "model_dump") else (bbox if isinstance(bbox, dict) else None)
            struct.questions.append(
                StructuredQuestion(
                    raw_question_number=None,
                    normalized_number=str(idx),
                    display_number=str(idx),
                    question_text=fb_text,
                    question_type="descriptive",
                    max_marks=fb_marks,
                    section=None,
                    page_start=p_num,
                    page_end=p_num,
                    bbox=bbox_dict,
                    ocr_confidence=0.5,
                    verification_status="NEEDS_REVIEW",
                    review_reason="Question number missing; please review and set marks",
                )
            )

    # Reconcile exam total marks if explicitly printed on paper and significantly different
    if struct.exam_max_marks and abs(exam.total_marks - struct.exam_max_marks) > 1e-9:
        log.info("Detected paper max marks %g vs exam total %g", struct.exam_max_marks, exam.total_marks)

    pages_by_num = {p["page_number"]: p for p, _ in results}
    pos, rows = 0, []
    for q in struct.questions:
        pos += 1
        p = pages_by_num.get(q.page_start) or results[0][0]
        nb, crop = _bbox_and_crop(p, q.bbox, wd, f"q{pos:03d}")

        row = ExamQuestion(
            exam_id=exam.id,
            document_id=doc.id,
            display_number=q.display_number,
            normalized_number=q.normalized_number,
            question_text=q.question_text,
            raw_ocr_text=q.question_text,
            question_type=q.question_type,
            max_marks=q.max_marks,
            section=q.section,
            position=pos,
            page_start=q.page_start,
            page_end=q.page_end,
            bbox=nb,
            crop_file=crop,
            ocr_confidence=q.ocr_confidence,
            verification_status=q.verification_status,
            review_reason=q.review_reason,
        )
        rows.append(row)
        db.add(row)

    seen: dict[str, list[ExamQuestion]] = {}
    for r in rows:
        if r.normalized_number:
            seen.setdefault(r.normalized_number, []).append(r)
    for grp in seen.values():
        if len(grp) > 1:
            for r in grp:
                r.verification_status = "NEEDS_REVIEW"
                r.review_reason = "; ".join(filter(None, [r.review_reason, "Duplicate question number"]))
    for num, grp in seen.items():
        if is_sub_question(num) and parent_number(num) in seen:
            for r in grp + seen[parent_number(num)]:
                if "sub-part" not in (r.review_reason or ""):
                    r.verification_status = "NEEDS_REVIEW"
                    r.review_reason = "; ".join(filter(None, [r.review_reason,
                                                              "Whole question and its sub-part both extracted"]))

    if rows:
        from .state import at_least
        if not at_least(exam, "QUESTIONS_EXTRACTED"):
            set_state(exam, "QUESTIONS_EXTRACTED")
    else:
        log.warning("No questions extracted for exam %s", exam.id)
        doc.error_message = "No questions could be extracted from this document. Please check the document or add questions manually."
    db.commit()


def _build_answer_key(db: Session, doc, exam: Exam, wd: Path, results) -> None:
    db.query(AnswerKey).filter_by(document_id=doc.id).delete()
    pages_by_num = {p["page_number"]: p for p, _ in results}
    keys = segment_answer_keys(results)
    n = 0
    for k in keys:
        n += 1
        p = pages_by_num.get(k.page_number) or results[0][0]
        nb, crop = _bbox_and_crop(p, k.bbox, wd, f"k{n:03d}")
        db.add(AnswerKey(
            exam_id=exam.id,
            document_id=doc.id,
            raw_question_number=k.raw_question_number,
            answer_text=k.answer_text,
            raw_ocr_text=k.answer_text,
            marks=k.marks,
            criteria=k.criteria,
            accepted_answers=k.accepted_answers,
            keywords=k.keywords,
            page_number=k.page_number,
            bbox=nb,
            crop_file=crop,
            ocr_confidence=k.ocr_confidence,
        ))
    db.flush()
    apply_key_mapping(db, exam.id, doc.id)
    db.commit()


def _build_student_answers(db: Session, doc, exam: Exam, wd: Path, results) -> None:
    ev = db.query(Evaluation).filter_by(answer_sheet_id=doc.id).one()
    db.query(StudentAnswer).filter_by(evaluation_id=ev.id).delete()
    pages_by_num = {p["page_number"]: p for p, _ in results}
    known = [q.normalized_number for q in _exam_questions(db, exam.id) if q.normalized_number]
    answers = segment_student_answers(results, known)
    n = 0
    for a in answers:
        n += 1
        p = pages_by_num.get(a.page_number) or results[0][0]
        nb, crop = _bbox_and_crop(p, a.bbox, wd, f"a{n:03d}")
        db.add(StudentAnswer(
            evaluation_id=ev.id,
            raw_question_number=a.raw_question_number,
            raw_ocr_text=a.raw_ocr_text,
            answer_text=a.answer_text,
            page_number=a.page_number,
            bbox=nb,
            crop_file=crop,
            ocr_confidence=a.ocr_confidence,
            position=a.position or n,
        ))
    db.flush()
    apply_student_mapping(db, ev)
    ev.status = "OCR_REVIEW"
    db.commit()
    from .evaluation_service import refresh_evaluation_status
    refresh_evaluation_status(db, ev)
    from .state import at_least
    if at_least(exam, "ANSWER_KEY_VERIFIED") and exam.status == "ANSWER_KEY_VERIFIED":
        set_state(exam, "READY_FOR_EVALUATION")
    db.commit()


def recover_interrupted_jobs() -> None:
    """Background tasks do not survive a restart. Anything left mid-run would stay 'processing' forever and the
    retry button refuses busy documents, so mark such work as failed and retryable."""
    from .state import set_state as _set
    db = SessionLocal()
    try:
        busy = ("UPLOADED", "RENDERING", "OCR_PROCESSING", "EXTRACTING")
        for model_cls, _, _ in KINDS.values():
            for doc in db.query(model_cls).filter(model_cls.status.in_(busy)):
                doc.status, doc.stage = "FAILED", "Interrupted"
                doc.error_message = "Processing was interrupted because the server restarted. Retry this document."
        for ev in db.query(Evaluation).filter_by(run_status="RUNNING"):
            ev.run_status = "ERROR"
        for exam in db.query(Exam).filter_by(status="EVALUATING"):
            _set(exam, "REVIEW_REQUIRED")
        db.commit()
    except Exception:
        log.exception("Could not recover interrupted jobs")
        db.rollback()
    finally:
        db.close()
