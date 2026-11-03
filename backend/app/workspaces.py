"""Shared workspace authorization, used by HTTP and jobs. Every workspace member sees the whole workspace."""

from sqlalchemy.orm import Session

from .models import Exam, SchoolClass, Subject, Teacher, Workspace


def owner_id(db: Session, user: Teacher) -> str:
    ws = db.get(Workspace, user.workspace_id) if user.workspace_id else None
    return ws.owner_id if ws else user.id


def assigned(db: Session, user: Teacher, class_id: str, subject_id: str) -> bool:
    return True  # there are no teacher assignments any more; kept for callers


def exams_query(db: Session, user: Teacher):
    return (
        db.query(Exam).filter(Exam.workspace_id == user.workspace_id)
        if user.workspace_id
        else db.query(Exam).filter(Exam.teacher_id == user.id)
    )


def classes_query(db: Session, user: Teacher):
    return db.query(SchoolClass).filter_by(teacher_id=owner_id(db, user))


def subjects_query(db: Session, user: Teacher):
    return db.query(Subject).filter_by(teacher_id=owner_id(db, user))


def can_access_exam(db: Session, user: Teacher, exam: Exam) -> bool:
    if not user.is_active or user.must_change_password:
        return False
    ws = db.get(Workspace, user.workspace_id) if user.workspace_id else None
    if ws and not ws.is_active:
        return False
    return exams_query(db, user).filter(Exam.id == exam.id).first() is not None
