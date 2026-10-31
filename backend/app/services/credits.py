"""Credit wallets. Money moves only through CreditLedger rows, written in the same transaction as the wallet change.
(type, ref_id) is unique, so a retried webhook, a double click or a second signup never counts twice."""
from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models import CreditLedger, CreditSetting, Wallet

# Editable by the Platform Admin. One credit evaluates one student's answer sheet, whatever its length or subject.
DEFAULTS = {
    "eval_per_sheet": 1,       # each student answer sheet evaluated
    "paper_fixed": 0,          # parent selects a generated paper (0 = free until decided)
    "signup_school": 10,       # free tier, granted when a school is approved
    "signup_parent": 10,       # free tier, granted when a parent account is created
    "expiry_days": 365,
}


class InsufficientCredits(Exception):
    def __init__(self, needed: int, available: int):
        super().__init__(f"Needs {needed} credits, {available} available.")
        self.needed, self.available = needed, available


def setting(db: Session, key: str) -> float:
    row = db.get(CreditSetting, key)
    return row.value if row else DEFAULTS[key]


def wallet_for(db: Session, owner_type: str, owner_id: str) -> Wallet:
    w = db.query(Wallet).filter_by(owner_type=owner_type, owner_id=owner_id).first()
    if w is None:
        w = Wallet(owner_type=owner_type, owner_id=owner_id)
        db.add(w)
        db.flush()
    return w


def post(db: Session, wallet: Wallet, type_: str, amount: int, ref_id: str, *, ref_type: str = "", note: str = "",
         actor_id: str | None = None, held_change: int = 0) -> CreditLedger:
    """Apply one movement. Returns the existing row if this (type, ref_id) was already posted.
    The caller commits. Raises InsufficientCredits rather than letting the balance go below zero."""
    done = db.query(CreditLedger).filter_by(type=type_, ref_id=ref_id).first()
    if done is not None:
        return done
    # row lock on PostgreSQL; SQLite serialises writers on its own
    w = db.execute(select(Wallet).where(Wallet.id == wallet.id).with_for_update()).scalar_one()
    if w.balance + amount < 0:
        raise InsufficientCredits(-amount, w.balance)
    w.balance += amount
    w.held = max(0, w.held + held_change)
    row = CreditLedger(wallet_id=w.id, type=type_, amount=amount, balance_after=w.balance, ref_type=ref_type,
                       ref_id=ref_id, note=note, actor_id=actor_id)
    db.add(row)
    db.flush()
    return row


def grant_signup_bonus(db: Session, owner_type: str, owner_id: str, phone_key: str) -> None:
    """Free credits once per account, and once per phone number across accounts."""
    amount = int(setting(db, f"signup_{owner_type}"))
    if amount <= 0:
        return
    ref = f"{owner_type}-phone:{phone_key}" if phone_key else f"{owner_type}:{owner_id}"
    post(db, wallet_for(db, owner_type, owner_id), "SIGNUP_BONUS", amount, ref, ref_type=owner_type,
         note="Free signup credits")


# ---------- evaluation charging: hold on start, capture on success, release on failure ----------
def wallet_of_exam(db: Session, exam) -> Wallet | None:
    """The wallet an exam's evaluations are charged to: its school's, or the parent's for a family exam. None for an
    exam outside any workspace (records from before workspaces), which is not charged."""
    from ..models import Workspace
    ws = db.get(Workspace, exam.workspace_id) if getattr(exam, "workspace_id", None) else None
    if ws is None:
        return None
    return wallet_for(db, "parent", ws.owner_id) if ws.kind == "FAMILY" else wallet_for(db, "school", ws.id)


def _holds(db: Session, ev_id: str) -> list[CreditLedger]:
    return db.query(CreditLedger).filter(CreditLedger.type == "EVAL_HOLD", CreditLedger.ref_id.like(f"{ev_id}#%")).all()


def _settled(db: Session, hold: CreditLedger) -> bool:
    return db.query(CreditLedger).filter(CreditLedger.ref_id == hold.ref_id,
                                         CreditLedger.type.in_(("EVAL_CAPTURE", "EVAL_RELEASE"))).first() is not None


def evaluation_cost(db: Session, ev) -> int:
    return int(setting(db, "eval_per_sheet"))


def is_charged(db: Session, ev) -> bool:
    """The sheet was paid for already: grading it again (after a teacher's correction, a retry) is free."""
    return any(db.query(CreditLedger).filter_by(type="EVAL_CAPTURE", ref_id=h.ref_id).first() for h in _holds(db, ev.id))


def quote(db: Session, ev, exam) -> dict:
    wallet = wallet_of_exam(db, exam)
    free = wallet is None or is_charged(db, ev)
    cost = 0 if free else evaluation_cost(db, ev)
    balance = wallet.balance if wallet else None
    return {"credits": cost, "free": free, "balance": balance, "enough": free or (balance or 0) >= cost,
            "reason": "Already paid: grading again is free." if wallet and free else
                      ("Not charged." if wallet is None else f"{cost} credit(s) per answer sheet.")}


def hold_evaluation(db: Session, ev, exam, actor_id: str | None = None) -> CreditLedger | None:
    """Reserve the sheet's credits before a full grading run. None when it costs nothing (paid already, no wallet,
    or a hold is still open). Raises InsufficientCredits. The caller commits."""
    wallet = wallet_of_exam(db, exam)
    if wallet is None or is_charged(db, ev):
        return None
    holds = _holds(db, ev.id)
    if any(not _settled(db, h) for h in holds):
        return None  # a run already holds credits for this sheet
    cost = evaluation_cost(db, ev)
    if cost <= 0:
        return None
    return post(db, wallet, "EVAL_HOLD", -cost, f"{ev.id}#{len(holds) + 1}", ref_type="evaluation",
                note="Credits held while the answer sheet is graded", actor_id=actor_id, held_change=cost)


def settle_evaluation(db: Session, ev_id: str, success: bool) -> None:
    """Capture the open hold when grading succeeded, give the credits back when it failed. Nothing to do without an
    open hold (a free re-grade). The caller commits."""
    for h in _holds(db, ev_id):
        if _settled(db, h):
            continue
        wallet = db.get(Wallet, h.wallet_id)
        if success:
            post(db, wallet, "EVAL_CAPTURE", 0, h.ref_id, ref_type="evaluation", note="Answer sheet graded",
                 held_change=h.amount)  # h.amount is negative: the hold leaves "held"
        else:
            post(db, wallet, "EVAL_RELEASE", -h.amount, h.ref_id, ref_type="evaluation",
                 note="Grading failed: credits returned", held_change=h.amount)
