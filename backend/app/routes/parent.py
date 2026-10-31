"""The parent portal (spec 6.4, 07): children, the paper bank, timed exams and their reports.

A parent's exam is an ordinary exam in the family workspace (origin PARENT), copied from a paper in the bank with its
questions and locked key, so the evaluation pipeline grades it as it grades a school's. All times are the server's:
start sets ends_at and upload_closes_at; every read moves the state on (IN_PROGRESS -> AWAITING_UPLOAD -> MISSED,
EVALUATING -> COMPLETED / FAILED). Pages are served only while the exam runs, watermarked; the key never leaves the
server.
"""
from __future__ import annotations
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import err
from ..documents.storage import abs_path, read_validated_upload
from ..models import (AnswerKey, AnswerSheetDocument, Child, Evaluation, EvaluationItem, Exam, ExamQuestion,
                      GeneratedPaper, ParentExam, QuestionPaperDocument, SchoolClass, Student, Subject, Teacher)
from ..security import current_parent
from ..services import credits, quality
from ..services.audit import audit

router = APIRouter(prefix="/api/parent")
UPLOAD_WINDOW = timedelta(hours=1)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


# ---------- children ----------
class ChildIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    standard: int
    subjects: list[str] = Field(default_factory=list)


def child_view(c: Child) -> dict:
    return {"id": c.id, "name": c.name, "standard": c.standard, "subjects": c.subjects or [],
            "created_at": c.created_at.isoformat() if c.created_at else None}


def _child(db: Session, p: Teacher, cid: str) -> Child:
    c = db.get(Child, cid)
    if c is None or c.parent_id != p.id:
        raise err(404, "NOT_FOUND", "Child not found.")
    return c


@router.get("/children")
def children(db: Session = Depends(get_db), p: Teacher = Depends(current_parent)):
    return [child_view(c) for c in db.query(Child).filter_by(parent_id=p.id).order_by(Child.created_at)]


@router.post("/children", status_code=201)
def add_child(body: ChildIn, db: Session = Depends(get_db), p: Teacher = Depends(current_parent)):
    if body.standard not in (10, 12):
        raise err(422, "BAD_STANDARD", "Choose Class 10 or Class 12.")
    # the class and student rows the pipeline grades this child's sheets against
    cls = SchoolClass(teacher_id=p.id, workspace_id=p.workspace_id, name=f"{body.standard}")
    db.add(cls)
    db.flush()
    st = Student(class_id=cls.id, name=body.name.strip(), roll_number="1")
    db.add(st)
    db.flush()
    c = Child(parent_id=p.id, name=body.name.strip(), standard=body.standard, subjects=body.subjects,
              class_id=cls.id, student_id=st.id)
    db.add(c)
    db.flush()
    audit(db, exam_id=None, teacher_id=p.id, entity_type="child", entity_id=c.id, action="CHILD_ADDED")
    db.commit()
    return child_view(c)


@router.patch("/children/{cid}")
def edit_child(cid: str, body: ChildIn, db: Session = Depends(get_db), p: Teacher = Depends(current_parent)):
    c = _child(db, p, cid)
    if body.standard not in (10, 12):
        raise err(422, "BAD_STANDARD", "Choose Class 10 or Class 12.")
    c.name, c.standard, c.subjects = body.name.strip(), body.standard, body.subjects
    if c.student_id and (st := db.get(Student, c.student_id)):
        st.name = c.name
    db.commit()
    return child_view(c)


@router.delete("/children/{cid}")
def remove_child(cid: str, db: Session = Depends(get_db), p: Teacher = Depends(current_parent)):
    c = _child(db, p, cid)
    if db.query(ParentExam).filter_by(child_id=c.id).filter(ParentExam.status.in_(("IN_PROGRESS", "EVALUATING"))).first():
        raise err(409, "EXAM_RUNNING", "Wait until this child's running exam is finished.")
    db.delete(c)
    db.commit()
    return {"ok": True}


# ---------- the paper bank ----------
def paper_view(g: GeneratedPaper, db: Session) -> dict:
    exam = db.get(Exam, g.exam_id) if g.exam_id else None
    return {"id": g.id, "standard": g.standard, "subject": g.subject, "units": g.units or [], "source": g.model or "sample",
            "total_marks": exam.total_marks if exam else None, "duration_minutes": (exam.duration_minutes if exam else None) or 180,
            "questions": db.query(ExamQuestion).filter_by(exam_id=g.exam_id).count() if exam else 0}


@router.get("/papers")
def papers(standard: int | None = None, subject: str = "", db: Session = Depends(get_db),
           p: Teacher = Depends(current_parent)):
    rows = db.query(GeneratedPaper).filter(GeneratedPaper.exam_id.isnot(None))
    if standard:
        rows = rows.filter(GeneratedPaper.standard == standard)
    if subject:
        rows = rows.filter(GeneratedPaper.subject.ilike(f"%{subject}%"))
    return {"papers": [paper_view(g, db) for g in rows.order_by(GeneratedPaper.created_at.desc())],
            "paper_charge": int(credits.setting(db, "paper_fixed"))}


def _copy_rows(db: Session, model, rows, **overrides) -> dict:
    """Copies of rows (new ids); returns old id -> new row."""
    out = {}
    cols = [c.key for c in model.__table__.columns if c.key not in ("id",)]
    for r in rows:
        data = {k: getattr(r, k) for k in cols}
        data.update(overrides)
        new = model(**data)
        db.add(new)
        out[r.id] = new
    db.flush()
    return out


class SelectIn(BaseModel):
    child_id: str
    paper_id: str


@router.post("/exams", status_code=201)
def select_paper(body: SelectIn, db: Session = Depends(get_db), p: Teacher = Depends(current_parent)):
    """The parent picks a paper for a child: its fixed charge is taken and the paper and its locked key are copied
    into an exam of the family (spec 07 "Select paper")."""
    c = _child(db, p, body.child_id)
    paper = db.get(GeneratedPaper, body.paper_id)
    template = db.get(Exam, paper.exam_id) if paper and paper.exam_id else None
    if template is None:
        raise err(404, "NOT_FOUND", "Paper not found.")
    if paper.standard != c.standard:
        raise err(409, "WRONG_STANDARD", f"This paper is for Class {paper.standard}.")
    subject = db.query(Subject).filter_by(teacher_id=p.id, name=paper.subject).first()
    if subject is None:
        subject = Subject(teacher_id=p.id, workspace_id=p.workspace_id, name=paper.subject)
        db.add(subject)
        db.flush()
    exam = Exam(teacher_id=p.id, workspace_id=p.workspace_id, class_id=c.class_id, subject_id=subject.id,
                name=f"{paper.subject} practice", academic_year=template.academic_year, exam_type="Practice",
                total_marks=template.total_marks, duration_minutes=template.duration_minutes or 180,
                status="ANSWER_KEY_VERIFIED", origin="PARENT")
    db.add(exam)
    db.flush()
    qmap = _copy_rows(db, ExamQuestion, db.query(ExamQuestion).filter_by(exam_id=template.id), exam_id=exam.id,
                      document_id=None)
    for k in db.query(AnswerKey).filter_by(exam_id=template.id, is_active=True):
        data = {col.key: getattr(k, col.key) for col in AnswerKey.__table__.columns if col.key != "id"}
        data.update(exam_id=exam.id, document_id=None,
                    exam_question_id=qmap[k.exam_question_id].id if k.exam_question_id in qmap else None)
        db.add(AnswerKey(**data))
    pe = ParentExam(child_id=c.id, paper_id=paper.id, exam_id=exam.id, duration_minutes=exam.duration_minutes)
    db.add(pe)
    db.flush()
    charge = int(credits.setting(db, "paper_fixed"))
    if charge:
        try:
            credits.post(db, credits.wallet_for(db, "parent", p.id), "PAPER_CHARGE", -charge, pe.id,
                         ref_type="parent_exam", note=f"{paper.subject} paper", actor_id=p.id)
        except credits.InsufficientCredits as e:
            db.rollback()
            raise err(402, "INSUFFICIENT_CREDITS", f"Choosing a paper costs {e.needed} credits; you have {e.available}. "
                      "Buy credits to continue.")
        pe.credits_paper = charge
    audit(db, exam_id=exam.id, teacher_id=p.id, entity_type="parent_exam", entity_id=pe.id, action="PAPER_SELECTED")
    db.commit()
    return exam_view(db, pe)


# ---------- the exam ----------
def advance(db: Session, pe: ParentExam) -> ParentExam:
    """Move the exam on by the server's clock and the evaluation's outcome."""
    now = _now()
    if pe.status == "IN_PROGRESS" and now >= _aware(pe.ends_at):
        pe.status = "AWAITING_UPLOAD"
    if pe.status == "AWAITING_UPLOAD" and now >= _aware(pe.upload_closes_at) and not pe.uploaded_at:
        pe.status = "MISSED"
    if pe.status == "EVALUATING" and pe.evaluation_id:
        ev = db.get(Evaluation, pe.evaluation_id)
        doc = db.get(AnswerSheetDocument, ev.answer_sheet_id) if ev else None
        if ev and ev.run_status == "DONE":
            pe.status = "COMPLETED"
        elif (ev and ev.run_status == "ERROR") or (doc and doc.status in ("FAILED", "AI_ERROR")):
            pe.status = "FAILED"
    return pe


def exam_view(db: Session, pe: ParentExam) -> dict:
    exam = db.get(Exam, pe.exam_id)
    paper = db.get(GeneratedPaper, pe.paper_id)
    doc = db.query(QuestionPaperDocument).filter_by(exam_id=paper.exam_id, is_active=True).first() if paper else None
    return {"id": pe.id, "child_id": pe.child_id, "status": pe.status, "subject": paper.subject if paper else None,
            "standard": paper.standard if paper else None, "units": paper.units if paper else [],
            "total_marks": exam.total_marks if exam else None, "duration_minutes": pe.duration_minutes,
            "pages": len(doc.pages or []) if doc else 0, "server_time": _now().isoformat(),
            "started_at": _aware(pe.started_at).isoformat() if pe.started_at else None,
            "ends_at": _aware(pe.ends_at).isoformat() if pe.ends_at else None,
            "upload_closes_at": _aware(pe.upload_closes_at).isoformat() if pe.upload_closes_at else None,
            "uploaded_at": _aware(pe.uploaded_at).isoformat() if pe.uploaded_at else None,
            "credits_paper": pe.credits_paper, "credits_eval": pe.credits_eval,
            "evaluation_id": pe.evaluation_id}


def _exam(db: Session, p: Teacher, eid: str) -> ParentExam:
    pe = db.get(ParentExam, eid)
    if pe is None or db.get(Child, pe.child_id).parent_id != p.id:
        raise err(404, "NOT_FOUND", "Exam not found.")
    advance(db, pe)
    db.commit()
    return pe


@router.get("/exams")
def exams(child_id: str | None = None, db: Session = Depends(get_db), p: Teacher = Depends(current_parent)):
    kids = [c.id for c in db.query(Child).filter_by(parent_id=p.id)]
    rows = db.query(ParentExam).filter(ParentExam.child_id.in_(kids or [""]))
    if child_id:
        rows = rows.filter(ParentExam.child_id == child_id)
    out = [exam_view(db, advance(db, pe)) for pe in rows.order_by(ParentExam.selected_at.desc())]
    db.commit()
    return out


@router.get("/exams/{eid}")
def exam_state(eid: str, db: Session = Depends(get_db), p: Teacher = Depends(current_parent)):
    return exam_view(db, _exam(db, p, eid))


@router.post("/exams/{eid}/start")
def start(eid: str, db: Session = Depends(get_db), p: Teacher = Depends(current_parent)):
    pe = _exam(db, p, eid)
    if pe.status != "PAPER_SELECTED":
        raise err(409, "ALREADY_STARTED", "This exam has already started.")
    pe.started_at = _now()
    pe.ends_at = pe.started_at + timedelta(minutes=pe.duration_minutes)
    pe.upload_closes_at = pe.ends_at + UPLOAD_WINDOW
    pe.status = "IN_PROGRESS"
    audit(db, exam_id=pe.exam_id, teacher_id=p.id, entity_type="parent_exam", entity_id=pe.id, action="EXAM_STARTED")
    db.commit()
    return exam_view(db, pe)


@router.get("/exams/{eid}/pages/{n}")
def page(eid: str, n: int, db: Session = Depends(get_db), p: Teacher = Depends(current_parent)):
    """Page n of the paper as an image, watermarked with the parent's email and the exam id; only while it runs."""
    from PIL import Image, ImageDraw
    pe = _exam(db, p, eid)
    if pe.status != "IN_PROGRESS":
        raise err(403, "EXAM_NOT_RUNNING", "The paper is shown only while the exam is running.")
    paper = db.get(GeneratedPaper, pe.paper_id)
    doc = db.query(QuestionPaperDocument).filter_by(exam_id=paper.exam_id, is_active=True).first()
    pages = sorted(doc.pages or [], key=lambda x: x["page_number"]) if doc else []
    if not 1 <= n <= len(pages):
        raise err(404, "NOT_FOUND", "Page not found.")
    img = Image.open(abs_path(pages[n - 1]["processed_file"])).convert("RGB")
    draw = ImageDraw.Draw(img)
    mark = f"{p.email} · {pe.id[:8]}"
    for y in range(80, img.height, max(240, img.height // 6)):
        draw.text((40, y), mark, fill=(200, 200, 200))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/exams/{eid}/quote")
def exam_quote(eid: str, db: Session = Depends(get_db), p: Teacher = Depends(current_parent)):
    pe = _exam(db, p, eid)
    w = credits.wallet_for(db, "parent", p.id)
    db.commit()
    cost = int(credits.setting(db, "eval_per_sheet"))
    return {"credits": cost, "balance": w.balance, "enough": w.balance >= cost, "status": pe.status}


@router.post("/exams/{eid}/upload", status_code=202)
async def upload(eid: str, bg: BackgroundTasks, files: list[UploadFile] = File(...), db: Session = Depends(get_db),
                 p: Teacher = Depends(current_parent)):
    """The child's sheet: photos or PDFs, in order, checked for quality before anything is charged, merged into one
    PDF and graded (the sheet's credits are held when grading starts)."""
    from ..services.job_queue import submit
    from ..services.pipeline import process_document
    from .documents import _save
    pe = _exam(db, p, eid)
    if pe.status not in ("IN_PROGRESS", "AWAITING_UPLOAD"):
        raise err(409, "UPLOAD_CLOSED", "The upload window has closed." if pe.status == "MISSED"
                  else "This exam cannot take an answer sheet now.")
    if not files:
        raise err(400, "NO_FILES", "Add the photos or PDF of the answer sheet.")
    parts, problems = [], []
    for i, f in enumerate(files, 1):
        data, ext, _ = await read_validated_upload(f, {"pdf", "png", "jpg", "jpeg"})
        try:
            for r in quality.check(data, ext):
                problems += [{"file": i, "page": r["page"], "problem": x} for x in r["problems"]]
        except ValueError as e:
            problems.append({"file": i, "page": 1, "problem": str(e)})
        parts.append((data, ext))
    if problems:
        raise err(422, "QUALITY_CHECK_FAILED", "Some pages need to be retaken.", issues=[
            {"question": f"File {x['file']}, page {x['page']}", "reason": x["problem"]} for x in problems])
    merged = quality.merge_to_pdf(parts)
    c = db.get(Child, pe.child_id)
    doc = _save(db, "answer-sheet", pe.exam_id, merged, "pdf", "application/pdf", "answer-sheet.pdf", student_id=c.student_id)
    db.flush()
    ev = Evaluation(exam_id=pe.exam_id, student_id=c.student_id, answer_sheet_id=doc.id, status="DRAFT")
    db.add(ev)
    db.flush()
    pe.uploaded_at, pe.evaluation_id, pe.status = _now(), ev.id, "EVALUATING"
    import pymupdf
    pe.pages = pymupdf.open(stream=merged, filetype="pdf").page_count
    pe.credits_eval = int(credits.setting(db, "eval_per_sheet"))
    audit(db, exam_id=pe.exam_id, teacher_id=p.id, entity_type="parent_exam", entity_id=pe.id, action="SHEET_UPLOADED",
          new={"pages": pe.pages})
    db.commit()
    bg.add_task(submit, pe.exam_id, process_document, "answer-sheet", doc.id)
    return exam_view(db, pe)


@router.get("/exams/{eid}/report")
def report(eid: str, db: Session = Depends(get_db), p: Teacher = Depends(current_parent)):
    """Score and per-question marks with the grader's feedback; the key and model answers are never shown."""
    pe = _exam(db, p, eid)
    if pe.status != "COMPLETED":
        raise err(409, "NOT_READY", "The report is ready once the sheet is graded.")
    ev = db.get(Evaluation, pe.evaluation_id)
    rows = []
    for it in db.query(EvaluationItem).filter_by(evaluation_id=ev.id):
        q = db.get(ExamQuestion, it.exam_question_id)
        rows.append({"question": q.display_number if q else None, "max_marks": q.max_marks if q else None,
                     "marks": it.final_marks, "feedback": it.ai_feedback, "position": q.position if q else 0})
    rows.sort(key=lambda r: r["position"] or 0)
    got = sum(r["marks"] or 0 for r in rows)
    exam = db.get(Exam, pe.exam_id)
    return {"exam": exam_view(db, pe), "score": got, "max": exam.total_marks,
            "percentage": round(100 * got / exam.total_marks, 1) if exam.total_marks else None,
            "questions": [{k: v for k, v in r.items() if k != "position"} for r in rows],
            "weak": [r["question"] for r in rows if r["max_marks"] and (r["marks"] or 0) < r["max_marks"] / 2]}


# ---------- data rights ----------
@router.post("/delete-my-data")
def delete_my_data(db: Session = Depends(get_db), p: Teacher = Depends(current_parent)):
    """The parent's children, their exams and sheets are removed and the account closed (spec 6.4). The ledger and
    payments stay: money records are kept for accounting."""
    from ..models import Workspace
    for c in db.query(Child).filter_by(parent_id=p.id):
        db.query(ParentExam).filter_by(child_id=c.id).delete()
        db.delete(c)
    for e in db.query(Exam).filter_by(workspace_id=p.workspace_id):
        db.delete(e)
    audit(db, exam_id=None, teacher_id=p.id, entity_type="user", entity_id=p.id, action="DELETE_MY_DATA")
    p.is_active, p.session_version = False, (p.session_version or 0) + 1
    p.name, p.phone, p.profile = "Deleted parent", "", None
    p.email = f"deleted-{p.id}@deleted.invalid"
    p.google_sub = None
    if (ws := db.get(Workspace, p.workspace_id)) is not None:
        ws.is_active, ws.name = False, "Deleted family"
    db.commit()
    return {"ok": True, "message": "Your data has been deleted and your account closed."}
