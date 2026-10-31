"""Year rollover (spec 6.2): the School Manager moves each class's students into next year's class. Students are
copied, not moved, so last year's classes, marks and report cards stay exactly as they were; a class marked
"graduate" (Class 12, or students leaving) is not carried forward."""
from __future__ import annotations
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ..database import get_db
from ..deps import err
from ..models import SchoolClass, Student, Teacher
from ..security import current_school_manager
from ..services.audit import audit
from ..services.student_io import split_class_name
from ..workspaces import classes_query, owner_id

router = APIRouter(prefix="/api/school/rollover")


class Move(BaseModel):
    from_class_id: str
    to_class_name: str = Field("", max_length=100)  # empty with graduate=True
    graduate: bool = False


class RolloverIn(BaseModel):
    academic_year: str = Field(..., min_length=4, max_length=20)
    moves: list[Move] = Field(..., min_length=1)
    dry_run: bool = False


@router.get("")
def rollover_plan(db: Session = Depends(get_db), t: Teacher = Depends(current_school_manager)):
    """Every class with its student count, for the rollover screen."""
    out = []
    for c in classes_query(db, t).order_by(SchoolClass.name).all():
        out.append({"id": c.id, "name": c.name, "students": db.query(Student).filter_by(class_id=c.id).count()})
    return {"classes": out}


@router.post("")
def run_rollover(body: RolloverIn, db: Session = Depends(get_db), t: Teacher = Depends(current_school_manager)):
    owner = owner_id(db, t)
    mine = {c.id: c for c in classes_query(db, t).all()}
    if len({m.from_class_id for m in body.moves}) != len(body.moves):
        raise err(400, "DUPLICATE_CLASS", "Each class can be rolled over only once.")
    for m in body.moves:
        if m.from_class_id not in mine:
            raise err(404, "CLASS_NOT_FOUND", "Class not found.")
        if not m.graduate and not m.to_class_name.strip():
            raise err(400, "TARGET_REQUIRED", f"Choose next year's class for {mine[m.from_class_id].name}.")
        if not m.graduate and split_class_name(m.to_class_name.strip())[0] not in {"10", "12"}:
            raise err(400, "CBSE_CLASS_REQUIRED", "Eval AI supports CBSE Classes 10 and 12 only.")
    # read every source roster first, so a class that is both a source and a target is not double-copied
    rosters = {m.from_class_id: db.query(Student).filter_by(class_id=m.from_class_id).all() for m in body.moves}
    by_name = {c.name.strip().lower(): c for c in mine.values()}
    result = []
    for m in body.moves:
        src = mine[m.from_class_id]
        if m.graduate:
            result.append({"from": src.name, "to": None, "copied": 0, "skipped": 0, "graduated": len(rosters[src.id])})
            continue
        name = m.to_class_name.strip()
        target = by_name.get(name.lower())
        created = target is None
        if created:
            target = SchoolClass(teacher_id=owner, workspace_id=t.workspace_id, name=name)
            if not body.dry_run:
                db.add(target)
                db.flush()
            by_name[name.lower()] = target
        taken = set() if created else {r for (r,) in db.query(Student.roll_number).filter_by(class_id=target.id)}
        copied = skipped = 0
        for s in rosters[src.id]:
            if s.roll_number in taken:
                skipped += 1  # already in next year's class (rollover run twice) or a roll number clash
                continue
            taken.add(s.roll_number)
            copied += 1
            if not body.dry_run:
                db.add(Student(class_id=target.id, name=s.name, roll_number=s.roll_number,
                               registration_number=s.registration_number, section=s.section))
        result.append({"from": src.name, "to": name, "created": created, "copied": copied, "skipped": skipped})
    if body.dry_run:
        db.rollback()
    else:
        audit(db, exam_id=None, teacher_id=t.id, entity_type="workspace", entity_id=t.workspace_id or owner,
              action="year_rollover", new={"academic_year": body.academic_year, "moves": result})
        db.commit()
    return {"academic_year": body.academic_year, "dry_run": body.dry_run, "moves": result}
