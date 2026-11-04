import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { Button, Card, ErrorPanel, Modal } from "./ui";
import PaperGenerator, { type GenerateBody } from "./PaperGenerator";
import GeneratedPaperView, { GEN_BUSY, GenerationStatus, type GenPaperSummary } from "./GeneratedPaperView";

interface ExamGen { subject: { grade: "10" | "12"; key: string } | null; paper: GenPaperSummary | null }

/** Exam workspace: write this exam's question paper and answer key with the AI instead of uploading them. */
export default function ExamPaperGenerator({ examId, examStatus, locked, onAttached }: {
  examId: string; examStatus: string; locked: boolean; onAttached: () => void;
}) {
  const { data, reload } = useApi<ExamGen>(`/exams/${examId}/generated-paper`, (d) => {
    if (d.paper && GEN_BUSY.includes(d.paper.status)) return 2500;
    return null;
  });
  const [open, setOpen] = useState(false);
  const [view, setView] = useState(false);
  const [body, setBody] = useState<GenerateBody | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const gp = data?.paper;
  const attached = examStatus === "READY_FOR_EVALUATION";
  const running = !!gp && GEN_BUSY.includes(gp.status);
  // generation finished while this page was open: the paper was attached, refresh the documents
  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current && !running) onAttached();
    wasRunning.current = running;
  }, [running]);

  if (!data || (!data.subject && !gp)) return null;
  if (locked && !gp) return null;

  const reattach = async () => {
    if (!gp) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/generation/papers/${gp.id}/use/${examId}`, { method: "POST" });
      await reload();
      onAttached();
    } catch (e) { setError(e); } finally { setBusy(false); }
  };

  const start = async () => {
    if (!body) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/exams/${examId}/generate-paper`, { method: "POST", json: body });
      setOpen(false);
      await reload();
      onAttached();  // the exam page shows the progress too (banner, tab badges)
    } catch (e) { setError(e); } finally { setBusy(false); }
  };

  return (
    <Card className="p-5 shadow-soft space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-ink">
            {running ? "Generating the question paper and answer key" : attached && gp ? "AI-generated question paper" : "Generate with AI"}
          </h2>
          <p className="text-xs text-mute">
            {running
              ? "The questions and answer key appear below when they are ready, already verified. This page updates by itself."
              : attached && gp
              ? "Written from the NCERT textbook and CBSE sample papers. The questions below and the answer key are verified."
              : "No paper yet? The AI writes the question paper and answer key from the NCERT textbook and CBSE sample papers. They go straight into the exam, verified, with no reading or review step."}
          </p>
        </div>
        <div className="flex gap-2">
          {gp?.status === "READY" && <Button small variant="soft" onClick={() => setView(true)}>View generated paper</Button>}
          {!locked && gp?.status === "READY" && !attached && (
            <Button small variant="primary" busy={busy} onClick={reattach}>Use this paper (no review)</Button>
          )}
          {!locked && data.subject && (
            <Button small variant="primary" disabled={running} onClick={() => setOpen(true)}>
              {gp ? "Generate again" : "Generate paper"}
            </Button>
          )}
        </div>
      </div>
      {gp && <GenerationStatus gp={gp} />}
      {!open && <ErrorPanel error={error} />}
      {gp?.status === "READY" && !gp.error && gp.exam_id === examId && attached && (
        <p className="text-xs text-ok">The generated questions and answer key are in this exam and verified. You can upload answer sheets now.</p>
      )}
      {gp?.status === "READY" && gp.error && <p className="text-xs text-rose-700">{gp.error}</p>}

      {open && data.subject && (
        <Modal title="Generate question paper and answer key" wide onClose={() => setOpen(false)}
               footer={<>
                 <Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
                 <Button variant="primary" busy={busy} disabled={!body} onClick={start}>Generate</Button>
               </>}>
          <div className="space-y-4">
            <PaperGenerator grade={data.subject.grade} subjectKey={data.subject.key} onChange={setBody} disabled={busy} />
            <p className="text-xs text-mute">A question paper or answer key already uploaded to this exam is replaced.</p>
            <ErrorPanel error={error} />
          </div>
        </Modal>
      )}
      {view && gp && (
        <Modal title="Generated paper" wide="xl" onClose={() => setView(false)}>
          <GeneratedPaperView id={gp.id} />
        </Modal>
      )}
    </Card>
  );
}
