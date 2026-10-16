import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { useApi } from "../../hooks/useApi";
import type { Evaluation, Student } from "../../types";
import { BUSY_DOC, fmt, label } from "../../utils/format";
import { Badge, Button, Card, Confirm, Empty, ErrorPanel, Field, Input, Loading, Select, StatusBadge } from "../../components/ui";
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
        hint="Students are added automatically when you upload their answer sheet, or you can enroll them under the Students roster."
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
              <tr key={s.id} className="hover:bg-sunken/40">
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

export function AnswerSheets() {
  const { exam, reload } = useExam();
  const students = useApi<Student[]>(`/students?class_id=${exam.class_id}`);
  const sheets = useApi<Evaluation[]>(
    `/exams/${exam.id}/answer-sheets`,
    (d) => (d.some((s) => s.document && BUSY_DOC.includes(s.document.status)) ? 2000 : null)
  );

  const [mode, setMode] = useState<"existing" | "new">("existing");
  const [studentId, setStudentId] = useState("");
  const [name, setName] = useState("");
  const [roll, setRoll] = useState("");
  const [del, setDel] = useState<Evaluation | null>(null);

  const open = ["ANSWER_KEY_VERIFIED", "READY_FOR_EVALUATION", "EVALUATING", "REVIEW_REQUIRED"].includes(exam.status);
  const taken = new Set((sheets.data ?? []).map((s) => s.student.id));
  const identified = mode === "existing" ? Boolean(studentId) : Boolean(name.trim() && roll.trim());

  const upload = async (file: File) => {
    const f = new FormData();
    f.append("file", file);
    if (mode === "existing" && studentId) {
      f.append("student_id", studentId);
    } else {
      f.append("student_name", name.trim());
      f.append("roll_number", roll.trim());
    }
    await api(`/exams/${exam.id}/answer-sheets`, { method: "POST", form: f });
    setStudentId("");
    setName("");
    setRoll("");
    await Promise.all([sheets.reload(), students.reload(), reload()]);
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
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
            <div>
              <h2 className="text-base font-semibold text-ink">Upload Student Answer Sheet</h2>
              <p className="text-xs text-mute">Identify the student and upload their scanned answer document.</p>
            </div>
            <div className="flex rounded-lg border border-line bg-sunken p-0.5 text-xs">
              <button
                type="button"
                onClick={() => setMode("existing")}
                className={`rounded-md px-3 py-1 font-medium transition-colors ${
                  mode === "existing" ? "bg-surface font-semibold text-pen shadow-xs" : "text-mute hover:text-ink"
                }`}
              >
                Enrolled Student
              </button>
              <button
                type="button"
                onClick={() => setMode("new")}
                className={`rounded-md px-3 py-1 font-medium transition-colors ${
                  mode === "new" ? "bg-surface font-semibold text-pen shadow-xs" : "text-mute hover:text-ink"
                }`}
              >
                New Student
              </button>
            </div>
          </div>

          {mode === "existing" ? (
            <div className="max-w-md">
              <Field label="Choose Enrolled Student" hint="Only students without an uploaded sheet appear here.">
                {(id) => (
                  <Select id={id} value={studentId} onChange={(e) => setStudentId(e.target.value)}>
                    <option value="">Select a student...</option>
                    {students.data
                      ?.filter((s) => !taken.has(s.id))
                      .map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.roll_number} — {s.name}
                        </option>
                      ))}
                  </Select>
                )}
              </Field>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 max-w-lg">
              <Field label="Student Full Name">
                {(id) => <Input id={id} placeholder="e.g. Aditi Sharma" value={name} onChange={(e) => setName(e.target.value)} />}
              </Field>
              <Field label="Roll Number">
                {(id) => <Input id={id} placeholder="e.g. 101" value={roll} onChange={(e) => setRoll(e.target.value)} />}
              </Field>
            </div>
          )}

          <UploadZone
            accept=".pdf,.png,.jpg,.jpeg"
            disabled={!identified}
            onFile={upload}
            hint={
              identified
                ? "PDF, PNG or JPG. Ensure answer numbers are legible. One student per file."
                : "Select or enter the student details above to enable upload."
            }
          />
        </Card>
      )}

      <ErrorPanel error={sheets.error} />

      {sheets.data && sheets.data.length > 0 && (
        <Card className="overflow-x-auto shadow-soft">
          <div className="border-b border-line px-4 py-3">
            <h3 className="text-sm font-semibold text-ink">Uploaded Answer Sheets ({sheets.data.length})</h3>
          </div>
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line bg-surface text-xs font-semibold uppercase tracking-wider text-mute">
              <tr>
                <th className="px-4 py-3">Student</th>
                <th className="px-4 py-3">OCR Status</th>
                <th className="px-4 py-3">Pages</th>
                <th className="px-4 py-3">Detected</th>
                <th className="px-4 py-3">Needs Review</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line text-sm">
              {sheets.data.map((e) => (
                <tr key={e.id} className="hover:bg-sunken/40">
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
                The original file is retained in storage and the deletion will be recorded in the audit trail.
              </p>
            </div>
          }
          onConfirm={async () => {
            await api(`/evaluations/${del.id}`, { method: "DELETE" });
            await Promise.all([sheets.reload(), reload()]);
          }}
          onClose={() => setDel(null)}
        />
      )}
    </div>
  );
}

export function ExamEvaluation() {
  const { exam } = useExam();
  const { data, loading, error } = useApi<Evaluation[]>(`/exams/${exam.id}/answer-sheets`);

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
      <div className="flex items-center justify-between px-1">
        <h3 className="text-sm font-semibold text-ink">Student Evaluation Queue ({data.length})</h3>
        <span className="text-xs text-mute">Click any student to open the evaluation workspace</span>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {data.map((e) => (
          <Link
            key={e.id}
            to={`/evaluations/${e.id}`}
            className="group block rounded-xl border border-line bg-surface p-4 shadow-soft transition-all hover:border-pen/40 hover:shadow-card"
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="font-semibold text-ink group-hover:text-pen transition-colors">
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

export function ExamResults() {
  const { exam, reload } = useExam();
  const { data, loading, error } = useApi<Evaluation[]>(`/exams/${exam.id}/results`);
  const [err, setErr] = useState<unknown>(null);
  const [confirm, setConfirm] = useState(false);

  if (loading) return <Loading />;
  const done = (data ?? []).filter((e) => e.status === "FINALIZED");
  const allFinalized = data && data.length > 0 && done.length === data.length;

  return (
    <div className="space-y-4">
      <ErrorPanel error={error ?? err} />

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
                  <tr key={e.id} className="hover:bg-sunken/40">
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
                        {e.status === "FINALIZED" ? "View Report &rarr;" : "Review &rarr;"}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
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
