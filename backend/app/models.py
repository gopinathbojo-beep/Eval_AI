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


class School(Base):
    """One school = one organisation. Self-signed-up schools stay PENDING until a Platform Admin approves them."""
    __tablename__ = "schools"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(200))
    board: Mapped[str] = mapped_column(String(20), default="CBSE")
    address: Mapped[str] = mapped_column(Text, default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    state: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING | ACTIVE | SUSPENDED
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class User(Base):
    """Every account. One email = one role. Teachers keep the column name teacher_id on the rows they own."""
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
<<<<<<< 7c662e7
    phone: Mapped[str] = mapped_column(String(30), default="")
    role: Mapped[str] = mapped_column(String(20), default="teacher")  # platform_admin | school_manager | teacher | parent
    admin_role: Mapped[str | None] = mapped_column(String(20), nullable=True)  # super_admin | admin | viewer
    school_id: Mapped[str | None] = mapped_column(ForeignKey("schools.id"), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # invited | active | suspended | removed
    password_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)  # null = Google-only or invited
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)  # bumping it signs out every session
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    school: Mapped[School | None] = relationship()


Teacher = User  # the teacher routes predate roles; a teacher is a User with role "teacher"
=======
    password_hash: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    google_sub: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    session_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_status: Mapped[str] = mapped_column(String(20), default="APPROVED", server_default="APPROVED")
    registration_source: Mapped[str] = mapped_column(String(20), default="ADMIN", server_default="ADMIN")
    profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    profile_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    role: Mapped[str] = mapped_column(String(20), default="TEACHER", server_default="TEACHER")
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


# Keep the legacy table and authentication alias for existing API clients.
User = Teacher


class BackgroundJob(Base):
    __tablename__ = "background_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    exam_id: Mapped[str | None] = mapped_column(String(36), index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    actor_id: Mapped[str | None] = mapped_column(String(36))
    session_version: Mapped[int | None] = mapped_column(Integer)
    handler: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSON)
    active_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="QUEUED", index=True)
    error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[str | None] = mapped_column(String(36))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PendingUpload(Base):
    __tablename__ = "pending_uploads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    exam_id: Mapped[str] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[str] = mapped_column(String(36), index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    object_key: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str] = mapped_column(String(300))
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(Integer)
    fields: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    kind: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(200))
    owner_id: Mapped[str] = mapped_column(String(36), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TeacherAssignment(Base):
    __tablename__ = "teacher_assignments"
    __table_args__ = (UniqueConstraint("teacher_id", "class_id", "subject_id", name="uq_assignment"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    teacher_id: Mapped[str] = mapped_column(ForeignKey("teachers.id"), index=True)
    class_id: Mapped[str] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"))
    subject_id: Mapped[str] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"))
>>>>>>> kishore/Version2.0


class SchoolClass(Base):
    __tablename__ = "classes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
<<<<<<< 7c662e7
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
=======
    teacher_id: Mapped[str] = mapped_column(ForeignKey("teachers.id"), index=True)
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id"), index=True)
>>>>>>> kishore/Version2.0
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
<<<<<<< 7c662e7
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
=======
    teacher_id: Mapped[str] = mapped_column(ForeignKey("teachers.id"), index=True)
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id"), index=True)
>>>>>>> kishore/Version2.0
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
    registration_number: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    section: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    school_class: Mapped[SchoolClass] = relationship()


class Exam(Base):
    __tablename__ = "exams"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
<<<<<<< 7c662e7
    # The owner: a teacher, or for origin PARENT the parent. Schools see exams whose owner belongs to the school,
    # so parent exams (owner has no school) never reach a school.
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    origin: Mapped[str] = mapped_column(String(20), default="TEACHER")  # TEACHER | PARENT
=======
    teacher_id: Mapped[str] = mapped_column(ForeignKey("teachers.id"), index=True)
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id"), index=True)
>>>>>>> kishore/Version2.0
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
    # after finalization the exam's files are deleted from disk at files_purge_at (reports are kept)
    files_purge_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    files_purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
    # Either/or alternatives share a group ("38" for 38(a) OR 38(b)); the student answers one, it counts once
    choice_group: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # The section says "answer any N" (N), and this question must be answered anyway (formatter/common/choices.py)
    answer_any: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compulsory: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    crop_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(20), default="UNVERIFIED")
    review_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    course_outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)    # CO1, CO2, ...
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
    # null until the student is identified from the sheet (or picked by the teacher)
    student_id: Mapped[str | None] = mapped_column(ForeignKey("students.id"), index=True, nullable=True)
    # what was read from the sheet header and how it was matched: {read, match, note, candidates}
    identity: Mapped[dict | None] = mapped_column(JSON, nullable=True)


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
    # The marking rubric built from this key (formatter build_rubric): points, notes, deductions, problems
    rubric: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rubric_status: Mapped[str] = mapped_column(String(20), default="UNREVIEWED")  # UNREVIEWED|CONFIRMED
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
<<<<<<< 7c662e7
    teacher_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # the acting user, whatever the role
=======
    teacher_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
>>>>>>> kishore/Version2.0
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(60))
    old_value: Mapped[dict | list | str | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | list | str | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class VerifiedReferenceExample(Base):
    """Local, reusable collection of teacher-approved ground-truth examples."""
    __tablename__ = "verified_reference_examples"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    exam_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    teacher_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
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



class SchoolProfile(Base):
    """School details printed on reports and report cards (one per teacher)."""
    __tablename__ = "school_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    principal_name: Mapped[str] = mapped_column(String(200), default="")
    logo_file: Mapped[str | None] = mapped_column(String(500), nullable=True)   # path relative to data dir
    # active template per document: "preset:<id>" or a ReportTemplate id
    active_report_template: Mapped[str] = mapped_column(String(60), default="preset:classic")
    active_card_template: Mapped[str] = mapped_column(String(60), default="preset:classic")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class ReportTemplate(Base):
    """A teacher's saved layout for the exam report ("report") or the report card ("report_card")."""
    __tablename__ = "report_templates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


# ---------- accounts ----------
class AuthToken(Base):
    """A single-use emailed link (invite, password reset, signup email check). Only the SHA-256 of the token is kept."""
    __tablename__ = "auth_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    kind: Mapped[str] = mapped_column(String(20))  # invite | reset | verify
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    signup_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SignupRequest(Base):
    """A public school or parent signup, held until the email is confirmed. Nothing else exists before that."""
    __tablename__ = "signup_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    kind: Mapped[str] = mapped_column(String(10))  # school | parent
    email: Mapped[str] = mapped_column(String(200), index=True)
    phone_key: Mapped[str] = mapped_column(String(10), default="", index=True)  # last ten digits
    payload: Mapped[dict] = mapped_column(JSON, default=dict)  # form fields and the password hash
    status: Mapped[str] = mapped_column(String(20), default="AWAITING_EMAIL")  # AWAITING_EMAIL | COMPLETED
    created_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Consent(Base):
    __tablename__ = "consents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # privacy | terms | child_data
    version: Mapped[str] = mapped_column(String(20))
    ip: Mapped[str] = mapped_column(String(64), default="")
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ---------- parents ----------
class Child(Base):
    __tablename__ = "children"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    parent_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    standard: Mapped[int] = mapped_column(Integer)  # 10 | 12
    subjects: Mapped[list] = mapped_column(JSON, default=list)
    # the class and student rows the evaluation pipeline grades this child's sheets against
    class_id: Mapped[str | None] = mapped_column(ForeignKey("classes.id"), nullable=True)
    student_id: Mapped[str | None] = mapped_column(ForeignKey("students.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class GeneratedPaper(Base):
    """A question paper made by the paper generator; its questions and locked key live on exam_id."""
    __tablename__ = "generated_papers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    standard: Mapped[int] = mapped_column(Integer)
    subject: Mapped[str] = mapped_column(String(100))
    units: Mapped[list] = mapped_column(JSON, default=list)
    exam_id: Mapped[str | None] = mapped_column(ForeignKey("exams.id"), nullable=True)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    validation: Mapped[dict] = mapped_column(JSON, default=dict)
    model: Mapped[str] = mapped_column(String(100), default="")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ParentExam(Base):
    """A timed exam a parent set for a child. All times are decided by the server."""
    __tablename__ = "parent_exams"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    child_id: Mapped[str] = mapped_column(ForeignKey("children.id"), index=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey("generated_papers.id"))
    exam_id: Mapped[str] = mapped_column(ForeignKey("exams.id"))
    # PAPER_SELECTED | IN_PROGRESS | AWAITING_UPLOAD | EVALUATING | COMPLETED | MISSED | FAILED
    status: Mapped[str] = mapped_column(String(20), default="PAPER_SELECTED")
    duration_minutes: Mapped[int] = mapped_column(Integer)
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    upload_closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pages: Mapped[int] = mapped_column(Integer, default=0)
    evaluation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    credits_paper: Mapped[int] = mapped_column(Integer, default=0)
    credits_eval: Mapped[int] = mapped_column(Integer, default=0)


# ---------- credits ----------
class Wallet(Base):
    __tablename__ = "wallets"
    __table_args__ = (UniqueConstraint("owner_type", "owner_id", name="uq_wallet_owner"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    owner_type: Mapped[str] = mapped_column(String(10))  # school | parent
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    balance: Mapped[int] = mapped_column(Integer, default=0)  # available
    held: Mapped[int] = mapped_column(Integer, default=0)     # reserved by running evaluations
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class CreditLedger(Base):
    """Append-only. Every credit movement is one row; (type, ref_id) is unique so retries never double-count."""
    __tablename__ = "credit_ledger"
    __table_args__ = (UniqueConstraint("type", "ref_id", name="uq_ledger_type_ref"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    wallet_id: Mapped[str] = mapped_column(ForeignKey("wallets.id"), index=True)
    # PURCHASE, SIGNUP_BONUS, ADMIN_GRANT, ADMIN_DEDUCT, PAPER_CHARGE, PAPER_REFUND, EVAL_HOLD, EVAL_CAPTURE,
    # EVAL_RELEASE, DISPUTE_REFUND, PAYMENT_REFUND, EXPIRY
    type: Mapped[str] = mapped_column(String(20))
    amount: Mapped[int] = mapped_column(Integer)  # signed change to the available balance
    balance_after: Mapped[int] = mapped_column(Integer)
    ref_type: Mapped[str] = mapped_column(String(20), default="")
    ref_id: Mapped[str] = mapped_column(String(64))
    note: Mapped[str] = mapped_column(Text, default="")
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CreditPack(Base):
    __tablename__ = "credit_packs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(100))
    credits: Mapped[int] = mapped_column(Integer)
    price_inr: Mapped[float] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class CreditSetting(Base):
    """Prices in credits, editable by the Platform Admin (see services/credits.py for keys and defaults)."""
    __tablename__ = "credit_settings"
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[float] = mapped_column(Float)


class Payment(Base):
    """A Razorpay order and its outcome, written when checkout opens so unfinished payments can be reconciled."""
    __tablename__ = "payments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    wallet_id: Mapped[str] = mapped_column(ForeignKey("wallets.id"), index=True)
    pack_id: Mapped[str] = mapped_column(ForeignKey("credit_packs.id"))
    credits: Mapped[int] = mapped_column(Integer)
    amount_inr: Mapped[float] = mapped_column(Float)
    gst_amount: Mapped[float] = mapped_column(Float, default=0)
    razorpay_order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="CREATED")  # CREATED | PAID | FAILED | REFUNDED
    invoice_no: Mapped[str | None] = mapped_column(String(30), unique=True, nullable=True)
    created_by: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------- support ----------
class Dispute(Base):
    __tablename__ = "disputes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    raised_by: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id"))
    exam_question_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")  # OPEN | UPHELD | REJECTED
    resolution: Mapped[str] = mapped_column(Text, default="")
    refund_credits: Mapped[int] = mapped_column(Integer, default=0)
    resolved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    subject: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")  # OPEN | ANSWERED | CLOSED
    reply: Mapped[str] = mapped_column(Text, default="")
    replied_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
