from __future__ import annotations
from fastapi import HTTPException
from sqlalchemy.orm import Session
from .models import Evaluation, Exam, Teacher
from . import formatter
from .services import paper_format
from .workspaces import can_access_exam


def err(status: int, code: str, message: str, issues: list | None = None):
    d = {"code": code, "message": message}
    if issues is not None:
        d["issues"] = issues
    return HTTPException(status, detail=d)


def get_exam(db: Session, teacher: Teacher, exam_id: str) -> Exam:
    exam = db.get(Exam, exam_id)
    if exam is None or not can_access_exam(db, teacher, exam):
        raise err(404, "NOT_FOUND", "Exam not found.")
    paper_format.set_for_exam(exam)  # the rest of the request parses with this subject's format
    formatter.set_for_exam(exam)  # ... and this subject's formatter (app/formatter)
    return exam


def get_evaluation(db: Session, teacher: Teacher, ev_id: str) -> Evaluation:
    ev = db.get(Evaluation, ev_id)
    if ev is None:
        raise err(404, "NOT_FOUND", "Evaluation not found.")
    get_exam(db, teacher, ev.exam_id)
    return ev
