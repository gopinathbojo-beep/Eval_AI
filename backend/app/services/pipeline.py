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
from ..models import (AnswerKey, AnswerKeyDocument, AnswerSheetDocument, Evaluation, EvaluationItem, Exam, ExamQuestion,
                      QuestionPaperDocument, StudentAnswer)
from ..ocr import prompts
from ..ocr.internvl import AIResponseError, AIUnavailable, chat_structured, check_model
from ..ocr.schemas import AnswerKeyPageResult, QuestionPageResult, StudentPageResult
from .doc_structure import parse_question_paper_structure, StructuredQuestion
from .key_segmentation import segment_answer_keys
from .student_segmentation import segment_student_answers
from .mapping_service import apply_key_mapping, apply_student_mapping, refresh_key_state
from .numbering import normalize_question_number
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


_CANCEL_REQUESTED: set[str] = set()


def request_cancellation(doc_id: str) -> None:
    _CANCEL_REQUESTED.add(doc_id)


def is_cancelled(doc_id: str, db: Session, doc) -> bool:
    if doc_id in _CANCEL_REQUESTED:
        return True
    try:
        db.refresh(doc)
        if doc.status == "CANCELLED":
            return True
    except Exception:
        pass
    return False


def _handle_cancel(db: Session, doc, doc_id: str) -> None:
    _CANCEL_REQUESTED.discard(doc_id)
    doc.status = "CANCELLED"
    doc.stage = "Cancelled by user"
    doc.error_message = "OCR processing was stopped by user."
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
        if doc and doc.status != "CANCELLED":
            err_detail = f": {type(e).__name__} - {e}" if str(e) else f": {type(e).__name__}"
            doc.status, doc.error_message = "FAILED", f"Processing failed unexpectedly{err_detail}. See the server log for details."
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

    if is_cancelled(doc_id, db, doc):
        _handle_cancel(db, doc, doc_id)
        return

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

    if is_cancelled(doc_id, db, doc):
        _handle_cancel(db, doc, doc_id)
        return

    try:
        check_model()
    except AIUnavailable as e:
        log.error("AI unavailable: %s", e.detail)
        doc.status, doc.error_message, doc.stage = "AI_ERROR", AI_UNAVAILABLE_MESSAGE, "AI service unavailable"
        db.commit()
        return

    (wd / "ocr").mkdir(exist_ok=True)
    total = len(doc.pages)
    _progress(db, doc, f"OCR: page 1 of {total}", 0, total, "OCR_PROCESSING")
    for i, p in enumerate(list(doc.pages)):
        if is_cancelled(doc_id, db, doc):
            _handle_cancel(db, doc, doc_id)
            return

        if only_failed and p.get("ocr_status") == "OK":
            continue
        _progress(db, doc, f"OCR: processing page {p['page_number']} of {total}", i)
        img = abs_path(p["processed_file"])
        out = wd / "ocr" / f"page-{p['page_number']:03d}.json"
        prompt_kwargs = {}
        if kind == "answer-sheet":
            canonical_qs = []
            for q in db.query(ExamQuestion).filter_by(exam_id=exam.id).order_by(ExamQuestion.position).all():
                q_text = (q.question_text or "").strip()
                clean_lines = [line.strip() for line in q_text.splitlines() if line.strip()]
                compact_text = " | ".join(clean_lines[:3])
                if len(compact_text) > 160:
                    compact_text = compact_text[:157] + "..."
                canonical_qs.append(f"Q{q.display_number}: {compact_text}")
            if canonical_qs:
                prompt_kwargs["canonical_questions"] = canonical_qs
        prompt_str = prompt_fn(p["page_number"], p["ocr_width"], p["ocr_height"], **prompt_kwargs)
        try:
            call = chat_structured(prompts.OCR_SYSTEM, prompt_str,
                                   schema, img)
            out.write_text(json.dumps({"status": "OK", "raw": call.raw, "parsed": call.parsed.model_dump(),
                                       "attempts": call.attempts}, ensure_ascii=False, indent=1), encoding="utf-8")
            _set_pages(db, doc, i, ocr_status="OK", ocr_error=None, ocr_file=rel(out))
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

        if is_cancelled(doc_id, db, doc):
            _handle_cancel(db, doc, doc_id)
            return

    doc.progress_current = total

    if is_cancelled(doc_id, db, doc):
        _handle_cancel(db, doc, doc_id)
        return

    _progress(db, doc, "Extracting and validating", None, None, "EXTRACTING")
    results = _load_results(doc, schema)
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
        doc.status, doc.stage, doc.error_message = "READY", "Ready for review", None
    db.commit()


def _load_results(doc, schema):
    out = []
    pdf_doc = None
    try:
        orig = abs_path(doc.original_file)
        if orig.exists() and orig.suffix.lower() == ".pdf":
            import pymupdf
            pdf_doc = pymupdf.open(orig)
    except Exception:
        pdf_doc = None

    for p in doc.pages:
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
        data = json.loads(abs_path(p["ocr_file"]).read_text(encoding="utf-8"))
        out.append((p_dict, schema.model_validate(data["parsed"])))

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
    existing_q_ids = [q.id for q in db.query(ExamQuestion).filter_by(exam_id=exam.id).all()]
    if existing_q_ids:
        db.query(AnswerKey).filter_by(exam_id=exam.id).update({AnswerKey.exam_question_id: None})
        db.query(StudentAnswer).filter(StudentAnswer.exam_question_id.in_(existing_q_ids)).update({StudentAnswer.exam_question_id: None}, synchronize_session=False)
        db.query(EvaluationItem).filter(EvaluationItem.exam_question_id.in_(existing_q_ids)).delete(synchronize_session=False)
        db.query(ExamQuestion).filter_by(exam_id=exam.id).delete()
    struct = parse_question_paper_structure(results)

    # Safety Net: If 0 questions were parsed, check if OCR captured any non-empty text blocks (excluding instructions)
    if not struct.questions:
        fallback_texts = []
        for p, pres in results:
            raw_qs = getattr(pres, "questions", [])
            for q in raw_qs:
                t = (getattr(q, "question_text", None) or "").strip()
                if t and getattr(q, "question_type", None) not in ("information", "instruction", "metadata", "header"):
                    fallback_texts.append((p.get("page_number", 1), getattr(q, "bbox", None), t, getattr(q, "marks", None)))

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

    # Reconcile exam total marks, duration, and instructions if printed on paper
    if struct.exam_max_marks and abs(exam.total_marks - struct.exam_max_marks) > 1e-9:
        log.info("Detected paper max marks %g vs exam total %g", struct.exam_max_marks, exam.total_marks)
        exam.total_marks = struct.exam_max_marks

    if struct.exam_duration_minutes and exam.duration_minutes != struct.exam_duration_minutes:
        exam.duration_minutes = struct.exam_duration_minutes

    if struct.instructions and not exam.instructions:
        exam.instructions = "\n".join(struct.instructions)

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

    try:
        import json
        struct_path = wd / "structure.json"
        with open(struct_path, "w", encoding="utf-8") as f:
            json.dump({
                "stated_question_count": struct.stated_question_count,
                "stated_printed_pages": struct.stated_printed_pages,
                "exam_duration_minutes": struct.exam_duration_minutes,
                "exam_max_marks": struct.exam_max_marks,
                "qp_code": struct.qp_code,
                "sections": struct.sections,
                "unclassified_blocks": struct.unclassified_blocks,
            }, f, indent=2)
    except Exception as e:
        log.warning("Could not write structure.json: %s", e)

    if rows:
        from .state import at_least
        if not at_least(exam, "QUESTIONS_EXTRACTED"):
            set_state(exam, "QUESTIONS_EXTRACTED")
    else:
        log.warning("No questions extracted for exam %s", exam.id)
        doc.error_message = "No questions could be extracted from this document. Please check the document or add questions manually."
    db.commit()

    # Reconcile dependent answer keys and student answers when question paper is processed or reprocessed
    for key_doc in db.query(AnswerKeyDocument).filter_by(exam_id=exam.id, is_active=True).all():
        apply_key_mapping(db, exam.id, key_doc.id)
    for ev in db.query(Evaluation).filter_by(exam_id=exam.id).all():
        if ev.status != "FINALIZED":
            apply_student_mapping(db, ev)
    db.commit()


def _build_answer_key(db: Session, doc, exam: Exam, wd: Path, results) -> None:
    db.query(AnswerKey).filter(AnswerKey.exam_id == exam.id, AnswerKey.document_id != doc.id).update({AnswerKey.is_active: False})
    db.query(AnswerKey).filter_by(document_id=doc.id).delete()
    pages_by_num = {p["page_number"]: p for p, _ in results}
    canonical_qs = db.query(ExamQuestion).filter_by(exam_id=exam.id).order_by(ExamQuestion.position).all()
    keys = segment_answer_keys(results, canonical_questions=canonical_qs)
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
    canonical_qs = db.query(ExamQuestion).filter_by(exam_id=exam.id).order_by(ExamQuestion.position).all()
    answers = segment_student_answers(results, canonical_questions=canonical_qs)
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
