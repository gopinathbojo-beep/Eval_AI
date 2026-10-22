import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useApi } from "../hooks/useApi";
import type { EvalItem, EvalQuestion, EvaluationDetail, StudentAnswer } from "../types";
import { fmt, label, pct, BUSY_DOC } from "../utils/format";
import {
  Badge,
  Button,
  Card,
  Confirm,
  Empty,
  ErrorPanel,
  Field,
  Input,
  Loading,
  MathTextarea,
  MathView,
  Modal,
  PageHeader,
  PenScore,
  ProgressBar,
  Select,
  Stat,
  StatusBadge,
  Textarea,
} from "../components/ui";
import { PageViewer } from "../components/PageViewer";
import { AuthImage } from "../components/AuthImage";
import { DocProgress } from "../components/DocPanel";
import {
  IconCheck,
  IconCheckCircle,
  IconEdit,
  IconSplit,
  IconMerge,
  IconSparkles,
  IconFileText,
  IconAlertCircle,
  IconAlertTriangle,
  IconRotateCcw,
  IconEye,
  IconChevronRight,
  IconX,
} from "../components/Icons";

type Tab = "mapping" | "marks";
const FILTERS = ["All", "Mapped", "Suggested", "Needs review", "Unmapped", "Missing", "Read error"] as const;

export default function EvaluationPage() {
  const { id } = useParams();
  const { data, error, loading, reload } = useApi<EvaluationDetail>(
    `/evaluations/${id}`,
    (d) => (d.evaluation.run_status === "RUNNING" || BUSY_DOC.includes(d.document.status) ? 1500 : null)
  );
  const [tab, setTab] = useState<Tab>("mapping");

  if (loading) return <Loading text="Loading evaluation workspace..." />;
  if (error || !data) return <ErrorPanel error={error} />;

  const ev = data.evaluation;
  const reading = BUSY_DOC.includes(data.document.status);

  return (
    <div className="space-y-5">
      {/* Page Header */}
      <PageHeader
        title={
          <div className="flex flex-wrap items-center gap-2.5">
            <span>{ev.student.name}</span>
            <span className="stamp rotate-[-2deg] border-pen/40 px-2 py-0.5 font-mono text-[11px] text-pen">
              Roll {ev.student.roll_number}
            </span>
          </div>
        }
        sub={
          <div className="flex items-center gap-2 text-sm text-mute">
            <span>{data.exam.name}</span>
            <span>•</span>
            <Link
              className="text-pen font-medium hover:underline flex items-center gap-1"
              to={`/exams/${ev.exam_id}/answer-sheets`}
            >
              <span>Back to answer sheets</span>
            </Link>
          </div>
        }
        actions={
          <div className="flex items-center gap-2">
            <StatusBadge status={ev.status} />
          </div>
        }
      />

      {/* OCR Ingestion Progress if document is still processing */}
      {(reading || data.document.status !== "READY") && (
        <DocProgress
          doc={data.document}
          onChanged={reload}
          canRetry={ev.status !== "FINALIZED" && data.items.length === 0}
          rebuildWarning="Reading again rebuilds the detected answers for this sheet. Edits and mapping decisions will be lost."
        />
      )}

      {/* Main Tabs Navigation */}
      {!reading && (
        <div className="space-y-4">
          {/* stays at the top of the page while scrolling */}
          <div className="sticky top-0 z-30 -mx-1 flex h-12 items-end gap-1.5 border-b border-line bg-paper/95 px-2 backdrop-blur">
            <button
              onClick={() => setTab("mapping")}
              className={`-mb-px flex items-center gap-2 rounded-t-md border px-4 py-2.5 text-sm font-semibold transition-ui ${
                tab === "mapping"
                  ? "border-line border-b-surface border-t-2 border-t-pen bg-surface text-ink"
                  : "border-transparent text-mute hover:bg-hover hover:text-brown"
              }`}
            >
              <IconFileText size={16} />
              <span>1. Mapping Review</span>
              {data.summary.needs_review > 0 && (
                <span className="rounded-full bg-warn-soft px-1.5 py-0.2 text-[11px] font-bold text-warn">
                  {data.summary.needs_review}
                </span>
              )}
            </button>
            <button
              onClick={() => setTab("marks")}
              className={`-mb-px flex items-center gap-2 rounded-t-md border px-4 py-2.5 text-sm font-semibold transition-ui ${
                tab === "marks"
                  ? "border-line border-b-surface border-t-2 border-t-pen bg-surface text-ink"
                  : "border-transparent text-mute hover:bg-hover hover:text-brown"
              }`}
            >
              <IconCheckCircle size={16} />
              <span>2. Marks & Finalize</span>
              {data.items.length > 0 && (
                <span className="rounded-full bg-pen-soft px-1.5 py-0.2 text-[11px] font-bold text-pen">
                  {data.items.filter((i) => i.status === "APPROVED").length}/{data.questions.length}
                </span>
              )}
            </button>
          </div>

          {tab === "mapping" ? (
            <MappingTab d={data} reload={reload} />
          ) : (
            <MarksTab d={data} reload={reload} />
          )}
        </div>
      )}
    </div>
  );
}

function MappingTab({ d, reload }: { d: EvaluationDetail; reload: () => Promise<void> }) {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("All");
  const [page, setPage] = useState(1);
  const [sel, setSel] = useState<string | null>(null);
  const [dlg, setDlg] = useState<StudentAnswer | null>(null);
  const [splitAns, setSplitAns] = useState<StudentAnswer | null>(null);
  const [mergeAns, setMergeAns] = useState<StudentAnswer | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState<string | null>(null);
  // Responsive mode on tablet/mobile: "document" vs "mappings"
  const [mobileView, setMobileView] = useState<"both" | "sheet" | "answers">("both");

  const locked = d.evaluation.status === "FINALIZED";
  const qmap = new Map(d.questions.map((q) => [q.id, q]));
  const answered = new Set(
    d.answers.filter((a) => a.status !== "IGNORED" && a.exam_question_id).map((a) => a.exam_question_id)
  );
  const missing = d.questions.filter((q) => !answered.has(q.id));
  const ocrErrors = d.document.pages.filter((p) => p.ocr_status !== "OK");

  const rows = d.answers.filter((a) => {
    switch (filter) {
      case "Mapped":
        return ["MAPPED", "EVALUATING", "EVALUATED", "APPROVED"].includes(a.status);
      case "Suggested":
        return a.status === "NEEDS_REVIEW" && a.mapping_candidates.length > 0;
      case "Unmapped":
        return a.status === "UNMAPPED";
      case "Needs review":
        return a.status === "NEEDS_REVIEW";
      case "Missing":
      case "Read error":
        return false;
      default:
        return true;
    }
  });

  const act = async (a: StudentAnswer, json: object, key: string) => {
    setBusy(a.id + key);
    setErr(null);
    try {
      await api(`/evaluations/${d.evaluation.id}/mapping/${a.id}`, { method: "PATCH", json });
      await reload();
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(null);
    }
  };
  const selected = d.answers.find((a) => a.id === sel);

  const unconfirmed = d.answers.filter(
    (a) => a.status === "MAPPED" && a.exam_question_id && !a.mapping_confirmed
  );

  const confirmAll = async () => {
    setBusy("all:c");
    setErr(null);
    try {
      await api(`/evaluations/${d.evaluation.id}/confirm-all-mappings`, { method: "POST" });
      await reload();
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(null);
    }
  };

  // Helper count badges for each filter
  const getFilterCount = (f: (typeof FILTERS)[number]) => {
    switch (f) {
      case "All":
        return d.answers.length;
      case "Mapped":
        return d.summary.mapped;
      case "Suggested":
        return d.summary.suggested ?? 0;
      case "Needs review":
        return d.summary.needs_review;
      case "Missing":
        return d.summary.missing;
      case "Read error":
        return ocrErrors.length;
      case "Unmapped":
        return d.answers.filter((a) => a.status === "UNMAPPED").length;
    }
  };

  return (
    <div className="space-y-4">
      {/* Question Mapping Metrics */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Total Questions" value={d.summary.total_questions} />
        <Stat label="Mapped" value={d.summary.mapped} tone="ok" />
        <Stat
          label="Suggested"
          value={d.summary.suggested ?? 0}
          tone={d.summary.suggested ? "pen" : "mute"}
        />
        <Stat
          label="Needs Review"
          value={d.summary.needs_review}
          tone={d.summary.needs_review ? "warn" : "mute"}
        />
        <Stat
          label="Missing Answers"
          value={d.summary.missing}
          tone={d.summary.missing ? "mark" : "mute"}
        />
        <Stat
          label="Read Errors"
          value={ocrErrors.length}
          tone={ocrErrors.length ? "mark" : "mute"}
        />
      </div>

      {/* Filters Toolbar and Bulk Actions */}
      <div className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-3 sm:flex-row sm:items-center sm:justify-between shadow-xs">
        {/* Filter Pills with Counts */}
        <div className="flex flex-wrap items-center gap-1.5" role="tablist" aria-label="Filter answers">
          {FILTERS.map((f) => {
            const count = getFilterCount(f);
            const active = filter === f;
            return (
              <button
                key={f}
                role="tab"
                aria-selected={active}
                onClick={() => setFilter(f)}
                className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-ui ${
                  active
                    ? "bg-pen text-white shadow-xs"
                    : "bg-sunken text-ink hover:bg-hover"
                }`}
              >
                <span>{f}</span>
                <span
                  className={`rounded-full px-1.5 py-0.2 text-[10px] font-bold ${
                    active ? "bg-white/20 text-white" : "bg-line/60 text-mute"
                  }`}
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Bulk approval button & mobile view switcher */}
        <div className="flex items-center gap-2">
          {/* Mobile view switcher */}
          <div className="flex items-center rounded-lg border border-line bg-sunken p-0.5 lg:hidden text-xs">
            <button
              onClick={() => setMobileView("sheet")}
              className={`rounded px-2.5 py-1 font-medium ${
                mobileView === "sheet" ? "bg-surface shadow-xs text-pen" : "text-mute"
              }`}
            >
              Scan
            </button>
            <button
              onClick={() => setMobileView("both")}
              className={`rounded px-2.5 py-1 font-medium ${
                mobileView === "both" ? "bg-surface shadow-xs text-pen" : "text-mute"
              }`}
            >
              Both
            </button>
            <button
              onClick={() => setMobileView("answers")}
              className={`rounded px-2.5 py-1 font-medium ${
                mobileView === "answers" ? "bg-surface shadow-xs text-pen" : "text-mute"
              }`}
            >
              Cards
            </button>
          </div>

          {!locked && unconfirmed.length > 0 && (
            <Button
              small
              variant="primary"
              busy={busy === "all:c"}
              onClick={confirmAll}
              icon={<IconCheckCircle size={15} />}
            >
              Approve All Mappings ({unconfirmed.length})
            </Button>
          )}
        </div>
      </div>

      <ErrorPanel error={err} />

      {/* Main 2-Panel Workspace */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Left Panel: Original Answer Sheet Scan */}
        <div
          className={`h-[calc(100vh-17rem)] min-h-[30rem] overflow-hidden rounded-lg border border-line bg-surface shadow-sm ${
            mobileView === "answers" ? "hidden lg:block" : "block"
          }`}
        >
          <PageViewer
            kind="answer-sheet"
            docId={d.document.id}
            pages={d.document.pages}
            page={page}
            onPage={setPage}
            highlight={selected?.page_number === page ? selected.bbox : null}
          />
        </div>

        {/* Right Panel: Detected Answers and Mappings */}
        <div
          className={`h-[calc(100vh-17rem)] min-h-[30rem] space-y-3 overflow-y-auto pr-1 ${
            mobileView === "sheet" ? "hidden lg:block" : "block"
          }`}
        >
          {filter === "Missing" &&
            (missing.length ? (
              missing.map((q) => (
                <Card key={q.id} className="border-l-4 border-l-warn border-line p-4 space-y-2">
                  <div className="flex items-center gap-2">
                    <IconAlertTriangle size={16} className="text-warn" />
                    <p className="font-semibold text-ink">
                      Question {q.display_number}: No answer detected in document
                    </p>
                  </div>
                  <div className="doc-text line-clamp-3 text-xs text-mute bg-sunken/60 rounded-lg p-2.5">
                    <MathView text={q.question_text} />
                  </div>
                  <p className="text-xs text-mute">
                    If it was answered, find it on the scan and use "Edit Text & Mapping" to link it.
                  </p>
                </Card>
              ))
            ) : (
              <Empty title="No missing answers" hint="All examination questions have at least one mapped answer." />
            ))}

          {filter === "Read error" &&
            (ocrErrors.length ? (
              ocrErrors.map((p) => (
                <Card key={p.page_number} className="border-l-4 border-l-mark border-line p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="font-semibold text-mark">Page {p.page_number}: Processing Issue</p>
                    <StatusBadge status={p.ocr_status} />
                  </div>
                  <p className="text-sm text-mute">{p.ocr_error || "Failed to process text on this page scan."}</p>
                </Card>
              ))
            ) : (
              <Empty title="No read errors" hint="Every uploaded page scan was read successfully." />
            ))}

          {!["Missing", "Read error"].includes(filter) &&
            (rows.length === 0 ? (
              <Empty
                title="No answers match this filter"
                hint="Try selecting 'All' to review all detected student answer cards."
              />
            ) : (
              rows.map((a) => {
                const q = a.exam_question_id ? qmap.get(a.exam_question_id) : undefined;
                const topCandId = a.mapping_candidates?.[0];
                const topCand = topCandId ? qmap.get(topCandId) : undefined;
                const needs = a.status === "UNMAPPED" || a.status === "NEEDS_REVIEW";
                const isSelected = sel === a.id;

                return (
                  <Card
                    key={a.id}
                    className={`p-4 transition-ui ${
                      isSelected ? "ring-2 ring-pen shadow-md" : "hover:border-line"
                    } ${needs ? "border-l-4 border-l-warn" : "border-l-4 border-l-ok"} ${
                      a.status === "IGNORED" ? "opacity-60 bg-sunken/30" : ""
                    }`}
                  >
                    {/* Clickable Header for Card selection */}
                    <button
                      className="block w-full text-left"
                      onClick={() => {
                        setSel(a.id);
                        if (a.page_number) setPage(a.page_number);
                      }}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-ink">
                            Student wrote:{" "}
                            <span className="font-mono text-pen bg-pen-soft px-1.5 py-0.5 rounded">
                              {a.raw_question_number ?? "no number"}
                            </span>
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {topCand && a.status === "NEEDS_REVIEW" && (
                            <Badge tone="pen">
                              Suggested: Q{topCand.display_number}
                            </Badge>
                          )}
                          <span className="rounded-md bg-sunken px-2 py-0.5 text-xs font-medium text-mute">
                            p.{a.page_number}
                          </span>
                          <span className="rounded-md bg-sunken px-2 py-0.5 text-xs font-medium text-mute">
                            conf. {pct(a.ocr_confidence)}
                          </span>
                          <StatusBadge status={a.status} />
                        </div>
                      </div>

                      {/* Target Mapped Question Banner */}
                      <div className="mt-2.5 rounded-lg border border-line/60 bg-sunken/40 px-3 py-2 text-xs">
                        {q ? (
                          <div className="flex items-baseline gap-1.5 text-ink">
                            <span className="font-semibold text-pen shrink-0">
                              Mapped to Question {q.display_number}:
                            </span>
                            <span className="truncate text-mute">{q.question_text.slice(0, 85)}</span>
                          </div>
                        ) : (
                          <span className="font-semibold text-mark flex items-center gap-1">
                            <IconAlertCircle size={14} />
                            Not mapped to any question
                          </span>
                        )}
                      </div>

                      {/* Mapping Note / Issue if Needs Review */}
                      {a.mapping_note && needs && (
                        <p className="mt-2 text-xs font-semibold text-warn flex items-center gap-1.5">
                          <IconAlertTriangle size={14} />
                          {a.mapping_note}
                        </p>
                      )}

                      {/* Extracted Student Answer Text */}
                      <div className="doc-text mt-2.5 line-clamp-4 rounded-lg border border-line/40 bg-surface p-2.5 text-sm text-ink/90 leading-relaxed">
                        {a.answer_text ? (
                          <MathView text={a.answer_text} />
                        ) : (
                          <em className="text-mute font-normal">No text transcribed</em>
                        )}
                      </div>

                      {a.edited && (
                        <p className="mt-1.5 text-[11px] text-mute flex items-center gap-1">
                          <IconEdit size={12} className="text-pen" />
                          Edited by teacher (original transcription retained in audit).
                        </p>
                      )}
                    </button>

                    {/* What the model read: Approximate Crop Preview */}
                    {isSelected && a.has_crop && (
                      <div className="mt-3 rounded-lg border border-line bg-sunken/60 p-2.5 animate-fadeIn">
                        <p className="mb-1 text-xs font-medium text-mute flex items-center gap-1">
                          <IconEye size={13} />
                          What the model read (approximate crop):
                        </p>
                        <AuthImage
                          path={`/crops/student-answer/${a.id}`}
                          alt="Crop of detected answer"
                          className="max-h-44 rounded border border-line/60 bg-surface object-contain"
                        />
                      </div>
                    )}

                    {/* Actions Toolbar — Consolidated, Consistent Controls */}
                    {!locked && (
                      <div className="mt-3.5 flex flex-wrap items-center gap-1.5 border-t border-line/60 pt-3">
                        {a.status === "IGNORED" ? (
                          <Button
                            small
                            variant="secondary"
                            onClick={() => act(a, { restore: true }, "r")}
                            busy={busy === a.id + "r"}
                            icon={<IconRotateCcw size={13} />}
                          >
                            Restore Answer
                          </Button>
                        ) : (
                          <>
                            {topCand && a.status === "NEEDS_REVIEW" && (
                              <Button
                                small
                                variant="primary"
                                busy={busy === a.id + "s"}
                                onClick={() => act(a, { accept_suggestion: true }, "s")}
                                icon={<IconCheck size={14} />}
                              >
                                Accept Suggestion (Q{topCand.display_number})
                              </Button>
                            )}

                            {/* Consolidated single Edit Text & Mapping button */}
                            <Button
                              small
                              variant="secondary"
                              onClick={() => setDlg(a)}
                              icon={<IconEdit size={13} />}
                              title="Edit transcribed text or change the mapped question"
                            >
                              Edit Text & Mapping
                            </Button>

                            <Button
                              small
                              variant="secondary"
                              onClick={() => setSplitAns(a)}
                              icon={<IconSplit size={13} />}
                              title="Split this answer into two questions"
                            >
                              Split
                            </Button>

                            <Button
                              small
                              variant="secondary"
                              onClick={() => setMergeAns(a)}
                              icon={<IconMerge size={13} />}
                              title="Merge with another detected answer card"
                            >
                              Merge
                            </Button>

                            <Button
                              small
                              variant="ghost"
                              busy={busy === a.id + "i"}
                              onClick={() => act(a, { ignore: true }, "i")}
                              className="text-mute hover:text-mark"
                              title="Ignore this detected block"
                            >
                              Ignore
                            </Button>
                          </>
                        )}
                      </div>
                    )}
                  </Card>
                );
              })
            ))}
        </div>
      </div>

      {/* Modals for Editing, Splitting, Merging */}
      {dlg && <MapDlg a={dlg} d={d} onClose={() => setDlg(null)} onDone={reload} />}
      {splitAns && (
        <SplitAnswerModal
          a={splitAns}
          evId={d.evaluation.id}
          onClose={() => setSplitAns(null)}
          onDone={reload}
        />
      )}
      {mergeAns && (
        <MergeAnswerModal
          a={mergeAns}
          evId={d.evaluation.id}
          allAnswers={d.answers}
          onClose={() => setMergeAns(null)}
          onDone={reload}
        />
      )}
    </div>
  );
}

function MapDlg({
  a,
  d,
  onClose,
  onDone,
}: {
  a: StudentAnswer;
  d: EvaluationDetail;
  onClose: () => void;
  onDone: () => Promise<void>;
}) {
  const [qid, setQid] = useState(a.exam_question_id ?? "");
  const [label_, setLabel] = useState(a.raw_question_number ?? "");
  const [text, setText] = useState(a.answer_text);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const hint = new Set(a.mapping_candidates);

  const save = async () => {
    setBusy(true);
    setErr(null);
    const json: Record<string, unknown> = { reason: reason || undefined };
    if (text !== a.answer_text) json.answer_text = text;
    if (qid && qid !== a.exam_question_id) json.exam_question_id = qid;
    else if (label_ !== (a.raw_question_number ?? "")) json.raw_question_number = label_;

    try {
      await api(`/evaluations/${d.evaluation.id}/mapping/${a.id}`, { method: "PATCH", json });
      await onDone();
      onClose();
    } catch (e) {
      setErr(e);
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Edit Text & Question Mapping"
      wide
      onClose={onClose}
      icon={<IconEdit className="text-pen" size={20} />}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" busy={busy} onClick={save} icon={<IconCheck size={16} />}>
            Save Mapping
          </Button>
        </>
      }
    >
      <div className="grid gap-6 md:grid-cols-2">
        {/* Source document crop / page */}
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wider text-mute">
            Source Document Scan (Page {a.page_number})
          </p>
          <div className="h-80 overflow-hidden rounded-lg border border-line bg-sunken/40 shadow-xs">
            {a.page_number && (
              <PageViewer
                kind="answer-sheet"
                docId={d.document.id}
                pages={d.document.pages}
                page={a.page_number}
                onPage={() => {}}
                highlight={a.bbox}
              />
            )}
          </div>
        </div>

        {/* Form fields */}
        <div className="space-y-4">
          <Field
            label="Detected Question Label"
            hint="The label the student wrote (e.g. Q1, 7(a))"
          >
            {(id) => (
              <Input
                id={id}
                value={label_}
                placeholder="e.g. Q8, 2(b)"
                onChange={(e) => setLabel(e.target.value)}
              />
            )}
          </Field>

          <Field
            label="Target Exam Question"
            hint={hint.size ? "Suggested matches are highlighted with ★" : undefined}
          >
            {(id) => (
              <Select id={id} value={qid} onChange={(e) => setQid(e.target.value)}>
                <option value="">Not mapped to any question</option>
                {[...d.questions]
                  .sort(
                    (x, y) =>
                      Number(hint.has(y.id)) - Number(hint.has(x.id)) || x.position - y.position
                  )
                  .map((q: EvalQuestion) => (
                    <option key={q.id} value={q.id}>
                      {hint.has(q.id) ? "★ " : ""}Question {q.display_number} — {q.question_text.slice(0, 50)}
                    </option>
                  ))}
              </Select>
            )}
          </Field>

          <Field label="Transcribed Answer Text (incl. Math)">
            {(id) => <MathTextarea id={id} rows={6} value={text} onChange={setText} />}
          </Field>

          <Field label="Correction Reason (Optional)" hint="Logged in the permanent audit trail">
            {(id) => (
              <Input
                id={id}
                placeholder="e.g. Corrected misrecognized subquestion label"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            )}
          </Field>

          <ErrorPanel error={err} />
        </div>
      </div>
    </Modal>
  );
}

function SplitAnswerModal({
  a,
  evId,
  onClose,
  onDone,
}: {
  a: StudentAnswer;
  evId: string;
  onClose: () => void;
  onDone: () => Promise<void>;
}) {
  const [pos, setPos] = useState(Math.floor(a.answer_text.length / 2));
  const [lbl, setLbl] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const head = a.answer_text.slice(0, pos);
  const tail = a.answer_text.slice(pos);

  const save = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api(`/evaluations/${evId}/answers/${a.id}/split`, {
        method: "POST",
        json: { at_char: pos, new_label: lbl },
      });
      await onDone();
      onClose();
    } catch (e) {
      setErr(e);
      setBusy(false);
    }
  };

  return (
    <Modal
      title={`Split Answer Block “${a.raw_question_number ?? "no number"}”`}
      wide
      onClose={onClose}
      icon={<IconSplit size={20} className="text-pen" />}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            busy={busy}
            disabled={pos <= 0 || !lbl.trim()}
            onClick={save}
            icon={<IconCheck size={16} />}
          >
            Split Here
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <p className="text-sm text-mute">
          Drag the slider to choose where to split. The second part becomes a new answer.
        </p>

        <Field label="Question Number for Second Answer (e.g. Q8(b) or 9)" required>
          {(id) => (
            <Input
              id={id}
              placeholder="e.g. Q8(b)"
              value={lbl}
              onChange={(e) => setLbl(e.target.value)}
            />
          )}
        </Field>

        <div className="space-y-1.5 rounded-lg border border-line bg-sunken/40 p-4">
          <div className="flex items-center justify-between text-xs text-mute font-medium">
            <span>Split slider position</span>
            <span className="font-mono text-pen font-bold">
              Character {pos} of {a.answer_text.length}
            </span>
          </div>
          <input
            type="range"
            min={1}
            max={Math.max(1, a.answer_text.length - 1)}
            value={pos}
            onChange={(e) => setPos(Number(e.target.value))}
            className="w-full accent-pen cursor-pointer"
          />
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-line bg-surface p-3.5 text-xs shadow-xs">
            <p className="mb-1.5 font-bold uppercase tracking-wider text-pen">
              Kept in Current Answer ({a.raw_question_number ?? "none"})
            </p>
            <div className="doc-text max-h-40 overflow-y-auto whitespace-pre-wrap font-mono text-xs text-ink/90 bg-sunken/30 rounded p-2">
              {head}
            </div>
          </div>
          <div className="rounded-lg border border-line bg-sunken/60 p-3.5 text-xs shadow-xs">
            <p className="mb-1.5 font-bold uppercase tracking-wider text-ok">
              New Answer ({lbl || "..."})
            </p>
            <div className="doc-text max-h-40 overflow-y-auto whitespace-pre-wrap font-mono text-xs text-ink/90 bg-surface rounded p-2">
              {tail}
            </div>
          </div>
        </div>

        <ErrorPanel error={err} />
      </div>
    </Modal>
  );
}

function MergeAnswerModal({
  a,
  evId,
  allAnswers,
  onClose,
  onDone,
}: {
  a: StudentAnswer;
  evId: string;
  allAnswers: StudentAnswer[];
  onClose: () => void;
  onDone: () => Promise<void>;
}) {
  const [otherId, setOtherId] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const others = allAnswers.filter((x) => x.id !== a.id && x.status !== "IGNORED");

  const save = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api(`/evaluations/${evId}/answers/${a.id}/merge`, {
        method: "POST",
        json: { other_id: otherId },
      });
      await onDone();
      onClose();
    } catch (e) {
      setErr(e);
      setBusy(false);
    }
  };

  return (
    <Modal
      title={`Merge Answer Block “${a.raw_question_number ?? "no number"}”`}
      onClose={onClose}
      icon={<IconMerge size={20} className="text-pen" />}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            busy={busy}
            disabled={!otherId}
            onClick={save}
            icon={<IconCheck size={16} />}
          >
            Confirm Merge
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <p className="text-sm text-mute leading-relaxed">
          Add another answer's text to this one. The other answer is removed.
        </p>

        <Field label="Select Answer Block to Merge Into This One" required>
          {(id) => (
            <Select id={id} value={otherId} onChange={(e) => setOtherId(e.target.value)}>
              <option value="">Choose an answer...</option>
              {others.map((x) => (
                <option key={x.id} value={x.id}>
                  Answer {x.raw_question_number ?? "(no number)"} (p.{x.page_number}) — {x.answer_text.slice(0, 50)}
                </option>
              ))}
            </Select>
          )}
        </Field>

        <ErrorPanel error={err} />
      </div>
    </Modal>
  );
}

function MarksTab({ d, reload }: { d: EvaluationDetail; reload: () => Promise<void> }) {
  const nav = useNavigate();
  const ev = d.evaluation;
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [edit, setEdit] = useState<{ q: EvalQuestion; item: EvalItem } | null>(null);
  const [confirmFinalize, setConfirmFinalize] = useState(false);

  const items = new Map(d.items.map((i) => [i.exam_question_id, i]));
  const ans = new Map(
    d.answers
      .filter((a) => a.exam_question_id && a.status !== "IGNORED")
      .map((a) => [a.exam_question_id!, a])
  );
  const locked = ev.status === "FINALIZED";

  const call = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key);
    setErr(null);
    try {
      await fn();
      await reload();
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(null);
    }
  };

  const total = d.questions.reduce((s, q) => s + (items.get(q.id)?.final_marks ?? 0), 0);
  const max = d.questions.reduce((s, q) => s + (q.max_marks ?? 0), 0);
  const unresolved = d.answers.some((a) => a.status === "UNMAPPED" || a.status === "NEEDS_REVIEW");

  const finalizeAction = async () => {
    setBusy("fin");
    setErr(null);
    try {
      await api(`/evaluations/${ev.id}/finalize`, { method: "POST" });
      nav(`/results/${ev.id}`);
    } catch (e) {
      setErr(e);
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4">
      {/* Sticky Assessment Action Bar */}
      <div className="sticky top-12 z-20 flex flex-wrap items-center justify-between gap-4 rounded-lg border border-line border-l-4 border-l-mark bg-surface/95 p-4 shadow-card backdrop-blur-md">
        <div className="flex items-center gap-3">
          <PenScore got={total} max={max} />
          <div>
            <p className="font-display text-base font-semibold text-ink">
              {ev.status === "FINALIZED" ? "Final Examination Score" : "Current Assessment Marks"}
            </p>
            <p className="text-xs text-mute">
              {ev.run_status === "RUNNING"
                ? "AI evaluation in progress..."
                : locked
                ? "Evaluation finalized and locked"
                : "Review and approve question scores"}
            </p>
          </div>
        </div>

        {!locked && (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              busy={busy === "run" || ev.run_status === "RUNNING"}
              onClick={() => call("run", () => api(`/evaluations/${ev.id}/run`, { method: "POST" }))}
              icon={<IconSparkles size={16} />}
            >
              {d.items.length ? "Re-run AI (Unapproved)" : "Run AI Evaluation"}
            </Button>

            <Button
              variant="secondary"
              disabled={!d.items.some((i) => i.status === "EVALUATED")}
              busy={busy === "all"}
              onClick={() => call("all", () => api(`/evaluations/${ev.id}/items/approve-all`, { method: "POST" }))}
              icon={<IconCheck size={16} />}
            >
              Approve All Evaluated
            </Button>

            <Button
              variant="primary"
              busy={busy === "fin"}
              onClick={() => setConfirmFinalize(true)}
              icon={<IconCheckCircle size={16} />}
            >
              Finalize Student
            </Button>
          </div>
        )}
      </div>

      {/* Progress Bar during AI evaluation */}
      {ev.run_status === "RUNNING" && (
        <Card className="p-4 space-y-2">
          <div className="flex items-center justify-between text-xs text-mute font-medium">
            <span>Evaluating...</span>
            <span className="font-semibold text-pen">
              Question {ev.run_progress} of {ev.run_total}
            </span>
          </div>
          <ProgressBar value={ev.run_progress} max={ev.run_total} />
        </Card>
      )}

      {ev.run_status === "ERROR" && (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-lg border border-mark/40 bg-mark-soft p-4 text-sm text-mark"
        >
          <IconAlertCircle className="h-5 w-5 shrink-0" />
          <div>
            <p className="font-semibold">AI Perception Engine Offline</p>
            <p className="mt-0.5 text-xs text-mark/90">
              The AI model is not running. Start Ollama, then try again.
            </p>
          </div>
        </div>
      )}

      {unresolved && (
        <div className="flex items-start gap-3 rounded-lg border border-warn/40 bg-warn-soft p-4 text-sm text-ink">
          <IconAlertTriangle className="h-5 w-5 shrink-0 text-warn" />
          <div>
            <p className="font-semibold text-warn">Unresolved Question Mappings</p>
            <p className="mt-0.5 text-xs text-mute">
              Some answers require mapping verification. Please review them in the <b>Mapping review</b> tab before finalizing scores.
            </p>
          </div>
        </div>
      )}

      <ErrorPanel
        error={err}
        action={
          err instanceof ApiError && err.code === "EVALUATION_NOT_READY" ? (
            <p className="text-xs text-pen font-medium">
              Resolve pending items below or switch back to the Mapping review tab.
            </p>
          ) : undefined
        }
      />

      {/* Issues Accordion before finalization */}
      {!err && !locked && d.issues.length > 0 && d.items.length > 0 && (
        <details className="group rounded-lg border border-warn/30 bg-warn-soft/40 p-4 text-sm transition-ui">
          <summary className="flex cursor-pointer items-center justify-between font-semibold text-warn">
            <span className="flex items-center gap-2">
              <IconAlertTriangle size={16} />
              {d.issues.length} item(s) pending before this evaluation can be finalized
            </span>
            <IconChevronRight
              size={16}
              className="transition-transform group-open:rotate-90"
            />
          </summary>
          <ul className="mt-3 space-y-1.5 border-t border-warn/20 pt-2.5 text-xs">
            {d.issues.map((i, k) => (
              <li key={k} className="flex items-baseline gap-2">
                <span className="rounded bg-warn/15 px-1.5 py-0.2 font-bold text-warn">
                  {i.question}
                </span>
                <span className="text-ink">{i.reason}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {/* Questions & Assessment Cards */}
      {d.questions.length === 0 ? (
        <Empty title="No questions found for this exam" />
      ) : (
        <div className="space-y-4">
          {d.questions.map((q) => {
            const it = items.get(q.id);
            const a = ans.get(q.id);
            const isMissing = it && ["EVALUATION_ERROR", "MISSING"].includes(it.status);

            return (
              <Card
                key={q.id}
                className={`p-5 transition-ui ${
                  isMissing
                    ? "border-l-4 border-l-mark"
                    : it?.status === "APPROVED"
                    ? "border-l-4 border-l-ok"
                    : "border-l-4 border-l-pen"
                }`}
              >
                {/* Question Header & Score */}
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span
                        className="flex h-8 min-w-8 items-center justify-center rounded-full border-2 border-pen/60 px-1.5 font-display text-sm font-semibold text-pen"
                        title={`Question ${q.display_number}`}
                      >
                        {q.display_number}
                      </span>
                      <span className="font-doc text-xs italic text-mute">
                        [{fmt(q.max_marks)} marks]
                      </span>
                      {q.section && (
                        <span className="rounded-md bg-pen-soft px-2 py-0.5 text-xs font-semibold text-pen">
                          {q.section}
                        </span>
                      )}
                    </div>
                    <div className="doc-text mt-1.5 line-clamp-2 text-sm text-ink/90">
                      <MathView text={q.question_text} />
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    {it && <StatusBadge status={it.status} />}
                    {it && it.final_marks !== null && (
                      <PenScore got={it.final_marks} max={q.max_marks} />
                    )}
                  </div>
                </div>

                {/* Answers Side-by-Side Comparison */}
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <div className="rounded-md border border-pen/20 bg-pen-soft/40 p-3.5 space-y-1">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-pen">
                      Official Marking Scheme & Criteria
                    </p>
                    <div className="doc-text text-xs text-ink/90 leading-relaxed max-h-36 overflow-y-auto">
                      <MathView text={q.official_answer || "(No official answer uploaded)"} />
                    </div>
                  </div>

                  <div className="ruled rounded-md border border-line bg-surface p-3.5 pl-14 space-y-1">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-mute">
                      Student's Answer (Transcribed)
                    </p>
                    <div className="doc-text text-sm text-ink leading-7 max-h-40 overflow-y-auto">
                      {a?.answer_text ? (
                        <MathView text={a.answer_text} />
                      ) : (
                        <em className="text-mark font-normal">No answer mapped to this question</em>
                      )}
                    </div>
                  </div>
                </div>

                {it?.error && (
                  <p className="mt-3 text-xs font-semibold text-mark flex items-center gap-1.5">
                    <IconAlertCircle size={14} />
                    {it.error}
                  </p>
                )}

                {/* AI Evaluation Breakdown */}
                {it && it.ai_marks !== null && (
                  <div className="mt-4 rounded-lg border border-pen/20 bg-pen-soft/30 p-3.5 space-y-2 text-xs">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-bold text-ink">
                        AI Assessment: {fmt(it.ai_marks)} / {fmt(q.max_marks)} marks
                      </span>
                      {it.ai_decision && <Badge tone="pen">{label(it.ai_decision)}</Badge>}
                      {it.ai_confidence !== null && (
                        <span className="text-mute">
                          (Confidence {pct(it.ai_confidence)})
                        </span>
                      )}
                    </div>

                    {it.ai_feedback && (
                      <p className="text-ink/90 italic leading-relaxed">
                        “{it.ai_feedback}”
                      </p>
                    )}

                    {it.matched_points.length > 0 && (
                      <div className="flex items-start gap-1.5 text-ok">
                        <IconCheck size={14} className="shrink-0 mt-0.5" />
                        <span><b>Matched criteria:</b> {it.matched_points.join("; ")}</span>
                      </div>
                    )}

                    {it.missing_points.length > 0 && (
                      <div className="flex items-start gap-1.5 text-mark">
                        <IconX size={14} className="shrink-0 mt-0.5" />
                        <span><b>Missing criteria:</b> {it.missing_points.join("; ")}</span>
                      </div>
                    )}

                    {it.teacher_overridden && (
                      <p className="text-warn font-medium">
                        * You overrode the AI score for this question.
                      </p>
                    )}
                  </div>
                )}

                {/* Action Buttons */}
                {it && !locked && (
                  <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-line/60 pt-3">
                    {it.status !== "APPROVED" && it.status !== "PENDING" && (
                      <Button
                        small
                        variant="primary"
                        busy={busy === it.id}
                        onClick={() =>
                          it.status === "MISSING"
                            ? setEdit({ q, item: it })
                            : call(it.id, () =>
                                api(`/evaluations/${ev.id}/items/${it.id}`, {
                                  method: "PATCH",
                                  json: { approve: true },
                                })
                              )
                        }
                        icon={<IconCheck size={14} />}
                      >
                        {it.status === "MISSING" ? "Resolve Unattempted..." : "Approve Score"}
                      </Button>
                    )}

                    {it.status === "APPROVED" && (
                      <Button
                        small
                        variant="secondary"
                        busy={busy === it.id}
                        onClick={() =>
                          call(it.id, () =>
                            api(`/evaluations/${ev.id}/items/${it.id}`, {
                              method: "PATCH",
                              json: { approve: false },
                            })
                          )
                        }
                      >
                        Unapprove
                      </Button>
                    )}

                    {it.status !== "PENDING" && (
                      <Button
                        small
                        variant="secondary"
                        onClick={() => setEdit({ q, item: it })}
                        icon={<IconEdit size={13} />}
                      >
                        Adjust Marks
                      </Button>
                    )}

                    {it.status !== "PENDING" && (
                      <Button
                        small
                        variant="ghost"
                        busy={busy === it.id + "r"}
                        onClick={() =>
                          call(it.id + "r", () =>
                            api(`/evaluations/${ev.id}/items/${it.id}/rerun`, { method: "POST" })
                          )
                        }
                        icon={<IconRotateCcw size={13} />}
                      >
                        Re-evaluate with AI
                      </Button>
                    )}
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}

      {/* Marks Adjustment Dialog */}
      {edit && (
        <MarksDlg
          q={edit.q}
          item={edit.item}
          evId={ev.id}
          onClose={() => setEdit(null)}
          onDone={reload}
        />
      )}

      {/* Finalization Confirmation Dialog */}
      {confirmFinalize && (
        <Confirm
          title={`Finalize Evaluation for ${ev.student.name}?`}
          confirmLabel="Finalize & Lock Results"
          body={
            <div className="space-y-2">
              <p>
                Are you ready to lock the final evaluation score of{" "}
                <b className="text-ink">
                  {fmt(total)} out of {fmt(max)} marks
                </b>{" "}
                for student <b>{ev.student.name}</b> (Roll {ev.student.roll_number})?
              </p>
              <p className="text-xs text-mute">
                Once finalized, the marks are locked and appear in the results.
              </p>
            </div>
          }
          onConfirm={finalizeAction}
          onClose={() => setConfirmFinalize(false)}
        />
      )}
    </div>
  );
}

function MarksDlg({
  q,
  item,
  evId,
  onClose,
  onDone,
}: {
  q: EvalQuestion;
  item: EvalItem;
  evId: string;
  onClose: () => void;
  onDone: () => Promise<void>;
}) {
  const [marks, setMarks] = useState(item.final_marks !== null ? String(item.final_marks) : "");
  const [reason, setReason] = useState("");
  const [fb, setFb] = useState(item.teacher_feedback ?? "");
  const [na, setNa] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);

  const save = async (approve: boolean) => {
    setBusy(true);
    setErr(null);
    const json: Record<string, unknown> = {
      reason: reason || undefined,
      teacher_feedback: fb || undefined,
    };
    if (item.status === "MISSING" && na) json.confirm_not_attempted = true;
    if (marks !== "") json.final_marks = Number(marks);
    if (approve) json.approve = true;

    try {
      await api(`/evaluations/${evId}/items/${item.id}`, { method: "PATCH", json });
      await onDone();
      onClose();
    } catch (e) {
      setErr(e);
      setBusy(false);
    }
  };

  return (
    <Modal
      title={`Adjust Marks — Question ${q.display_number}`}
      onClose={onClose}
      icon={<IconEdit className="text-pen" size={20} />}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="secondary" busy={busy} onClick={() => save(false)}>
            Save Only
          </Button>
          <Button
            variant="primary"
            busy={busy}
            onClick={() => save(true)}
            icon={<IconCheck size={16} />}
          >
            Save & Approve Score
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {item.ai_marks !== null && (
          <div className="rounded-lg border border-pen/20 bg-pen-soft/40 p-3 text-xs text-pen font-medium">
            AI suggested <b>{fmt(item.ai_marks)}</b> of {fmt(q.max_marks)} marks. The AI perception record is preserved in the audit log.
          </div>
        )}

        {item.status === "MISSING" && (
          <label className="flex items-start gap-2.5 rounded-lg border border-line bg-sunken/60 p-3 text-xs text-ink cursor-pointer">
            <input
              type="checkbox"
              className="mt-0.5 rounded accent-pen"
              checked={na}
              onChange={(e) => setNa(e.target.checked)}
            />
            <span>
              I have checked the paper scan and confirmed this question was not attempted (0 marks).
            </span>
          </label>
        )}

        <Field label={`Final Score (0 to ${fmt(q.max_marks)})`} required>
          {(id) => (
            <Input
              id={id}
              type="number"
              min={0}
              max={q.max_marks ?? undefined}
              step={0.5}
              value={marks}
              onChange={(e) => setMarks(e.target.value)}
            />
          )}
        </Field>

        <Field
          label="Reason for Mark Override"
          hint="Required whenever the score differs from the AI's proposal"
        >
          {(id) => (
            <Input
              id={id}
              placeholder="e.g. Awarded partial credit for working steps"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          )}
        </Field>

        <Field label="Constructive Feedback for Student (Optional)">
          {(id) => (
            <Textarea
              id={id}
              rows={3}
              placeholder="Explain what the student can improve..."
              value={fb}
              onChange={(e) => setFb(e.target.value)}
            />
          )}
        </Field>

        <ErrorPanel error={err} />
      </div>
    </Modal>
  );
}
