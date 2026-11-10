/* The Marks tab of a student's evaluation: the AI marks per question, and the teacher's changes. */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../../api/client";
import type { EvalItem, EvalQuestion, EvaluationDetail } from "../../types";
import { fmt, label, pct, nameIsRoll } from "../../utils/format";
import { groupAnswerBlocks } from "../../utils/answerBlocks";
import {
  Badge,
  Button,
  Card,
  Confirm,
  Empty,
  ErrorPanel,
  Field,
  Input,
  MathView,
  Modal,
  PenScore,
  ProgressBar,
  StatusBadge,
  Textarea,
} from "../../components/ui";
import { PageViewer } from "../../components/PageViewer";
import {
  IconCheck,
  IconCheckCircle,
  IconEdit,
  IconSparkles,
  IconAlertCircle,
  IconAlertTriangle,
  IconRotateCcw,
  IconEye,
  IconChevronRight,
  IconX,
} from "../../components/Icons";

export function MarksTab({ d, reload }: { d: EvaluationDetail; reload: () => Promise<void> }) {
  const nav = useNavigate();
  const ev = d.evaluation;
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [edit, setEdit] = useState<{ q: EvalQuestion; item: EvalItem } | null>(null);
  const [confirmFinalize, setConfirmFinalize] = useState(false);

  const items = new Map(d.items.map((i) => [i.exam_question_id, i]));
  const ans = groupAnswerBlocks(d.answers);
  // every page the student's answer to a question is written on (a whole question can run over several pages)
  const pagesOf = new Map<string, number[]>();
  for (const a of d.answers) {
    if (!a.exam_question_id || a.status === "IGNORED" || !a.page_number) continue;
    const list = pagesOf.get(a.exam_question_id) ?? [];
    if (!list.includes(a.page_number)) list.push(a.page_number);
    pagesOf.set(a.exam_question_id, list.sort((x, y) => x - y));
  }
  const [shown, setShown] = useState<string | null>(null);
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
            <p className="text-base font-bold text-ink">
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
              OpenRouter is unavailable. Check the API key, Gemini model access and credits, then try again.
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
                <span className="rounded bg-warn/15 px-1.5 py-px font-bold text-warn">
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
            const answerBlocks = ans.get(q.id) ?? [];
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
                        className="flex h-8 min-w-8 items-center justify-center rounded-full border-2 border-pen/60 px-1.5 font-bold text-xs text-pen"
                        title={`Question ${q.display_number}`}
                      >
                        {q.display_number}
                      </span>
                      <span className="text-xs font-semibold text-mute">
                        [{fmt(q.max_marks)} marks]
                      </span>
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

                  <div className="rounded-lg border border-line bg-surface p-3.5 space-y-1">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-mute">
                      Student's Answer (Transcribed)
                      {(pagesOf.get(q.id)?.length ?? 0) > 1 && ` · All ${pagesOf.get(q.id)!.length} pages`}
                    </p>
                    <div className="doc-text text-sm text-ink leading-7 max-h-80 overflow-y-auto">
                      {answerBlocks.some((a) => a.answer_text) ? (
                        <div className="space-y-3">
                          {answerBlocks.filter((a) => a.answer_text).map((a) => (
                            <div key={a.id}>
                              {answerBlocks.length > 1 && <p className="mb-1 font-sans text-[11px] font-semibold text-mute">Page {a.page_number ?? "–"}</p>}
                              <MathView text={a.answer_text} />
                            </div>
                          ))}
                        </div>
                      ) : (
                        <em className="text-mark font-normal">No answer mapped to this question</em>
                      )}
                    </div>
                    {(pagesOf.get(q.id)?.length ?? 0) > 0 && (
                      <button
                        type="button"
                        className="mt-1 inline-flex items-center gap-1 text-[11px] font-semibold text-pen hover:underline"
                        onClick={() => setShown(shown === q.id ? null : q.id)}
                        aria-expanded={shown === q.id}
                      >
                        <IconEye size={13} />
                        {shown === q.id ? "Hide sheet" : `View on sheet (page ${pagesOf.get(q.id)!.join(", ")})`}
                      </button>
                    )}
                  </div>
                </div>

                {shown === q.id && (
                  <div className="mt-3 space-y-2 rounded-lg border border-line bg-sunken/40 p-2">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-[11px] text-mute">The student's sheet as scanned, including any drawing. Use + / − to zoom.</p>
                      <Button small variant="secondary" onClick={() => setShown(null)} title="Close this page">
                        Close
                      </Button>
                    </div>
                    <AnswerPages docId={d.document.id} pages={d.document.pages} numbers={pagesOf.get(q.id)!} />
                  </div>
                )}

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
                      {it.evidence_checked && <Badge tone="ok">Evidence checked</Badge>}
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

                    {(it.criterion_awards?.length ?? 0) > 0 && (
                      <details className="rounded border border-line bg-surface/60 p-2.5">
                        <summary className="cursor-pointer font-semibold text-ink">Marks and supporting evidence</summary>
                        <div className="mt-2 space-y-3">
                          {it.criterion_awards!.filter((award) => award.counted !== false).map((award) => (
                            <div key={award.id} className="border-t border-line pt-2">
                              <p className="font-semibold">{award.id}: {fmt(award.marks)}{award.allocation !== undefined ? ` / ${fmt(award.allocation)}` : ""} marks</p>
                              {award.evidence && <p className="mt-1 text-mute">{award.evidence}</p>}
                              {award.evidence_quotes?.map((quote, index) => (
                                <blockquote key={index} className="mt-1 border-l-2 border-pen/40 pl-2"><MathView text={quote} /></blockquote>
                              ))}
                              {award.scheme_quote && <p className="mt-1 text-mute"><b>Scheme point:</b> {award.scheme_quote}</p>}
                            </div>
                          ))}
                        </div>
                      </details>
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
                                  json: { approve: true } })
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
                              json: { approve: false } })
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
                for student <b>{ev.student.name}</b>{nameIsRoll(ev.student) ? "" : ` (Roll ${ev.student.roll_number})`}?
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

/** The page(s) a student's answer is written on, full page with zoom: drawings are never cropped away. */
function AnswerPages({ docId, pages, numbers }: { docId: string; pages: EvaluationDetail["document"]["pages"]; numbers: number[] }) {
  const own = pages.filter((p) => numbers.includes(p.page_number));
  const [page, setPage] = useState(numbers[0]);
  return (
    <div className="h-[34rem] overflow-hidden rounded border border-line/60 bg-surface">
      <PageViewer kind="answer-sheet" docId={docId} pages={own} page={page} onPage={setPage} baseZoom={0.5} />
    </div>
  );
}

function MarksDlg({
  q,
  item,
  evId,
  onClose,
  onDone }: {
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
      teacher_feedback: fb || undefined };
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
              step="any"
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
