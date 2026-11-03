"""Create a ready-to-upload test exam without any AI call: question paper and answer key marked read and verified,
three questions with their keys, status READY_FOR_EVALUATION, and one uploader code.

Run: .venv\\Scripts\\python scripts\\make_test_exam.py [school-owner-email]   (default develop@gmail.com)
Uses the local database (DATABASE_URL must be empty). Answer sheets uploaded to it are still read by the AI.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if os.environ.get("DATABASE_URL"):
    raise SystemExit("Refusing to run against DATABASE_URL; this is for the local SQLite database only.")

import fitz  # noqa: E402

from app.database import SessionLocal, init_db  # noqa: E402
from app.documents.storage import doc_dir, rel  # noqa: E402
from app.models import (AnswerKey, AnswerKeyDocument, Exam, ExamQuestion, QuestionPaperDocument, SchoolClass,  # noqa: E402
                        Subject, Teacher, UploaderCode)
from app.routes.uploader import _new_code  # noqa: E402

QUESTIONS = [("1", "Define photosynthesis.", 2, "Plants make food from carbon dioxide and water using sunlight and chlorophyll."),
             ("2", "Name the gas released during photosynthesis.", 1, "Oxygen."),
             ("3", "Explain why leaves are green.", 2, "Leaves contain chlorophyll, which reflects green light.")]


def _pdf(title: str, lines: list[str], path: Path) -> int:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 80), title, fontsize=14)
    for i, line in enumerate(lines):
        page.insert_text((72, 120 + 24 * i), line, fontsize=11)
    path.write_bytes(doc.tobytes())
    return path.stat().st_size


def _doc(model, kind: str, exam_id: str, title: str, lines: list[str]):
    row = model(exam_id=exam_id, original_filename=f"{kind}.pdf", original_file="", mime_type="application/pdf",
                file_size=0, status="READY", stage="Ready for review")
    row.id = __import__("uuid").uuid4().hex[:8] + "-test-" + kind[:6]
    path = doc_dir(kind, exam_id, row.id) / "original.pdf"
    row.file_size = _pdf(title, lines, path)
    row.original_file = rel(path)
    return row


def main(email: str) -> None:
    init_db()
    db = SessionLocal()
    try:
        owner = db.query(Teacher).filter_by(email=email.lower()).first()
        if not owner or owner.role != "MANAGEMENT" or not owner.workspace_id:
            raise SystemExit(f"{email} is not a school management account with a workspace.")
        cls = db.query(SchoolClass).filter_by(teacher_id=owner.id, name="10-A").first() or \
            SchoolClass(teacher_id=owner.id, workspace_id=owner.workspace_id, name="10-A")
        sub = db.query(Subject).filter_by(teacher_id=owner.id, name="Science").first() or \
            Subject(teacher_id=owner.id, workspace_id=owner.workspace_id, name="Science")
        db.add_all([cls, sub])
        db.flush()
        exam = Exam(teacher_id=owner.id, workspace_id=owner.workspace_id, class_id=cls.id, subject_id=sub.id,
                    name=f"Test Exam {datetime.now():%d %b %H:%M}", academic_year="2026-27", exam_type="School exam",
                    total_marks=sum(q[2] for q in QUESTIONS), duration_minutes=60, status="READY_FOR_EVALUATION")
        db.add(exam)
        db.flush()
        qp = _doc(QuestionPaperDocument, "question-paper", exam.id, "Test Exam - Science (Class 10)",
                  [f"Q{n}. {text} ({m})" for n, text, m, _ in QUESTIONS])
        ak = _doc(AnswerKeyDocument, "answer-key", exam.id, "Answer Key",
                  [f"Q{n}. {key} ({m})" for n, _, m, key in QUESTIONS])
        db.add_all([qp, ak])
        db.flush()
        for pos, (n, text, marks, key) in enumerate(QUESTIONS):
            q = ExamQuestion(exam_id=exam.id, document_id=qp.id, display_number=n, normalized_number=n, question_text=text,
                             raw_ocr_text=text, max_marks=marks, position=pos, verification_status="VERIFIED")
            db.add(q)
            db.flush()
            db.add(AnswerKey(exam_id=exam.id, document_id=ak.id, raw_question_number=n, normalized_number=n,
                             exam_question_id=q.id, answer_text=key, raw_ocr_text=key, marks=marks,
                             mapping_status="MAPPED", verification_status="VERIFIED"))
        code = UploaderCode(exam_id=exam.id, workspace_id=owner.workspace_id, code=_new_code(db), label="Test uploader")
        db.add(code)
        db.commit()
        print(f"Exam:          {exam.name}  (id {exam.id})")
        print(f"School:        {email}  ·  Class 10-A  ·  Science  ·  {exam.total_marks:g} marks")
        print(f"Status:        {exam.status}")
        print(f"Uploader code: {code.code}")
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "develop@gmail.com")
