import { useState, type ReactNode } from "react";
import { api, downloadFile } from "../api/client";
import { useApi } from "../hooks/useApi";
import { Badge, Button, Card, ErrorPanel, Loading, Spinner, Textarea } from "./ui";

export interface GenSource { id: number; chapter: string; title: string; pages: string; excerpt: string }
export interface GenItem {
  text: string; options: string[]; answer: string; marking_points: { point: string; marks: number }[];
  type: string; difficulty: string; sources: GenSource[]; support: number | null;
  grounding: "GROUNDED" | "PARTIAL" | "WEAK" | "UNSUPPORTED"; notes: string[]; edited?: boolean;
}
export interface GenQuestion extends GenItem { number: number; section: string; marks: number; or: GenItem | null }
export interface GenPaperSummary {
  id: string; exam_id: string | null; standard: number; subject: string; subject_name: string | null; title: string;
  status: "QUEUED" | "GENERATING" | "READY" | "FAILED"; stage: string | null; error: string | null; created_at: string;
  total_marks: number | null; question_count: number; flagged: number;
}
export interface GenPaper extends GenPaperSummary {
  paper: null | { title: string; total_marks: number; duration_minutes: number; instructions: string[];
                  questions: GenQuestion[]; chapters: string[] };
}

export const GEN_BUSY = ["QUEUED", "GENERATING"];
const GROUNDING: Record<GenItem["grounding"], { tone: "ok" | "warn" | "mark"; text: string }> = {
  GROUNDED: { tone: "ok", text: "From the textbook" },
  PARTIAL: { tone: "warn", text: "Partly in the textbook" },
  WEAK: { tone: "mark", text: "Check: weak textbook support" },
  UNSUPPORTED: { tone: "mark", text: "Check: no source cited" },
};

export function GenerationStatus({ gp }: { gp: GenPaperSummary }) {
  if (GEN_BUSY.includes(gp.status))
    return (
      <div className="flex items-center gap-3 text-sm text-ink">
        <Spinner size={16} />
        <span>{gp.stage || "Generating"}... a full board paper takes about 3-5 minutes.</span>
      </div>
    );
  if (gp.status === "FAILED") return <p className="text-sm text-rose-700">Generation failed: {gp.error}</p>;
  return null;
}

function Item({ q, marks, showAnswers, onSave }: { q: GenItem; marks: number; showAnswers: boolean;
                                                 onSave: (patch: Partial<GenItem>) => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(q.text);
  const [answer, setAnswer] = useState(q.answer);
  const [busy, setBusy] = useState(false);
  const g = GROUNDING[q.grounding] ?? GROUNDING.UNSUPPORTED;
  const save = async () => {
    setBusy(true);
    try { await onSave({ text, answer }); setEditing(false); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-2">
      {editing ? (
        <Textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} />
      ) : (
        <p className="whitespace-pre-wrap text-sm text-ink">{q.text}</p>
      )}
      {q.options.length > 0 && (
        <ol className="grid gap-1 text-sm text-ink sm:grid-cols-2">
          {q.options.map((o, i) => <li key={i}>({String.fromCharCode(97 + i)}) {o}</li>)}
        </ol>
      )}
      {showAnswers && (
        <div className="rounded-xl bg-slate-50 p-3 space-y-2">
          {editing ? (
            <Textarea rows={4} value={answer} onChange={(e) => setAnswer(e.target.value)} />
          ) : (
            <p className="whitespace-pre-wrap text-sm text-ink"><b>Answer:</b> {q.answer}</p>
          )}
          {q.marking_points.length > 0 && (
            <ul className="text-xs text-slate-700 list-disc pl-5">
              {q.marking_points.map((p, i) => <li key={i}>{p.point} <b>({p.marks})</b></li>)}
            </ul>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={g.tone}>{g.text}{q.support !== null ? ` (${Math.round(q.support * 100)}%)` : ""}</Badge>
            {q.edited && <Badge tone="pen">Edited</Badge>}
            {q.sources.map((s) => (
              <details key={s.id} className="text-xs text-mute">
                <summary className="cursor-pointer">{s.chapter}, p.{s.pages}</summary>
                <p className="mt-1 whitespace-pre-wrap rounded-lg border border-slate-200 bg-white p-2">{s.excerpt}...</p>
              </details>
            ))}
          </div>
          {q.notes.map((n, i) => <p key={i} className="text-xs text-amber-700">{n}</p>)}
        </div>
      )}
      <div className="flex gap-2">
        {editing ? (
          <>
            <Button small variant="primary" busy={busy} onClick={save}>Save</Button>
            <Button small variant="ghost" onClick={() => { setEditing(false); setText(q.text); setAnswer(q.answer); }}>Cancel</Button>
          </>
        ) : (
          <Button small variant="ghost" onClick={() => setEditing(true)}>Edit</Button>
        )}
        <span className="sr-only">{marks} marks</span>
      </div>
    </div>
  );
}

/** A generated paper: status while it is written, then the questions with answers, sources and grounding checks. */
export default function GeneratedPaperView({ id, actions, onChanged }: { id: string; actions?: ReactNode; onChanged?: () => void }) {
  const { data: gp, loading, error, reload } = useApi<GenPaper>(`/generation/papers/${id}`,
    (d) => (GEN_BUSY.includes(d.status) ? 2500 : null));
  const [showAnswers, setShowAnswers] = useState(true);
  const [err, setErr] = useState<unknown>(null);
  const [downloading, setDownloading] = useState<string | null>(null);

  if (loading && !gp) return <Loading />;
  if (error) return <ErrorPanel error={error} />;
  if (!gp) return null;

  const download = async (kind: "question-paper" | "answer-key") => {
    setDownloading(kind);
    setErr(null);
    try { await downloadFile(`/generation/papers/${gp.id}/${kind}.pdf`, `${gp.subject}-${kind}.pdf`); }
    catch (e) { setErr(e); } finally { setDownloading(null); }
  };
  const save = async (number: number, alternative: boolean, patch: Partial<GenItem>) => {
    setErr(null);
    try {
      await api(`/generation/papers/${gp.id}/questions/${number}`, { method: "PATCH", json: { ...patch, alternative } });
      await reload();
      onChanged?.();
    } catch (e) { setErr(e); throw e; }
  };

  const p = gp.paper;
  let section = "";
  return (
    <div className="space-y-4">
      <Card className="p-5 space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-ink">{p?.title || gp.title}</h2>
            <p className="text-xs text-mute">
              Class {gp.standard} {gp.subject_name}
              {p && <> &middot; {p.total_marks} marks &middot; {p.duration_minutes} minutes &middot; {p.questions.length} questions</>}
            </p>
          </div>
          {gp.status === "READY" && (
            <div className="flex flex-wrap gap-2">
              <Button small variant="soft" busy={downloading === "question-paper"} onClick={() => download("question-paper")}>Question paper PDF</Button>
              <Button small variant="soft" busy={downloading === "answer-key"} onClick={() => download("answer-key")}>Answer key PDF</Button>
              {actions}
            </div>
          )}
        </div>
        <GenerationStatus gp={gp} />
        {gp.status === "READY" && (
          <div className="flex flex-wrap items-center gap-3 text-xs text-mute">
            {gp.flagged > 0
              ? <Badge tone="warn">{gp.flagged} question(s) to check</Badge>
              : <Badge tone="ok">Every answer is backed by the textbook</Badge>}
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={showAnswers} onChange={(e) => setShowAnswers(e.target.checked)} /> Show answer key
            </label>
          </div>
        )}
        <ErrorPanel error={err} />
      </Card>

      {p?.questions.map((q) => {
        const header = q.section !== section ? (section = q.section) : null;
        return (
          <div key={q.number} className="space-y-3">
            {header && <h3 className="pt-2 text-center text-sm font-bold tracking-wide text-ink">SECTION {header}</h3>}
            <Card className="p-4 space-y-3">
              <div className="flex items-center justify-between text-xs text-mute">
                <span className="font-bold text-ink text-sm">Q{q.number}</span>
                <span>{q.type} &middot; {q.difficulty} &middot; <b>{q.marks} mark{q.marks === 1 ? "" : "s"}</b></span>
              </div>
              <Item q={q} marks={q.marks} showAnswers={showAnswers} onSave={(patch) => save(q.number, false, patch)} />
              {q.or && (
                <>
                  <p className="text-center text-xs font-bold text-mute">OR</p>
                  <Item q={q.or} marks={q.marks} showAnswers={showAnswers} onSave={(patch) => save(q.number, true, patch)} />
                </>
              )}
            </Card>
          </div>
        );
      })}
    </div>
  );
}
