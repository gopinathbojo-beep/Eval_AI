"""Regression tests for question/answer/mark mapping, mark validation and pipeline robustness."""
from types import SimpleNamespace

import pytest

from app.ocr.schemas import EvaluationResult
from app.services.evaluation_rules import EvaluationValidationError, mark_step, validate_evaluation
from app.services.mapping import NEEDS_REVIEW, map_label
from .conftest import BEHAVIOUR, make_pdf


def j(r, code=None):
    if code is not None:
        assert r.status_code == code, f"{r.status_code}: {r.text}"
    return r.json()


# ---------- mark validation (pure) ----------

def test_marks_round_half_up_to_half_mark_grid():
    assert validate_evaluation(EvaluationResult(marks_awarded=1.25), 2).marks_awarded == 1.5
    assert validate_evaluation(EvaluationResult(marks_awarded=0.75), 2).marks_awarded == 1.0
    assert validate_evaluation(EvaluationResult(marks_awarded=1.2), 2).marks_awarded == 1.0


def test_quarter_mark_questions_keep_quarter_grid():
    assert mark_step(2) == 0.5 and mark_step(1.75) == 0.25 and mark_step(1.3) is None
    # full marks on a 1.75 question must not be snapped down to 1.5
    r = validate_evaluation(EvaluationResult(marks_awarded=1.75), 1.75)
    assert r.marks_awarded == 1.75 and r.decision == "CORRECT"


def test_not_attempted_is_kept_only_with_zero_marks():
    assert validate_evaluation(EvaluationResult(marks_awarded=0, decision="not_attempted"), 2).decision == "NOT_ATTEMPTED"
    assert validate_evaluation(EvaluationResult(marks_awarded=1, decision="NOT_ATTEMPTED"), 2).decision == "PARTIALLY_CORRECT"
    assert validate_evaluation(EvaluationResult(marks_awarded=0, decision="CORRECT"), 2).decision == "INCORRECT"


def test_non_positive_maximum_rejected():
    with pytest.raises(EvaluationValidationError):
        validate_evaluation(EvaluationResult(marks_awarded=0), 0)


def test_mapping_candidates_carry_details():
    qs = [SimpleNamespace(id="a", normalized_number="3(a)"), SimpleNamespace(id="b", normalized_number="3(b)")]
    res = map_label("3", qs)
    assert res.status == NEEDS_REVIEW and res.candidates == ["a", "b"]
    assert [d["id"] for d in res.candidate_details] == ["a", "b"] and all(d["reason"] for d in res.candidate_details)


# ---------- API workflow ----------

def _exam_with_questions(c, h, total=15):
    cls = j(c.post("/api/classes", json={"name": f"MM-{total}-{id(c)}"}, headers=h), 201)
    sub = j(c.post("/api/subjects", json={"name": f"Sci-{total}-{id(c)}"}, headers=h), 201)
    exam = j(c.post("/api/exams", headers=h, json={"name": "Mapping", "academic_year": "2026-27", "class_id": cls["id"],
             "subject_id": sub["id"], "exam_type": "Unit", "total_marks": total}), 201)
    BEHAVIOUR["garbage_pages"] = set()
    j(c.post(f"/api/exams/{exam['id']}/question-paper", headers=h,
             files={"file": ("paper.pdf", make_pdf(2), "application/pdf")}), 202)
    qs = j(c.get(f"/api/exams/{exam['id']}/questions", headers=h), 200)["questions"]
    assert [q["display_number"] for q in qs] == ["1", "2", "3(a)", "3(b)"]
    return exam["id"], {q["display_number"]: q["id"] for q in qs}


def test_whole_question_and_sub_part_cannot_both_be_verified(client, auth):
    c, h = client, auth
    eid, _ = _exam_with_questions(c, h)
    q3 = j(c.post(f"/api/exams/{eid}/questions", headers=h,
                  json={"display_number": "3", "question_text": "Plants", "max_marks": 8}), 201)
    r = c.patch(f"/api/exam-questions/{q3['id']}", headers=h, json={"verification_status": "VERIFIED"})
    assert r.status_code == 400 and "sub-parts" in r.json()["message"]
    j(c.post(f"/api/exams/{eid}/questions/accept-valid", headers=h), 200)
    r = c.post(f"/api/exams/{eid}/questions/verify", headers=h, json={"confirm_marks_mismatch": True})
    assert r.status_code == 400 and r.json()["code"] == "QUESTIONS_NOT_READY"
    assert any("sub-part" in i["reason"] for i in r.json()["issues"])


def test_marks_total_mismatch_needs_confirmation(client, auth):
    c, h = client, auth
    eid, _ = _exam_with_questions(c, h, total=20)  # questions add up to 15
    j(c.post(f"/api/exams/{eid}/questions/accept-valid", headers=h), 200)
    r = c.post(f"/api/exams/{eid}/questions/verify", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "MARKS_TOTAL_MISMATCH"
    assert j(c.get(f"/api/exams/{eid}", headers=h))["status"] == "QUESTIONS_EXTRACTED"
    v = j(c.post(f"/api/exams/{eid}/questions/verify", headers=h, json={"confirm_marks_mismatch": True}), 200)
    assert v["marks_warning"] and j(c.get(f"/api/exams/{eid}", headers=h))["status"] == "QUESTIONS_VERIFIED"


def test_teacher_key_marks_are_kept_and_flagged(client, auth):
    c, h = client, auth
    eid, qid = _exam_with_questions(c, h)
    j(c.post(f"/api/exams/{eid}/questions/accept-valid", headers=h), 200)
    j(c.post(f"/api/exams/{eid}/questions/verify", headers=h), 200)

    k = j(c.post(f"/api/exams/{eid}/answer-keys", headers=h,
                 json={"exam_question_id": qid["2"], "answer_text": "Diffusion", "marks": 5}), 201)
    assert k["mapping_confirmed"] and not k["mark_mismatch"]
    # far above the question's 5 marks: kept as typed and flagged, not silently cut down
    k = j(c.patch(f"/api/answer-keys/{k['id']}", headers=h, json={"marks": 20}), 200)
    assert k["marks"] == 20 and k["mark_mismatch"]
    # an explicit 0 is not replaced by the question's maximum
    k = j(c.patch(f"/api/answer-keys/{k['id']}", headers=h, json={"marks": 0}), 200)
    assert k["marks"] == 0 and k["mark_mismatch"]
    k = j(c.patch(f"/api/answer-keys/{k['id']}", headers=h, json={"mismatch_resolution": "keep_question_marks"}), 200)
    assert k["marks"] == 5 and not k["mark_mismatch"]

    # a wrong mapping can be cleared
    k = j(c.patch(f"/api/answer-keys/{k['id']}", headers=h, json={"exam_question_id": None}), 200)
    assert k["exam_question_id"] is None and k["mapping_status"] == "UNMAPPED" and not k["mapping_confirmed"]


def test_negative_ai_key_marks_rejected(client, auth):
    c, h = client, auth
    eid, qid = _exam_with_questions(c, h)
    j(c.post(f"/api/exams/{eid}/questions/accept-valid", headers=h), 200)
    j(c.post(f"/api/exams/{eid}/questions/verify", headers=h), 200)
    r = c.post(f"/api/exams/{eid}/answer-keys/save-ai", headers=h,
               json={"answers": [{"exam_question_id": qid["1"], "answer_text": "x", "marks": -1}]})
    assert r.status_code == 422


# ---------- pipeline ----------

def test_failed_reread_keeps_existing_questions(client, auth):
    from app.database import SessionLocal
    from app.models import QuestionPaperDocument
    from app.services.pipeline import process_document
    c, h = client, auth
    eid, qid = _exam_with_questions(c, h)
    doc_id = j(c.get(f"/api/exams/{eid}/question-paper", headers=h), 200)["id"]
    db = SessionLocal()
    doc = db.get(QuestionPaperDocument, doc_id)
    doc.pages = [{**p, "ocr_status": "FAILED_PARSE"} for p in doc.pages]
    db.commit()
    db.close()
    BEHAVIOUR["garbage_pages"] = {1, 2}
    try:
        process_document("question-paper", doc_id, only_failed=True)
    finally:
        BEHAVIOUR["garbage_pages"] = set()
    qs = j(c.get(f"/api/exams/{eid}/questions", headers=h), 200)["questions"]
    assert {q["id"] for q in qs} == set(qid.values())
    assert j(c.get(f"/api/exams/{eid}/question-paper", headers=h), 200)["status"] == "FAILED"


def test_interrupted_jobs_become_retryable(client, auth):
    from app.database import SessionLocal
    from app.models import QuestionPaperDocument
    from app.services.pipeline import recover_interrupted_jobs
    c, h = client, auth
    eid, _ = _exam_with_questions(c, h)
    doc_id = j(c.get(f"/api/exams/{eid}/question-paper", headers=h), 200)["id"]
    db = SessionLocal()
    db.get(QuestionPaperDocument, doc_id).status = "OCR_PROCESSING"
    db.commit()
    db.close()
    recover_interrupted_jobs()
    doc = j(c.get(f"/api/exams/{eid}/question-paper", headers=h), 200)
    assert doc["status"] == "FAILED" and "interrupted" in doc["error_message"]
    j(c.post(f"/api/documents/question-paper/{doc_id}/reprocess", headers=h), 202)
