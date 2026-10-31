"""Development accounts, created once by setup.bat:

    Super Admin   admin@adem.local / ChangeMe123   (Admin app; must choose a new password at first sign-in)
    Teacher       rao@school.org   / password123   (Web app; in the active "Demo School")
    Parent        parent@adem.local / password123  (Parents app; 10 free credits)

Run from the backend folder:  .venv\\Scripts\\python.exe scripts\\seed_dev.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import School, User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services import credits  # noqa: E402


def main():
    init_db()
    db = SessionLocal()
    if not db.query(User).filter_by(email="admin@adem.local").first():
        db.add(User(name="Platform Admin", email="admin@adem.local", role="platform_admin", admin_role="super_admin",
                    password_hash=hash_password("ChangeMe123"), must_change_password=True))
        print("  - Super Admin: admin@adem.local / ChangeMe123 (Admin app, http://localhost:5174)")
    if not db.query(User).filter_by(email="rao@school.org").first():
        school = School(name="Demo School", city="Chennai", state="Tamil Nadu", status="ACTIVE")
        db.add(school)
        db.flush()
        db.add(User(name="Ms Rao", email="rao@school.org", role="teacher", school_id=school.id,
                    password_hash=hash_password("password123")))
        credits.grant_signup_bonus(db, "school", school.id, "")
        print("  - Teacher: rao@school.org / password123 (Web app, http://localhost:5173)")
    if not db.query(User).filter_by(email="parent@adem.local").first():
        parent = User(name="Demo Parent", email="parent@adem.local", phone="9000000000", role="parent",
                      password_hash=hash_password("password123"))
        db.add(parent)
        db.flush()
        credits.grant_signup_bonus(db, "parent", parent.id, "")
        print("  - Parent: parent@adem.local / password123 (Parents app, http://localhost:5175)")
    db.commit()
    db.close()
    print("  - Database ready.")


if __name__ == "__main__":
    main()
