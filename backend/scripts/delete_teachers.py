"""Delete every TEACHER account (teachers were retired; schools work through School Management and uploader codes).

Exams a teacher created stay with their school: they are handed to the school's owner account first.
Dry run by default; pass --yes to delete. Back up data/ first (scripts/backup_data.py).

Run: .venv\\Scripts\\python scripts\\delete_teachers.py [--yes]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import SessionLocal, init_db  # noqa: E402
from app.models import Exam, Teacher, TeacherAssignment, Workspace  # noqa: E402


def main(apply: bool) -> None:
    init_db()
    db = SessionLocal()
    try:
        teachers = db.query(Teacher).filter_by(role="TEACHER").all()
        print(f"{len(teachers)} teacher account(s){'' if apply else ' (dry run, pass --yes to delete)'}:")
        for t in teachers:
            ws = db.get(Workspace, t.workspace_id) if t.workspace_id else None
            exams = db.query(Exam).filter_by(teacher_id=t.id).all()
            print(f"  {t.email}  school={ws.name if ws else '-'}  exams={len(exams)}")
            if not apply:
                continue
            for e in exams:
                if ws is None:
                    raise SystemExit(f"{t.email} owns exams but has no school; resolve by hand.")
                e.teacher_id = ws.owner_id
            db.query(TeacherAssignment).filter_by(teacher_id=t.id).delete()
            db.delete(t)
        if apply:
            db.commit()
            print("Deleted.")
    finally:
        db.close()


if __name__ == "__main__":
    main("--yes" in sys.argv[1:])
