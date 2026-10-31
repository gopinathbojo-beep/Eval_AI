from __future__ import annotations
from sqlalchemy.orm import Session
from ..models import AuditLog, Teacher, Exam, Workspace


def audit(db: Session, *, exam_id: str | None, teacher_id: str | None, entity_type: str, entity_id: str,
<<<<<<< 7c662e7
          action: str, old=None, new=None, reason: str | None = None, ip: str = "") -> None:
    db.add(AuditLog(exam_id=exam_id, teacher_id=teacher_id, entity_type=entity_type, entity_id=entity_id,
                    action=action, old_value=old, new_value=new, reason=reason, ip=ip))
=======
          action: str, old=None, new=None, reason: str | None = None) -> None:
    from ..actor import actor_id
    if action.startswith("ai_") and actor_id.get():
        teacher_id = actor_id.get()
    actor = db.get(Teacher, teacher_id) if teacher_id else None
    exam = db.get(Exam, exam_id) if exam_id else None
    target = db.get(Teacher, entity_id) if entity_type in {"user", "teacher"} else None
    workspace_id = getattr(exam, "workspace_id", None) or getattr(target, "workspace_id", None) or getattr(actor, "workspace_id", None)
    if entity_type == "workspace" and db.get(Workspace, entity_id):
        workspace_id = entity_id
    db.add(AuditLog(exam_id=exam_id, teacher_id=teacher_id, workspace_id=workspace_id, entity_type=entity_type, entity_id=entity_id,
                    action=action, old_value=old, new_value=new, reason=reason))
>>>>>>> kishore/Version2.0
