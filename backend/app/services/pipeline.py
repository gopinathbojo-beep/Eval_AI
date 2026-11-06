"""Background processing: render pages -> Gemini per page -> store raw+parsed -> build entities."""
from __future__ import annotations
import copy
import json
import logging
from uuid import uuid4
from pathlib import Path
from sqlalchemy.orm import Session
from ..config import get_settings, ai_unavailable_message, ai_bad_response_message
from ..database import SessionLocal
from ..documents import cropping
from ..documents.renderer import RenderError, page_text as pdf_page_text, render_document
from ..documents.storage import abs_path, rel
from ..models import (AnswerKey, AnswerKeyDocument, AnswerSheetDocument, Evaluation, EvaluationItem, Exam, ExamQuestion,
                      QuestionPaperDocument, StudentAnswer)
from ..ocr import prompts
from ..ocr.internvl import AIResponseError, AIUnavailable, chat_structured, check_model
from .ai_labeler import label_key_criteria, label_question_types
from ..ocr.schemas import AnswerKeyPageResult, QuestionPageResult, StudentPageResult
from ..formatter.common.paper import apply_pdf_question_text, parse_question_paper_structure, StructuredQuestion
from ..formatter.common.keys import segment_answer_keys
from .job_queue import keyed_lock
from ..formatter.common.answers import segment_student_answers
from .mapping_service import apply_key_mapping, apply_student_mapping
from .state import set_state
from .. import formatter

log = logging.getLogger("adem.pipeline")

KINDS = {
    "question-paper": (QuestionPaperDocument, prompts.question_paper_prompt, QuestionPageResult),
    "answer-key": (AnswerKeyDocument, prompts.answer_key_prompt, AnswerKeyPageResult),
    "answer-sheet": (AnswerSheetDocument, prompts.student_answer_prompt, StudentPageResult),
}


def recover_failed_page(page, schema):
    """Revalidate a saved parse failure after a parser update, preserving source text.

    Check the collection and page identity explicitly: schemas with default
    empty collections must never accept a response from another extraction mode.
    """
    if page.get("ocr_status") != "FAILED_PARSE" or not page.get("ocr_file"):
        return None
    from ..ocr.parser import extract_json_object
    from pydantic import ValidationError
    try:
        source = abs_path(page["ocr_file"])
        saved = json.loads(source.read_text(encoding="utf-8"))
        raw = saved.get("raw") or ""
        obj = extract_json_object(raw)
        collection = next((name for name in ("fragments", "questions", "answers") if name in schema.model_fields), None)
        if (not collection or not isinstance(obj.get(collection), list)
                or obj.get("page_number", page["page_number"]) != page["page_number"]):
            return None
        parsed = schema.model_validate(obj)
        if not getattr(parsed, collection):
            return None
        return {"status": "OK", "raw": raw, "parsed": parsed.model_dump(), "attempts": 0,
                "recovered_from": rel(source), "recovery": "Saved response accepted by the updated parser"}
    except (OSError, ValueError, TypeError, ValidationError):
        return None


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
    doc.error_message = "Reading was stopped by the user."
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
    if exam.standard_profile_id and kind in {"question-paper", "answer-key"}:
        from ..cbse.extraction import Page
        schema = Page
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
        if kind == "question-paper":
            from ..cbse.variant import pick_variant
            if pick_variant(exam, doc.pages):
                log.info("Exam %s: question paper names variant %s", exam.id, exam.standard_profile_id)
        db.commit()

    adopted_profile = None
    if kind == "question-paper":
        from ..cbse.variant import adopt_printed_profile
        adopted_profile = adopt_printed_profile(exam, doc.pages)
        if adopted_profile:
            # Cached legacy responses use a different schema: read every page
            # with whole-question trees instead of reusing those responses.
            only_failed = False
            db.commit()
    if exam.standard_profile_id and kind in {"question-paper", "answer-key"}:
        from ..cbse.extraction import Page
        schema = Page

    if is_cancelled(doc_id, db, doc):
        _handle_cancel(db, doc, doc_id)
        return

    unavailable_msg = ai_unavailable_message()
    bad_response_msg = ai_bad_response_message()
    try:
        check_model()
    except AIUnavailable as e:
        log.error("AI unavailable: %s", e.detail)
        doc.status, doc.error_message, doc.stage = "AI_ERROR", unavailable_msg, "AI service unavailable"
        db.commit()
        return

    (wd / "ocr").mkdir(exist_ok=True)
    total = len(doc.pages)
    changed_key_pages = (set() if only_failed and kind == "answer-key" and exam.standard_profile_id
                         and db.query(AnswerKey.id).filter_by(document_id=doc.id).first() else None)
    _progress(db, doc, f"Reading page 1 of {total}", 0, total, "OCR_PROCESSING")
    for i, p in enumerate(list(doc.pages)):
        if is_cancelled(doc_id, db, doc):
            _handle_cancel(db, doc, doc_id)
            return

        if only_failed and p.get("ocr_status") == "OK":
            compatible = True
            if exam.standard_profile_id and kind in {"question-paper", "answer-key"}:
                try:
                    cached = json.loads(abs_path(p["ocr_file"]).read_text(encoding="utf-8"))
                    compatible = "fragments" in cached.get("parsed", {})
                except (KeyError, ValueError, OSError):
                    compatible = False
            if kind == "answer-sheet":
                try:  # saved before empty readings were caught: a page of blank answers is read again
                    cached = json.loads(abs_path(p["ocr_file"]).read_text(encoding="utf-8"))
                    compatible = not _blank_answers(schema.model_validate(cached.get("parsed") or {}))
                except (KeyError, ValueError, OSError):
                    compatible = False
            if compatible:
                continue
        recovered = recover_failed_page(p, schema) if only_failed else None
        if recovered:
            out = wd / "ocr" / f"page-{p['page_number']:03d}-recovered-{uuid4().hex[:8]}.json"
            out.write_text(json.dumps(recovered, ensure_ascii=False, indent=1), encoding="utf-8")
            _set_pages(db, doc, i, ocr_status="OK", ocr_error=None, ocr_file=rel(out))
            if changed_key_pages is not None:
                changed_key_pages.add(p["page_number"])
            log.info("Page %s recovered from saved response with updated parser", p["page_number"])
            continue
        _progress(db, doc, f"Reading page {p['page_number']} of {total}", i)
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
            if i and doc.pages[i - 1].get("ocr_status") == "OK":
                try:
                    previous = json.loads(abs_path(doc.pages[i - 1]["ocr_file"]).read_text(encoding="utf-8"))["parsed"]
                    prompt_kwargs["previous_answers"] = [
                        {"label": a.get("raw_question_label"), "last_written_text": (a.get("answer_text") or "")[-400:]}
                        for a in previous.get("answers", [])[-2:]]
                except (KeyError, ValueError, OSError):
                    pass
        prompt_str = prompt_fn(p["page_number"], p["ocr_width"], p["ocr_height"], **prompt_kwargs)
        system = prompts.OCR_SYSTEM
        if exam.standard_profile_id and kind in {"question-paper", "answer-key"}:
            from ..cbse.extraction import prompt as cbse_prompt, SYSTEM
            from ..cbse.catalog import get_profile
            previous = []
            if i and doc.pages[i-1].get("ocr_status") == "OK":
                try:
                    previous = [f["root"] for f in json.loads(abs_path(doc.pages[i-1]["ocr_file"]).read_text(encoding="utf-8"))["parsed"].get("fragments", [])]
                except (KeyError, ValueError, OSError):
                    pass
            prompt_str = cbse_prompt(kind,get_profile(exam.standard_profile_id),p["page_number"],total,previous,p.get("page_text", ""),exam.standard_options)
            system = SYSTEM
        try:
            call = chat_structured(system, prompt_str, schema, img)
            if kind == "answer-sheet" and _empty_numbered(call.parsed):
                # a numbered answer with no text ("Q9": ""): part of the page was not read. Ask once more and keep the
                # reading with more transcribed answers; a page where nothing at all was transcribed is unreadable,
                # so the automatic page retry reads it again (never a silently empty page)
                again = chat_structured(system, prompt_str, schema, img)
                if _transcribed(again.parsed) > _transcribed(call.parsed):
                    call = again
                if _blank_answers(call.parsed):
                    raise AIResponseError("FAILED_PARSE", "answers were listed but none was transcribed", call.raw)
            if system is not prompts.OCR_SYSTEM:  # a CBSE paper or scheme page: every printed question must come back
                call = _reread_missed_rows(doc, p["page_number"], call, system, prompt_str, schema, img)
            check = (_check_sheet_page(call, p["page_number"], img, system, abs_path(p["source_file"]), wd / "ocr")
                     if kind == "answer-sheet" else None)
            out.write_text(json.dumps({"status": "OK", "raw": call.raw, "parsed": call.parsed.model_dump(),
                                       "attempts": call.attempts, "engine": "internvl",
                                       **({"check": check} if check else {})},
                                      ensure_ascii=False, indent=1), encoding="utf-8")
            _set_pages(db, doc, i, ocr_status="OK", ocr_error=None, ocr_file=rel(out))
            if changed_key_pages is not None:
                changed_key_pages.add(p["page_number"])
        except AIUnavailable as e:
            log.error("AI became unavailable mid-run: %s", e.detail)
            doc.status, doc.error_message = "AI_ERROR", unavailable_msg
            db.commit()
            return
        except AIResponseError as e:
            log.error("Page %s: %s | raw=%r", p["page_number"], e.detail, e.raw[:500])
            out.write_text(json.dumps({"status": e.kind, "raw": e.raw, "parsed": None, "error": e.detail},
                                      ensure_ascii=False, indent=1), encoding="utf-8")
            _set_pages(db, doc, i, ocr_status=e.kind, ocr_error=bad_response_msg, ocr_file=rel(out))

        if is_cancelled(doc_id, db, doc):
            _handle_cancel(db, doc, doc_id)
            return

    doc.progress_current = total

    if is_cancelled(doc_id, db, doc):
        _handle_cancel(db, doc, doc_id)
        return

    if kind == "answer-sheet" and doc.student_id is None:
        # held for the teacher to pick the student: the pages are read now, the answers are built once assigned
        doc.status, doc.stage = "NEEDS_STUDENT", "Pick the student (answers already read)"
        db.commit()
        return

    if kind == "answer-key" and not db.query(ExamQuestion.id).filter_by(exam_id=exam.id).first():
        # read in parallel with the question paper; built when its questions exist (see _build_questions)
        doc.status, doc.stage = "WAITING", "Read; waiting for the questions"
        db.commit()
        return

    _progress(db, doc, "Extracting and validating", None, None, "EXTRACTING")
    results = _load_results(doc, schema)
    # pages of several documents are read in parallel, but building one re-maps the exam's keys and sheets
    with keyed_lock(f"exam:{exam.id}"):
        db.refresh(exam)
        if kind == "question-paper":
            _build_questions(db, doc, exam, wd, results)
        elif kind == "answer-key":
            _build_answer_key(db, doc, exam, wd, results, changed_pages=changed_key_pages)
        else:
            _build_student_answers(db, doc, exam, wd, results)

    failed = [p["page_number"] for p in doc.pages if p.get("ocr_status") != "OK"]
    if failed and kind == "answer-sheet" and schedule_page_retry(db, doc, failed):
        return
    if failed:
        doc.status = "NEEDS_ATTENTION"
        doc.error_message = f"{bad_response_msg} Page(s) affected: {', '.join(map(str, failed))}."
        doc.stage = "Needs attention"
    else:
        doc.status, doc.stage, doc.error_message = "READY", "Ready for review", None
    db.commit()

    if adopted_profile:
        # Legacy marking-scheme rows have the same alternative/step-total
        # problem. Re-read the active uploaded scheme with the new schema.
        from .job_queue import submit
        for key_doc in db.query(AnswerKeyDocument).filter_by(exam_id=exam.id, is_active=True):
            key_doc.status, key_doc.stage = "UPLOADED", "Queued for whole-question extraction"
            db.commit()
            submit(exam.id, process_document, "answer-key", key_doc.id, False)



def _transcribed(parsed) -> int:
    return sum(1 for a in getattr(parsed, "answers", None) or [] if (getattr(a, "answer_text", "") or "").strip())


def _empty_numbered(parsed) -> bool:
    """Some answer has a question number but no text: that part of the page was skipped."""
    return any(not (getattr(a, "answer_text", "") or "").strip() and getattr(a, "question_number", None)
               for a in getattr(parsed, "answers", None) or []) or _blank_answers(parsed)


def _blank_answers(parsed) -> bool:
    """A sheet page read as answers with no text at all (e.g. ten empty entries): the reading failed."""
    answers = getattr(parsed, "answers", None) or []
    return bool(answers) and not any((getattr(a, "answer_text", "") or "").strip() for a in answers)

# A sheet page the AI could not read is read again by itself, waiting longer each time, before the teacher is asked.
PAGE_RETRY_DELAYS = (60, 120, 300, 600, 1200, 1800)  # seconds: six more tries over about an hour
AUTO_RETRY_STAGE = "Re-reading unreadable page(s) automatically"


def schedule_page_retry(db: Session, doc, failed: list[int]) -> bool:
    """Queue the failed pages of an answer sheet to be read again later. False once the tries are used up."""
    import threading
    from ..config import get_settings
    from .job_queue import submit
    from .student_identity import run_sheet
    if get_settings().job_queue_inline:
        return False  # tests run jobs inline: no delayed retries there
    pages = copy.deepcopy(doc.pages)
    tries = max((p.get("auto_retries") or 0) for p in pages if p.get("page_number") in failed)
    if tries >= len(PAGE_RETRY_DELAYS):
        return False
    for p in pages:
        if p.get("page_number") in failed:
            p["auto_retries"] = tries + 1
    doc.pages = pages
    doc.status, doc.error_message = "UPLOADED", None
    doc.stage = f"{AUTO_RETRY_STAGE} (try {tries + 1} of {len(PAGE_RETRY_DELAYS)}): page(s) {', '.join(map(str, failed))}"
    db.commit()
    exam_id, doc_id = doc.exam_id, doc.id
    timer = threading.Timer(PAGE_RETRY_DELAYS[tries], submit, (exam_id, run_sheet, doc_id))
    timer.daemon = True
    timer.start()
    log.info("Sheet %s: page(s) %s unreadable, re-reading in %ss (try %s)", doc_id, failed, PAGE_RETRY_DELAYS[tries], tries + 1)
    return True


def _check_sheet_page(call, page_number, img, system, source, out_dir):
    """Check a sheet page's first reading against the image (see ocr.check); the first reading stays when the
    check itself fails."""
    s = get_settings()
    if not s.ai_check_sheet_reads:
        return None
    from ..ocr.check import check_page
    try:
        return check_page(call.parsed, page_number, img, system, chat_structured, s.ai_request_logprobs,
                          zoom_source=source if Path(source).exists() else None, zoom_dir=out_dir)
    except AIResponseError as e:
        log.warning("Page %s: reading check failed, first reading kept: %s", page_number, e.detail)
        return {"error": e.detail}


def _reread_missed_rows(doc, page_number, call, system, prompt_str, schema, img):
    """Read a page once more when the model left out question numbers the PDF prints on it (a truncated or
    malformed reply keeps only the first questions); the read that returns more of them is kept."""
    from ..cbse.layout import printed_by_page

    printed = (printed_by_page(doc) or {}).get(page_number) or set()

    def missed(result):
        return sorted(printed - {f.root for f in result.fragments})

    first = missed(call.parsed)
    if not first:
        return call
    log.warning("Page %s: questions %s printed but not read; reading the page again", page_number, first)
    try:
        retry = chat_structured(system, prompt_str + (
            f"\nA previous read of this page left out printed question(s) {', '.join(map(str, first))}. Return EVERY "
            "printed question on this page as its own fragment in the top-level fragments list; never nest one "
            "fragment inside another."), schema, img)
    except AIResponseError:
        return call
    return retry if len(missed(retry.parsed)) < len(first) else call


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
        if pdf_doc and formatter.current().uses_pdf_text():  # re-read so earlier uploads get current extraction (e.g. superscripts kept)
            p_num = p_dict.get("page_number", 1)
            if 1 <= p_num <= len(pdf_doc):
                try:
                    p_dict["page_text"] = pdf_page_text(pdf_doc[p_num - 1])
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
    if exam.standard_profile_id:
        from ..cbse.build import build_questions
        return build_questions(db,doc,exam,results)
    existing_q_ids = [q.id for q in db.query(ExamQuestion).filter_by(exam_id=exam.id).all()]
    if existing_q_ids:
        db.query(AnswerKey).filter_by(exam_id=exam.id).update({AnswerKey.exam_question_id: None})
        db.query(StudentAnswer).filter(StudentAnswer.exam_question_id.in_(existing_q_ids)).update({StudentAnswer.exam_question_id: None}, synchronize_session=False)
        db.query(EvaluationItem).filter(EvaluationItem.exam_question_id.in_(existing_q_ids)).delete(synchronize_session=False)
        db.query(ExamQuestion).filter_by(exam_id=exam.id).delete()
    struct = parse_question_paper_structure(results)
    apply_pdf_question_text(struct.questions, [p.get("page_text") or "" for p, _ in results])
    labeler_model = get_settings().ai_model
    if labeler_model:
        label_question_types(struct.questions, labeler_model)

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
            choice_group=q.choice_group,
            answer_any=q.answer_any,
            compulsory=q.compulsory,
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
    waiting = []
    for key_doc in db.query(AnswerKeyDocument).filter_by(exam_id=exam.id, is_active=True).all():
        if key_doc.status == "WAITING" and rows:
            key_doc.status, key_doc.stage = "UPLOADED", "Queued"
            waiting.append(key_doc.id)
            continue
        apply_key_mapping(db, exam.id, key_doc.id)
    for ev in db.query(Evaluation).filter_by(exam_id=exam.id).all():
        if ev.status != "FINALIZED":
            apply_student_mapping(db, ev)
    db.commit()
    from .job_queue import submit
    for key_id in waiting:  # the key waited for the questions: read it now (pages already read are skipped)
        submit(exam.id, process_document, "answer-key", key_id, True)


def _build_answer_key(db: Session, doc, exam: Exam, wd: Path, results, changed_pages=None) -> None:
    if exam.standard_profile_id:
        from ..cbse.build import build_keys
        return build_keys(db,doc,exam,results,changed_pages=changed_pages)
    db.query(AnswerKey).filter(AnswerKey.exam_id == exam.id, AnswerKey.document_id != doc.id).update({AnswerKey.is_active: False})
    db.query(AnswerKey).filter_by(document_id=doc.id).delete()
    pages_by_num = {p["page_number"]: p for p, _ in results}
    canonical_qs = db.query(ExamQuestion).filter_by(exam_id=exam.id).order_by(ExamQuestion.position).all()
    keys = segment_answer_keys(results, canonical_questions=canonical_qs)
    labeler_model = get_settings().ai_model
    if labeler_model:
        label_key_criteria(keys, canonical_qs, labeler_model)
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


import re as _re
# what the model writes for crossed-out ink: ~~text~~, <s>/<del>/<strike>, [crossed out ...], [struck-through ...]
_STRUCK = _re.compile(r"~~.*?~~|<(s|del|strike)>.*?</\1>|\[\s*(?:crossed[\s-]*out|struck[\s-]*(?:through|out)|strike[\s-]*through|scribbled[\s-]*out|cancelled)[^\]]*\]", _re.I | _re.S)


def drop_struck(text: str | None) -> str:
    """The answer without anything the student struck out, and without lines that held only struck words."""
    if not text:
        return text or ""
    kept = []
    for line in text.split("\n"):
        cleaned = _re.sub(r"[ \t]{2,}", " ", _STRUCK.sub("", line)).rstrip()
        if cleaned.strip() or not line.strip():
            kept.append(cleaned)
    return _re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()

def _answer_crop(pages_by_num: dict, pieces, wd: Path, name: str) -> str | None:
    """One picture of an answer from its band on each page it covers, top to bottom in page order."""
    from PIL import Image
    images = []
    for page_number, band in pieces:
        p = pages_by_num.get(page_number)
        nb = cropping.normalise_bbox(band, p["ocr_width"], p["ocr_height"], p["width"], p["height"]) if p and band else None
        if nb is None:
            continue
        with Image.open(abs_path(p["source_file"])) as im:
            images.append(im.crop((int(nb["x"]), int(nb["y"]), int(nb["x"] + nb["width"]), int(nb["y"] + nb["height"])))
                          .convert("RGB"))
    if not images:
        return None
    width = max(i.width for i in images)
    sheet = Image.new("RGB", (width, sum(i.height for i in images) + 8 * (len(images) - 1)), "white")
    y = 0
    for image in images:
        sheet.paste(image, (0, y))
        y += image.height + 8
    dest = wd / "crops" / f"{name}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest, "PNG")
    return rel(dest)


def _build_student_answers(db: Session, doc, exam: Exam, wd: Path, results) -> None:
    ev = db.query(Evaluation).filter_by(answer_sheet_id=doc.id).one()
    db.query(StudentAnswer).filter_by(evaluation_id=ev.id).delete()
    # pages of another student's paper (another subject or class) are left out before answers are built
    from .sheet_pages import check_pages
    excluded, notes, other_rolls = check_pages(results, exam)
    doc.identity = {**(doc.identity or {}), "excluded_pages": notes, "other_roll_pages": other_rolls}
    if excluded:
        log.warning("Sheet %s: left out page(s) %s from another paper", doc.id, sorted(excluded))
        results = [(p, r) for p, r in results if p["page_number"] not in excluded]
    if not results:
        db.commit()
        return
    pages_by_num = {p["page_number"]: p for p, _ in results}
    canonical_qs = db.query(ExamQuestion).filter_by(exam_id=exam.id).order_by(ExamQuestion.position).all()
    answers = segment_student_answers(results, canonical_questions=canonical_qs)
    for a in answers:  # struck-out writing is not the student's answer
        a.answer_text, a.raw_ocr_text = drop_struck(a.answer_text), drop_struck(a.raw_ocr_text)
    answers = [a for a in answers if a.answer_text.strip()]
    n = 0
    crop_run = uuid4().hex[:8]
    for a in answers:
        n += 1
        p = pages_by_num.get(a.page_number) or results[0][0]
        nb, crop = _bbox_and_crop(p, a.bbox, wd, f"a{n:03d}-{crop_run}")
        if getattr(a, "pieces", None):  # a formatter giving the answer's band on each page: one stitched crop
            crop = _answer_crop(pages_by_num, a.pieces, wd, f"a{n:03d}-{crop_run}") or crop
        db.add(StudentAnswer(
            evaluation_id=ev.id,
            raw_question_number=a.raw_question_number,
            normalized_number=a.normalized_number,
            raw_ocr_text=a.raw_ocr_text,
            answer_text=a.answer_text,
            page_number=a.page_number,
            bbox=nb,
            crop_file=crop,
            ocr_confidence=a.ocr_confidence,
            position=a.position or n,
            mapping_note=a.mapping_note,
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
