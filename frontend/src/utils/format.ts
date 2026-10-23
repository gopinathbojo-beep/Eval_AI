export type Tone = "ok" | "warn" | "mark" | "pen" | "mute";

const TONES: Record<string, Tone> = {
  VERIFIED: "ok", MAPPED: "ok", APPROVED: "ok", FINALIZED: "ok", READY: "ok", EVALUATED: "pen", DONE: "ok",
  FINALIZABLE: "ok", AI_EVALUATED: "pen", TEACHER_REVIEW: "pen", OK: "ok",
  UNVERIFIED: "mute", PENDING: "mute", UPLOADED: "mute", DRAFT: "mute", IDLE: "mute", IGNORED: "mute",
  NEEDS_REVIEW: "mark", UNMAPPED: "mark", MISSING: "warn", EVALUATION_ERROR: "mark", AI_ERROR: "mark", FAILED: "mark",
  FAILED_PARSE: "mark", NEEDS_ATTENTION: "warn", MAPPING_REVIEW: "warn", OCR_REVIEW: "warn", REVIEW_REQUIRED: "warn",
  RENDERING: "pen", OCR_PROCESSING: "pen", EXTRACTING: "pen", EVALUATING: "pen", RUNNING: "pen", ERROR: "mark",
  CANCELLED: "warn", WAITING: "mute", IDENTIFYING: "pen", NEEDS_STUDENT: "warn",
};
export const toneOf = (s: string | null | undefined): Tone => (s ? TONES[s] ?? "pen" : "mute");
// status codes keep their names; only the words shown to teachers change
const LABELS: Record<string, string> = {
  OCR_PROCESSING: "Reading pages", OCR_REVIEW: "Transcription review", WAITING: "Waiting for verified questions",
  IDENTIFYING: "Identifying student", NEEDS_STUDENT: "Needs student", AI_EVALUATED: "Evaluated",
};
export const label = (s: string | null | undefined) =>
  (s && LABELS[s]) || (s ?? "").toLowerCase().replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase())
    .replace(/\bai\b/gi, "AI");
export const BUSY_DOC = ["UPLOADED", "RENDERING", "OCR_PROCESSING", "EXTRACTING", "IDENTIFYING"];
export const K_LEVELS: { key: string; label: string }[] = [
  { key: "K1", label: "Remember" }, { key: "K2", label: "Understand" }, { key: "K3", label: "Apply" },
  { key: "K4", label: "Analyse" }, { key: "K5", label: "Evaluate" }, { key: "K6", label: "Create" },
];
export const kLabel = (k: string | null | undefined) => (k && K_LEVELS.find((l) => l.key === k)?.label) || k || "–";
export const fmt = (n: number | null | undefined) => (n === null || n === undefined ? "–" : Number.isInteger(n) ? String(n) : n.toFixed(1));
export const pct = (c: number | null) => (c === null ? "–" : `${Math.round(c * 100)}%`);
export const date = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : "–");

export const EXAM_STEPS: { key: string; label: string }[] = [
  { key: "DRAFT", label: "Draft" }, { key: "QUESTION_PAPER_UPLOADED", label: "Paper uploaded" },
  { key: "QUESTIONS_EXTRACTED", label: "Questions read" }, { key: "QUESTIONS_VERIFIED", label: "Questions verified" },
  { key: "ANSWER_KEY_UPLOADED", label: "Key uploaded" }, { key: "ANSWER_KEY_VERIFIED", label: "Key verified" },
  { key: "READY_FOR_EVALUATION", label: "Ready" }, { key: "EVALUATING", label: "Evaluating" },
  { key: "REVIEW_REQUIRED", label: "In review" }, { key: "FINALIZED", label: "Finalized" },
];
