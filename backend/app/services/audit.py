from __future__ import annotations
from sqlalchemy.orm import Session
from ..models import AuditLog


def audit(db: Session, *, exam_id: str | None, teacher_id: str | None, entity_type: str, entity_id: str,
          action: str, old=None, new=None, reason: str | None = None) -> None:
    db.add(AuditLog(exam_id=exam_id, teacher_id=teacher_id, entity_type=entity_type, entity_id=entity_id,
                    action=action, old_value=old, new_value=new, reason=reason))
