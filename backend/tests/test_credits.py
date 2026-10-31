"""Credits (spec 08): grading holds a sheet's credits, captures them on success and returns them on failure; grading
again is free; packs are bought through Razorpay (simulated without keys) once per payment, with a GST invoice."""
import hashlib
import hmac
import json
import uuid

from app.database import SessionLocal
from app.models import AnswerSheetDocument, CreditLedger, Evaluation, Exam, SchoolClass, Student, Subject, Teacher, Workspace
from app.services import credits


def _school_sheet(balance: int):
    """A school with `balance` credits and one evaluation of one of its exams."""
    db = SessionLocal()
    m = Teacher(name="M", email=f"m{uuid.uuid4().hex[:8]}@x.org", role="MANAGEMENT", password_hash="!x")
    db.add(m)
    db.flush()
    ws = Workspace(kind="SCHOOL", name="Credit school", owner_id=m.id)
    db.add(ws)
    db.flush()
    m.workspace_id = ws.id
    cls = SchoolClass(teacher_id=m.id, name="10-A")
    sub = Subject(teacher_id=m.id, name="Science")
    db.add_all([cls, sub])
    db.flush()
    st = Student(class_id=cls.id, name="Asha", roll_number="1")
    exam = Exam(teacher_id=m.id, class_id=cls.id, subject_id=sub.id, name="T", academic_year="2026-27",
                exam_type="Unit", total_marks=10)
    db.add_all([st, exam])
    db.flush()
    doc = AnswerSheetDocument(exam_id=exam.id, student_id=st.id, original_filename="s.pdf", original_file="s.pdf",
                              mime_type="application/pdf", file_size=1, status="READY")
    db.add(doc)
    db.flush()
    ev = Evaluation(exam_id=exam.id, student_id=st.id, answer_sheet_id=doc.id)
    db.add(ev)
    if balance:
        credits.post(db, credits.wallet_for(db, "school", ws.id), "ADMIN_GRANT", balance, f"grant-{ws.id}")
    db.commit()
    return db, ws, exam, ev


def test_hold_capture_and_free_regrade(client):
    db, ws, exam, ev = _school_sheet(5)
    w = credits.wallet_for(db, "school", ws.id)
    assert credits.quote(db, ev, exam)["credits"] == 1
    credits.hold_evaluation(db, ev, exam)
    db.commit()
    db.refresh(w)
    assert (w.balance, w.held) == (4, 1)
    assert credits.hold_evaluation(db, ev, exam) is None  # a run already holds credits
    credits.settle_evaluation(db, ev.id, success=True)
    db.commit()
    db.refresh(w)
    assert (w.balance, w.held) == (4, 0)
    assert credits.quote(db, ev, exam)["free"] and credits.hold_evaluation(db, ev, exam) is None  # graded again: free
    db.close()


def test_failed_grading_returns_the_credits_and_a_retry_charges_once(client):
    db, ws, exam, ev = _school_sheet(3)
    w = credits.wallet_for(db, "school", ws.id)
    credits.hold_evaluation(db, ev, exam)
    credits.settle_evaluation(db, ev.id, success=False)
    db.commit()
    db.refresh(w)
    assert (w.balance, w.held) == (3, 0)
    credits.hold_evaluation(db, ev, exam)
    credits.settle_evaluation(db, ev.id, success=True)
    db.commit()
    db.refresh(w)
    assert (w.balance, w.held) == (2, 0)
    types = [r.type for r in db.query(CreditLedger).filter_by(wallet_id=w.id).order_by(CreditLedger.created_at)]
    assert types == ["ADMIN_GRANT", "EVAL_HOLD", "EVAL_RELEASE", "EVAL_HOLD", "EVAL_CAPTURE"]
    db.close()


def test_no_credits_no_grading(client):
    db, ws, exam, ev = _school_sheet(0)
    try:
        credits.hold_evaluation(db, ev, exam)
        raise AssertionError("graded without credits")
    except credits.InsufficientCredits as e:
        assert (e.needed, e.available) == (1, 0)
    assert credits.quote(db, ev, exam)["enough"] is False
    db.close()


def test_management_buys_a_pack_once_and_gets_an_invoice(client, auth, teach):
    mine = client.get("/api/credits", headers=auth).json()
    assert mine["can_buy"] is True and client.get("/api/credits", headers=teach).json()["can_buy"] is False
    pack = client.get("/api/public/credit-packs").json()[0]
    assert client.post("/api/credits/order", headers=teach, json={"pack_id": pack["id"]}).status_code == 403
    order = client.post("/api/credits/order", headers=auth, json={"pack_id": pack["id"]}).json()
    assert order["simulation"] is True
    bad = client.post("/api/credits/verify", headers=auth, json={"order_id": order["order_id"], "payment_id": "pay_x",
                                                                  "signature": "forged"})
    assert bad.status_code == 400
    order = client.post("/api/credits/order", headers=auth, json={"pack_id": pack["id"]}).json()
    body = {"order_id": order["order_id"], "payment_id": f"pay_{uuid.uuid4().hex[:10]}", "signature": "simulated"}
    paid = client.post("/api/credits/verify", headers=auth, json=body).json()
    assert paid["status"] == "PAID" and paid["balance"] == mine["balance"] + pack["credits"] and paid["invoice_no"]
    again = client.post("/api/credits/verify", headers=auth, json=body).json()
    assert again["balance"] == paid["balance"]  # verified twice, credited once
    pdf = client.get(f"/api/credits/invoices/{paid['id']}", headers=auth)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_webhook_needs_the_signature(client, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "razorpay_webhook_secret", "whsec")
    body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_1", "order_id": "x"}}}}).encode()
    assert client.post("/api/public/razorpay/webhook", content=body, headers={"x-razorpay-signature": "nope"}).status_code == 400
    sig = hmac.new(b"whsec", body, hashlib.sha256).hexdigest()
    assert client.post("/api/public/razorpay/webhook", content=body, headers={"x-razorpay-signature": sig}).status_code == 200
