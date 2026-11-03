"""One Finalize step for exam setup. The question paper and answer key are read in parallel; the school reviews
both on one screen, then Finalize verifies the questions, then the key, and opens the exam for answer sheets."""

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import err, get_exam
from ..models import AnswerKeyDocument, QuestionPaperDocument, Teacher
from ..services.state import set_state
from .answer_keys import verify_keys
from .documents import BUSY, release_waiting_key
from .management import management
from .questions import accept_valid, verify_questions

router = APIRouter(prefix="/api")
SETUP_STATES = ("QUESTION_PAPER_UPLOADED", "QUESTIONS_EXTRACTED", "QUESTIONS_VERIFIED", "ANSWER_KEY_UPLOADED",
                "ANSWER_KEY_VERIFIED")


@router.post("/exams/{exam_id}/finalize-setup")
def finalize_setup(exam_id: str, bg: BackgroundTasks, db: Session = Depends(get_db), t: Teacher = Depends(management)):
    exam = get_exam(db, t, exam_id)
    if exam.status in ("READY_FOR_EVALUATION", "EVALUATING", "REVIEW_REQUIRED"):
        return {"status": exam.status}
    if exam.status not in SETUP_STATES:
        raise err(409, "SETUP_INCOMPLETE", "Upload the question paper and the answer key first."
                  if exam.status == "DRAFT" else "This exam is closed.")
    for model, what in ((QuestionPaperDocument, "question paper"), (AnswerKeyDocument, "answer key")):
        doc = db.query(model).filter_by(exam_id=exam.id, is_active=True).order_by(model.uploaded_at.desc()).first()
        if doc is None:
            raise err(409, "SETUP_INCOMPLETE", f"Upload the {what} first.")
        if doc.status in BUSY or doc.status == "WAITING":
            raise err(409, "PROCESSING_IN_PROGRESS", f"The {what} is still being read. Wait for it to finish.")
    # each step returns early once done, so Finalize can be pressed again after fixing what a step reported
    if exam.status in ("QUESTION_PAPER_UPLOADED", "QUESTIONS_EXTRACTED"):
        accept_valid(exam.id, db, t)  # pressing Finalize is the school's acceptance of what it reviewed
        verify_questions(exam.id, bg, db, t)
        db.refresh(exam)
    if exam.status == "QUESTIONS_VERIFIED":
        release_waiting_key(db, exam, bg)
        db.refresh(exam)
    if exam.status == "ANSWER_KEY_UPLOADED":
        verify_keys(exam.id, db, t)
        db.refresh(exam)
    if exam.status == "ANSWER_KEY_VERIFIED":
        set_state(exam, "READY_FOR_EVALUATION")
        db.commit()
    return {"status": exam.status}
