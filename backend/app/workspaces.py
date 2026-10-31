"""Shared workspace and exact-assignment authorization, used by HTTP and jobs."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Exam, SchoolClass, Subject, Teacher, TeacherAssignment, Workspace


def owner_id(db: Session, user: Teacher) -> str:
    ws = db.get(Workspace, user.workspace_id) if user.workspace_id else None
    return ws.owner_id if ws else user.id


def assigned(db: Session, user: Teacher, class_id: str, subject_id: str) -> bool:
    return (
        user.role != "TEACHER"
        or db.query(TeacherAssignment)
        .filter_by(teacher_id=user.id, class_id=class_id, subject_id=subject_id)
        .first()
        is not None
    )


def exams_query(db: Session, user: Teacher):
    q = (
        db.query(Exam).filter(Exam.workspace_id == user.workspace_id)
        if user.workspace_id
        else db.query(Exam).filter(Exam.teacher_id == user.id)
    )
    if user.role == "TEACHER" and user.workspace_id:
        q = q.filter(
            Exam.teacher_id == user.id,
            select(TeacherAssignment.id)
            .where(
                TeacherAssignment.teacher_id == user.id,
                TeacherAssignment.class_id == Exam.class_id,
                TeacherAssignment.subject_id == Exam.subject_id,
            )
            .exists(),
        )
    return q


def classes_query(db: Session, user: Teacher):
    q = db.query(SchoolClass).filter_by(teacher_id=owner_id(db, user))
    if user.role == "TEACHER" and user.workspace_id:
        q = q.filter(
            SchoolClass.id.in_(
                select(TeacherAssignment.class_id).where(
                    TeacherAssignment.teacher_id == user.id
                )
            )
        )
    return q


def subjects_query(db: Session, user: Teacher):
    q = db.query(Subject).filter_by(teacher_id=owner_id(db, user))
    if user.role == "TEACHER" and user.workspace_id:
        q = q.filter(
            Subject.id.in_(
                select(TeacherAssignment.subject_id).where(
                    TeacherAssignment.teacher_id == user.id
                )
            )
        )
    return q


def can_access_exam(db: Session, user: Teacher, exam: Exam) -> bool:
    if not user.is_active or user.must_change_password:
        return False
    ws = db.get(Workspace, user.workspace_id) if user.workspace_id else None
    if ws and not ws.is_active:
        return False
    return exams_query(db, user).filter(Exam.id == exam.id).first() is not None
