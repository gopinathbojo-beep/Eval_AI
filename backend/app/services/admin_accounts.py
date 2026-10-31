from sqlalchemy.orm import Session
from ..config import get_settings
from ..models import Teacher


def ensure_owner(db: Session) -> None:
    """The platform owner named by ADMIN_EMAIL: a Super Admin console account. Nothing when ADMIN_EMAIL is empty
    (create console users with python -m app.create_admin instead)."""
    email = get_settings().admin_email.strip().lower()
    if not email:
        return
    owner = db.query(Teacher).filter_by(email=email).first()
    if owner is None:
        # No default password. The owner signs in with verified Google identity first.
        db.add(Teacher(name="Administrator", email=email, role="ADMIN", admin_role="super_admin",
                       password_hash="!google-login-required"))
    else:
        owner.role, owner.admin_role = "ADMIN", "super_admin"
    db.commit()
