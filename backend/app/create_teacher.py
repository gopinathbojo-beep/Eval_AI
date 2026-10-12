"""Create a teacher account:  python -m app.create_teacher "Name" email@school.org password"""
import sys
from .database import SessionLocal, init_db
from .models import Teacher
from .security import hash_password


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    name, email, pw = sys.argv[1:]
    if len(pw) < 8:
        print("Password must be at least 8 characters.")
        sys.exit(1)
    init_db()
    db = SessionLocal()
    if db.query(Teacher).filter_by(email=email.lower()).first():
        print("A teacher with that email already exists.")
        sys.exit(1)
    db.add(Teacher(name=name, email=email.lower(), password_hash=hash_password(pw)))
    db.commit()
    print(f"Created teacher {email}")


if __name__ == "__main__":
    main()
