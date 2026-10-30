from __future__ import annotations
import logging
from typing import Any
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ..database import get_db
from ..deps import err
from ..models import Teacher, VerifiedReferenceExample
from ..security import current_teacher
from ..services.reference_learning import (
    calculate_accuracy_diagnostics as compute_reference_collection_metrics,
    compute_accuracy_score,
    compute_cer,
    compute_wer,
    get_few_shot_prompt_hints,
    seed_verified_reference_collection,
)

log = logging.getLogger("adem.routes.reference_collection")
router = APIRouter(prefix="/api/reference-collection", tags=["reference-collection"])


class ReferenceExampleCreate(BaseModel):
    document_type: str = Field("question_paper", description="question_paper, answer_key, or student_answer")
    subject: str = Field("General", description="Subject name e.g. Mathematics, English, Chemistry")
    source_document: str = Field(..., description="Document title or identifier")
    page_number: int = Field(1, ge=1)
    question_number: str | None = None
    normalized_number: str | None = None
    original_ocr: str = ""
    corrected_text: str = ""
    error_category: str = Field("none", description="mathematical_symbols, chemical_formula, table_formatting, numbering, word_typo, missing_content, none")
    structure_type: str = Field("descriptive", description="formula, equation, table, notice_box, subquestion, descriptive, mcq")
    approved_marks: float | None = None
    criteria: list[str] = Field(default_factory=list)
    verification_status: str = Field("APPROVED", description="APPROVED or REVIEW_REQUIRED")


def _view_example(ex: VerifiedReferenceExample) -> dict[str, Any]:
    cer = compute_cer(ex.corrected_text or "", ex.original_ocr or "")
    wer = compute_wer(ex.corrected_text or "", ex.original_ocr or "")
    acc = compute_accuracy_score(ex.corrected_text or "", ex.original_ocr or "")
    return {
        "id": ex.id,
        "exam_id": ex.exam_id,
        "document_type": ex.document_type,
        "subject": ex.subject,
        "source_document": ex.source_document,
        "page_number": ex.page_number,
        "question_number": ex.question_number,
        "normalized_number": ex.normalized_number,
        "original_ocr": ex.original_ocr,
        "corrected_text": ex.corrected_text,
        "error_category": ex.error_category,
        "structure_type": ex.structure_type,
        "approved_marks": ex.approved_marks,
        "criteria": ex.criteria or [],
        "verification_status": ex.verification_status,
        "cer": round(cer, 4),
        "wer": round(wer, 4),
        "accuracy_pct": acc,
        "created_at": ex.created_at.isoformat() if ex.created_at else None,
    }


@router.get("")
def list_reference_examples(
    subject: str | None = Query(None),
    document_type: str | None = Query(None),
    error_category: str | None = Query(None),
    db: Session = Depends(get_db),
    t: Teacher = Depends(current_teacher),
):
    """Retrieve verified reference examples, ensuring seed collection is loaded."""
    q = db.query(VerifiedReferenceExample).filter_by(workspace_id=t.workspace_id, teacher_id=t.id)
    if subject:
        q = q.filter(VerifiedReferenceExample.subject.ilike(f"%{subject}%"))
    if document_type:
        q = q.filter_by(document_type=document_type)
    if error_category:
        q = q.filter_by(error_category=error_category)
    rows = q.order_by(VerifiedReferenceExample.subject, VerifiedReferenceExample.page_number, VerifiedReferenceExample.created_at).all()
    return {"examples": [_view_example(r) for r in rows], "total": len(rows)}


@router.post("", status_code=201)
def add_reference_example(
    body: ReferenceExampleCreate,
    db: Session = Depends(get_db),
    t: Teacher = Depends(current_teacher),
):
    """Save teacher-verified correction into the reusable local reference collection."""
    if not body.corrected_text.strip():
        raise err(400, "INVALID_INPUT", "Corrected text cannot be empty.")

    ex = VerifiedReferenceExample(
        teacher_id=t.id,
        workspace_id=t.workspace_id,
        document_type=body.document_type,
        subject=body.subject,
        source_document=body.source_document,
        page_number=body.page_number,
        question_number=body.question_number,
        normalized_number=body.normalized_number,
        original_ocr=body.original_ocr,
        corrected_text=body.corrected_text,
        error_category=body.error_category,
        structure_type=body.structure_type,
        approved_marks=body.approved_marks,
        criteria=body.criteria,
        verification_status=body.verification_status,
    )
    db.add(ex)
    db.commit()
    db.refresh(ex)
    log.info("Saved verified reference example for %s Q%s (category=%s)", ex.subject, ex.question_number, ex.error_category)
    return _view_example(ex)


@router.get("/diagnostics")
def get_diagnostics(
    db: Session = Depends(get_db),
    t: Teacher = Depends(current_teacher),
):
    """Return objective, honest accuracy benchmarks (CER, WER, question numbering accuracy, marks accuracy)."""
    metrics = compute_reference_collection_metrics(db, workspace_id=t.workspace_id, teacher_id=t.id)
    return {
        "status": "OK",
        "model": "blaifa/InternVL3_5:4B (Ollama)",
        "diagnostics": metrics,
        "hardware_constraint_note": (
            "Model running via local Ollama. Fine-tuning InternVL3.5 4B requires 16GB-24GB+ VRAM "
            "with a training framework (e.g. PyTorch/Unsloth/DeepSpeed), which is not technically supported "
            "on 6GB laptop VRAM or within Ollama inference runtime."
        ),
    }


@router.get("/prompt-hints")
def get_prompt_hints(
    subject: str | None = Query(None),
    t: Teacher = Depends(current_teacher),
):
    """Returns few-shot prompt guidance synthesized from teacher-verified references."""
    return {"hints": get_few_shot_prompt_hints(subject)}
