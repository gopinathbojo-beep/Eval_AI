/* The Mapping tab of a student's evaluation: which answer belongs to which question. */
import { useState } from "react";
import { api } from "../../api/client";
import type { EvalQuestion, EvaluationDetail, StudentAnswer } from "../../types";
import { pct } from "../../utils/format";
import {
  Badge,
  Button,
  Card,
  Empty,
  ErrorPanel,
  Field,
  Input,
  MathTextarea,
  MathView,
  Modal,
  Select,
  Stat,
  StatusBadge,
} from "../../components/ui";
import { PageViewer } from "../../components/PageViewer";
import {
  IconCheck,
  IconCheckCircle,
  IconEdit,
  IconAlertCircle,
  IconAlertTriangle,
  IconRotateCcw,
  IconChevronDown,
} from "../../components/Icons";

const FILTERS = ["All", "Mapped", "Suggested", "Needs review", "Unmapped", "Missing", "Read error"] as const;

export function MappingTab({ d, reload }: { d: EvaluationDetail; reload: () => Promise<void> }) {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("All");
  const [page, setPage] = useState(1);
  const [sel, setSel] = useState<string | null>(null);
  const [dlg, setDlg] = useState<StudentAnswer | null>(null);
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
      {d.coverage && d.coverage.required > 0 && (
        <div
          className={`rounded-lg border px-4 py-3 text-sm ${
            d.coverage.missing.length ? "border-warn/30 bg-warn-soft text-ink" : "border-ok/30 bg-ok-soft text-ink"
          }`}
        >
          <b>
            {d.coverage.answered} of {d.coverage.required} questions answered on this sheet.
          </b>{" "}
          {d.coverage.missing.length ? (
            <span className="text-mute">
              Not found: {d.coverage.missing.join(", ")}. Check the sheet: skipped by the student, or not read.
            </span>
          ) : (
            <span className="text-mute">Every question has an answer.</span>
          )}
        </div>
      )}
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
                  className={`rounded-full px-1.5 py-px text-[10px] font-bold ${
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
                    If it was answered, find it on the scan and use "Edit" to link it.
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
                      type="button"
                      className="block w-full text-left"
                      aria-expanded={isSelected}
                      onClick={() => {
                        if (isSelected) return setSel(null);
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
                          <span
                            className={`rounded-md px-2 py-0.5 text-xs font-medium ${
                              a.ocr_confidence != null && a.ocr_confidence < 0.6
                                ? "bg-warn-soft text-warn"
                                : "bg-sunken text-mute"
                            }`}
                            title={
                              a.ocr_confidence != null && a.ocr_confidence < 0.6
                                ? "The second look at this page read this answer differently: check it against the page"
                                : undefined
                            }
                          >
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
                      <div className={`doc-text mt-2.5 ${isSelected ? "" : "line-clamp-4"} rounded-lg border border-line/40 bg-surface p-2.5 text-sm text-ink/90 leading-relaxed`}>
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
                      <span className="mt-2 inline-flex items-center gap-1 text-[11px] font-semibold text-pen">
                        {isSelected ? "Show less" : "Show more"}
                        <IconChevronDown size={13} className={`transition-transform ${isSelected ? "rotate-180" : ""}`} />
                      </span>
                    </button>

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

                            {/* Consolidated single Edit button */}
                            <Button
                              small
                              variant="secondary"
                              onClick={() => setDlg(a)}
                              icon={<IconEdit size={13} />}
                              title="Edit transcribed text or change the mapped question"
                            >
                              Edit
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

      {/* Edit modal */}
      {dlg && <MapDlg a={dlg} d={d} onClose={() => setDlg(null)} onDone={reload} />}
    </div>
  );
}

function MapDlg({
  a,
  d,
  onClose,
  onDone }: {
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
