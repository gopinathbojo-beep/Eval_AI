"""Question paper and answer key generation (app/generation): from the QP & Answer Key tab, or for one exam."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..cbse.catalog import get_profile
from ..database import get_db
from ..deps import err, get_exam
from ..generation import retrieve
from ..generation.attach import attach_to_exam
from ..generation.generate import expire_stale, run_job
from ..generation.render import key_pdf, paper_pdf
from ..models import GeneratedPaper, Teacher
from ..reference.search import subject_of
from ..security import current_teacher
from ..services.audit import audit
from .core import textbook_subjects

router = APIRouter(prefix="/api")


class GenerateIn(BaseModel):
    grade: Literal["10", "12"] | None = None  # taken from the exam when generating for one
    subject_key: str | None = Field(None, max_length=80)
    pattern: Literal["board", "custom"] = "board"
    profile_id: str | None = Field(None, max_length=40)
    mix: dict[str, int] | None = None  # {"1": 10, "2": 5, ...} marks -> number of questions (custom pattern)
    duration_minutes: int = Field(180, ge=15, le=240)
    choices: bool = True
    source_ids: list[str] = Field(default_factory=list, max_length=200)  # chapters; empty = the whole syllabus
    difficulty: Literal["easy", "balanced", "hard"] = "balanced"
    topics: str = Field("", max_length=500)
    notes: str = Field("", max_length=800)
    title: str = Field("", max_length=300)


def _entry(grade: str, key: str) -> dict:
    entry = next((x for x in textbook_subjects().get(grade, []) if x["key"] == key), None)
    if entry is None:
        raise err(400, "SUBJECT_REQUIRED", "Choose a subject from the list.")
    return entry


def _check_mix(body: GenerateIn) -> None:
    if body.pattern != "custom":
        return
    mix = {k: v for k, v in (body.mix or {}).items() if v}
    try:
        if not mix or any(float(k) <= 0 or float(k) > 10 or not 0 < v <= 40 for k, v in mix.items()):
            raise ValueError
    except ValueError:
        raise err(400, "INVALID_PATTERN", "Give each mark value (1-10) a question count between 1 and 40.")
    if sum(mix.values()) > 60:
        raise err(400, "INVALID_PATTERN", "A paper can have at most 60 questions.")


def _start(db: Session, t: Teacher, bg: BackgroundTasks, body: GenerateIn, grade: str, entry: dict,
           exam_id: str | None = None) -> GeneratedPaper:
    _check_mix(body)
    standard = int(grade)
    if not retrieve.library_subjects(db).get(entry["key"]):
        raise err(409, "NO_REFERENCE", f"No NCERT textbook for Class {grade} {entry['name']} is loaded in the reference "
                                       "library yet, so a paper cannot be generated from it.")
    profile_id = body.profile_id if body.profile_id in entry["profiles"] else (entry["profiles"] or [None])[0]
    profile = get_profile(profile_id)
    pattern = body.pattern if profile and not profile.get("upload_driven") else "custom"
    req = {**body.model_dump(), "pattern": pattern, "profile_id": profile_id, "subject_name": entry["name"]}
    if pattern == "custom" and not body.mix:
        req["mix"] = None  # the default 80-mark shape
    gp = GeneratedPaper(teacher_id=t.id, workspace_id=t.workspace_id, exam_id=exam_id, standard=standard,
                        subject=entry["key"], title=body.title or f"Class {grade} {entry['name']}",
                        status="QUEUED", stage="Queued", request=req)
    db.add(gp)
    db.commit()
    bg.add_task(run_job, gp.id)
    return gp


def _view(gp: GeneratedPaper, full: bool = False) -> dict:
    p = gp.paper or {}
    out = {"id": gp.id, "exam_id": gp.exam_id, "standard": gp.standard, "subject": gp.subject, "title": gp.title,
           "subject_name": (gp.request or {}).get("subject_name"), "status": gp.status, "stage": gp.stage,
           "error": gp.error, "created_at": gp.created_at.isoformat(), "request": gp.request,
           "total_marks": p.get("total_marks"), "question_count": len(p.get("questions", [])),
           "flagged": p.get("flagged", 0)}
    if full:
        out["paper"] = gp.paper
    return out


def _get(db: Session, t: Teacher, pid: str) -> GeneratedPaper:
    gp = db.get(GeneratedPaper, pid)
    mine = gp is not None and (gp.workspace_id == t.workspace_id if t.workspace_id else gp.teacher_id == t.id)
    if not mine:
        raise err(404, "NOT_FOUND", "Generated paper not found.")
    expire_stale(db, gp)
    return gp


def _ready(gp: GeneratedPaper) -> dict:
    if gp.status != "READY" or not gp.paper:
        raise err(409, "NOT_READY", "The paper is not ready yet.")
    return gp.paper


@router.get("/generation/subjects")
def subjects(db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    """Each catalog subject with its CBSE patterns and how many textbook chapters the library holds for it."""
    loaded = retrieve.library_subjects(db)
    out = {}
    for grade, items in textbook_subjects().items():
        out[grade] = []
        for s in items:
            patterns = []
            for pid in s["profiles"]:
                p = get_profile(pid)
                if p and not p.get("upload_driven") and p["sections"]:
                    patterns.append({"id": pid, "name": p["name"], "total_marks": p["total_marks"],
                                     "duration_minutes": p["duration_minutes"], "questions": p["question_count"]})
            out[grade].append({"key": s["key"], "name": s["name"], "patterns": patterns, "chapters": loaded.get(s["key"], 0)})
    return out


@router.get("/generation/chapters")
def chapters(subject: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    try:
        standard = int(subject.split("-", 1)[0])
    except ValueError:
        raise err(400, "SUBJECT_REQUIRED", "Unknown subject.")
    return retrieve.chapters(db, standard, subject)


@router.post("/generation/papers", status_code=202)
def generate_paper(body: GenerateIn, bg: BackgroundTasks, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    if not body.grade or not body.subject_key:
        raise err(400, "SUBJECT_REQUIRED", "Choose a class and subject.")
    return _view(_start(db, t, bg, body, body.grade, _entry(body.grade, body.subject_key)))


@router.get("/generation/papers")
def list_papers(db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    q = db.query(GeneratedPaper)
    q = q.filter(GeneratedPaper.workspace_id == t.workspace_id) if t.workspace_id else q.filter(GeneratedPaper.teacher_id == t.id)
    rows = q.order_by(GeneratedPaper.created_at.desc()).limit(100).all()
    for gp in rows:
        expire_stale(db, gp)
    return [_view(gp) for gp in rows]


@router.get("/generation/papers/{pid}")
def get_paper(pid: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    return _view(_get(db, t, pid), full=True)


@router.delete("/generation/papers/{pid}")
def delete_paper(pid: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    gp = _get(db, t, pid)
    db.delete(gp)
    db.commit()
    return {"ok": True}


class QuestionEdit(BaseModel):
    text: str | None = Field(None, max_length=6000)
    options: list[str] | None = None
    answer: str | None = Field(None, max_length=8000)
    marking_points: list[dict] | None = None
    alternative: bool = False  # edit the OR alternative instead of the main question


@router.patch("/generation/papers/{pid}/questions/{number}")
def edit_question(pid: str, number: int, body: QuestionEdit, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    gp = _get(db, t, pid)
    paper = dict(_ready(gp))
    qs = [dict(q) for q in paper["questions"]]
    q = next((q for q in qs if q["number"] == number), None)
    if q is None:
        raise err(404, "NOT_FOUND", "Question not found.")
    target = dict(q["or"]) if body.alternative and q.get("or") else q
    for f in ("text", "options", "answer", "marking_points"):
        v = getattr(body, f)
        if v is not None:
            target[f] = v
    target["edited"] = True
    if body.alternative and q.get("or"):
        q["or"] = target
    paper["questions"] = qs
    gp.paper = paper  # reassign: JSON columns are not mutation-tracked
    db.commit()
    return _view(gp, full=True)


def _pdf(data: bytes, name: str) -> Response:
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/generation/papers/{pid}/question-paper.pdf")
def question_paper_pdf(pid: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    gp = _get(db, t, pid)
    return _pdf(paper_pdf(_ready(gp)), f"{gp.subject}-question-paper.pdf")


@router.get("/generation/papers/{pid}/answer-key.pdf")
def answer_key_pdf(pid: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    gp = _get(db, t, pid)
    return _pdf(key_pdf(_ready(gp)), f"{gp.subject}-answer-key.pdf")


# ---------- for one exam ----------
def _exam_subject(exam) -> tuple[str, dict]:
    scope = subject_of(exam)
    if scope is None:
        raise err(409, "NO_REFERENCE", "This exam's subject is not in the reference library, so a paper cannot be generated.")
    grade = str(scope[0])
    return grade, _entry(grade, scope[1])


def _editable(db: Session, exam) -> None:
    from ..generation.attach import EDITABLE
    from ..models import Evaluation
    if exam.status not in EDITABLE or db.query(Evaluation.id).filter_by(exam_id=exam.id).first():
        raise err(409, "QUESTIONS_LOCKED", "Answer sheets are already uploaded, so the question paper can no longer be replaced.")


@router.post("/exams/{exam_id}/generate-paper", status_code=202)
def generate_for_exam(exam_id: str, body: GenerateIn, bg: BackgroundTasks, db: Session = Depends(get_db),
                      t: Teacher = Depends(current_teacher)):
    exam = get_exam(db, t, exam_id)
    _editable(db, exam)
    grade, entry = _exam_subject(exam)
    if body.profile_id is None and exam.standard_profile_id in entry["profiles"]:
        body.profile_id = exam.standard_profile_id
    if not body.title:
        body.title = exam.name
    gp = _start(db, t, bg, body, grade, entry, exam.id)
    audit(db, exam_id=exam.id, teacher_id=t.id, entity_type="exam", entity_id=exam.id, action="paper_generation_started", new=gp.id)
    db.commit()
    return _view(gp)


@router.get("/exams/{exam_id}/generated-paper")
def exam_generated_paper(exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    """The exam's latest generated paper, and the library subject a new one would be written for (null: none)."""
    exam = get_exam(db, t, exam_id)
    scope = subject_of(exam)
    gp = db.query(GeneratedPaper).filter_by(exam_id=exam.id).order_by(GeneratedPaper.created_at.desc()).first()
    if gp is not None:
        expire_stale(db, gp)
    return {"subject": {"grade": str(scope[0]), "key": scope[1]} if scope else None,
            "paper": _view(gp) if gp else None}


@router.post("/generation/papers/{pid}/use/{exam_id}", status_code=202)
def use_for_exam(pid: str, exam_id: str, db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    """Attach an already generated paper (from the QP & Answer Key tab) to an exam of the same class and subject."""
    gp = _get(db, t, pid)
    _ready(gp)
    exam = get_exam(db, t, exam_id)
    _editable(db, exam)
    grade, entry = _exam_subject(exam)
    if entry["key"] != gp.subject:
        raise err(409, "SUBJECT_MISMATCH", "This paper is for a different class or subject than the exam.")
    gp.exam_id = exam.id
    db.commit()
    attach_to_exam(db, gp)
    return _view(gp)
