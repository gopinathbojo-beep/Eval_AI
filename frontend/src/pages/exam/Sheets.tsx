import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { useApi } from "../../hooks/useApi";
import type { Evaluation, Student } from "../../types";
import { BUSY_DOC, fmt, label } from "../../utils/format";
import { Button, Card, Confirm, Empty, ErrorPanel, Field, Input, Loading, Select, StatusBadge } from "../../components/ui";
import { UploadZone } from "../../components/DocPanel";
import { useExam } from "../ExamWorkspace";

export function ExamStudents() {
  const { exam } = useExam();
  const students = useApi<Student[]>(`/students?class_id=${exam.class_id}`);
  const sheets = useApi<Evaluation[]>(`/exams/${exam.id}/answer-sheets`);
  if (students.loading || sheets.loading) return <Loading />;
  const by = new Map((sheets.data ?? []).map((s) => [s.student.id, s]));
  if (!students.data?.length) return <Empty title="No students in this class" hint="Students are added automatically when you upload their answer sheet, or add them under Students." />;
  return (
    <Card className="overflow-x-auto"><table className="w-full text-sm">
      <thead className="border-b border-line text-left text-mute"><tr>{["Roll no.", "Name", "Answer sheet", "Evaluation", "Marks"].map((h) => <th key={h} className="px-4 py-2 font-medium">{h}</th>)}</tr></thead>
      <tbody className="divide-y divide-line">{students.data.map((s) => { const ev = by.get(s.id); return (
        <tr key={s.id}><td className="px-4 py-2">{s.roll_number}</td><td className="px-4 py-2">{s.name}</td>
          <td className="px-4 py-2">{ev ? "Uploaded" : <span className="text-mute">Not uploaded</span>}</td>
          <td className="px-4 py-2">{ev ? <Link to={ev.status === "FINALIZED" ? `/results/${ev.id}` : `/evaluations/${ev.id}`}><StatusBadge status={ev.status} /></Link> : "–"}</td>
          <td className="px-4 py-2">{ev?.status === "FINALIZED" ? `${fmt(ev.total_marks)} / ${fmt(ev.maximum_marks)}` : "–"}</td></tr>); })}</tbody>
    </table></Card>
  );
}

export function AnswerSheets() {
  const { exam, reload } = useExam();
  const students = useApi<Student[]>(`/students?class_id=${exam.class_id}`);
  const sheets = useApi<Evaluation[]>(`/exams/${exam.id}/answer-sheets`, (d) => (d.some((s) => s.document && BUSY_DOC.includes(s.document.status)) ? 2000 : null));
  const [studentId, setStudentId] = useState("");
  const [name, setName] = useState("");
  const [roll, setRoll] = useState("");
  const [del, setDel] = useState<Evaluation | null>(null);
  const open = ["ANSWER_KEY_VERIFIED", "READY_FOR_EVALUATION", "EVALUATING", "REVIEW_REQUIRED"].includes(exam.status);
  const taken = new Set((sheets.data ?? []).map((s) => s.student.id));
  const identified = studentId || (name.trim() && roll.trim());
  const upload = async (file: File) => {
    const f = new FormData(); f.append("file", file);
    if (studentId) f.append("student_id", studentId); else { f.append("student_name", name); f.append("roll_number", roll); }
    await api(`/exams/${exam.id}/answer-sheets`, { method: "POST", form: f });
    setStudentId(""); setName(""); setRoll("");
    await Promise.all([sheets.reload(), students.reload(), reload()]);
  };
  return (
    <div className="space-y-5">
      {!open ? <Card className="p-4 text-sm">Answer sheets can be uploaded once the answer key is verified.</Card> : (
        <Card className="space-y-4 p-5">
          <h2 className="font-semibold">Upload a student's answer sheet</h2>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Existing student">{(id) => <Select id={id} value={studentId} onChange={(e) => setStudentId(e.target.value)}><option value="">New student…</option>
              {students.data?.filter((s) => !taken.has(s.id)).map((s) => <option key={s.id} value={s.id}>{s.roll_number} — {s.name}</option>)}</Select>}</Field>
            {!studentId && <><Field label="Name">{(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
              <Field label="Roll number">{(id) => <Input id={id} value={roll} onChange={(e) => setRoll(e.target.value)} />}</Field></>}
          </div>
          <UploadZone accept=".pdf,.png,.jpg,.jpeg" disabled={!identified} onFile={upload} hint={identified ? "PDF, PNG or JPG. One student per file." : "Choose or enter the student first."} />
        </Card>
      )}
      <ErrorPanel error={sheets.error} />
      {sheets.data && sheets.data.length > 0 && (
        <Card className="overflow-x-auto"><table className="w-full text-sm">
          <thead className="border-b border-line text-left text-mute"><tr>{["Student", "Reading", "Pages", "Answers found", "Need review", "Status", ""].map((h) => <th key={h} className="px-4 py-2 font-medium">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-line">{sheets.data.map((e) => (
            <tr key={e.id}><td className="px-4 py-2">{e.student.roll_number} — {e.student.name}</td>
              <td className="px-4 py-2">{e.document && <StatusBadge status={e.document.status} />}{e.document && BUSY_DOC.includes(e.document.status) && <span className="ml-2 text-xs text-mute">{e.document.stage}</span>}</td>
              <td className="px-4 py-2">{e.document?.pages.length ?? "–"}</td><td className="px-4 py-2">{e.detected_answers}</td>
              <td className={`px-4 py-2 ${e.unresolved_answers ? "font-medium text-mark" : ""}`}>{e.unresolved_answers}</td>
              <td className="px-4 py-2"><StatusBadge status={e.status} /></td>
              <td className="space-x-2 whitespace-nowrap px-4 py-2 text-right">
                <Link to={`/evaluations/${e.id}`}><Button small>Open</Button></Link>
                {e.status !== "FINALIZED" && <Button small variant="ghost" onClick={() => setDel(e)}>Delete</Button>}</td></tr>))}</tbody>
        </table></Card>
      )}
      {del && <Confirm title="Delete answer sheet" danger confirmLabel="Delete" body={<p>Remove {del.student.name}'s answer sheet and its evaluation? The original file stays on disk and the deletion is logged.</p>}
        onConfirm={async () => { await api(`/evaluations/${del.id}`, { method: "DELETE" }); await Promise.all([sheets.reload(), reload()]); }} onClose={() => setDel(null)} />}
    </div>
  );
}

export function ExamEvaluation() {
  const { exam } = useExam();
  const { data, loading, error } = useApi<Evaluation[]>(`/exams/${exam.id}/answer-sheets`);
  if (loading) return <Loading />;
  if (error) return <ErrorPanel error={error} />;
  if (!data?.length) return <Empty title="No answer sheets yet" hint="Upload answer sheets to begin evaluating." />;
  return (
    <Card className="divide-y divide-line">{data.map((e) => (
      <Link key={e.id} to={`/evaluations/${e.id}`} className="flex flex-wrap items-center justify-between gap-2 p-4 hover:bg-sunken">
        <div><p className="font-medium">{e.student.name} <span className="text-mute">({e.student.roll_number})</span></p>
          <p className="text-xs text-mute">{e.unresolved_answers ? `${e.unresolved_answers} answer(s) need mapping` : label(e.run_status)}</p></div>
        <StatusBadge status={e.status} /></Link>))}</Card>
  );
}

export function ExamResults() {
  const { exam, reload } = useExam();
  const { data, loading, error } = useApi<Evaluation[]>(`/exams/${exam.id}/results`);
  const [err, setErr] = useState<unknown>(null);
  const [confirm, setConfirm] = useState(false);
  if (loading) return <Loading />;
  const done = (data ?? []).filter((e) => e.status === "FINALIZED");
  return (
    <div className="space-y-4">
      <ErrorPanel error={error ?? err} />
      {!data?.length ? <Empty title="No results yet" /> : (
        <Card className="overflow-x-auto"><table className="w-full text-sm">
          <thead className="border-b border-line text-left text-mute"><tr>{["Roll no.", "Student", "Marks", "Percentage", "Status"].map((h) => <th key={h} className="px-4 py-2 font-medium">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-line">{data.map((e) => (
            <tr key={e.id}><td className="px-4 py-2">{e.student.roll_number}</td>
              <td className="px-4 py-2"><Link className="text-pen hover:underline" to={e.status === "FINALIZED" ? `/results/${e.id}` : `/evaluations/${e.id}`}>{e.student.name}</Link></td>
              <td className="px-4 py-2">{e.status === "FINALIZED" ? `${fmt(e.total_marks)} / ${fmt(e.maximum_marks)}` : "–"}</td>
              <td className="px-4 py-2">{e.status === "FINALIZED" ? `${e.percentage}%` : "–"}</td><td className="px-4 py-2"><StatusBadge status={e.status} /></td></tr>))}</tbody>
        </table></Card>
      )}
      {exam.status !== "FINALIZED" && data && data.length > 0 && (
        <Button disabled={done.length !== data.length} onClick={() => setConfirm(true)}>Finalize the whole exam</Button>
      )}
      {confirm && <Confirm title="Finalize exam" confirmLabel="Finalize exam" body={<p>This closes the exam. No more answer sheets can be added.</p>}
        onConfirm={async () => { try { await api(`/exams/${exam.id}/finalize`, { method: "POST" }); await reload(); } catch (e) { setErr(e); throw e; } }} onClose={() => setConfirm(false)} />}
    </div>
  );
}
