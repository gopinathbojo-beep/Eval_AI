export interface Teacher {
  id: string;
  name: string;
  email: string;
}

export interface ClassRow {
  id: string;
  name: string;
  student_count: number;
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
}

export interface Exam {
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
}

export interface ExamDetail extends Exam {
  question_paper: DocInfo | null;
  answer_key_document: DocInfo | null;
  question_count: number;
  verified_question_count: number;
  evaluation_count: number;
  finalized_count: number;
}

export interface BBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Question {
  id: string;
  display_number: string;
  normalized_number: string | null;
  question_text: string;
  raw_ocr_text: string;
  question_type: string | null;
  max_marks: number | null;
  section: string | null;
  position: number;
  page_start: number | null;
  bbox: BBox | null;
  has_crop: boolean;
  ocr_confidence: number | null;
  verification_status: "UNVERIFIED" | "VERIFIED" | "NEEDS_REVIEW";
  review_reason: string | null;
}

export interface QuestionsResponse {
  questions: Question[];
  document_id: string | null;
  sum_of_marks: number;
  exam_total_marks: number;
  marks_warning: string | null;
  locked: boolean;
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
  mapping_status: string;
  mapping_note: string | null;
  mapping_candidates: string[];
  mapping_candidate_details: CandidateDetail[];
  mapping_confirmed: boolean;
  mark_mismatch: boolean;
  verification_status: string;
}

export interface KeysResponse {
  keys: AnswerKeyRow[];
  document_id: string | null;
  locked: boolean;
  missing_question_ids: string[];
  questions: { id: string; display_number: string; max_marks: number | null; question_text: string }[];
}

export interface AnswerKeyValidationIssue {
  key_id: string | null;
  question: string;
  reason: string;
  issue_type: "ocr_failed" | "unmapped" | "needs_review" | "empty_solution" | "mark_mismatch" | "unapproved" | "missing_key" | "duplicate_mapping";
}

export interface AnswerKeyValidationResponse {
  valid: boolean;
  summary: {
    total_processed?: number;
    total_keys: number;
    total_questions: number;
    verified_count: number;
    needs_review_count: number;
    failed_count?: number;
    blocking_issues_count: number;
  };
  blocking_issues: AnswerKeyValidationIssue[];
  issues: { question: string; reason: string }[];
}

export interface VerifyAllResponse extends AnswerKeyValidationResponse {
  keys: AnswerKeyRow[];
  questions?: { id: string; display_number: string; max_marks: number | null; question_text: string }[];
  missing_question_ids?: string[];
  locked?: boolean;
  all_verified?: boolean;
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
  mapping_candidate_details: CandidateDetail[];
  mapping_confirmed: boolean;
  edited: boolean;
}

export interface CandidateDetail {
  id: string;
  num: string | null;
  score: number;
  reason: string;
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
}

export interface Issue {
  question: string;
  reason: string;
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
    missing_question_ids?: string[];
  };
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
  recent_exams: Exam[];
  recent_evaluations: Evaluation[];
}
