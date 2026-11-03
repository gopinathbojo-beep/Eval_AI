"""The dashboard bell: everything in the workspace that needs a person, newest first.

Held answer sheets (student unclear, typed roll or page count differs from the details page), evaluations the AI
flagged for review, and question papers, answer keys or sheets that could not be read. Each item links to where it
is fixed; it disappears once fixed, so nothing has to be marked as read."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AnswerKeyDocument, AnswerSheetDocument, Evaluation, QuestionPaperDocument, Student, Teacher
from ..security import current_teacher
from ..workspaces import exams_query

router = APIRouter(prefix="/api")
REVIEW = ("MAPPING_REVIEW", "AI_EVALUATED", "TEACHER_REVIEW")
UNREAD = ("NEEDS_ATTENTION", "FAILED", "AI_ERROR")
LIMIT = 100


@router.get("/notifications")
def notifications(db: Session = Depends(get_db), t: Teacher = Depends(current_teacher)):
    exams = {e.id: e for e in exams_query(db, t)}
    if not exams:
        return {"count": 0, "items": []}
    ids = list(exams)
    items: list[dict] = []

    def add(kind: str, exam_id: str, title: str, detail: str, link: str, at) -> None:
        items.append({"kind": kind, "exam_id": exam_id, "exam": exams[exam_id].name, "title": title, "detail": detail,
                      "link": link, "at": at.isoformat() if at else None})

    for d in db.query(AnswerSheetDocument).filter(AnswerSheetDocument.exam_id.in_(ids), AnswerSheetDocument.is_active.is_(True),
                                                  AnswerSheetDocument.status.in_(("NEEDS_STUDENT", *UNREAD))):
        ident = d.identity or {}
        roll = ident.get("typed_roll") or (db.get(Student, d.student_id).roll_number if d.student_id else None)
        who = f"Roll {roll}" if roll else d.original_filename
        if d.status == "NEEDS_STUDENT":
            add("sheet_held", d.exam_id, f"{who}: answer sheet needs a check",
                ident.get("note") or "Pick the student this sheet belongs to.", f"/exams/{d.exam_id}/submissions", d.uploaded_at)
        else:
            add("sheet_unread", d.exam_id, f"{who}: answer sheet could not be read",
                d.error_message or "Retry reading the sheet.", f"/exams/{d.exam_id}/submissions", d.uploaded_at)

    for ev in db.query(Evaluation).filter(Evaluation.exam_id.in_(ids), Evaluation.status.in_(REVIEW)):
        st = ev.student
        add("evaluation_review", ev.exam_id, f"Roll {st.roll_number if st else '?'}: marks need your review",
            "The AI flagged answers it was not sure about.", f"/evaluations/{ev.id}", ev.created_at)

    for model, what, path in ((QuestionPaperDocument, "Question paper", "questions"), (AnswerKeyDocument, "Answer key", "answer-key")):
        for d in db.query(model).filter(model.exam_id.in_(ids), model.is_active.is_(True), model.status.in_(UNREAD)):
            add("document_unread", d.exam_id, f"{what} could not be read fully",
                d.error_message or "Retry the pages that failed, or upload it again.", f"/exams/{d.exam_id}/{path}", d.uploaded_at)

    items.sort(key=lambda i: i["at"] or "", reverse=True)
    return {"count": len(items), "items": items[:LIMIT]}
