"""Grade disputes and support tickets from any signed-in account (spec 11, "any signed in"). The Platform Admin
resolves them in the console (routes/console.py)."""
from __future__ import annotations
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import err, get_evaluation
from ..models import Dispute, SupportTicket, Teacher
from ..security import current_account, current_teacher
from ..services.audit import audit

router = APIRouter(prefix="/api")


def dispute_view(d: Dispute) -> dict:
    return {"id": d.id, "evaluation_id": d.evaluation_id, "exam_question_id": d.exam_question_id, "reason": d.reason,
            "status": d.status, "resolution": d.resolution, "refund_credits": d.refund_credits,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "resolved_at": d.resolved_at.isoformat() if d.resolved_at else None}


def ticket_view(t: SupportTicket) -> dict:
    return {"id": t.id, "subject": t.subject, "message": t.message, "status": t.status, "reply": t.reply,
            "created_at": t.created_at.isoformat() if t.created_at else None}


class DisputeIn(BaseModel):
    evaluation_id: str
    exam_question_id: str | None = None
    reason: str = Field(min_length=5, max_length=4000)


@router.post("/disputes", status_code=201)
def raise_dispute(body: DisputeIn, request: Request, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    """A grade the account can see (its school's, or its child's) is questioned; one open dispute per question."""
    ev = get_evaluation(db, t, body.evaluation_id)  # 404 unless the evaluation is the account's to see
    if db.query(Dispute).filter_by(evaluation_id=ev.id, exam_question_id=body.exam_question_id, status="OPEN").first():
        raise err(409, "ALREADY_DISPUTED", "This grade already has an open dispute.")
    d = Dispute(raised_by=t.id, evaluation_id=ev.id, exam_question_id=body.exam_question_id, reason=body.reason.strip())
    db.add(d)
    db.flush()
    audit(db, exam_id=ev.exam_id, teacher_id=t.id, entity_type="dispute", entity_id=d.id, action="DISPUTE_RAISED",
          ip=request.client.host if request.client else "")
    db.commit()
    return dispute_view(d)


@router.get("/disputes")
def my_disputes(db: Session = Depends(get_db), t: Teacher = Depends(current_account)):
    return [dispute_view(d) for d in db.query(Dispute).filter_by(raised_by=t.id).order_by(Dispute.created_at.desc())]


class TicketIn(BaseModel):
    subject: str = Field(min_length=3, max_length=200)
    message: str = Field(min_length=5, max_length=8000)


@router.post("/support", status_code=201)
def contact_support(body: TicketIn, db: Session = Depends(get_db), t: Teacher = Depends(current_account)):
    ticket = SupportTicket(user_id=t.id, subject=body.subject.strip(), message=body.message.strip())
    db.add(ticket)
    db.flush()
    audit(db, exam_id=None, teacher_id=t.id, entity_type="support", entity_id=ticket.id, action="SUPPORT_TICKET")
    db.commit()
    return ticket_view(ticket)


@router.get("/support")
def my_tickets(db: Session = Depends(get_db), t: Teacher = Depends(current_account)):
    return [ticket_view(x) for x in db.query(SupportTicket).filter_by(user_id=t.id).order_by(SupportTicket.created_at.desc())]
