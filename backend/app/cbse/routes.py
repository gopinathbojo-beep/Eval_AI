from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from .catalog import PROFILES, grade_for
from .extraction import Node
from .validation import validate, active_doc
from ..database import get_db
from ..deps import get_exam, err
from ..models import (
    Teacher,
    ExamQuestion,
    AnswerKey,
    QuestionPaperDocument,
    AnswerKeyDocument,
    Evaluation,
    EvaluationItem,
)
from ..security import current_teacher
from ..services.audit import audit
from ..workspaces import classes_query, subjects_query, assigned
from ..serializers import question_view, key_view

router = APIRouter(prefix="/api")


def candidates(subject, grade):
    name = subject.name.strip().casefold()
    family = {
        "math": "Mathematics",
        "maths": "Mathematics",
        "mathematics": "Mathematics",
        "english": "English",
        "hindi": "Hindi",
    }.get(name)
    return [
        p
        for p in PROFILES
        if p["class_level"] == grade
        and (
            subject.code == p["code"]
            or name in [p["name"].casefold(), *[a.casefold() for a in p["aliases"]]]
            or family
            and p["name"].startswith(family)
        )
    ]


@router.get("/standards")
def standards(
    class_id: str | None = None,
    db: Session = Depends(get_db),
    user: Teacher = Depends(current_teacher),
):
    classes = list(classes_query(db, user))
    if class_id:
        classes = [c for c in classes if c.id == class_id]
        if not classes:
            raise err(404, "NOT_FOUND", "Class not found.")
    subjects = list(subjects_query(db, user))
    grades = {grade_for(c) for c in classes}
    allowed = {}
    for c in classes:
        for s in subjects:
            if assigned(db, user, c.id, s.id):
                for p in candidates(s, grade_for(c)):
                    allowed.setdefault(p["id"], []).append(s.id)
    return [
        {**p, "subject_ids": list(dict.fromkeys(allowed.get(p["id"], [])))}
        for p in PROFILES
        if p["class_level"] in grades and (user.role != "TEACHER" or p["id"] in allowed)
    ]


@router.get("/exams/{exam_id}/standard-validation")
def validation(
    exam_id: str,
    phase: Literal["paper", "scheme", "evaluation"] = "evaluation",
    db: Session = Depends(get_db),
    user: Teacher = Depends(current_teacher),
):
    exam = get_exam(db, user, exam_id)
    result = validate(db, exam, phase)
    db.commit()
    documents = []
    for kind, model in (
        ("question-paper", QuestionPaperDocument),
        ("answer-key", AnswerKeyDocument),
    ):
        doc = active_doc(db, model, exam.id)
        if doc:
            documents.append(
                {
                    "id": doc.id,
                    "kind": kind,
                    "status": doc.status,
                    "extraction": doc.extraction,
                }
            )
    return {
        **result,
        "documents": documents,
        "options": exam.standard_options,
        "can_edit": exam.status not in {"EVALUATING", "REVIEW_REQUIRED", "FINALIZED"}
        and not db.query(EvaluationItem)
        .join(Evaluation)
        .filter(Evaluation.exam_id == exam.id)
        .first(),
        "questions": [
            question_view(q)
            for q in db.query(ExamQuestion)
            .filter_by(exam_id=exam.id)
            .order_by(ExamQuestion.position)
        ],
        "keys": [
            key_view(k)
            for k in db.query(AnswerKey).filter_by(exam_id=exam.id, is_active=True)
        ],
    }


class Review(BaseModel):
    target: Literal["question", "key", "question-paper", "answer-key", "options"]
    id: str | None = None
    root: int | None = Field(None, gt=0)
    tree: Node | None = None
    metadata: dict | None = None
    instructions: list[str] | None = None
    issues: list[str] | None = None
    options: dict | None = None
    reason: str = Field(min_length=3, max_length=1000)


@router.post("/exams/{exam_id}/standard-review")
def review(
    exam_id: str,
    body: Review,
    db: Session = Depends(get_db),
    user: Teacher = Depends(current_teacher),
):
    exam = get_exam(db, user, exam_id)
    if not exam.standard_profile_id:
        raise err(409, "LEGACY_EXAM", "Legacy exams use the existing review workflow.")
    if (
        exam.status in {"EVALUATING", "REVIEW_REQUIRED", "FINALIZED"}
        or db.query(EvaluationItem)
        .join(Evaluation)
        .filter(Evaluation.exam_id == exam.id)
        .first()
    ):
        raise err(
            409,
            "STANDARD_LOCKED",
            "Evaluation has started; reviewed source rules are locked.",
        )
    old = None
    if body.target == "options":
        old = exam.standard_options
        options = body.options or {}
        if options.get("accessibility") not in {"standard", "accessible"} or (
            options.get("accountancy_option") not in {None, "financial", "computerised"}
        ):
            raise err(
                400, "INVALID_OPTIONS", "Choose a valid paper audience and branch."
            )
        exam.standard_options = options
    elif body.target in {"question-paper", "answer-key"}:
        doc = active_doc(
            db,
            QuestionPaperDocument
            if body.target == "question-paper"
            else AnswerKeyDocument,
            exam.id,
        )
        if not doc or doc.id != body.id or doc.status != "READY":
            raise err(404, "NOT_FOUND", "Processed active document not found.")
        old = doc.extraction
        data = dict(old or {})
        for field in ("metadata", "instructions", "issues"):
            if getattr(body, field) is not None:
                data[field] = getattr(body, field)
        doc.extraction = data
    else:
        row = db.get(ExamQuestion if body.target == "question" else AnswerKey, body.id)
        if (
            not row
            or row.exam_id != exam.id
            or (body.target == "key" and not row.is_active)
        ):
            raise err(404, "NOT_FOUND", "Question or scheme entry not found.")
        if body.target == "question":
            old = row.structure
            data = dict(old or {})
            if body.root is not None:
                data["root"] = body.root
                row.normalized_number = row.display_number = str(body.root)
            if body.tree is not None:
                data["tree"] = body.tree.model_dump()
            if body.issues is not None:
                data["issues"] = body.issues
            row.structure = data
        else:
            old = row.rubric
            data = dict(old or {})
            if body.tree is not None:
                data["cbse_tree"] = body.tree.model_dump()
            if body.issues is not None:
                data["problems"] = body.issues
            row.rubric = data
    # Any source/rule change requires a fresh paper AND scheme verification.
    for q in db.query(ExamQuestion).filter_by(exam_id=exam.id):
        q.verification_status = "UNVERIFIED"
    for k in db.query(AnswerKey).filter_by(exam_id=exam.id, is_active=True):
        k.verification_status, k.rubric_status = "UNVERIFIED", "UNREVIEWED"
    exam.status = "QUESTIONS_EXTRACTED"
    exam.standard_validation = None
    audit(
        db,
        exam_id=exam.id,
        teacher_id=user.id,
        entity_type="cbse_review",
        entity_id=body.id or exam.id,
        action="cbse_source_corrected",
        old=old,
        new=body.model_dump(exclude={"reason"}),
        reason=body.reason,
    )
    db.commit()
    result = validate(db, exam, "paper" if body.target != "key" else "scheme")
    db.commit()
    return result
