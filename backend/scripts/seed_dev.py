"""Development accounts, created once by setup.bat (each only if its email is not taken yet):

    Management    develop@gmail.com  / password123   (Web app; runs the active "Demo School": the main dev login)
    Super Admin   admin@adem.local   / password123   (Admin app)
    Teacher       rao@school.org     / password123   (Web app; Demo School, Class 10-A Mathematics Basic and Standard)
    Parent        parent@adem.local  / password123   (Parents/web app; finishes the family profile at first sign-in)

It writes to the database backend/.env points at. Run from the backend folder:  .venv\\Scripts\\python.exe scripts\\seed_dev.py"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import SchoolClass, SchoolProfile, Subject, Teacher, TeacherAssignment, Workspace  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services import credits, school_setup  # noqa: E402


def main():
    init_db()
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    if not db.query(Teacher).filter_by(email="admin@adem.local").first():
        db.add(Teacher(name="Platform Admin", email="admin@adem.local", role="ADMIN", admin_role="super_admin",
                       password_hash=hash_password("password123")))
        print("  - Super Admin: admin@adem.local / password123 (Admin app, http://localhost:5174)")
    manager = db.query(Teacher).filter_by(email="develop@gmail.com").first()
    if manager is None:
        manager = Teacher(name="Developer", email="develop@gmail.com", role="MANAGEMENT", phone="9000000001",
                          password_hash=hash_password("password123"), profile_completed_at=now)
        db.add(manager)
        db.flush()
        school = Workspace(kind="SCHOOL", name="Demo School", owner_id=manager.id, city="Chennai", state="Tamil Nadu",
                           status="ACTIVE")
        db.add(school)
        db.flush()
        manager.workspace_id = school.id
        db.add(SchoolProfile(teacher_id=manager.id, name=school.name))
        credits.grant_signup_bonus(db, "school", school.id, "")
        print("  - Management: develop@gmail.com / password123 (Web app, http://localhost:5173)")
    for school in db.query(Workspace).filter_by(kind="SCHOOL"):
        # every school starts with all the CBSE subjects; classes and subjects made without their school (older
        # seeds) get it, so management can assign them to teachers
        for row in (*db.query(SchoolClass).filter_by(teacher_id=school.owner_id, workspace_id=None),
                    *db.query(Subject).filter_by(teacher_id=school.owner_id, workspace_id=None)):
            row.workspace_id = school.id
        if added := school_setup.default_subjects(db, school):
            print(f"  - {school.name}: {len(added)} CBSE subjects added")
    if manager.workspace_id:
        # the demo teacher, assigned by management to Class 10-A for both Mathematics papers (no other subject)
        cls = db.query(SchoolClass).filter_by(teacher_id=manager.id, name="10-A").first()
        if cls is None:
            cls = SchoolClass(teacher_id=manager.id, workspace_id=manager.workspace_id, name="10-A")
            db.add(cls)
        rao = db.query(Teacher).filter_by(email="rao@school.org").first()
        if rao is None:
            rao = Teacher(name="Ms Rao", email="rao@school.org", role="TEACHER", workspace_id=manager.workspace_id,
                          password_hash=hash_password("password123"), profile_completed_at=now)
            db.add(rao)
            print("  - Teacher: rao@school.org / password123 (Web app, http://localhost:5173)")
        db.flush()
        for name in ("Mathematics Basic", "Mathematics Standard"):
            subject = db.query(Subject).filter_by(teacher_id=manager.id, name=name).one()
            if not db.query(TeacherAssignment).filter_by(teacher_id=rao.id, class_id=cls.id, subject_id=subject.id).first():
                db.add(TeacherAssignment(teacher_id=rao.id, class_id=cls.id, subject_id=subject.id))
                print(f"  - {rao.name}: Class 10-A {name}")
    if not db.query(Teacher).filter_by(email="parent@adem.local").first():
        parent = Teacher(name="Demo Parent", email="parent@adem.local", phone="9000000000", role="PARENT",
                         password_hash=hash_password("password123"))
        db.add(parent)
        db.flush()
        family = Workspace(kind="FAMILY", name="Demo Parent", owner_id=parent.id, status="ACTIVE")
        db.add(family)
        db.flush()
        parent.workspace_id = family.id
        credits.grant_signup_bonus(db, "parent", parent.id, "")
        print("  - Parent: parent@adem.local / password123 (Parents app, http://localhost:5175)")
    db.commit()
    db.close()
    print("  - Database ready.")


if __name__ == "__main__":
    main()
