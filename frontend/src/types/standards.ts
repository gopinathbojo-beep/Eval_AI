export interface StandardProfile {
  id: string;
  version: string;
  class_level: number;
  code: string;
  name: string;
  duration_minutes: number;
  total_marks: number;
  question_count: number;
  upload_driven: boolean;
  subject_ids: string[];
  sections: { key: string; start: number; end: number; marks: number }[];
}
export interface ScoringNode {
  id: string;
  kind: "all" | "choose" | "point" | "context";
  label: string;
  text: string;
  marks: number | null;
  limit: number | null;
  audience: string | null;
  children: ScoringNode[];
  deductions?: { id: string; maximum: number; text: string }[];
  choice_type?: "question" | "method";
  response_type?: "open" | "mcq";
}
