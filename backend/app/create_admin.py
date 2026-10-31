"""Create the first Super Admin:  python -m app.create_admin "Name" admin@example.com password

The account must change its password at first sign-in. Further console users are invited from the Admin app."""
import sys
from .database import SessionLocal, init_db
from .models import User
from .security import hash_password
from .services.accounts import normalize_email, password_problem


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    name, email, pw = sys.argv[1], normalize_email(sys.argv[2]), sys.argv[3]
    if problem := password_problem(pw):
        print(problem)
        sys.exit(1)
    init_db()
    db = SessionLocal()
    if db.query(User).filter_by(email=email).first():
        print("An account with that email already exists.")
        sys.exit(1)
    db.add(User(name=name, email=email, role="platform_admin", admin_role="super_admin",
                password_hash=hash_password(pw), must_change_password=True))
    db.commit()
    print(f"Created Super Admin {email}. Sign in to the Admin app and choose a new password.")


if __name__ == "__main__":
    main()
