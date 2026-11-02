from sqlalchemy.orm import Session
from ..config import get_settings
from ..models import Teacher


def ensure_owner(db: Session) -> None:
    email = get_settings().admin_email.strip().lower()
    if not db.query(Teacher).filter_by(email=email).first():
        # No default password. The owner signs in with verified Google identity first.
        db.add(Teacher(name="Administrator", email=email, role="ADMIN", password_hash="!google-login-required"))
        db.commit()
    else:
        owner = db.query(Teacher).filter_by(email=email).one()
        owner.role = "ADMIN"
        db.commit()
