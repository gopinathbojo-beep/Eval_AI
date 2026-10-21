from __future__ import annotations
from .models import (AnswerKey, Evaluation, EvaluationItem, ExamQuestion, Student, StudentAnswer)


def doc_view(doc, kind: str) -> dict | None:
    if doc is None:
        return None
    return {
        "id": doc.id, "kind": kind, "original_filename": doc.original_filename, "status": doc.status,
        "stage": doc.stage, "progress_current": doc.progress_current, "progress_total": doc.progress_total,
        "error_message": doc.error_message, "uploaded_at": doc.uploaded_at.isoformat(),
        "pages": [{"page_number": p["page_number"], "width": p["width"], "height": p["height"],
                   "ocr_status": p.get("ocr_status"), "ocr_error": p.get("ocr_error")} for p in doc.pages],
    }


def question_view(q: ExamQuestion) -> dict:
    q_text = q.question_text or ""
    passage_text = None
    if "[/Reading Passage Context]" in q_text:
        parts = q_text.split("[/Reading Passage Context]", 1)
        passage_text = parts[0].replace("[Reading Passage Context]\n", "").replace("[Reading Passage Context]", "").strip()
        q_text = parts[1].strip()
    elif "[Reading Passage Context]\n" in q_text:
        parts = q_text.split("[Reading Passage Context]\n", 1)
        subparts = parts[1].split("\n\n(", 1)
        if len(subparts) == 2:
            passage_text = subparts[0].strip()
            q_text = "(" + subparts[1].strip()
        else:
            subparts = parts[1].split("\n\n", 1)
            if len(subparts) == 2:
                passage_text = subparts[0].strip()
                q_text = subparts[1].strip()
    elif "[Reading Passage]\n" in q_text:
        parts = q_text.split("[Reading Passage]\n", 1)
        subparts = parts[1].split("\n\n[Questions]\n", 1)
        if len(subparts) == 2:
            passage_text = subparts[0].strip()
            q_text = subparts[1].strip()
        else:
            subparts = parts[1].split("\n\n", 1)
            if len(subparts) == 2:
                passage_text = subparts[0].strip()
                q_text = subparts[1].strip()

    return {
        "k_level": q.k_level, "k_level_source": q.k_level_source, "course_outcome": q.course_outcome,
        "id": q.id, "exam_id": q.exam_id, "display_number": q.display_number,
        "normalized_number": q.normalized_number, "question_text": q_text,
        "clean_question_text": q_text, "passage_text": passage_text,
        "raw_ocr_text": q.raw_ocr_text, "question_type": q.question_type, "max_marks": q.max_marks,
        "section": q.section, "position": q.position, "page_start": q.page_start, "page_end": q.page_end,
        "bbox": q.bbox, "has_crop": bool(q.crop_file), "document_id": q.document_id,
        "ocr_confidence": q.ocr_confidence, "verification_status": q.verification_status,
        "review_reason": q.review_reason,
    }


def key_view(k: AnswerKey) -> dict:
    return {
        "id": k.id, "document_id": k.document_id, "raw_question_number": k.raw_question_number,
        "normalized_number": k.normalized_number, "exam_question_id": k.exam_question_id,
        "answer_text": k.answer_text, "marks": k.marks, "criteria": k.criteria,
        "accepted_answers": k.accepted_answers, "keywords": k.keywords, "page_number": k.page_number,
        "bbox": k.bbox, "has_crop": bool(k.crop_file), "ocr_confidence": k.ocr_confidence,
        "mapping_status": k.mapping_status, "mapping_note": k.mapping_note,
        "mapping_candidates": k.mapping_candidates, "mark_mismatch": k.mark_mismatch,
        "verification_status": k.verification_status,
    }


def answer_view(a: StudentAnswer) -> dict:
    return {
        "id": a.id, "raw_question_number": a.raw_question_number, "normalized_number": a.normalized_number,
        "exam_question_id": a.exam_question_id, "raw_ocr_text": a.raw_ocr_text, "answer_text": a.answer_text,
        "page_number": a.page_number, "bbox": a.bbox, "has_crop": bool(a.crop_file),
        "ocr_confidence": a.ocr_confidence, "status": a.status, "mapping_note": a.mapping_note,
        "mapping_candidates": a.mapping_candidates, "mapping_confirmed": a.mapping_confirmed,
        "position": a.position, "edited": a.answer_text != a.raw_ocr_text,
    }


def item_view(i: EvaluationItem) -> dict:
    return {
        "id": i.id, "exam_question_id": i.exam_question_id, "student_answer_id": i.student_answer_id,
        "status": i.status, "ai_marks": i.ai_marks, "ai_decision": i.ai_decision,
        "matched_points": i.matched_points, "missing_points": i.missing_points,
        "ai_feedback": i.ai_feedback, "ai_confidence": i.ai_confidence, "error": i.error,
        "final_marks": i.final_marks, "teacher_overridden": i.teacher_overridden,
        "teacher_feedback": i.teacher_feedback, "not_attempted_confirmed": i.not_attempted_confirmed,
    }


def student_view(s: Student) -> dict:
    return {"id": s.id, "name": s.name, "roll_number": s.roll_number, "class_id": s.class_id,
            "registration_number": s.registration_number, "section": s.section,
            "class_name": s.school_class.name if s.school_class else None}


def evaluation_view(ev: Evaluation) -> dict:
    ex = ev.exam
    st = ev.student
    cls_name = ex.school_class.name if ex and ex.school_class else (st.school_class.name if st and st.school_class else None)
    cls_id = ex.class_id if ex else (st.class_id if st else None)
    sub_name = ex.subject.name if ex and ex.subject else None
    sub_id = ex.subject_id if ex else None
    return {
        "id": ev.id, "exam_id": ev.exam_id, "student": student_view(st), "status": ev.status,
        "run_status": ev.run_status, "run_progress": ev.run_progress, "run_total": ev.run_total,
        "total_marks": ev.total_marks, "maximum_marks": ev.maximum_marks, "percentage": ev.percentage,
        "finalized_at": ev.finalized_at.isoformat() if ev.finalized_at else None,
        "answer_sheet_id": ev.answer_sheet_id, "exam_name": ex.name if ex else None,
        "class_id": cls_id, "class_name": cls_name,
        "subject_id": sub_id, "subject_name": sub_name,
        "created_at": ev.created_at.isoformat(),
    }
