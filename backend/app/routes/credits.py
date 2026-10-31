"""Credits for schools and parents (spec 08): balance and ledger, packs, buying a pack through Razorpay (or its
simulation while no keys are set), the payment webhook and GST invoices.

Who owns which wallet: a school's management and teachers see the school wallet, only management buys for it; a
parent sees and buys for their own. Money moves only through services/credits.post, idempotent by reference.
"""
from __future__ import annotations
import hashlib
import hmac
import io
import json
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import err
from ..models import CreditLedger, CreditPack, Payment, Teacher, Wallet, Workspace
from ..security import current_teacher
from ..services import credits
from ..services.audit import audit

router = APIRouter(prefix="/api")

# Placeholders until the business sets them (spec 08): the Platform Admin edits packs in the console
DEFAULT_PACKS = [("Starter", 100, 500.0), ("Standard", 500, 2000.0), ("Large", 1000, 3500.0)]


def ensure_packs(db: Session) -> None:
    if db.query(CreditPack).count() == 0:
        for i, (name, n, price) in enumerate(DEFAULT_PACKS):
            db.add(CreditPack(name=name, credits=n, price_inr=price, sort_order=i))
        db.flush()


def own_wallet(db: Session, t: Teacher) -> Wallet:
    """The wallet of the signed-in account: the school's (management and teachers) or the parent's."""
    ws = db.get(Workspace, t.workspace_id) if t.workspace_id else None
    if t.role == "PARENT":
        return credits.wallet_for(db, "parent", t.id)
    if ws is None or ws.kind != "SCHOOL":
        raise err(404, "NO_WALLET", "This account has no credit wallet.")
    return credits.wallet_for(db, "school", ws.id)


def _buyer(t: Teacher) -> None:
    if t.role not in ("MANAGEMENT", "PARENT"):
        raise err(403, "BUYER_REQUIRED", "School management buys credits for the school.")


def ledger_view(r: CreditLedger) -> dict:
    return {"id": r.id, "type": r.type, "amount": r.amount, "balance_after": r.balance_after, "ref_type": r.ref_type,
            "ref_id": r.ref_id, "note": r.note, "created_at": r.created_at.isoformat() if r.created_at else None}


def pack_view(p: CreditPack) -> dict:
    return {"id": p.id, "name": p.name, "credits": p.credits, "price_inr": p.price_inr, "active": p.active}


def payment_view(p: Payment) -> dict:
    return {"id": p.id, "credits": p.credits, "amount_inr": p.amount_inr, "gst_amount": p.gst_amount, "status": p.status,
            "razorpay_order_id": p.razorpay_order_id, "invoice_no": p.invoice_no,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "paid_at": p.paid_at.isoformat() if p.paid_at else None}


@router.get("/public/credit-packs")
def public_packs(db: Session = Depends(get_db)):
    ensure_packs(db)
    db.commit()
    return [pack_view(p) for p in db.query(CreditPack).filter_by(active=True).order_by(CreditPack.sort_order)]


@router.get("/credits")
def my_credits(db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    w = own_wallet(db, t)
    db.commit()
    rows = db.query(CreditLedger).filter_by(wallet_id=w.id).order_by(CreditLedger.created_at.desc()).limit(50).all()
    return {"balance": w.balance, "held": w.held, "can_buy": t.role in ("MANAGEMENT", "PARENT"),
            "eval_per_sheet": credits.setting(db, "eval_per_sheet"), "paper_fixed": credits.setting(db, "paper_fixed"),
            "low": w.balance < credits.setting(db, "eval_per_sheet") * 10, "ledger": [ledger_view(r) for r in rows]}


@router.get("/credits/ledger")
def my_ledger(limit: int = 200, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    w = own_wallet(db, t)
    rows = db.query(CreditLedger).filter_by(wallet_id=w.id).order_by(CreditLedger.created_at.desc()).limit(min(limit, 1000))
    return [ledger_view(r) for r in rows]


@router.get("/credits/payments")
def my_payments(db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    w = own_wallet(db, t)
    return [payment_view(p) for p in db.query(Payment).filter_by(wallet_id=w.id).order_by(Payment.created_at.desc())]


# ---------- buying a pack ----------
def simulation() -> bool:
    s = get_settings()
    return not (s.razorpay_key_id and s.razorpay_key_secret)


class OrderIn(BaseModel):
    pack_id: str


@router.post("/credits/order", status_code=201)
def create_order(body: OrderIn, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    _buyer(t)
    pack = db.get(CreditPack, body.pack_id)
    if pack is None or not pack.active:
        raise err(404, "NOT_FOUND", "Credit pack not found.")
    w = own_wallet(db, t)
    s = get_settings()
    amount_paise = int(round(pack.price_inr * 100))
    receipt = f"adem-{uuid.uuid4().hex[:16]}"
    if simulation():
        order_id = f"order_sim_{uuid.uuid4().hex[:14]}"
    else:
        try:
            r = httpx.post("https://api.razorpay.com/v1/orders", auth=(s.razorpay_key_id, s.razorpay_key_secret),
                           json={"amount": amount_paise, "currency": "INR", "receipt": receipt}, timeout=20)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise err(502, "PAYMENT_GATEWAY", f"The payment gateway did not respond. Try again. ({e.__class__.__name__})")
        order_id = r.json()["id"]
    gst = round(pack.price_inr - pack.price_inr / (1 + s.gst_percent / 100), 2)
    p = Payment(wallet_id=w.id, pack_id=pack.id, credits=pack.credits, amount_inr=pack.price_inr, gst_amount=gst,
                razorpay_order_id=order_id, created_by=t.id)
    db.add(p)
    db.flush()
    audit(db, exam_id=None, teacher_id=t.id, entity_type="payment", entity_id=p.id, action="PAYMENT_ORDER_CREATED",
          new={"pack": pack.name, "amount_inr": pack.price_inr})
    db.commit()
    return {"payment_id": p.id, "order_id": order_id, "amount_paise": amount_paise, "currency": "INR",
            "key_id": s.razorpay_key_id or None, "simulation": simulation(), "pack": pack_view(pack)}


def _mark_paid(db: Session, p: Payment, payment_id: str) -> Payment:
    """Credit the wallet once for this payment (the webhook and the browser may both report it)."""
    if p.status == "PAID":
        return p
    w = db.get(Wallet, p.wallet_id)
    credits.post(db, w, "PURCHASE", p.credits, payment_id, ref_type="payment", note=f"Bought {p.credits} credits")
    p.status, p.razorpay_payment_id, p.paid_at = "PAID", payment_id, datetime.now(timezone.utc)
    year = p.paid_at.year
    count = db.query(Payment).filter(Payment.invoice_no.like(f"ADEM-{year}-%")).count()
    p.invoice_no = f"ADEM-{year}-{count + 1:05d}"
    return p


class VerifyIn(BaseModel):
    order_id: str
    payment_id: str
    signature: str


@router.post("/credits/verify")
def verify_payment(body: VerifyIn, request: Request, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    p = db.query(Payment).filter_by(razorpay_order_id=body.order_id).first()
    if p is None or p.wallet_id != own_wallet(db, t).id:
        raise err(404, "NOT_FOUND", "Payment not found.")
    if simulation():
        ok = body.order_id.startswith("order_sim_") and body.signature == "simulated"
    else:
        expected = hmac.new(get_settings().razorpay_key_secret.encode(), f"{body.order_id}|{body.payment_id}".encode(),
                            hashlib.sha256).hexdigest()
        ok = hmac.compare_digest(expected, body.signature)
    if not ok:
        p.status = "FAILED" if p.status == "CREATED" else p.status
        db.commit()
        raise err(400, "PAYMENT_UNVERIFIED", "The payment could not be verified. No credits were added.")
    _mark_paid(db, p, body.payment_id)
    audit(db, exam_id=None, teacher_id=t.id, entity_type="payment", entity_id=p.id, action="PAYMENT_PAID",
          new={"credits": p.credits, "invoice": p.invoice_no}, ip=request.client.host if request.client else "")
    db.commit()
    return {**payment_view(p), "balance": db.get(Wallet, p.wallet_id).balance}


@router.post("/public/razorpay/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """payment.captured from Razorpay, checked against the webhook secret. Replays never credit twice."""
    secret = get_settings().razorpay_webhook_secret
    body = await request.body()
    sig = request.headers.get("x-razorpay-signature", "")
    if not secret or not hmac.compare_digest(hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(), sig):
        raise err(400, "BAD_SIGNATURE", "Webhook signature does not match.")
    event = json.loads(body or b"{}")
    entity = (((event.get("payload") or {}).get("payment") or {}).get("entity") or {})
    if event.get("event") == "payment.captured" and entity.get("order_id"):
        p = db.query(Payment).filter_by(razorpay_order_id=entity["order_id"]).first()
        if p is not None:
            _mark_paid(db, p, entity["id"])
            db.commit()
    elif event.get("event") == "payment.failed" and entity.get("order_id"):
        p = db.query(Payment).filter_by(razorpay_order_id=entity["order_id"]).first()
        if p is not None and p.status == "CREATED":
            p.status = "FAILED"
            db.commit()
    return {"ok": True}


# ---------- invoices ----------
def invoice_pdf(db: Session, p: Payment) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib import colors
    s = get_settings()
    w = db.get(Wallet, p.wallet_id)
    if w.owner_type == "school":
        ws = db.get(Workspace, w.owner_id)
        billed = f"{ws.name}<br/>{ws.address or ''} {ws.city or ''} {ws.state or ''}".strip() if ws else "School"
    else:
        u = db.get(Teacher, w.owner_id)
        billed = f"{u.name}<br/>{u.email}" if u else "Parent"
    st = getSampleStyleSheet()
    taxable = round(p.amount_inr - p.gst_amount, 2)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"Invoice {p.invoice_no}")
    rows = [["Description", "Credits", "Amount (INR)"],
            [f"Credit pack ({p.credits} credits)", str(p.credits), f"{taxable:.2f}"],
            [f"GST {s.gst_percent:g}%", "", f"{p.gst_amount:.2f}"],
            ["Total", "", f"{p.amount_inr:.2f}"]]
    table = Table(rows, colWidths=[260, 80, 120])
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                               ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("ALIGN", (1, 0), (-1, -1), "RIGHT")]))
    story = [Paragraph(f"<b>Tax invoice {p.invoice_no}</b>", st["Title"]),
             Paragraph(f"{s.invoice_legal_name}<br/>{s.invoice_address}<br/>GSTIN: {s.invoice_gstin or 'not registered'}", st["Normal"]),
             Spacer(1, 12), Paragraph(f"<b>Billed to</b><br/>{billed}", st["Normal"]), Spacer(1, 12),
             Paragraph(f"Date: {p.paid_at:%d %b %Y} · Payment: {p.razorpay_payment_id}", st["Normal"]), Spacer(1, 12), table]
    doc.build(story)
    return buf.getvalue()


@router.get("/credits/invoices/{payment_id}")
def invoice(payment_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    p = db.get(Payment, payment_id)
    if p is None or p.wallet_id != own_wallet(db, t).id or p.status != "PAID":
        raise err(404, "NOT_FOUND", "Invoice not found.")
    return Response(invoice_pdf(db, p), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{p.invoice_no}.pdf"'})
