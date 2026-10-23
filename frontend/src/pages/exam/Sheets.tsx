import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, fetchBlobUrl } from "../../api/client";
import { useApi } from "../../hooks/useApi";
import type { Evaluation, IdentityRead, OutcomeSummary, ReviewSummary, Student, UnassignedSheet } from "../../types";
import { OutcomeTables } from "../../components/OutcomeTables";
import { BUSY_DOC, date, fmt, label } from "../../utils/format";
import { Badge, Button, Card, Confirm, Empty, ErrorPanel, Loading, Modal, Select, StatusBadge } from "../../components/ui";
import { UploadZone } from "../../components/DocPanel";
import { useExam } from "../ExamWorkspace";

export function ExamStudents() {
  const { exam } = useExam();
  const students = useApi<Student[]>(`/students?class_id=${exam.class_id}`);
  const sheets = useApi<Evaluation[]>(`/exams/${exam.id}/answer-sheets`);

  if (students.loading || sheets.loading) return <Loading />;
  const by = new Map((sheets.data ?? []).map((s) => [s.student.id, s]));

  if (!students.data?.length) {
    return (
      <Empty
        title="No students in this class"
        hint="Add or import students in the Students section."
      />
    );
  }

  return (
    <Card className="overflow-x-auto shadow-soft">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-line bg-surface text-xs font-semibold uppercase tracking-wider text-mute">
          <tr>
            <th className="px-4 py-3">Roll No.</th>
            <th className="px-4 py-3">Student Name</th>
            <th className="px-4 py-3">Answer Sheet</th>
            <th className="px-4 py-3">Evaluation Status</th>
            <th className="px-4 py-3 text-right">Marks</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line text-sm">
          {students.data.map((s) => {
            const ev = by.get(s.id);
            return (
              <tr key={s.id} className="hover:bg-hover">
                <td className="whitespace-nowrap px-4 py-3 font-mono font-medium text-ink">{s.roll_number}</td>
                <td className="px-4 py-3 font-medium text-ink">{s.name}</td>
                <td className="px-4 py-3">
                  {ev ? (
                    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-ok">
                      <span className="h-1.5 w-1.5 rounded-full bg-ok" />
                      Uploaded
                    </span>
                  ) : (
                    <span className="text-xs text-mute">Not uploaded</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  {ev ? (
                    <Link
                      to={ev.status === "FINALIZED" ? `/results/${ev.id}` : `/evaluations/${ev.id}`}
                      className="inline-block transition-opacity hover:opacity-80"
                    >
                      <StatusBadge status={ev.status} />
                    </Link>
                  ) : (
                    <span className="text-mute">–</span>
                  )}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-right font-medium text-ink">
                  {ev?.status === "FINALIZED" ? (
                    <span className="rounded bg-ok-soft px-2 py-0.5 text-xs text-ok font-semibold">
                      {fmt(ev.total_marks)} / {fmt(ev.maximum_marks)}
                    </span>
                  ) : (
                    <span className="text-mute">–</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}

const UPLOAD_BATCH = 10;

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

/** The batch summary, polled while sheets are still being read or graded. `onProgress` refreshes the lists alongside,
 * but only when a sheet has moved on, not on every poll. */
function useReviewSummary(examId: string, onProgress?: () => Promise<unknown>) {
  const progress = useRef(onProgress);
  progress.current = onProgress;
  const last = useRef<number | null>(null);
  return useApi<ReviewSummary>(`/exams/${examId}/review-summary`, (d) => {
    if (last.current !== null && last.current !== d.processing) void progress.current?.();
    last.current = d.processing;
    return d.processing ? POLL_MS : null;
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
                Reading and grading sheets one after another: {summary.processing} still in progress…
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
                  <p className="font-mono text-xs text-mute">Roll: {r.student.roll_number}</p>
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

export function AnswerSheets() {
  const { exam, reload } = useExam();
  const students = useApi<Student[]>(`/students?class_id=${exam.class_id}`);
  const sheets = useApi<Evaluation[]>(
    `/exams/${exam.id}/answer-sheets`,
    (d) => (d.some((s) => (s.document && BUSY_DOC.includes(s.document.status)) || s.run_status === "RUNNING") ? POLL_MS : null)
  );
  const unassigned = useApi<UnassignedSheet[]>(
    `/exams/${exam.id}/answer-sheets/unassigned`,
    (d) => (d.some((s) => BUSY_DOC.includes(s.status)) ? POLL_MS : null)
  );
  const summary = useReviewSummary(exam.id, () => Promise.all([sheets.reload(), unassigned.reload()]));

  const [del, setDel] = useState<Evaluation | null>(null);
  const [progress, setProgress] = useState<string | null>(null);

  const open = ["ANSWER_KEY_VERIFIED", "READY_FOR_EVALUATION", "EVALUATING", "REVIEW_REQUIRED"].includes(exam.status);
  const taken = new Set((sheets.data ?? []).map((s) => s.student.id));

  const refresh = async () => {
    await Promise.all([sheets.reload(), unassigned.reload(), summary.reload(), reload()]);
  };

  const upload = async (files: File[]) => {
    try {
      for (let i = 0; i < files.length; i += UPLOAD_BATCH) {
        const batch = files.slice(i, i + UPLOAD_BATCH);
        setProgress(`Uploading ${Math.min(i + batch.length, files.length)} of ${files.length}…`);
        const f = new FormData();
        batch.forEach((file) => f.append("files", file));
        await api(`/exams/${exam.id}/answer-sheets/bulk`, { method: "POST", form: f });
        await Promise.all([unassigned.reload(), summary.reload()]);
      }
    } finally {
      setProgress(null);
      await refresh();
    }
  };

  return (
    <div className="space-y-5">
      {!open ? (
        <Card className="flex items-center gap-3 p-4 text-sm text-mute">
          <svg className="h-5 w-5 text-warn flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span>Answer sheets can be uploaded once the exam questions and answer key are verified.</span>
        </Card>
      ) : (
        <Card className="space-y-4 p-5 shadow-soft">
          <div className="border-b border-line pb-3">
            <h2 className="text-lg font-semibold text-ink">Upload Student Answer Sheets</h2>
            <p className="text-xs text-mute">
              Drop all sheets at once. Each is matched to its student by the registration or roll number on it.
            </p>
          </div>
          <UploadZone
            accept=".pdf,.png,.jpg,.jpeg,.docx"
            onFiles={upload}
            hint={progress ?? "PDF, Word, PNG or JPG. One student per file."}
          />
          {!students.loading && !students.data?.length && (
            <p className="text-xs text-warn">
              No students in {exam.class_name} yet. Add or import them in the Students section so sheets can be matched.
            </p>
          )}
        </Card>
      )}

      <ErrorPanel error={sheets.error || unassigned.error} />

      {summary.data && <BatchReview examId={exam.id} summary={summary.data} onChanged={refresh} />}

      {unassigned.data && unassigned.data.length > 0 && (
        <UnassignedSheets rows={unassigned.data} students={students.data ?? []} taken={taken} onChanged={refresh} />
      )}


      {sheets.data && sheets.data.length > 0 && (
        <Card className="overflow-x-auto shadow-soft">
          <div className="border-b border-line px-4 py-3">
            <h3 className="text-sm font-semibold text-ink">Uploaded Answer Sheets ({sheets.data.length})</h3>
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
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line text-sm">
              {sheets.data.map((e) => (
                <tr key={e.id} className="hover:bg-hover">
                  <td className="px-4 py-3">
                    <p className="font-medium text-ink">{e.student.name}</p>
                    <p className="font-mono text-xs text-mute">Roll: {e.student.roll_number}</p>
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
                      <Badge tone="warn">{e.unresolved_answers} to map</Badge>
                    ) : (
                      <span className="text-xs text-mute">0</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={e.status} />
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1.5">
                      <Link to={`/evaluations/${e.id}`}>
                        <Button small variant="primary" className="shadow-xs">
                          <span>Open Review</span>
                          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                          </svg>
                        </Button>
                      </Link>
                      {e.status !== "FINALIZED" && (
                        <Button
                          small
                          variant="ghost"
                          className="text-mark hover:bg-mark-soft hover:text-mark"
                          onClick={() => setDel(e)}
                          title="Delete sheet"
                        >
                          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {del && (
        <Confirm
          title="Delete Answer Sheet"
          danger
          confirmLabel="Delete Sheet"
          body={
            <div className="space-y-2 text-sm text-ink">
              <p>
                Remove <b>{del.student.name}</b>'s answer sheet and all extracted evaluation marks?
              </p>
              <p className="text-xs text-mute">
                The original file is kept and the deletion is logged.
              </p>
            </div>
          }
          onConfirm={async () => {
            await api(`/evaluations/${del.id}`, { method: "DELETE" });
            await refresh();
          }}
          onClose={() => setDel(null)}
        />
      )}
    </div>
  );
}

export function ExamEvaluation() {
  const { exam, reload } = useExam();
  const { data, loading, error, reload: reloadSheets } = useApi<Evaluation[]>(`/exams/${exam.id}/answer-sheets`);
  const summary = useReviewSummary(exam.id, reloadSheets);

  if (loading) return <Loading />;
  if (error) return <ErrorPanel error={error} />;
  if (!data?.length) {
    return (
      <Empty
        title="No answer sheets uploaded"
        hint="Upload answer sheets in the Answer Sheets tab to begin evaluation."
      />
    );
  }

  return (
    <div className="space-y-3">
      {summary.data && (
        <BatchReview
          examId={exam.id}
          summary={summary.data}
          onChanged={async () => { await Promise.all([reloadSheets(), summary.reload(), reload()]); }}
        />
      )}
      <div className="flex items-center justify-between px-1">
        <h3 className="text-sm font-semibold text-ink">Student Evaluation Queue ({data.length})</h3>
        <span className="text-xs text-mute">Click any student to open the evaluation workspace</span>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {data.map((e) => (
          <Link
            key={e.id}
            to={`/evaluations/${e.id}`}
            className="group block rounded-lg border border-line bg-surface p-4 shadow-soft transition-all hover:border-pen/40 hover:shadow-card"
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="font-semibold text-ink group-hover:text-brown transition-colors">
                  {e.student.name}
                </p>
                <p className="font-mono text-xs text-mute">Roll: {e.student.roll_number}</p>
              </div>
              <StatusBadge status={e.status} />
            </div>
            <div className="mt-3 flex items-center justify-between border-t border-line/60 pt-2.5 text-xs text-mute">
              <span>
                {(e.unresolved_answers ?? 0) > 0 ? (
                  <span className="font-semibold text-mark">{e.unresolved_answers} need mapping</span>
                ) : (
                  <span>{label(e.run_status)}</span>
                )}
              </span>
              <span className="inline-flex items-center gap-1 font-medium text-pen group-hover:translate-x-0.5 transition-transform">
                Open &rarr;
              </span>
            </div>
          </Link>
        ))}
      </div>
    </div>
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

export function ExamResults() {
  const { exam, reload } = useExam();
  const { data, loading, error } = useApi<Evaluation[]>(`/exams/${exam.id}/results`);
  const outcomes = useApi<OutcomeSummary>(`/exams/${exam.id}/outcome-summary`);
  const [err, setErr] = useState<unknown>(null);
  const [confirm, setConfirm] = useState(false);

  if (loading) return <Loading />;
  const done = (data ?? []).filter((e) => e.status === "FINALIZED");
  const allFinalized = data && data.length > 0 && done.length === data.length;

  return (
    <div className="space-y-4">
      <ErrorPanel error={error ?? err} />

      {exam.status === "FINALIZED" && <ExamFilesNotice />}

      {!data?.length ? (
        <Empty title="No evaluation results yet" hint="Results appear as answer sheets are evaluated and finalized." />
      ) : (
        <>
          <Card className="overflow-x-auto shadow-soft">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
              <div>
                <h3 className="text-sm font-semibold text-ink">Exam Final Results</h3>
                <p className="text-xs text-mute">
                  {done.length} of {data.length} students finalized
                </p>
              </div>
              {exam.status !== "FINALIZED" && (
                <Button
                  variant="primary"
                  disabled={!allFinalized}
                  onClick={() => setConfirm(true)}
                  title={!allFinalized ? "All students must be finalized first" : "Finalize exam"}
                >
                  Finalize the Whole Exam
                </Button>
              )}
            </div>
            <table className="w-full text-left text-sm">
              <thead className="border-b border-line bg-surface text-xs font-semibold uppercase tracking-wider text-mute">
                <tr>
                  <th className="px-4 py-3">Roll No.</th>
                  <th className="px-4 py-3">Student Name</th>
                  <th className="px-4 py-3">Total Marks</th>
                  <th className="px-4 py-3">Percentage</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line text-sm">
                {data.map((e) => (
                  <tr key={e.id} className="hover:bg-hover">
                    <td className="whitespace-nowrap px-4 py-3 font-mono font-medium text-ink">
                      {e.student.roll_number}
                    </td>
                    <td className="px-4 py-3 font-medium text-ink">
                      <Link
                        className="text-pen hover:underline"
                        to={e.status === "FINALIZED" ? `/results/${e.id}` : `/evaluations/${e.id}`}
                      >
                        {e.student.name}
                      </Link>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 font-medium text-ink">
                      {e.status === "FINALIZED" ? `${fmt(e.total_marks)} / ${fmt(e.maximum_marks)}` : "–"}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 font-medium text-ink">
                      {e.status === "FINALIZED" ? (
                        <span className="inline-flex items-center gap-1.5">
                          <span className="font-semibold">{e.percentage}%</span>
                        </span>
                      ) : (
                        "–"
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={e.status} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        to={e.status === "FINALIZED" ? `/results/${e.id}` : `/evaluations/${e.id}`}
                        className="text-xs font-medium text-pen hover:underline"
                      >
                        {e.status === "FINALIZED" ? "View Report →" : "Review →"}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          {outcomes.data && outcomes.data.finalized_students > 0 && (
            <div className="space-y-2">
              <p className="px-1 text-xs text-mute">
                Class performance across {outcomes.data.finalized_students} finalized student(s).
              </p>
              <OutcomeTables outcomes={outcomes.data} average />
            </div>
          )}
        </>
      )}

      {confirm && (
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
              await reload();
            } catch (e) {
              setErr(e);
              throw e;
            }
          }}
          onClose={() => setConfirm(false)}
        />
      )}
    </div>
  );
}
