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
