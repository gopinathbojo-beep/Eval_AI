"""Uploader codes: a 6-character login that may only upload answer sheets to one exam.

The school creates one code per uploader once the exam is finalized for evaluation. A code stops working when the
school deletes or regenerates it, or when the exam is closed (FINALIZED)."""

import secrets
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, Response, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import err, get_exam
from ..login_limiter import login_limiter
from ..models import AnswerSheetDocument, Exam, Teacher, UploaderCode, Workspace
from ..security import ALGO, create_token, require_browser_request
from ..services.job_queue import submit
from .management import management

router = APIRouter(prefix="/api")
_bearer = HTTPBearer(auto_error=False)
UPLOADER_COOKIE = "eval_uploader"
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I, so a code read aloud is not mistyped
OPEN_STATES = ("READY_FOR_EVALUATION", "EVALUATING", "REVIEW_REQUIRED")
SCOPE = "uploader"


def _new_code(db: Session) -> str:
    """6 characters mixing letters and digits (always at least one of each)."""
    while True:
        code = "".join(secrets.choice(ALPHABET) for _ in range(6))
        if not (any(c.isdigit() for c in code) and any(c.isalpha() for c in code)):
            continue
        if not db.query(UploaderCode).filter_by(code=code).first():
            return code


def _code_view(c: UploaderCode, db: Session) -> dict:
    return {"id": c.id, "code": c.code, "label": c.label, "uploader_name": c.uploader_name, "is_active": c.is_active,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "uploads": db.query(AnswerSheetDocument).filter_by(uploaded_by_code=c.id).count()}


# ---------- school side ----------
class CodesIn(BaseModel):
    labels: list[str] = Field(default_factory=list, max_length=50)  # one code per label ("Room 4", "Mr. Kumar")
    count: int = Field(0, ge=0, le=50)  # or this many unlabelled codes


def _school_code(db: Session, user: Teacher, code_id: str) -> UploaderCode:
    c = db.get(UploaderCode, code_id)
    if c is None or c.workspace_id != user.workspace_id:
        raise err(404, "NOT_FOUND", "Uploader code not found.")
    return c


@router.get("/exams/{exam_id}/uploader-codes")
def list_codes(exam_id: str, db: Session = Depends(get_db), user: Teacher = Depends(management)):
    exam = get_exam(db, user, exam_id)
    rows = db.query(UploaderCode).filter_by(exam_id=exam.id, is_active=True).order_by(UploaderCode.created_at)
    return [_code_view(c, db) for c in rows]


@router.post("/exams/{exam_id}/uploader-codes", status_code=201)
def create_codes(exam_id: str, body: CodesIn, db: Session = Depends(get_db), user: Teacher = Depends(management)):
    exam = get_exam(db, user, exam_id)
    if exam.status not in OPEN_STATES:
        raise err(409, "EXAM_NOT_OPEN", "Finalize the exam setup before creating uploader codes."
                  if exam.status != "FINALIZED" else "This exam is closed.")
    labels = [label.strip()[:100] or None for label in body.labels] or [None] * (body.count or 1)
    rows = [UploaderCode(exam_id=exam.id, workspace_id=user.workspace_id, code=_new_code(db), label=label)
            for label in labels]
    db.add_all(rows)
    db.commit()
    return [_code_view(c, db) for c in rows]


@router.post("/uploader-codes/{code_id}/regenerate")
def regenerate_code(code_id: str, db: Session = Depends(get_db), user: Teacher = Depends(management)):
    c = _school_code(db, user, code_id)
    c.code = _new_code(db)  # the old code stops working at once; uploads it sent stay linked to this row
    db.commit()
    return _code_view(c, db)


@router.delete("/uploader-codes/{code_id}", status_code=204)
def delete_code(code_id: str, db: Session = Depends(get_db), user: Teacher = Depends(management)):
    c = _school_code(db, user, code_id)
    c.is_active, c.revoked_at = False, datetime.now(timezone.utc)
    db.commit()


# ---------- uploader side ----------
class CodeLoginIn(BaseModel):
    code: str = Field(min_length=6, max_length=12)


def _open_code(db: Session, code_id: str | None) -> tuple[UploaderCode, Exam]:
    c = db.get(UploaderCode, code_id) if code_id else None
    exam = db.get(Exam, c.exam_id) if c else None
    ws = db.get(Workspace, c.workspace_id) if c else None
    if not c or not c.is_active or not exam or not ws or not ws.is_active:
        raise err(401, "CODE_INVALID", "This uploader code is not valid.")
    if exam.status not in OPEN_STATES:
        raise err(401, "EXAM_CLOSED", "This exam is closed for uploads.")
    return c, exam


@router.post("/auth/code-login")
def code_login(body: CodeLoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    require_browser_request(request)
    login_limiter.check(f"code:{request.client.host if request.client else 'unknown'}",
                        get_settings().login_attempts_per_minute)
    c = db.query(UploaderCode).filter_by(code=body.code.strip().upper().replace(" ", "")).first()
    if c is None:  # wrong codes from every address together: the IP can be faked through X-Forwarded-For
        login_limiter.check("code:failed", 60)
    _, exam = _open_code(db, c.id if c else None)
    # the token names the code and the code string, so regenerating the code ends this session
    token = create_token(c.id, 0, scope=f"{SCOPE}:{c.code}")
    s = get_settings()
    response.set_cookie(UPLOADER_COOKIE, token, max_age=s.access_token_minutes * 60,
                        httponly=True, secure=s.cookie_secure, samesite="strict", path="/api")
    return {"exam": _exam_view(exam)}


@router.post("/auth/code-logout", status_code=204)
def code_logout(response: Response):
    response.delete_cookie(UPLOADER_COOKIE, path="/api")


def current_uploader(request: Request, cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
                     db: Session = Depends(get_db)) -> tuple[UploaderCode, Exam]:
    raw = cred.credentials if cred else request.cookies.get(UPLOADER_COOKIE)
    if not raw:
        raise err(401, "UNAUTHENTICATED", "Enter your uploader code.")
    if not cred and request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_browser_request(request)
    try:
        payload = jwt.decode(raw, get_settings().jwt_secret, algorithms=[ALGO])
    except jwt.PyJWTError:
        raise err(401, "UNAUTHENTICATED", "Enter your uploader code.")
    scope, _, code = str(payload.get("scope") or "").partition(":")
    if scope != SCOPE:
        raise err(401, "UNAUTHENTICATED", "Enter your uploader code.")
    c, exam = _open_code(db, payload.get("sub"))
    if c.code != code:
        raise err(401, "CODE_INVALID", "This uploader code was replaced. Ask the school for the new one.")
    return c, exam


def _exam_view(exam: Exam) -> dict:
    return {"id": exam.id, "name": exam.name, "class_name": exam.school_class.name if exam.school_class else None,
            "subject": exam.subject.name if exam.subject else None, "exam_date": exam.exam_date}


@router.get("/uploader/me")
def uploader_me(ctx=Depends(current_uploader), db: Session = Depends(get_db)):
    c, exam = ctx
    docs = (db.query(AnswerSheetDocument).filter_by(uploaded_by_code=c.id, is_active=True)
            .order_by(AnswerSheetDocument.uploaded_at.desc()).limit(500))
    # status only: an uploader never sees marks
    return {"exam": _exam_view(exam), "label": c.label, "uploader_name": c.uploader_name,
            "uploads": [_upload_view(d) for d in docs]}


@router.get("/uploader/papers")
def uploader_papers(ctx=Depends(current_uploader), db: Session = Depends(get_db)):
    """Papers tab: every answer sheet saved for this exam (any uploader or the school), by roll number.
    Status only, never marks. Sheets other uploaders are still scanning are left out."""
    from ..models import Student
    c, exam = ctx
    docs = (db.query(AnswerSheetDocument).filter_by(exam_id=exam.id, is_active=True)
            .order_by(AnswerSheetDocument.uploaded_at.desc()).limit(2000).all())
    codes = {x.id: x for x in db.query(UploaderCode).filter_by(exam_id=exam.id)}
    rows = []
    for d in docs:
        if d.status == "CAPTURING" and d.uploaded_by_code != c.id:
            continue
        st = db.get(Student, d.student_id) if d.student_id else None
        by = codes.get(d.uploaded_by_code)
        rows.append({**_upload_view(d), "roll_number": st.roll_number if st else (d.identity or {}).get("typed_roll"),
                     "mine": d.uploaded_by_code == c.id,
                     "uploaded_by": (by.uploader_name or by.label or "Uploader") if by else "School"})
    rows.sort(key=lambda r: (str(r["roll_number"] or "~").zfill(12)))
    return {"papers": rows}


def _upload_view(d: AnswerSheetDocument) -> dict:
    from ..services.sheet_capture import page_files
    ident = d.identity or {}
    pages = len(page_files(d)) if d.status == "CAPTURING" else (len(d.pages or []) or ident.get("captured") or 0)
    return {"id": d.id, "original_filename": d.original_filename, "status": d.status, "stage": d.stage,
            "uploaded_at": d.uploaded_at.isoformat(), "pages": pages, "roll_number": ident.get("typed_roll"),
            "note": ident.get("note") if ident.get("match") == "HOLD" else None}


async def _pages_to_pdf(files: list[UploadFile]) -> UploadFile:
    """Phone photos of one student's sheet (one per page, in order) as a single PDF, so they become one answer sheet."""
    import io
    import fitz
    from starlette.datastructures import Headers
    from ..documents.storage import read_validated_upload
    if len(files) > MAX_PAGES:
        raise err(400, "TOO_MANY_PAGES", f"Send at most {MAX_PAGES} pages for one answer sheet.")
    pdf = fitz.open()
    for f in files:
        data, ext, _ = await read_validated_upload(f, {"png", "jpg", "jpeg"})
        img = fitz.open(stream=data, filetype=ext)
        pdf.insert_pdf(fitz.open("pdf", img.convert_to_pdf()))
    return UploadFile(io.BytesIO(pdf.tobytes()), filename="answer-sheet.pdf",
                      headers=Headers({"content-type": "application/pdf"}))


MAX_PAGES = 60


class UploaderNameIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


@router.put("/uploader/name")
def set_uploader_name(body: UploaderNameIn, ctx=Depends(current_uploader), db: Session = Depends(get_db)):
    """Who is using this code; the school sees it next to the code."""
    from .. import validation as valid
    try:
        name = valid.person_name(body.name, "Your name")
    except ValueError as e:
        raise err(400, "INVALID_NAME", str(e))
    c, _ = ctx
    c.uploader_name = name
    db.commit()
    return {"uploader_name": name}


@router.post("/uploader/answer-sheets", status_code=202)
async def uploader_upload(bg: BackgroundTasks, files: list[UploadFile] = File(...), one_sheet: bool = Form(False),
                          roll_number: str = Form("", max_length=50),
                          ctx=Depends(current_uploader), db: Session = Depends(get_db)):
    """One student's sheet: a file, or with one_sheet its photographed pages. A typed roll number decides the
    student; without one (uploaded files) the roll number is read from the sheet's details page."""
    c, exam = ctx
    ws = db.get(Workspace, c.workspace_id)
    owner = db.get(Teacher, ws.owner_id)  # sheets are processed as the school, the code only delivers them
    exam = get_exam(db, owner, exam.id)
    if one_sheet:
        files = [await _pages_to_pdf(files)]
    roll = roll_number.strip()
    if not roll:
        if len(files) != 1:
            raise err(400, "ONE_SHEET", "Send one student's sheet at a time, or use Bulk upload for many.")
        from .answer_sheets import _save_unassigned
        from ..services.student_identity import identify_sheets
        docs = await _save_unassigned(db, owner, exam, files)
        docs[0].uploaded_by_code = c.id
        db.commit()
        bg.add_task(submit, exam.id, identify_sheets, [docs[0].id], owner.id)
        return {"uploaded": 1, "roll_number": None}
    if len(files) != 1:
        raise err(400, "ONE_SHEET_PER_ROLL", "A roll number belongs to one answer sheet. Send one sheet at a time.")
    from ..models import Student
    from .answer_sheets import upload_answer_sheet
    known = db.query(Student).filter_by(class_id=exam.class_id, roll_number=roll).first()
    # saved under the typed roll number, then read AND graded
    result = await upload_answer_sheet(exam.id, BackgroundTasks(), files[0], None,
                                       known.name if known else f"Roll {roll}", roll, db, owner)
    doc = db.get(AnswerSheetDocument, result["document"]["id"])
    doc.uploaded_by_code = c.id
    db.commit()
    from ..services.student_identity import run_sheet
    bg.add_task(submit, exam.id, run_sheet, doc.id)
    return {"uploaded": 1, "roll_number": roll}


@router.post("/uploader/answer-sheets/bulk", status_code=202)
async def uploader_upload_bulk(bg: BackgroundTasks, files: list[UploadFile] = File(...),
                               ctx=Depends(current_uploader), db: Session = Depends(get_db)):
    """Many students at once, as the school's bulk upload: PDF or Word, one file per student. No roll numbers are
    typed; each sheet's roll number is read from its details page."""
    from .answer_sheets import BULK_EXT, _save_unassigned
    from ..services.student_identity import identify_sheets
    c, exam = ctx
    owner = _owner(db, c)  # sheets are processed as the school, the code only delivers them
    exam = get_exam(db, owner, exam.id)
    docs = await _save_unassigned(db, owner, exam, files, BULK_EXT)
    for d in docs:
        d.uploaded_by_code = c.id
    db.commit()
    for d in docs:  # one job per sheet, so sheets are identified and read in parallel
        bg.add_task(submit, exam.id, identify_sheets, [d.id], owner.id)
    return {"uploaded": len(docs)}


# ---------- page-by-page scanning (services/sheet_capture.py) ----------
_ROLL = __import__("re").compile(r"^[A-Za-z0-9/-]{1,20}$")
_IMAGES = {"png", "jpg", "jpeg"}
MAX_SCAN_PAGES = 60


def _owner(db: Session, c: UploaderCode) -> Teacher:
    return db.get(Teacher, db.get(Workspace, c.workspace_id).owner_id)


def _capturing(db: Session, c: UploaderCode, exam: Exam, sheet_id: str) -> AnswerSheetDocument:
    doc = db.get(AnswerSheetDocument, sheet_id)
    if doc is None or not doc.is_active or doc.exam_id != exam.id or doc.uploaded_by_code != c.id:
        raise err(404, "NOT_FOUND", "Answer sheet not found.")
    if doc.status != "CAPTURING":
        raise err(409, "SHEET_FINISHED", "This answer sheet is already finished.")
    return doc


async def _store_page(doc: AnswerSheetDocument, index: int, page: UploadFile) -> int:
    """Save (or replace, on a retry) page `index`; returns how many pages the sheet has now."""
    from ..documents.cloud import sync_file
    from ..documents.storage import abs_path, read_validated_upload
    from ..services.sheet_capture import page_files
    data, ext, _ = await read_validated_upload(page, _IMAGES)
    folder = abs_path(doc.original_file).parent / "pages"
    folder.mkdir(exist_ok=True)
    for old in folder.glob(f"{index:03d}.*"):
        old.unlink()
    (folder / f"{index:03d}.{ext}").write_bytes(data)
    sync_file(folder / f"{index:03d}.{ext}")  # /tmp is wiped on restart; the copy in cloud storage survives
    return len(page_files(doc))


@router.post("/uploader/sheets", status_code=201)
async def start_sheet(roll_number: str = Form(...), page: UploadFile = File(...),
                      ctx=Depends(current_uploader), db: Session = Depends(get_db)):
    """Start a student's sheet with page 1. The typed roll number says whose it is; nothing is read to identify them."""
    import uuid
    from ..documents.storage import doc_dir, rel
    from ..models import Evaluation, Student
    c, exam = ctx
    roll = roll_number.strip().upper()
    if not _ROLL.fullmatch(roll):
        raise err(400, "INVALID_ROLL", "Enter the student's roll number (letters and digits only).")
    st = db.query(Student).filter_by(class_id=exam.class_id, roll_number=roll).first()
    if st and db.query(Evaluation.id).filter_by(exam_id=exam.id, student_id=st.id).first():
        raise err(409, "ANSWER_SHEET_EXISTS", f"{st.name} ({st.roll_number}) already has an answer sheet for this exam. "
                                              "Delete it first to upload again.")
    busy = db.query(AnswerSheetDocument).filter_by(exam_id=exam.id, is_active=True, status="CAPTURING").all()
    if any((d.identity or {}).get("typed_roll") == roll for d in busy):
        raise err(409, "SHEET_IN_PROGRESS", f"Roll number {roll} is already being scanned.")
    doc_id = str(uuid.uuid4())
    folder = doc_dir("answer-sheet", exam.id, doc_id)
    doc = AnswerSheetDocument(id=doc_id, exam_id=exam.id, original_filename="answer-sheet.pdf",
                              original_file=rel(folder / "original.pdf"), mime_type="application/pdf", file_size=0,
                              status="CAPTURING", stage="Scanning pages", uploaded_by_code=c.id,
                              identity={"typed_roll": roll, "captured": 1})
    await _store_page(doc, 1, page)
    db.add(doc)
    db.commit()
    return {"id": doc.id, "roll_number": roll, "pages": 1, "status": doc.status}


@router.post("/uploader/sheets/{sheet_id}/pages")
async def add_sheet_page(sheet_id: str, index: int = Form(..., ge=2, le=MAX_SCAN_PAGES), page: UploadFile = File(...),
                         ctx=Depends(current_uploader), db: Session = Depends(get_db)):
    """Next page of the sheet. Sending the same index again replaces it, so a failed upload can simply be retried."""
    c, exam = ctx
    doc = _capturing(db, c, exam, sheet_id)
    n = await _store_page(doc, index, page)
    doc.identity = {**(doc.identity or {}), "captured": n}
    db.commit()
    return {"pages": n}


@router.post("/uploader/sheets/{sheet_id}/finish", status_code=202)
def finish_sheet(sheet_id: str, bg: BackgroundTasks, ctx=Depends(current_uploader), db: Session = Depends(get_db)):
    """End of the sheet: its pages become one PDF; a job then links it to the typed roll's student, reads and grades it."""
    import fitz
    from ..models import Student
    from ..services.sheet_capture import complete_sheet, page_files
    from ..services.student_io import split_class_name
    c, exam = ctx
    doc = _capturing(db, c, exam, sheet_id)
    files = page_files(doc)
    for want, f in enumerate(files, 1):
        if int(f.stem) != want:
            raise err(400, "PAGE_MISSING", f"Page {want} is missing. Scan it again before finishing.")
    pdf = fitz.open()
    for f in files:
        with fitz.open(f) as img:
            pdf.insert_pdf(fitz.open("pdf", img.convert_to_pdf()))
    from ..documents.storage import abs_path
    out = abs_path(doc.original_file)
    out.write_bytes(pdf.tobytes())
    from ..documents.cloud import sync_file
    sync_file(out)
    ident = doc.identity or {}
    roll = ident.get("typed_roll")
    st = db.query(Student).filter_by(class_id=exam.class_id, roll_number=roll).first()
    if st is None:
        section = split_class_name(exam.school_class.name)[1] if exam.school_class else None
        st = Student(class_id=exam.class_id, roll_number=roll, section=section,
                     name=f"Roll {roll}")
        db.add(st)
        db.flush()
    doc.file_size, doc.status, doc.stage = out.stat().st_size, "UPLOADED", "Queued"
    doc.identity = {**ident, "captured": len(files)}
    db.commit()
    owner = _owner(db, c)
    bg.add_task(submit, exam.id, complete_sheet, doc.id, st.id, owner.id)
    return {"id": doc.id, "pages": len(files), "status": doc.status}


@router.delete("/uploader/sheets/{sheet_id}", status_code=204)
def discard_sheet(sheet_id: str, ctx=Depends(current_uploader), db: Session = Depends(get_db)):
    """Throw away a sheet that is still being scanned (its photos too)."""
    import shutil
    from ..documents.storage import abs_path
    c, exam = ctx
    doc = _capturing(db, c, exam, sheet_id)
    from ..documents.cloud import remove_prefix
    remove_prefix(doc.original_file.rsplit("/", 1)[0])
    shutil.rmtree(abs_path(doc.original_file).parent, ignore_errors=True)
    db.delete(doc)
    db.commit()
