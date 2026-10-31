"""The Platform Admin console (spec 6.1, 11 "admin"): dashboard, schools (approve, suspend), parents, credits and
payments, the evaluations monitor, disputes, support, audit log, console users, support login-as.

Every route needs a console account (security.current_admin): a Viewer reads, every write is refused for it. Console
users and login-as need a Super Admin. Version2.0's account screens stay in routes/admin.py (/admin/users, ...).
"""
from __future__ import annotations
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import err
from ..models import (AuditLog, CreditLedger, CreditPack, CreditSetting, Dispute, Evaluation, Exam, Payment,
                      SupportTicket, Teacher, Wallet, Workspace)
from ..security import admin_role, create_token, current_admin, current_super_admin, hash_password
from ..services import credits, mailer
from ..services.accounts import account_view, issue_link, normalize_email
from .auth import portal_url
from ..services.audit import audit
from .credits import ensure_packs, ledger_view, pack_view, payment_view
from .support import dispute_view, ticket_view

router = APIRouter(prefix="/api/admin")


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- dashboard ----------
@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    today = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    month = today.replace(day=1)
    count = lambda q: q.scalar() or 0  # noqa: E731
    return {
        "schools": db.query(Workspace).filter_by(kind="SCHOOL").count(),
        "parents": db.query(Teacher).filter_by(role="PARENT").count(),
        "teachers": db.query(Teacher).filter_by(role="TEACHER").count(),
        "evaluations_today": db.query(Evaluation).filter(Evaluation.created_at >= today).count(),
        "evaluations_month": db.query(Evaluation).filter(Evaluation.created_at >= month).count(),
        "credits_sold": count(db.query(func.sum(CreditLedger.amount)).filter(CreditLedger.type == "PURCHASE")),
        # holds are negative and releases give them back (positive), so what was used is the net of the two
        "credits_used": -count(db.query(func.sum(CreditLedger.amount))
                               .filter(CreditLedger.type.in_(("EVAL_HOLD", "EVAL_RELEASE", "PAPER_CHARGE")))),
        "revenue_inr": count(db.query(func.sum(Payment.amount_inr)).filter(Payment.status == "PAID")),
        "attention": {
            "pending_schools": db.query(Workspace).filter_by(kind="SCHOOL", status="PENDING").count(),
            "failed_payments": db.query(Payment).filter_by(status="FAILED").count(),
            "failed_evaluations": db.query(Evaluation).filter_by(run_status="ERROR").count(),
            "low_credit_schools": db.query(Wallet).filter(Wallet.owner_type == "school", Wallet.balance < 10).count(),
            "open_disputes": db.query(Dispute).filter_by(status="OPEN").count(),
            "open_tickets": db.query(SupportTicket).filter_by(status="OPEN").count(),
        },
    }


# ---------- schools ----------
def _school_view(db: Session, ws: Workspace) -> dict:
    manager = db.get(Teacher, ws.owner_id) if ws.owner_id else None
    w = db.query(Wallet).filter_by(owner_type="school", owner_id=ws.id).first()
    return {"id": ws.id, "name": ws.name, "status": ws.status, "is_active": ws.is_active, "board": ws.board,
            "city": ws.city, "state": ws.state, "phone": ws.phone, "address": ws.address,
            "manager": {"id": manager.id, "name": manager.name, "email": manager.email} if manager else None,
            "teachers": db.query(Teacher).filter_by(workspace_id=ws.id, role="TEACHER").count(),
            "exams": db.query(Exam).filter_by(workspace_id=ws.id).count(),
            "balance": w.balance if w else 0, "wallet_id": w.id if w else None,
            "approved_at": ws.approved_at.isoformat() if ws.approved_at else None,
            "created_at": ws.created_at.isoformat() if ws.created_at else None}


@router.get("/schools")
def schools(status: str | None = None, q: str = "", db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    rows = db.query(Workspace).filter_by(kind="SCHOOL")
    if status:
        rows = rows.filter(Workspace.status == status.upper())
    if q:
        rows = rows.filter(Workspace.name.ilike(f"%{q}%"))
    return [_school_view(db, ws) for ws in rows.order_by(Workspace.created_at.desc())]


def _school(db: Session, sid: str) -> Workspace:
    ws = db.get(Workspace, sid)
    if ws is None or ws.kind != "SCHOOL":
        raise err(404, "NOT_FOUND", "School not found.")
    return ws


@router.get("/schools/{sid}")
def school_detail(sid: str, db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    ws = _school(db, sid)
    view = _school_view(db, ws)
    view["teacher_list"] = [account_view(t) for t in db.query(Teacher).filter_by(workspace_id=ws.id, role="TEACHER")]
    w = db.query(Wallet).filter_by(owner_type="school", owner_id=ws.id).first()
    view["ledger"] = [ledger_view(r) for r in db.query(CreditLedger).filter_by(wallet_id=w.id)
                      .order_by(CreditLedger.created_at.desc()).limit(100)] if w else []
    return view


@router.post("/schools/{sid}/approve")
def approve_school(sid: str, request: Request, db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    """A self-signed-up school goes live; its signup credits are granted now, once (spec 05)."""
    ws = _school(db, sid)
    if ws.status != "ACTIVE":
        ws.status, ws.approved_at, ws.approved_by = "ACTIVE", _now(), a.id
        credits.grant_signup_bonus(db, "school", ws.id, "")
        audit(db, exam_id=None, teacher_id=a.id, entity_type="workspace", entity_id=ws.id, action="SCHOOL_APPROVED",
              ip=_ip(request))
        manager = db.get(Teacher, ws.owner_id)
        db.commit()
        if manager:
            mailer.send(manager.email, "Your school is approved on ADEM", "Your school is live",
                        [f"Hello {manager.name},", f"{ws.name} is approved. Sign in and invite your teachers."],
                        ("Open ADEM", f"{portal_url('school')}/login"))
    return _school_view(db, ws)


class StatusIn(BaseModel):
    status: str  # ACTIVE | SUSPENDED


@router.post("/schools/{sid}/status")
def school_status(sid: str, body: StatusIn, request: Request, db: Session = Depends(get_db),
                  a: Teacher = Depends(current_admin)):
    ws = _school(db, sid)
    if body.status not in ("ACTIVE", "SUSPENDED"):
        raise err(422, "BAD_STATUS", "Use ACTIVE or SUSPENDED.")
    old, ws.status = ws.status, body.status
    audit(db, exam_id=None, teacher_id=a.id, entity_type="workspace", entity_id=ws.id, action="SCHOOL_STATUS",
          old={"status": old}, new={"status": body.status}, ip=_ip(request))
    db.commit()
    return _school_view(db, ws)


# ---------- parents ----------
def _parent_view(db: Session, u: Teacher) -> dict:
    w = db.query(Wallet).filter_by(owner_type="parent", owner_id=u.id).first()
    return {**account_view(u), "balance": w.balance if w else 0, "wallet_id": w.id if w else None,
            "exams": db.query(Exam).filter_by(workspace_id=u.workspace_id).count() if u.workspace_id else 0}


@router.get("/parents")
def parents(q: str = "", db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    rows = db.query(Teacher).filter_by(role="PARENT")
    if q:
        rows = rows.filter((Teacher.name.ilike(f"%{q}%")) | (Teacher.email.ilike(f"%{q}%")))
    return [_parent_view(db, u) for u in rows.order_by(Teacher.created_at.desc())]


def _account(db: Session, uid: str, role: str | None = None) -> Teacher:
    u = db.get(Teacher, uid)
    if u is None or (role and u.role != role):
        raise err(404, "NOT_FOUND", "Account not found.")
    return u


@router.get("/parents/{uid}")
def parent_detail(uid: str, db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    from ..models import Child
    u = _account(db, uid, "PARENT")
    view = _parent_view(db, u)
    view["children"] = [{"id": c.id, "name": c.name, "standard": c.standard, "subjects": c.subjects}
                        for c in db.query(Child).filter_by(parent_id=u.id)]
    return view


@router.post("/parents/{uid}/status")
def parent_status(uid: str, body: StatusIn, request: Request, db: Session = Depends(get_db),
                  a: Teacher = Depends(current_admin)):
    u = _account(db, uid, "PARENT")
    u.is_active = body.status == "ACTIVE"
    if not u.is_active:
        u.session_version = (u.session_version or 0) + 1
    audit(db, exam_id=None, teacher_id=a.id, entity_type="user", entity_id=u.id, action="PARENT_STATUS",
          new={"status": body.status}, ip=_ip(request))
    db.commit()
    return _parent_view(db, u)


# ---------- account support: unlock, reset, login as ----------
@router.post("/accounts/{uid}/unlock")
def unlock(uid: str, request: Request, db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    u = _account(db, uid)
    u.failed_attempts, u.locked_until = 0, None
    audit(db, exam_id=None, teacher_id=a.id, entity_type="user", entity_id=u.id, action="ACCOUNT_UNLOCKED", ip=_ip(request))
    db.commit()
    return {"ok": True}


@router.post("/accounts/{uid}/reset-password")
def send_reset(uid: str, request: Request, db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    u = _account(db, uid)
    raw = issue_link(db, "reset", user_id=u.id)
    audit(db, exam_id=None, teacher_id=a.id, entity_type="user", entity_id=u.id, action="ADMIN_PASSWORD_RESET",
          ip=_ip(request))
    db.commit()
    portal = "admin" if u.role == "ADMIN" else "parent" if u.role == "PARENT" else "school"
    mailer.send(u.email, "Reset your ADEM password", "Reset your password",
                [f"Hello {u.name},", "Our support team sent you this link to choose a new password. It works for one hour."],
                ("Choose a new password", f"{portal_url(portal)}/reset-password?token={raw}"))
    return {"ok": True, "message": f"A reset link was sent to {u.email}."}


@router.post("/accounts/{uid}/impersonate")
def impersonate(uid: str, request: Request, db: Session = Depends(get_db), a: Teacher = Depends(current_super_admin)):
    """Support login as a school or parent account (Super Admin only, audited). A short bearer session."""
    u = _account(db, uid)
    if u.role == "ADMIN":
        raise err(403, "FORBIDDEN", "Console accounts cannot be impersonated.")
    audit(db, exam_id=None, teacher_id=a.id, entity_type="user", entity_id=u.id, action="IMPERSONATE", ip=_ip(request),
          new={"as": u.email})
    db.commit()
    return {"access_token": create_token(u, portal="parent" if u.role == "PARENT" else "web"), "token_type": "bearer",
            "user": account_view(u), "impersonated_by": a.email}


# ---------- credits and payments ----------
class PackIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    credits: int = Field(gt=0)
    price_inr: float = Field(ge=0)
    active: bool = True
    sort_order: int = 0


@router.get("/credit-packs")
def list_packs(db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    ensure_packs(db)
    db.commit()
    return [{**pack_view(p), "sort_order": p.sort_order} for p in db.query(CreditPack).order_by(CreditPack.sort_order)]


@router.post("/credit-packs", status_code=201)
def create_pack(body: PackIn, db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    p = CreditPack(**body.model_dump())
    db.add(p)
    db.flush()
    audit(db, exam_id=None, teacher_id=a.id, entity_type="credit_pack", entity_id=p.id, action="PACK_CREATED",
          new=body.model_dump())
    db.commit()
    return pack_view(p)


@router.put("/credit-packs/{pid}")
def update_pack(pid: str, body: PackIn, db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    p = db.get(CreditPack, pid)
    if p is None:
        raise err(404, "NOT_FOUND", "Credit pack not found.")
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    audit(db, exam_id=None, teacher_id=a.id, entity_type="credit_pack", entity_id=p.id, action="PACK_UPDATED",
          new=body.model_dump())
    db.commit()
    return pack_view(p)


@router.delete("/credit-packs/{pid}")
def retire_pack(pid: str, db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    """Packs are retired, not deleted: past payments still point at them."""
    p = db.get(CreditPack, pid)
    if p is None:
        raise err(404, "NOT_FOUND", "Credit pack not found.")
    p.active = False
    db.commit()
    return {"ok": True}


@router.get("/credit-settings")
def get_settings_(db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    return {k: credits.setting(db, k) for k in credits.DEFAULTS}


@router.put("/credit-settings")
def put_settings(body: dict[str, float], db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    unknown = set(body) - set(credits.DEFAULTS)
    if unknown:
        raise err(422, "UNKNOWN_SETTING", f"Unknown setting(s): {', '.join(sorted(unknown))}.")
    for k, v in body.items():
        if v < 0:
            raise err(422, "BAD_VALUE", f"{k} cannot be negative.")
        row = db.get(CreditSetting, k) or CreditSetting(key=k, value=v)
        row.value = v
        db.merge(row)
    audit(db, exam_id=None, teacher_id=a.id, entity_type="credit_settings", entity_id="credit_settings",
          action="CREDIT_SETTINGS", new=body)
    db.commit()
    return {k: credits.setting(db, k) for k in credits.DEFAULTS}


class AdjustIn(BaseModel):
    amount: int  # + grant, - deduct
    reason: str = Field(min_length=3, max_length=500)


@router.post("/wallets/{wid}/adjust")
def adjust_wallet(wid: str, body: AdjustIn, request: Request, db: Session = Depends(get_db),
                  a: Teacher = Depends(current_admin)):
    import uuid
    w = db.get(Wallet, wid)
    if w is None:
        raise err(404, "NOT_FOUND", "Wallet not found.")
    if body.amount == 0:
        raise err(422, "BAD_AMOUNT", "Grant or deduct a non-zero amount.")
    try:
        credits.post(db, w, "ADMIN_GRANT" if body.amount > 0 else "ADMIN_DEDUCT", body.amount, f"adjust-{uuid.uuid4().hex}",
                     ref_type="admin", note=body.reason, actor_id=a.id)
    except credits.InsufficientCredits as e:
        raise err(409, "INSUFFICIENT_CREDITS", f"Only {e.available} credits to deduct.")
    audit(db, exam_id=None, teacher_id=a.id, entity_type="wallet", entity_id=w.id, action="CREDITS_ADJUSTED",
          new={"amount": body.amount, "reason": body.reason}, ip=_ip(request))
    db.commit()
    return {"balance": w.balance, "held": w.held}


@router.get("/ledger")
def global_ledger(limit: int = 500, db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    rows = db.query(CreditLedger).order_by(CreditLedger.created_at.desc()).limit(min(limit, 5000))
    return [{**ledger_view(r), "wallet_id": r.wallet_id} for r in rows]


@router.get("/payments")
def payments(status: str | None = None, db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    rows = db.query(Payment)
    if status:
        rows = rows.filter(Payment.status == status.upper())
    return [{**payment_view(p), "wallet_id": p.wallet_id} for p in rows.order_by(Payment.created_at.desc())]


@router.post("/payments/{pid}/refund")
def refund_payment(pid: str, request: Request, db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    """The pack's unused credits leave the wallet and the payment is marked refunded. With live keys the money is
    returned in the Razorpay dashboard (recorded here); in simulation nothing else happens."""
    p = db.get(Payment, pid)
    if p is None or p.status != "PAID":
        raise err(409, "NOT_REFUNDABLE", "Only paid payments can be refunded.")
    w = db.get(Wallet, p.wallet_id)
    take = min(p.credits, w.balance)
    if take:
        credits.post(db, w, "PAYMENT_REFUND", -take, p.razorpay_payment_id or p.id, ref_type="payment",
                     note="Payment refunded", actor_id=a.id)
    p.status = "REFUNDED"
    audit(db, exam_id=None, teacher_id=a.id, entity_type="payment", entity_id=p.id, action="PAYMENT_REFUNDED",
          new={"credits_removed": take}, ip=_ip(request))
    db.commit()
    return payment_view(p)


# ---------- evaluations monitor ----------
@router.get("/evaluations")
def evaluations(state: str = "ERROR", db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    rows = db.query(Evaluation).filter(Evaluation.run_status == state.upper()).order_by(Evaluation.created_at.desc()).limit(500)
    out = []
    for ev in rows:
        exam = db.get(Exam, ev.exam_id)
        out.append({"id": ev.id, "exam_id": ev.exam_id, "exam": exam.name if exam else None,
                    "workspace_id": exam.workspace_id if exam else None, "run_status": ev.run_status,
                    "status": ev.status, "created_at": ev.created_at.isoformat() if ev.created_at else None})
    return out


@router.post("/evaluations/{ev_id}/retry", status_code=202)
def retry_evaluation(ev_id: str, request: Request, db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    from ..services.evaluation_service import run_evaluation
    from ..services.job_queue import submit
    ev = db.get(Evaluation, ev_id)
    if ev is None:
        raise err(404, "NOT_FOUND", "Evaluation not found.")
    if ev.run_status == "RUNNING":
        raise err(409, "ALREADY_RUNNING", "Evaluation is already running.")
    exam = db.get(Exam, ev.exam_id)
    try:
        credits.hold_evaluation(db, ev, exam, a.id)
    except credits.InsufficientCredits as e:
        raise err(402, "INSUFFICIENT_CREDITS", f"The owner has {e.available} credits; {e.needed} needed.")
    ev.run_status, ev.run_progress = "RUNNING", 0
    audit(db, exam_id=ev.exam_id, teacher_id=a.id, entity_type="evaluation", entity_id=ev.id, action="ADMIN_RETRY",
          ip=_ip(request))
    db.commit()
    submit(ev.exam_id, run_evaluation, ev.id, grading=True)
    return {"run_status": "RUNNING"}


# ---------- disputes and support ----------
@router.get("/disputes")
def disputes(status: str = "OPEN", db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    rows = db.query(Dispute)
    if status != "ALL":
        rows = rows.filter(Dispute.status == status.upper())
    return [{**dispute_view(d), "raised_by": d.raised_by} for d in rows.order_by(Dispute.created_at.desc())]


class ResolveIn(BaseModel):
    status: str  # UPHELD | REJECTED
    resolution: str = Field(min_length=3, max_length=4000)
    refund_credits: int = Field(default=0, ge=0)


@router.post("/disputes/{did}/resolve")
def resolve_dispute(did: str, body: ResolveIn, request: Request, db: Session = Depends(get_db),
                    a: Teacher = Depends(current_admin)):
    d = db.get(Dispute, did)
    if d is None or d.status != "OPEN":
        raise err(409, "NOT_OPEN", "Only open disputes can be resolved.")
    if body.status not in ("UPHELD", "REJECTED"):
        raise err(422, "BAD_STATUS", "Use UPHELD or REJECTED.")
    if body.status == "UPHELD" and body.refund_credits:
        exam = db.get(Exam, db.get(Evaluation, d.evaluation_id).exam_id)
        w = credits.wallet_of_exam(db, exam)
        if w is not None:
            credits.post(db, w, "DISPUTE_REFUND", body.refund_credits, d.id, ref_type="dispute",
                         note="Dispute upheld: credits refunded", actor_id=a.id)
    d.status, d.resolution, d.refund_credits = body.status, body.resolution, body.refund_credits
    d.resolved_by, d.resolved_at = a.id, _now()
    audit(db, exam_id=None, teacher_id=a.id, entity_type="dispute", entity_id=d.id, action=f"DISPUTE_{body.status}",
          ip=_ip(request))
    db.commit()
    return dispute_view(d)


@router.get("/support")
def tickets(status: str = "OPEN", db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    rows = db.query(SupportTicket)
    if status != "ALL":
        rows = rows.filter(SupportTicket.status == status.upper())
    return [{**ticket_view(t), "user_id": t.user_id} for t in rows.order_by(SupportTicket.created_at.desc())]


class ReplyIn(BaseModel):
    reply: str = Field(min_length=1, max_length=8000)
    close: bool = False


@router.post("/support/{tid}/reply")
def reply_ticket(tid: str, body: ReplyIn, db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    t = db.get(SupportTicket, tid)
    if t is None:
        raise err(404, "NOT_FOUND", "Ticket not found.")
    t.reply, t.replied_by, t.status = body.reply, a.id, "CLOSED" if body.close else "ANSWERED"
    audit(db, exam_id=None, teacher_id=a.id, entity_type="support", entity_id=t.id, action="SUPPORT_REPLIED")
    db.commit()
    user = db.get(Teacher, t.user_id)
    if user:
        mailer.send(user.email, f"Re: {t.subject}", "ADEM support replied", [body.reply])
    return ticket_view(t)


# ---------- audit log ----------
@router.get("/audit-logs")
def audit_logs(action: str = "", workspace_id: str = "", actor_id: str = "", limit: int = 500,
               db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    rows = db.query(AuditLog)
    if action:
        rows = rows.filter(AuditLog.action.ilike(f"%{action}%"))
    if workspace_id:
        rows = rows.filter(AuditLog.workspace_id == workspace_id)
    if actor_id:
        rows = rows.filter(AuditLog.teacher_id == actor_id)
    return [{"id": r.id, "action": r.action, "actor_id": r.teacher_id, "workspace_id": r.workspace_id,
             "entity_type": r.entity_type, "entity_id": r.entity_id, "exam_id": r.exam_id, "ip": r.ip,
             "old": r.old_value, "new": r.new_value, "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows.order_by(AuditLog.created_at.desc()).limit(min(limit, 5000))]


# ---------- console users (Super Admin) ----------
@router.get("/console-users")
def console_users(db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    return [{**account_view(u), "admin_role": admin_role(u)} for u in db.query(Teacher).filter_by(role="ADMIN")]


class ConsoleUserIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: str
    admin_role: str = "viewer"


@router.post("/console-users", status_code=201)
def invite_console_user(body: ConsoleUserIn, request: Request, db: Session = Depends(get_db),
                        a: Teacher = Depends(current_super_admin)):
    email = normalize_email(body.email)
    if body.admin_role not in ("super_admin", "admin", "viewer"):
        raise err(422, "BAD_ROLE", "Use super_admin, admin or viewer.")
    if db.query(Teacher).filter_by(email=email).first():
        raise err(409, "EMAIL_TAKEN", "This email already has an account.")
    u = Teacher(name=body.name.strip(), email=email, role="ADMIN", admin_role=body.admin_role, status="invited",
                created_by=a.id)
    db.add(u)
    db.flush()
    raw = issue_link(db, "invite", user_id=u.id)
    audit(db, exam_id=None, teacher_id=a.id, entity_type="user", entity_id=u.id, action="CONSOLE_USER_INVITED",
          new={"admin_role": body.admin_role}, ip=_ip(request))
    db.commit()
    mailer.send(email, "You are invited to the ADEM console", "You are invited",
                [f"Hello {u.name},", f"You were invited to the ADEM admin console as {body.admin_role.replace('_', ' ')}."],
                ("Accept invitation", f"{portal_url('admin')}/accept-invite?token={raw}"))
    return account_view(u)


class ConsoleRoleIn(BaseModel):
    admin_role: str | None = None
    active: bool | None = None


@router.patch("/console-users/{uid}")
def change_console_user(uid: str, body: ConsoleRoleIn, request: Request, db: Session = Depends(get_db),
                        a: Teacher = Depends(current_super_admin)):
    u = _account(db, uid, "ADMIN")
    if u.id == a.id:
        raise err(409, "SELF", "You cannot change your own console role.")
    if body.admin_role is not None:
        if body.admin_role not in ("super_admin", "admin", "viewer"):
            raise err(422, "BAD_ROLE", "Use super_admin, admin or viewer.")
        u.admin_role = body.admin_role
    if body.active is not None:
        u.is_active = body.active
    u.session_version = (u.session_version or 0) + 1  # the change applies at once
    audit(db, exam_id=None, teacher_id=a.id, entity_type="user", entity_id=u.id, action="CONSOLE_USER_CHANGED",
          new=body.model_dump(), ip=_ip(request))
    db.commit()
    return {**account_view(u), "admin_role": admin_role(u)}


@router.get("/settings")
def platform_settings(a: Teacher = Depends(current_admin)):
    """What the platform is configured with (secrets never shown, only whether they are set)."""
    s = get_settings()
    return {"smtp_configured": bool(s.smtp_host), "smtp_from": s.smtp_from, "google_client_id": s.google_client_id or None,
            "razorpay": "live" if s.razorpay_key_id and s.razorpay_key_secret else "simulation",
            "gst_percent": s.gst_percent, "invoice_legal_name": s.invoice_legal_name, "invoice_gstin": s.invoice_gstin,
            "privacy_version": s.privacy_version, "terms_version": s.terms_version}


@router.post("/settings/test-email")
def test_email(a: Teacher = Depends(current_admin)):
    mailer.send(a.email, "ADEM test email", "Email works", ["This is a test email from the ADEM console."])
    return {"ok": True, "sent_to": a.email}


# ---------- paper bank (sample papers until the paper generator passes its quality gate) ----------
class PaperIn(BaseModel):
    exam_id: str
    standard: int
    subject: str = Field(min_length=1, max_length=100)
    units: list[str] = Field(default_factory=list)


@router.get("/papers")
def bank(db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    from ..models import GeneratedPaper
    from .parent import paper_view
    return [{**paper_view(g, db), "exam_id": g.exam_id, "disabled": bool((g.validation or {}).get("disabled"))}
            for g in db.query(GeneratedPaper).order_by(GeneratedPaper.created_at.desc())]


@router.post("/papers", status_code=201)
def add_paper(body: PaperIn, request: Request, db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    """A verified exam (questions and answer key) becomes a sample paper parents can choose."""
    from ..models import AnswerKey, ExamQuestion, GeneratedPaper
    from .parent import paper_view
    exam = db.get(Exam, body.exam_id)
    if exam is None:
        raise err(404, "NOT_FOUND", "Exam not found.")
    if body.standard not in (10, 12):
        raise err(422, "BAD_STANDARD", "Use 10 or 12.")
    qs = db.query(ExamQuestion).filter_by(exam_id=exam.id).count()
    keys = db.query(AnswerKey).filter_by(exam_id=exam.id, is_active=True).count()
    if not qs or keys < qs:
        raise err(409, "NOT_VERIFIED", "The exam needs verified questions and an answer key for every question.")
    g = GeneratedPaper(standard=body.standard, subject=body.subject.strip(), units=body.units, exam_id=exam.id,
                       model="sample", validation={"questions": qs, "keys": keys})
    db.add(g)
    db.flush()
    audit(db, exam_id=exam.id, teacher_id=a.id, entity_type="paper", entity_id=g.id, action="SAMPLE_PAPER_ADDED",
          ip=_ip(request))
    db.commit()
    return paper_view(g, db)


@router.delete("/papers/{gid}")
def disable_paper(gid: str, db: Session = Depends(get_db), a: Teacher = Depends(current_admin)):
    from ..models import GeneratedPaper
    g = db.get(GeneratedPaper, gid)
    if g is None:
        raise err(404, "NOT_FOUND", "Paper not found.")
    g.validation = {**(g.validation or {}), "disabled": True, "exam_id": g.exam_id}
    g.exam_id = None  # parents no longer see it; exams already taken keep their copy
    db.commit()
    return {"ok": True}
