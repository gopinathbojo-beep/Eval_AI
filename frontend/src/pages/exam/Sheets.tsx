import { Fragment, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, downloadFile, fetchBlobUrl } from "../../api/client";
import { useApi } from "../../hooks/useApi";
import type { Evaluation, IdentityRead, QuestionSummary, ReviewSummary, Student, UnassignedSheet } from "../../types";
import { BUSY_DOC, date, fmt, label, nameIsRoll } from "../../utils/format";
import { Badge, Button, Card, Confirm, Empty, ErrorPanel, LinkButton, Loading, Modal, Select, StatusBadge, Table } from "../../components/ui";
import { useExam } from "../ExamWorkspace";
import { DeleteSheetConfirm } from "../../components/DeleteSheetConfirm";
import { IconTrash } from "../../components/Icons";

function IdentityDetails({ read }: { read?: Partial<IdentityRead> }) {
  const parts: [string, string | null | undefined][] = [
    ["Name", read?.name], ["Roll", read?.roll_number], ["Reg", read?.registration_number], ["Sec", read?.section],
  ];
  const shown = parts.filter(([, v]) => v);
  if (!shown.length) return <span className="text-xs text-mute">Nothing legible</span>;
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs">
      {shown.map(([k, v]) => (
        <span key={k}>
          <span className="text-mute">{k}:</span> <span className="font-mono font-medium text-ink">{v}</span>
        </span>
      ))}
    </div>
  );
}

function UnassignedSheets({
  rows, students, taken, onChanged,
}: {
  rows: UnassignedSheet[]; students: Student[]; taken: Set<string>; onChanged: () => Promise<void>;
}) {
  const [pick, setPick] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [del, setDel] = useState<UnassignedSheet | null>(null);

  const act = async (id: string, fn: () => Promise<unknown>) => {
    setBusy(id);
    setError(null);
    try {
      await fn();
      await onChanged();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };
  const view = async (d: UnassignedSheet) => {
    try {
      window.open(await fetchBlobUrl(`/documents/answer-sheet/${d.id}/pages/1/image`), "_blank", "noopener");
    } catch (e) {
      setError(e);
    }
  };

  const held = rows.filter((d) => !BUSY_DOC.includes(d.status));
  const workingCount = rows.length - held.length;

  return (
    <Card className="overflow-x-auto shadow-soft">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-ink">Unidentified Answer Sheets ({rows.length})</h3>
          <p className="text-xs text-mute">
            {workingCount > 0 && <span className="animate-pulse">Reading {workingCount} sheet(s)… </span>}
            {held.length > 0 && "These could not be matched to one student with certainty, so they were held while the rest carried on. Pick the student and the sheet is graded straight away."}
          </p>
        </div>
      </div>
      <ErrorPanel error={error} />
      <table className="w-full text-left text-sm">
        <thead className="border-b border-line bg-surface text-xs font-semibold uppercase tracking-wider text-mute">
          <tr>
            <th className="px-4 py-3">File</th>
            <th className="px-4 py-3">Read From Sheet</th>
            <th className="px-4 py-3">Student</th>
            <th className="px-4 py-3 text-right">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line text-sm">
          {rows.map((d) => {
            const working = BUSY_DOC.includes(d.status);
            const candIds = new Set(d.candidates.map((c) => c.id));
            const others = students.filter((s) => !candIds.has(s.id) && !taken.has(s.id));
            const value = pick[d.id] ?? "";
            return (
              <tr key={d.id} className="align-top hover:bg-hover">
                <td className="px-4 py-3">
                  <p className="max-w-[14rem] truncate font-medium text-ink" title={d.original_filename}>{d.original_filename}</p>
                  <div className="mt-1 flex items-center gap-2">
                    <StatusBadge status={d.status} />
                    {working && <span className="font-mono text-xs text-mute animate-pulse">{d.stage}</span>}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <IdentityDetails read={d.identity?.read} />
                  {d.identity?.note && !working && <p className="mt-1 max-w-sm text-xs text-warn">{d.identity.note}</p>}
                  {d.error_message && <p className="mt-1 max-w-sm text-xs text-mark">{d.error_message}</p>}
                </td>
                <td className="px-4 py-3">
                  <Select
                    aria-label={`Student for ${d.original_filename}`}
                    value={value}
                    disabled={working || !d.pages.length}
                    onChange={(e) => setPick({ ...pick, [d.id]: e.target.value })}
                  >
                    <option value="">Choose student…</option>
                    {d.candidates.length > 0 && (
                      <optgroup label="Likely matches">
                        {d.candidates.filter((c) => !taken.has(c.id)).map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.roll_number} — {c.name}{c.registration_number ? ` (${c.registration_number})` : ""}
                          </option>
                        ))}
                      </optgroup>
                    )}
                    <optgroup label="All students without a sheet">
                      {others.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.roll_number} — {s.name}{s.registration_number ? ` (${s.registration_number})` : ""}
                        </option>
                      ))}
                    </optgroup>
                  </Select>
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-right">
                  <div className="flex items-center justify-end gap-1.5">
                    <Button
                      small
                      variant="primary"
                      disabled={!value || working}
                      busy={busy === d.id}
                      onClick={() => act(d.id, () => api(`/answer-sheets/${d.id}/assign`, { method: "POST", json: { student_id: value } }))}
                    >
                      Assign
                    </Button>
                    {d.pages.length > 0 && (
                      <Button small variant="soft" onClick={() => view(d)} title="Open the first page">View</Button>
                    )}
                    <Button
                      small
                      variant="ghost"
                      disabled={working}
                      onClick={() => act(d.id, () => api(`/answer-sheets/${d.id}/identify`, { method: "POST" }))}
                      title="Read the student details again"
                    >
                      Retry
                    </Button>
                    <Button
                      small
                      variant="ghost"
                      className="text-mark hover:bg-mark-soft hover:text-mark"
                      disabled={d.status === "IDENTIFYING"}
                      onClick={() => setDel(d)}
                      title="Delete sheet"
                    >
                      Delete
                    </Button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {del && (
        <Confirm
          title="Delete Answer Sheet"
          danger
          confirmLabel="Delete Sheet"
          body={<p className="text-sm text-ink">Remove <b>{del.original_filename}</b>? The original file is retained in storage.</p>}
          onConfirm={async () => {
            await api(`/answer-sheets/${del.id}`, { method: "DELETE" });
            await onChanged();
          }}
          onClose={() => setDel(null)}
        />
      )}
    </Card>
  );
}

/** Every database round trip is slow, so pages poll gently while sheets are being worked on. */
const POLL_MS = 4000;
// while the exam takes sheets, keep checking: the uploader sends them from another device at any time
const WATCH_MS = 6000;
const TAKES_SHEETS = ["ANSWER_KEY_VERIFIED", "READY_FOR_EVALUATION", "EVALUATING", "REVIEW_REQUIRED"];

/** The batch summary, polled while sheets are still being read or graded. `onProgress` refreshes the lists alongside,
 * but only when a sheet has moved on, not on every poll. */
function useReviewSummary(examId: string, onProgress?: () => Promise<unknown>, watch = false) {
  const progress = useRef(onProgress);
  progress.current = onProgress;
  const last = useRef<number | null>(null);
  return useApi<ReviewSummary>(`/exams/${examId}/review-summary`, (d) => {
    if (last.current !== null && last.current !== d.processing) void progress.current?.();
    last.current = d.processing;
    return d.processing ? POLL_MS : watch ? WATCH_MS : null;
  });
}

/** The uploaded batch at a glance: an alert once every sheet is read and graded, then one button to finalize the
 * sheets that are fine, with the ones that need the teacher listed and why. */
function BatchReview({
  examId, summary, onChanged,
}: {
  examId: string; summary: ReviewSummary; onChanged: () => Promise<void>;
}) {
  const [done, setDone] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const was = useRef(summary.processing);

  useEffect(() => {
    if (was.current > 0 && summary.processing === 0) setDone(true);
    was.current = summary.processing;
  }, [summary.processing]);

  const open = summary.ready.length + summary.needs_review.length;
  if (!summary.processing && !open && !summary.unassigned) return null;

  return (
    <Card className="overflow-x-auto shadow-soft">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-ink">Review & Finalize</h3>
          <p className="text-xs text-mute">
            {summary.processing > 0 ? (
              <span className="animate-pulse">
                Reading and grading sheets: {summary.processing} still in progress…
              </span>
            ) : (
              <>
                {summary.ready.length} ready · {summary.needs_review.length} need your review · {summary.finalized} finalized
                {summary.unassigned > 0 && <> · {summary.unassigned} without a student</>}
              </>
            )}
          </p>
        </div>
        <Button
          variant="primary"
          disabled={!summary.ready.length}
          onClick={() => setConfirm(true)}
          title={summary.ready.length ? "Approve the AI marks and finalize every sheet that needs nothing else" : "No sheet is ready yet"}
        >
          Finalize {summary.ready.length || ""} Reviewed Sheet{summary.ready.length === 1 ? "" : "s"}
        </Button>
      </div>
      {result && <p className="border-b border-line bg-ok-soft px-4 py-2 text-xs font-medium text-ok">{result}</p>}
      {summary.needs_review.length > 0 && (
        <table className="w-full text-left text-sm">
          <thead className="border-b border-line bg-surface text-xs font-semibold uppercase tracking-wider text-mute">
            <tr>
              <th className="px-4 py-3">Needs Review</th>
              <th className="px-4 py-3">What to check</th>
              <th className="px-4 py-3 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line text-sm">
            {summary.needs_review.map((r) => (
              <tr key={r.evaluation_id} className="align-top hover:bg-hover">
                <td className="px-4 py-3">
                  <p className="font-medium text-ink">{r.student.name}</p>
                  {!nameIsRoll(r.student) && <p className="font-mono text-xs text-mute">Roll: {r.student.roll_number}</p>}
                </td>
                <td className="px-4 py-3">
                  <ul className="space-y-0.5 text-xs">
                    {r.reasons.map((x, i) => (
                      <li key={i}>
                        <span className="font-mono font-medium text-ink">{x.question}</span>{" "}
                        <span className="text-warn">{x.reason}</span>
                      </li>
                    ))}
                  </ul>
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-right">
                  <Link to={`/evaluations/${r.evaluation_id}`} className="text-xs font-medium text-pen hover:underline">
                    Review →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {done && (
        <Modal
          title="Evaluation Completed"
          onClose={() => setDone(false)}
          footer={<Button variant="primary" onClick={() => setDone(false)}>OK</Button>}
        >
          <div className="space-y-2 text-sm text-ink">
            <p>All uploaded answer sheets have been read and graded.</p>
            <ul className="list-disc space-y-0.5 pl-5 text-xs">
              <li><b>{summary.ready.length}</b> ready to finalize after you look them over</li>
              {summary.needs_review.length > 0 && (
                <li className="text-warn"><b>{summary.needs_review.length}</b> need your review. They are listed with what to check.</li>
              )}
              {summary.unassigned > 0 && (
                <li className="text-warn"><b>{summary.unassigned}</b> could not be matched to a student</li>
              )}
            </ul>
          </div>
        </Modal>
      )}
      {confirm && (
        <Confirm
          title="Finalize Reviewed Sheets"
          confirmLabel={`Finalize ${summary.ready.length}`}
          body={
            <div className="space-y-2 text-sm text-ink">
              <p>
                Approve the AI marks and finalize <b>{summary.ready.length}</b> answer sheet(s)?
              </p>
              {summary.needs_review.length > 0 && (
                <p className="text-xs text-mute">
                  The {summary.needs_review.length} sheet(s) that need review are left as they are.
                </p>
              )}
            </div>
          }
          onConfirm={async () => {
            const r = await api<ReviewSummary & { finalized_now: number }>(`/exams/${examId}/finalize-ready`, { method: "POST" });
            setResult(`${r.finalized_now} sheet(s) finalized.`);
            await onChanged();
          }}
          onClose={() => setConfirm(false)}
        />
      )}
    </Card>
  );
}

/** After finalization: when the exam's files will be (or were) deleted, with a way to delete them now. */
function ExamFilesNotice() {
  const { exam, reload } = useExam();
  const [confirm, setConfirm] = useState(false);
  if (exam.files_purged_at) {
    return (
      <Card className="p-4 text-sm text-mute shadow-soft">
        Uploaded files for this exam were deleted on <b className="text-ink">{date(exam.files_purged_at)}</b>. Each student's
        official PDF report was kept and can still be downloaded.
      </Card>
    );
  }
  if (!exam.files_purge_at) return null;
  return (
    <Card className="flex flex-wrap items-center justify-between gap-3 border-warn/30 bg-warn-soft/30 p-4 text-sm shadow-soft">
      <p className="text-ink">
        Uploaded files, page images and raw AI output will be deleted on <b>{date(exam.files_purge_at)}</b>.
        Student PDF reports are kept.
      </p>
      <Button small variant="ghost" className="text-mark hover:bg-mark-soft hover:text-mark" onClick={() => setConfirm(true)}>
        Delete files now
      </Button>
      {confirm && (
        <Confirm
          title="Delete exam files now?"
          danger
          confirmLabel="Delete Files"
          body={<p className="text-sm text-ink">This permanently removes the uploaded documents and page images for <b>{exam.name}</b>. Marks, results and the saved PDF reports stay.</p>}
          onConfirm={async () => {
            await api(`/exams/${exam.id}/purge-files`, { method: "POST" });
            await reload();
          }}
          onClose={() => setConfirm(false)}
        />
      )}
    </Card>
  );
}

/** One row per student from upload to final result: reading, mapping, grading, marks, reports and finalizing the exam. */
export function AnswerSheets() {
  const { exam, reload } = useExam();
  const open = TAKES_SHEETS.includes(exam.status);
  const students = useApi<Student[]>(`/students?class_id=${exam.class_id}`);
  const sheets = useApi<Evaluation[]>(
    `/exams/${exam.id}/answer-sheets`,
    (d) => (d.some((s) => (s.document && BUSY_DOC.includes(s.document.status)) || s.run_status === "RUNNING")
      ? POLL_MS : open ? WATCH_MS : null)
  );
  const unassigned = useApi<UnassignedSheet[]>(
    `/exams/${exam.id}/answer-sheets/unassigned`,
    (d) => (d.some((s) => BUSY_DOC.includes(s.status)) ? POLL_MS : open ? WATCH_MS : null)
  );
  const summary = useReviewSummary(exam.id, () => Promise.all([sheets.reload(), unassigned.reload()]), open);
  const questions = useApi<QuestionSummary>(`/exams/${exam.id}/question-summary`);

  const [del, setDel] = useState<Evaluation | null>(null);
  const [remapping, setRemapping] = useState<string | null>(null);
  const [remapError, setRemapError] = useState<unknown>(null);
  const [remapNote, setRemapNote] = useState<string | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [confirmFinalize, setConfirmFinalize] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [bulkDownloading, setBulkDownloading] = useState(false);

  // sheets are finalized in the background too: the analysis follows the count while this page stays open
  const finalizedCount = (sheets.data ?? []).filter((e) => e.status === "FINALIZED").length;
  const lastFinalized = useRef<number | null>(null);
  const reloadQuestions = questions.reload;
  useEffect(() => {
    if (!sheets.data) return;
    if (lastFinalized.current !== null && lastFinalized.current !== finalizedCount) void reloadQuestions();
    lastFinalized.current = finalizedCount;
  }, [sheets.data, finalizedCount, reloadQuestions]);

  // the typed and the written roll number differ: the school says which is right, then the sheet is graded
  const settleRoll = async (rowId: string, docId: string, use: "typed" | "written") => {
    setRemapping(rowId + use); setRemapError(null);
    try {
      await api(`/answer-sheets/${docId}/roll-check`, { method: "POST", json: { use } });
    } catch (err) {
      setRemapError(err);
    } finally {
      setRemapping(null);
      await refresh();
    }
  };
  // map the answers again with the current rules (no page is re-read), then grade what is not yet approved
  const remap = async (target: string) => {
    setRemapping(target); setRemapError(null); setRemapNote(null);
    try {
      if (target === "all") {
        const r = await api<{ started: number; skipped: { reason: string }[] }>(`/exams/${exam.id}/remap-and-run`, { method: "POST" });
        setRemapNote(`Re-mapped and grading ${r.started} sheet${r.started === 1 ? "" : "s"}` +
          (r.skipped.length ? `; ${r.skipped.length} need a look first (open their review).` : "."));
      } else {
        await api(`/evaluations/${target}/remap-and-run`, { method: "POST" });
      }
    } catch (e) {
      setRemapError(e);
    } finally {
      setRemapping(null);
      await refresh();
    }
  };

  const downloadStudentReports = async () => {
    setBulkDownloading(true);
    setActionError(null);
    try {
      await downloadFile(`/exams/${exam.id}/student-reports.zip`,
        `StudentReports_${exam.name.replace(/[^a-zA-Z0-9_-]/g, "_")}.zip`);
    } catch (e) {
      setActionError(e);
    } finally {
      setBulkDownloading(false);
    }
  };

  const downloadExamReport = async () => {
    setDownloading(true);
    setActionError(null);
    try {
      await downloadFile(`/exams/${exam.id}/report.pdf`, `ExamReport_${exam.name.replace(/[^a-zA-Z0-9_-]/g, "_")}.pdf`);
    } catch (e) {
      setActionError(e);
    } finally {
      setDownloading(false);
    }
  };

  const taken = new Set((sheets.data ?? []).map((s) => s.student.id));

  const refresh = async () => {
    await Promise.all([sheets.reload(), unassigned.reload(), summary.reload(), questions.reload(), reload()]);
  };

  if (sheets.loading) return <Loading />;
  const rows = sheets.data ?? [];
  const allFinalized = rows.length > 0 && finalizedCount === rows.length;
  const examFinalized = exam.status === "FINALIZED";
  const nothingYet = !rows.length && !unassigned.data?.length && !sheets.error;

  return (
    <div className="space-y-5">
      {examFinalized ? (
        <ExamFilesNotice />
      ) : !open ? (
        <Card className="flex items-center gap-3 p-4 text-sm text-mute">
          <svg className="h-5 w-5 text-warn flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span>Answer sheets can be uploaded once the exam questions and answer key are verified.</span>
        </Card>
      ) : (
        <Card className="space-y-1 p-5 shadow-soft">
          <h2 className="text-lg font-semibold text-ink">Students</h2>
          <p className="text-xs text-mute">
            Sheets are sent from the uploader app with the student's roll number, then read and graded on their own.
            Each student is listed here from upload to final result.
          </p>
        </Card>
      )}

      <ErrorPanel error={sheets.error || unassigned.error || questions.error || remapError || actionError} />
      {remapNote && <Card className="p-3 text-sm text-ink">{remapNote}</Card>}

      {summary.data && <BatchReview examId={exam.id} summary={summary.data} onChanged={refresh} />}

      {unassigned.data && unassigned.data.length > 0 && (
        <UnassignedSheets rows={unassigned.data} students={students.data ?? []} taken={taken} onChanged={refresh} />
      )}

      {nothingYet && (
        <Empty title="No answer sheets uploaded" hint="Each student's review, marks and reports appear here once their sheet is uploaded." />
      )}

      {rows.length > 0 && (
        <Card className="overflow-x-auto shadow-soft">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
            <div>
              <h3 className="text-sm font-semibold text-ink">Students ({rows.length})</h3>
              <p className="text-xs text-mute">{finalizedCount} of {rows.length} students finalized</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {!examFinalized && (
                <Button small variant="soft" busy={remapping === "all"} disabled={!!remapping}
                        title="Map every sheet's answers again with the current rules, then grade what is not yet approved"
                        onClick={() => remap("all")}>
                  Re-map &amp; evaluate all
                </Button>
              )}
              <Button
                small
                busy={bulkDownloading}
                disabled={finalizedCount === 0}
                onClick={downloadStudentReports}
                title={finalizedCount === 0 ? "Finalize at least one student first"
                  : `Download the report of all ${finalizedCount} finalized students (ZIP of PDFs)`}
              >
                Download All Student Reports
              </Button>
              <Button
                small
                busy={downloading}
                disabled={finalizedCount === 0}
                onClick={downloadExamReport}
                title={finalizedCount === 0 ? "Finalize at least one student first" : "Download the exam-wise class report (PDF)"}
              >
                Download Exam Report (PDF)
              </Button>
              {!examFinalized && (
                <Button
                  small
                  variant="primary"
                  disabled={!allFinalized}
                  onClick={() => setConfirmFinalize(true)}
                  title={!allFinalized ? "All students must be finalized first" : "Finalize exam"}
                >
                  Finalize the Whole Exam
                </Button>
              )}
            </div>
          </div>
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line bg-surface text-xs font-semibold uppercase tracking-wider text-mute">
              <tr>
                <th className="px-4 py-3">Student</th>
                <th className="px-4 py-3">Reading Status</th>
                <th className="px-4 py-3">Pages</th>
                <th className="px-4 py-3">Detected</th>
                <th className="px-4 py-3">Needs Review</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Marks</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line text-sm">
              {rows.map((e) => {
                const final = e.status === "FINALIZED";
                const opens = final ? `/results/${e.id}` : `/evaluations/${e.id}`;
                const busy = e.run_status === "RUNNING" || (!!e.document && BUSY_DOC.includes(e.document.status));
                const rollCheck = e.document?.roll_check?.status === "MISMATCH" ? e.document.roll_check : null;
                return (
                  <Fragment key={e.id}>
                  <tr className="align-top hover:bg-hover">
                    <td className="px-4 py-3">
                      <Link to={opens} className="font-mono font-medium text-pen hover:underline">{e.student.roll_number}</Link>
                      {!nameIsRoll(e.student) && (
                        <Link to={opens} className="block text-xs text-mute hover:text-pen hover:underline">{e.student.name}</Link>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {e.document && (
                        <div className="flex items-center gap-2">
                          <StatusBadge status={e.document.status} />
                          {BUSY_DOC.includes(e.document.status) && (
                            <span className="font-mono text-xs text-mute animate-pulse">
                              {e.document.stage || "reading..."}
                            </span>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 font-mono text-mute">{e.document?.pages.length ?? "–"}</td>
                    <td className="px-4 py-3 font-medium text-ink">{e.detected_answers}</td>
                    <td className="px-4 py-3">
                      {(e.unresolved_answers ?? 0) > 0 ? (
                        <span className="whitespace-nowrap"><Badge tone="warn">{e.unresolved_answers} to map</Badge></span>
                      ) : (
                        <span className="text-xs text-mute">0</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className="whitespace-nowrap"><StatusBadge status={e.status} /></span>
                      {(e.unresolved_answers ?? 0) === 0 && e.run_status && (
                        <p className="mt-1 text-xs text-mute">{label(e.run_status)}</p>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 font-medium text-ink">
                      {final ? (
                        <>
                          <p>{fmt(e.total_marks)} / {fmt(e.maximum_marks)}</p>
                          <p className="text-xs font-semibold text-mute">{e.percentage}%</p>
                        </>
                      ) : "–"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="ml-auto flex min-w-[15rem] flex-wrap items-center justify-end gap-1.5">
                        {final && (
                          <LinkButton to={`/results/${e.id}`} small variant="primary" className="shadow-xs">
                            View Report
                          </LinkButton>
                        )}
                        <LinkButton to={`/evaluations/${e.id}`} small variant={final ? "soft" : "primary"} className="shadow-xs">
                          <span>Open Review</span>
                          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                          </svg>
                        </LinkButton>
                        <Button small variant="soft" title="The sheet as read, how each answer was mapped, and the AI's grading notes"
                                onClick={() => downloadFile(`/evaluations/${e.id}/extraction-report.pdf`, "Sheet_Report.pdf")}>
                          Sheet Report
                        </Button>
                        {!final && (
                          <Button small variant="soft" busy={remapping === e.id}
                                  disabled={!!remapping || busy}
                                  title="Map this sheet's answers again with the current rules, then grade what is not yet approved"
                                  onClick={() => remap(e.id)}>
                            Re-map &amp; evaluate
                          </Button>
                        )}
                        <Button
                          small
                          variant="ghost"
                          className="text-mark hover:bg-mark-soft hover:text-mark"
                          disabled={busy}
                          onClick={() => setDel(e)}
                          title={busy ? "Wait for reading or grading to finish" : "Delete this answer sheet"}
                          icon={<IconTrash size={14} />}
                        >
                          Delete
                        </Button>
                      </div>
                    </td>
                  </tr>
                  {rollCheck && (
                    <tr>
                      <td colSpan={8} className="px-4 pb-3 pt-0">
                        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-warn/40 bg-warn-soft/40 p-2 text-xs">
                          <div>
                            <p className="font-semibold text-ink">
                              Roll number check: typed <span className="font-mono">{rollCheck.typed}</span>, the
                              sheet says <span className="font-mono">{rollCheck.written}</span>
                            </p>
                            <p className="mt-0.5 text-mute">Grading waits until you choose.</p>
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            <Button small variant="soft" busy={remapping === e.id + "typed"} disabled={!!remapping}
                                    onClick={() => settleRoll(e.id, e.document!.id, "typed")}>
                              Keep {rollCheck.typed}
                            </Button>
                            <Button small variant="soft" busy={remapping === e.id + "written"} disabled={!!remapping}
                                    onClick={() => settleRoll(e.id, e.document!.id, "written")}>
                              Use {rollCheck.written}
                            </Button>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}

      {questions.data && questions.data.finalized_students > 0 && (
        <details className="space-y-2">
          <summary className="cursor-pointer px-1 text-sm font-semibold text-ink">
            Question-wise analysis
            <span className="ml-2 text-xs font-normal text-mute">Across {questions.data.finalized_students} finalized student(s).</span>
          </summary>
          <Table
            head={["Question", "Max", "Avg. marks", "Avg. %", "Full marks", "Zero / not attempted"]}
            rows={questions.data.questions.map((q) => ({
              key: q.no,
              cells: [<span className="font-medium text-ink">Q{q.no}</span>, fmt(q.max), fmt(q.average),
                      q.percentage == null ? "–" : `${q.percentage}%`, q.full, q.zero],
            }))}
          />
        </details>
      )}

      {del && <DeleteSheetConfirm ev={del} onDeleted={refresh} onClose={() => setDel(null)} />}

      {confirmFinalize && (
        <Confirm
          title="Finalize Exam"
          confirmLabel="Finalize Whole Exam"
          body={
            <div className="space-y-2 text-sm text-ink">
              <p>
                Are you ready to mark exam <b>{exam.name}</b> as finalized?
              </p>
              <p className="text-xs text-mute">
                This locks all evaluations for this exam. No further student answer sheets can be added.
              </p>
              <p className="text-xs text-mute">
                Each student's official PDF report is saved. <b className="text-ink">24 hours later</b>, the uploaded files
                (question paper, answer key, answer sheets), page images and raw AI output are permanently deleted from this
                computer. Marks, results and the marksheet stay available.
              </p>
            </div>
          }
          onConfirm={async () => {
            try {
              await api(`/exams/${exam.id}/finalize`, { method: "POST" });
              await refresh();
            } catch (e) {
              setActionError(e);
              throw e;
            }
          }}
          onClose={() => setConfirmFinalize(false)}
        />
      )}
    </div>
  );
}
