export interface Teacher {
  id: string;
  name: string;
  email: string;
  is_admin: boolean;
  role: "ADMIN" | "MANAGEMENT" | "TEACHER" | "PARENT" | "UNASSIGNED";
  workspace_id: string | null;
  must_change_password: boolean;
  approval_status: "PENDING" | "APPROVED" | "REJECTED";
  profile_complete: boolean;
  profile: {
    institution?: string;
    subject?: string;
    city?: string;
    phone?: string;
    experience_years?: number;
    school_name?: string;
    address?: string;
    state?: string;
    postcode?: string;
    principal_name?: string;
    affiliation_number?: string;
    child_name?: string;
    child_class?: "10" | "12";
  } | null;
  rejection_reason: string | null;
  email_verified: boolean;
}
export interface ClassRow {
  id: string;
  name: string;
  std: string;
  section: string | null;
  student_count: number;
  assigned_subject_ids?: string[] | null;
}
export interface Subject {
  id: string;
  name: string;
  code: string | null;
}
export interface Student {
  id: string;
  name: string;
  roll_number: string;
  class_id: string;
  class_name: string | null;
  class_std?: string | null;
  registration_number?: string | null;
  section?: string | null;
}
export interface IdentityRead {
  name: string | null;
  roll_number: string | null;
  registration_number: string | null;
  class_name: string | null;
  section: string | null;
}
export interface UnassignedSheet extends DocInfo {
  identity: {
    match?: string;
    note?: string;
    read?: Partial<IdentityRead>;
    candidates?: string[];
  };
  candidates: {
    id: string;
    name: string;
    roll_number: string;
    registration_number: string | null;
    section: string | null;
  }[];
}
export interface BatchRow {
  evaluation_id: string;
  student: Student;
  status: string;
}
export interface ReviewSummary {
  total: number;
  processing: number;
  unassigned: number;
  finalized: number;
  ready: BatchRow[];
  needs_review: (BatchRow & {
    reasons: { question: string; reason: string }[];
  })[];
}
export interface ImportSummary {
  created: number;
  updated: number;
  errors: { row: number; reason: string }[];
}
export interface QuestionSummary {
  finalized_students: number;
  questions: { no: string; max: number | null; average: number; percentage: number | null; full: number; zero: number }[];
}
export type ExamStatus =
  | "DRAFT"
  | "QUESTION_PAPER_UPLOADED"
  | "QUESTIONS_EXTRACTED"
  | "QUESTIONS_VERIFIED"
  | "ANSWER_KEY_UPLOADED"
  | "ANSWER_KEY_VERIFIED"
  | "READY_FOR_EVALUATION"
  | "EVALUATING"
  | "REVIEW_REQUIRED"
  | "FINALIZED";
export interface PageInfo {
  page_number: number;
  width: number;
  height: number;
  ocr_status: string | null;
  ocr_error: string | null;
}
export interface DocInfo {
  id: string;
  kind: string;
  original_filename: string;
  status: string;
  stage: string | null;
  progress_current: number;
  progress_total: number;
  error_message: string | null;
  uploaded_at: string;
  pages: PageInfo[];
  /** typed roll number vs the "Roll No" written on the sheet (uploader sheets only) */
  roll_check?: { typed: string; written: string | null; status: "MATCH" | "NOT_WRITTEN" | "MISMATCH" | "CONFIRMED"; chosen?: string } | null;
}
export interface Exam {
  standard_profile_id?: string | null;
  standard_version?: string | null;
  standard_options?: Record<string, string> | null;
  id: string;
  name: string;
  academic_year: string;
  class_id: string;
  class_name: string;
  subject_id: string;
  subject_name: string;
  exam_type: string;
  exam_date: string | null;
  duration_minutes: number | null;
  total_marks: number;
  instructions: string | null;
  status: ExamStatus;
  created_at: string;
  files_purge_at?: string | null;
  files_purged_at?: string | null;
}
export interface ExamDetail extends Exam {
  question_paper: DocInfo | null;
  answer_key_document: DocInfo | null;
  question_count: number;
  verified_question_count: number;
  evaluation_count: number;
  finalized_count: number;
  /** the latest AI-generated paper for this exam (app/generation), if any */
  generation?: { id: string; status: "QUEUED" | "GENERATING" | "READY" | "FAILED"; stage: string | null;
                 error: string | null; question_count: number } | null;
}
export interface BBox {
  x: number;
  y: number;
  width: number;
  height: number;
}
export interface VisualEvidence {
  kind: "diagram" | "image" | "graph" | "map" | "table" | "formula" | "other";
  description: string;
  labels: string[];
  page_number: number;
  bbox: BBox;
}
export interface Question {
  id: string;
  display_number: string;
  normalized_number: string | null;
  question_text: string;
  raw_ocr_text: string;
  clean_question_text?: string;
  passage_text?: string | null;
  question_type: string | null;
  max_marks: number | null;
  section: string | null;
  position: number;
  choice_group?: string | null; // either/or alternatives share it ("34" for 34(அ) OR 34(ஆ)); a choice counts once
  answer_any?: number | null; // the section says "answer any N"; compulsory questions always count
  compulsory?: boolean;
  page_start: number | null;
  page_end?: number | null;
  bbox: BBox | null;
  has_crop: boolean;
  ocr_confidence: number | null;
  visuals?: VisualEvidence[];
  verification_status: "UNVERIFIED" | "VERIFIED" | "NEEDS_REVIEW";
  review_reason: string | null;
}
export interface SectionSummary {
  section: string;
  count: number;
  marks: number;
  answer_any?: number | null; // "answer any N" section: marks count its best N
}
export interface UnclassifiedBlock {
  page_number: number;
  label: string | null;
  text: string;
  bbox?: BBox | null;
}
export interface QuestionsResponse {
  questions: Question[];
  document_id: string | null;
  document_status?: string | null;
  document_stage?: string | null;
  exam_status?: string;
  can_verify?: boolean;
  sum_of_marks: number;
  exam_total_marks: number;
  marks_warning: string | null;
  locked: boolean;
  exam_name?: string | null;
  exam_subject?: string | null;
  exam_duration_minutes?: number | null;
  exam_instructions?: string | null;
  stated_question_count?: number | null;
  stated_printed_pages?: number | null;
  qp_code?: string | null;
  sections_summary?: SectionSummary[];
  unclassified_blocks?: UnclassifiedBlock[];
}
export interface AnswerKeyRow {
  id: string;
  raw_question_number: string | null;
  normalized_number: string | null;
  exam_question_id: string | null;
  answer_text: string;
  marks: number | null;
  criteria: string[];
  accepted_answers: string[];
  keywords: string[];
  page_number: number | null;
  bbox: BBox | null;
  has_crop: boolean;
  ocr_confidence: number | null;
  visuals?: VisualEvidence[];
  mapping_status: string;
  mapping_note: string | null;
  mapping_candidates: string[];
  mark_mismatch: boolean;
  verification_status: string;
  rubric: Rubric | null;
  rubric_status: "UNREVIEWED" | "CONFIRMED";
}
/** A question's marking rubric, built from its answer key (backend formatter build_rubric). */
export interface RubricPoint {
  id: string;
  marks: number | null;
  text: string;
  kind: "number" | "unit" | "equation" | "exact" | "meaning" | "criterion";
  part: string | null;
  expected: string[];
}
export interface Rubric {
  cbse_tree?: import("./standards").ScoringNode;
  kind: string;
  points: RubricPoint[];
  notes: string[];
  deductions: string[];
  problems: string[];
  stated_total: number | null;
  total: number;
}
export interface KeysResponse {
  keys: AnswerKeyRow[];
  document_id: string | null;
  locked: boolean;
  missing_question_ids: string[];
  questions: {
    id: string;
    display_number: string;
    max_marks: number | null;
    question_text: string;
  }[];
}
export interface GeneratedAnswerItem {
  exam_question_id: string;
  question_number: string;
  question_text: string;
  max_marks: number | null;
  answer_text: string;
  marks: number | null;
  criteria: string[];
  keywords: string[];
  accepted_answers: string[];
}
export interface Evaluation {
  id: string;
  exam_id: string;
  student: Student;
  status: string;
  run_status: string;
  run_progress: number;
  run_total: number;
  total_marks: number | null;
  maximum_marks: number | null;
  percentage: number | null;
  finalized_at: string | null;
  exam_name: string | null;
  created_at: string;
  class_id?: string | null;
  class_name?: string | null;
  subject_id?: string | null;
  subject_name?: string | null;
  document?: DocInfo | null;
  detected_answers?: number;
  unresolved_answers?: number;
}
export interface StudentAnswer {
  id: string;
  raw_question_number: string | null;
  normalized_number: string | null;
  exam_question_id: string | null;
  raw_ocr_text: string;
  answer_text: string;
  page_number: number | null;
  bbox: BBox | null;
  has_crop: boolean;
  ocr_confidence: number | null;
  status: string;
  mapping_note: string | null;
  mapping_candidates: string[];
  mapping_confirmed: boolean;
  edited: boolean;
  position?: number;
}

export interface EvalItem {
  id: string;
  exam_question_id: string;
  status: string;
  ai_marks: number | null;
  ai_decision: string | null;
  matched_points: string[];
  missing_points: string[];
  ai_feedback: string | null;
  ai_confidence: number | null;
  error: string | null;
  final_marks: number | null;
  teacher_overridden: boolean;
  teacher_feedback: string | null;
  not_attempted_confirmed: boolean;
  evidence_checked?: boolean;
  criterion_awards?: {
    id: string;
    marks: number;
    allocation?: number;
    counted?: boolean;
    credit_type?: string;
    scheme_quote?: string;
    evidence?: string;
    evidence_quotes?: string[];
  }[];
}
export interface Issue {
  question?: string | null;
  reason?: string;
  message?: string;
  code?: string;
  page?: number | null;
}
export interface EvalQuestion extends Question {
  official_answer: string | null;
  criteria: string[];
}
export interface EvaluationDetail {
  evaluation: Evaluation;
  exam: { id: string; name: string; status: string };
  document: DocInfo;
  questions: EvalQuestion[];
  answers: StudentAnswer[];
  items: EvalItem[];
  summary: {
    total_questions: number;
    mapped: number;
    suggested?: number;
    needs_review: number;
    unmapped: number;
    missing: number;
    ignored: number;
  };
  /** questions the student had to answer vs answers found on the sheet */
  coverage?: { required: number; answered: number; missing: string[] };
  issues: Issue[];
}
export interface ResultRow {
  question_id: string;
  question: string;
  question_text: string;
  max_marks: number | null;
  final_marks: number | null;
  ai_marks: number | null;
  teacher_overridden: boolean;
  student_answer: string | null;
  official_answer: string | null;
  feedback: string | null;
  status: string;
}
export interface ResultResponse {
  finalized: boolean;
  evaluation: Evaluation;
  exam: { id: string; name: string; subject: string; class: string };
  total_marks: number;
  maximum_marks: number;
  percentage: number;
  questions: ResultRow[];
}
export interface AuditRow {
  id: string;
  entity_type: string;
  action: string;
  old_value: unknown;
  new_value: unknown;
  reason: string | null;
  user: string | null;
  created_at: string;
}
export interface Dashboard {
  total_classes: number;
  total_subjects: number;
  total_exams: number;
  total_students: number;
  pending_evaluations: number;
  completed_evaluations: number;
  /** School cards. credits is null while credits are unlimited (no payment gateway yet). */
  credits: number | null;
  pending_review: number;
  evaluated_sheets: number;
  recent_exams: Exam[];
  recent_evaluations: Evaluation[];
}

export interface SchoolProfile {
  name: string;
  address: string;
  principal_name: string;
  has_logo: boolean;
  active_report_template: string;
  active_card_template: string;
}
export type TemplateKind = "report" | "report_card";
export interface Toggle {
  id: string;
  visible: boolean;
}
export interface TemplateConfig {
  sections: Toggle[];
  columns: Toggle[];
  summary: Toggle[];
  labels: Record<string, string>;
  style: {
    accent: string;
    font: string;
    font_size: number;
    logo_size: number;
    logo_position: string;
    borders: string;
    zebra: boolean;
    paper: string;
  };
  text: { footer: string; note: string };
  signers: string[];
}
export interface ReportTemplate {
  id: string;
  name: string;
  preset: boolean;
  config: TemplateConfig;
}
export interface ReportCardTerm {
  term: string;
  academic_year: string;
  exam_type: string;
  subjects: string[];
}

export interface CatalogSubject {
  key: string;
  name: string;
  profiles: string[];
  /** choices the subject's board pattern needs at creation, e.g. Accountancy's Part B option */
  options?: { key: string; label: string; choices: { value: string; label: string }[] }[];
}

export interface UploaderCode {
  id: string;
  code: string;
  label: string | null;
  uploader_name: string | null;
  is_active: boolean;
  created_at: string | null;
  uploads: number;
}

export interface UploaderSession {
  exam: { id: string; name: string; class_name: string | null; subject: string | null; exam_date: string | null };
  label: string | null;
  uploader_name: string | null;
  uploads: {
    id: string; original_filename: string; status: string; stage: string | null; uploaded_at: string; pages: number;
    /** typed for scanned sheets; null for bulk files (read from the sheet) */
    roll_number?: string | null;
    /** why a sheet is held for review (e.g. cover page roll number or page count differs) */
    note?: string | null;
  }[];
}

export interface StudentTerm {
  term: string;
  academic_year: string;
  subjects: number;
  finalized: number;
}

/** A sheet being scanned page by page (POST /uploader/sheets). */
export interface ScanSheet {
  id: string;
  roll_number: string;
  pages: number;
  status: string;
}
