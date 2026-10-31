"""A school's starting setup: every CBSE subject Eval AI grades, owned by its management account.

Management then assigns each teacher the classes and subjects they handle (routes/management.py); teachers do not
create or change subjects themselves."""
from sqlalchemy.orm import Session

from ..cbse.common import standards
from ..models import Subject, Workspace


def default_subjects(db: Session, school: Workspace) -> list[Subject]:
    """Adds the CBSE subjects the school does not have yet (standards.catalog), matched by name; returns those added.
    Running it again adds nothing, so a subject management deleted comes back only when this is called again."""
    have = {(s.name or "").strip().casefold()
            for s in db.query(Subject).filter_by(teacher_id=school.owner_id)}
    added = [Subject(teacher_id=school.owner_id, workspace_id=school.id, name=name, code=code or None)
             for name, code in standards.catalog() if name.casefold() not in have]
    db.add_all(added)
    db.flush()
    return added
