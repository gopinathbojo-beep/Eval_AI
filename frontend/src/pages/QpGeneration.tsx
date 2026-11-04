import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import type { Exam } from "../types";
import { Badge, Button, Card, Confirm, ErrorPanel, Modal, PageHeader, Select } from "../components/ui";
import PaperGenerator, { type GenerateBody } from "../components/PaperGenerator";
import GeneratedPaperView, { GEN_BUSY, type GenPaperSummary } from "../components/GeneratedPaperView";

const EDITABLE = ["DRAFT", "QUESTION_PAPER_UPLOADED", "QUESTIONS_EXTRACTED"];

function UseInExam({ paper, onClose }: { paper: GenPaperSummary; onClose: () => void }) {
  const nav = useNavigate();
  const exams = useApi<Exam[]>("/exams");
  const [examId, setExamId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const open = (exams.data ?? []).filter((e) => EDITABLE.includes(e.status));
  const use = async () => {
    setBusy(true);
    setError(null);
    try {
      await api(`/generation/papers/${paper.id}/use/${examId}`, { method: "POST" });
      nav(`/exams/${examId}`);
    } catch (e) { setError(e); setBusy(false); }
  };
  return (
    <Modal title="Use in an exam" onClose={onClose}
           footer={<>
             <Button variant="secondary" onClick={onClose}>Cancel</Button>
             <Button variant="primary" busy={busy} disabled={!examId} onClick={use}>Use this paper</Button>
           </>}>
      <div className="space-y-3">
        <p className="text-sm text-mute">
          The questions and answer key go straight into the exam, verified, and it opens for answer sheets. Any paper
          already uploaded to that exam is replaced.
        </p>
        <Select value={examId} onChange={(e) => setExamId(e.target.value)} disabled={exams.loading}>
          <option value="">{exams.loading ? "Loading exams..." : open.length ? "Choose an exam" : "No exam is waiting for a question paper"}</option>
          {open.map((e) => <option key={e.id} value={e.id}>{e.name} ({e.class_name}, {e.subject_name})</option>)}
        </Select>
        <ErrorPanel error={error} />
      </div>
    </Modal>
  );
}

/** Question paper and answer key generation from the NCERT textbooks and CBSE sample papers (reference library). */
export default function QpGeneration() {
  const list = useApi<GenPaperSummary[]>("/generation/papers", (d) => (d.some((p) => GEN_BUSY.includes(p.status)) ? 3000 : null));
  const [body, setBody] = useState<GenerateBody | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [using, setUsing] = useState<GenPaperSummary | null>(null);
  const [deleting, setDeleting] = useState<GenPaperSummary | null>(null);
  const [showForm, setShowForm] = useState(true);

  const generate = async () => {
    if (!body) return;
    setBusy(true);
    setError(null);
    try {
      const gp = await api<GenPaperSummary>("/generation/papers", { method: "POST", json: body });
      setSelected(gp.id);
      setShowForm(false);
      await list.reload();
    } catch (e) { setError(e); } finally { setBusy(false); }
  };

  const current = list.data?.find((p) => p.id === selected) ?? null;

  return (
    <div className="space-y-6">
      <PageHeader title="QP & answer key generation"
                  sub="Generate CBSE question papers with matching answer keys, written from the NCERT textbooks and checked against them."
                  actions={!showForm && <Button variant="primary" onClick={() => setShowForm(true)}>New paper</Button>} />

      {showForm && (
        <Card className="p-6 space-y-5">
          <PaperGenerator onChange={setBody} disabled={busy} />
          <ErrorPanel error={error} />
          <div className="flex justify-end gap-2">
            {list.data && list.data.length > 0 && <Button variant="secondary" onClick={() => setShowForm(false)}>Close</Button>}
            <Button variant="primary" busy={busy} disabled={!body} onClick={generate}>Generate paper</Button>
          </div>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-[18rem_1fr]">
        <div className="space-y-2">
          <h2 className="text-sm font-semibold text-ink">Generated papers</h2>
          {list.data?.length === 0 && <p className="text-xs text-mute">None yet.</p>}
          {list.data?.map((p) => (
            <button key={p.id} type="button" onClick={() => setSelected(p.id)}
                    className={`w-full rounded-xl border p-3 text-left transition ${p.id === selected ? "border-blue-400 bg-blue-50" : "border-slate-200 bg-white hover:border-blue-200"}`}>
              <p className="truncate text-sm font-semibold text-ink">{p.title}</p>
              <p className="text-xs text-mute">Class {p.standard} {p.subject_name} &middot; {new Date(p.created_at).toLocaleDateString()}</p>
              <div className="mt-1 flex gap-2">
                {GEN_BUSY.includes(p.status) && <Badge tone="pen">Generating</Badge>}
                {p.status === "FAILED" && <Badge tone="mark">Failed</Badge>}
                {p.status === "READY" && <Badge tone="ok">{p.total_marks} marks</Badge>}
                {p.exam_id && <Badge tone="mute">In an exam</Badge>}
              </div>
            </button>
          ))}
        </div>
        <div className="min-w-0">
          {selected ? (
            <GeneratedPaperView key={selected} id={selected} onChanged={list.reload}
              actions={current && <>
                <Button small variant="primary" onClick={() => setUsing(current)}>Use in exam</Button>
                <Button small variant="ghost" onClick={() => setDeleting(current)}>Delete</Button>
              </>} />
          ) : (
            <Card className="p-10 text-center text-sm text-mute">Choose a generated paper to review it, or generate a new one.</Card>
          )}
        </div>
      </div>

      {using && <UseInExam paper={using} onClose={() => setUsing(null)} />}
      {deleting && (
        <Confirm title="Delete this generated paper?" body="Exams it was already used in keep their copy." confirmLabel="Delete" danger
                 onConfirm={async () => {
                   await api(`/generation/papers/${deleting.id}`, { method: "DELETE" });
                   setDeleting(null);
                   setSelected(null);
                   await list.reload();
                 }}
                 onClose={() => setDeleting(null)} />
      )}
    </div>
  );
}
