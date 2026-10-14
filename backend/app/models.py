from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Teacher(Base):
    __tablename__ = "teachers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SchoolClass(Base):
    __tablename__ = "classes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    teacher_id: Mapped[str] = mapped_column(ForeignKey("teachers.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    teacher_id: Mapped[str] = mapped_column(ForeignKey("teachers.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (UniqueConstraint("class_id", "roll_number", name="uq_student_roll"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    class_id: Mapped[str] = mapped_column(ForeignKey("classes.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    roll_number: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    school_class: Mapped[SchoolClass] = relationship()


class Exam(Base):
    __tablename__ = "exams"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    teacher_id: Mapped[str] = mapped_column(ForeignKey("teachers.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    academic_year: Mapped[str] = mapped_column(String(20))
    class_id: Mapped[str] = mapped_column(ForeignKey("classes.id"))
    subject_id: Mapped[str] = mapped_column(ForeignKey("subjects.id"))
    exam_type: Mapped[str] = mapped_column(String(50))
    exam_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_marks: Mapped[float] = mapped_column(Float)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    school_class: Mapped[SchoolClass] = relationship()
    subject: Mapped[Subject] = relationship()


class ExamQuestion(Base):
    """Canonical question. Its UUID is the only identity used downstream."""
    __tablename__ = "exam_questions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    exam_id: Mapped[str] = mapped_column(ForeignKey("exams.id"), index=True)
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    display_number: Mapped[str] = mapped_column(String(50))
    normalized_number: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    question_text: Mapped[str] = mapped_column(Text, default="")
    raw_ocr_text: Mapped[str] = mapped_column(Text, default="")
    question_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    max_marks: Mapped[float | None] = mapped_column(Float, nullable=True)
    section: Mapped[str | None] = mapped_column(String(100), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    crop_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(20), default="UNVERIFIED")
    review_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class _DocMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    original_filename: Mapped[str] = mapped_column(String(300))
    original_file: Mapped[str] = mapped_column(String(500))      # path relative to data dir
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(Integer)
    # UPLOADED, RENDERING, OCR_PROCESSING, EXTRACTING, READY, NEEDS_ATTENTION, AI_ERROR, FAILED
    status: Mapped[str] = mapped_column(String(30), default="UPLOADED")
    stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    progress_current: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    pages: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class QuestionPaperDocument(_DocMixin, Base):
    __tablename__ = "question_paper_documents"
    exam_id: Mapped[str] = mapped_column(ForeignKey("exams.id"), index=True)


class AnswerKeyDocument(_DocMixin, Base):
    __tablename__ = "answer_key_documents"
    exam_id: Mapped[str] = mapped_column(ForeignKey("exams.id"), index=True)


class AnswerSheetDocument(_DocMixin, Base):
    __tablename__ = "answer_sheet_documents"
    exam_id: Mapped[str] = mapped_column(ForeignKey("exams.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)


class AnswerKey(Base):
    __tablename__ = "answer_keys"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    exam_id: Mapped[str] = mapped_column(ForeignKey("exams.id"), index=True)
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    raw_question_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    normalized_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    exam_question_id: Mapped[str | None] = mapped_column(ForeignKey("exam_questions.id"), nullable=True, index=True)
    answer_text: Mapped[str] = mapped_column(Text, default="")
    raw_ocr_text: Mapped[str] = mapped_column(Text, default="")
    marks: Mapped[float | None] = mapped_column(Float, nullable=True)
    criteria: Mapped[list] = mapped_column(JSON, default=list)
    accepted_answers: Mapped[list] = mapped_column(JSON, default=list)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    crop_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    mapping_status: Mapped[str] = mapped_column(String(20), default="UNMAPPED")  # MAPPED|NEEDS_REVIEW|UNMAPPED
    mapping_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    mapping_candidates: Mapped[list] = mapped_column(JSON, default=list)
    mark_mismatch: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_status: Mapped[str] = mapped_column(String(20), default="UNVERIFIED")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (UniqueConstraint("exam_id", "student_id", name="uq_eval_exam_student"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    exam_id: Mapped[str] = mapped_column(ForeignKey("exams.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    answer_sheet_id: Mapped[str] = mapped_column(ForeignKey("answer_sheet_documents.id"))
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    run_status: Mapped[str] = mapped_column(String(20), default="IDLE")  # IDLE|RUNNING|DONE|ERROR
    run_progress: Mapped[int] = mapped_column(Integer, default=0)
    run_total: Mapped[int] = mapped_column(Integer, default=0)
    total_marks: Mapped[float | None] = mapped_column(Float, nullable=True)
    maximum_marks: Mapped[float | None] = mapped_column(Float, nullable=True)
    percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    student: Mapped[Student] = relationship()
    exam: Mapped[Exam] = relationship()


class StudentAnswer(Base):
    __tablename__ = "student_answers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id"), index=True)
    raw_question_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    normalized_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    exam_question_id: Mapped[str | None] = mapped_column(ForeignKey("exam_questions.id"), nullable=True, index=True)
    raw_ocr_text: Mapped[str] = mapped_column(Text, default="")   # never overwritten
    answer_text: Mapped[str] = mapped_column(Text, default="")    # teacher-editable
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    crop_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # UNMAPPED, MAPPED, EVALUATING, EVALUATED, NEEDS_REVIEW, APPROVED, IGNORED
    status: Mapped[str] = mapped_column(String(20), default="UNMAPPED")
    mapping_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    mapping_candidates: Mapped[list] = mapped_column(JSON, default=list)
    mapping_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)


class EvaluationItem(Base):
    __tablename__ = "evaluation_items"
    __table_args__ = (UniqueConstraint("evaluation_id", "exam_question_id", name="uq_item_eval_question"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id"), index=True)
    exam_question_id: Mapped[str] = mapped_column(ForeignKey("exam_questions.id"))
    student_answer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # PENDING, EVALUATED, EVALUATION_ERROR, MISSING, APPROVED
    status: Mapped[str] = mapped_column(String(25), default="PENDING")
    ai_marks: Mapped[float | None] = mapped_column(Float, nullable=True)      # never overwritten by teacher
    ai_decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    matched_points: Mapped[list] = mapped_column(JSON, default=list)
    missing_points: Mapped[list] = mapped_column(JSON, default=list)
    ai_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_marks: Mapped[float | None] = mapped_column(Float, nullable=True)   # teacher-approved mark
    teacher_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    teacher_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    not_attempted_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    exam_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    teacher_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(60))
    old_value: Mapped[dict | list | str | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | list | str | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class VerifiedReferenceExample(Base):
    """Local, reusable collection of teacher-approved ground-truth examples."""
    __tablename__ = "verified_reference_examples"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    exam_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    teacher_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    document_type: Mapped[str] = mapped_column(String(50))  # question_paper, answer_key, student_answer
    subject: Mapped[str] = mapped_column(String(100), default="General")
    source_document: Mapped[str] = mapped_column(String(300))
    page_number: Mapped[int] = mapped_column(Integer, default=1)
    question_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    normalized_number: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    original_ocr: Mapped[str] = mapped_column(Text, default="")
    corrected_text: Mapped[str] = mapped_column(Text, default="")
    error_category: Mapped[str] = mapped_column(String(60), default="none")
    # mathematical_symbols, chemical_formula, table_formatting, numbering, word_typo, missing_content, option_structure, none
    structure_type: Mapped[str] = mapped_column(String(60), default="descriptive")
    # formula, equation, table, notice_box, subquestion, descriptive, mcq
    approved_marks: Mapped[float | None] = mapped_column(Float, nullable=True)
    criteria: Mapped[list] = mapped_column(JSON, default=list)
    verification_status: Mapped[str] = mapped_column(String(30), default="APPROVED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

