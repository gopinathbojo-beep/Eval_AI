import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useApi } from "../hooks/useApi";
import type { EvalItem, EvalQuestion, EvaluationDetail, StudentAnswer } from "../types";
import { fmt, label, pct } from "../utils/format";
import { Badge, Button, Card, Empty, ErrorPanel, Field, Input, Loading, Modal, PageHeader, PenScore, ProgressBar, Select, Stat, StatusBadge, Textarea } from "../components/ui";
import { PageViewer } from "../components/PageViewer";
import { AuthImage } from "../components/AuthImage";
import { DocProgress } from "../components/DocPanel";
import { BUSY_DOC } from "../utils/format";

type Tab = "mapping" | "marks";
const FILTERS = ["All", "Mapped", "Suggested", "Needs review", "Unmapped", "Missing", "OCR error"] as const;

export default function EvaluationPage() {
  const { id } = useParams();
  const { data, error, loading, reload } = useApi<EvaluationDetail>(`/evaluations/${id}`, (d) =>
    d.evaluation.run_status === "RUNNING" || BUSY_DOC.includes(d.document.status) ? 1500 : null);
  const [tab, setTab] = useState<Tab>("mapping");
  if (loading) return <Loading />;
  if (error || !data) return <ErrorPanel error={error} />;
  const ev = data.evaluation;
  const reading = BUSY_DOC.includes(data.document.status);
  return (
    <>
      <PageHeader title={`${ev.student.name} (${ev.student.roll_number})`}
        sub={<>{data.exam.name} · <Link className="text-pen hover:underline" to={`/exams/${ev.exam_id}/answer-sheets`}>back to answer sheets</Link></>}
        actions={<StatusBadge status={ev.status} />} />
      {(reading || data.document.status !== "READY") && <div className="mb-4"><DocProgress doc={data.document} onChanged={reload} canRetry={ev.status !== "FINALIZED" && data.items.length === 0} rebuildWarning="Reading again rebuilds the detected answers for this sheet. Edits and mapping decisions will be lost." /></div>}
      {!reading && (
        <>
          <div className="mb-4 flex gap-1 border-b border-line">
            {([["mapping", "Mapping review"], ["marks", "Marks and finalize"]] as const).map(([k, t]) => (
              <button key={k} onClick={() => setTab(k)} className={`border-b-2 px-3 py-2 text-sm ${tab === k ? "border-pen font-medium text-pen" : "border-transparent text-mute hover:text-ink"}`}>{t}</button>))}
          </div>
          {tab === "mapping" ? <MappingTab d={data} reload={reload} /> : <MarksTab d={data} reload={reload} />}
        </>
      )}
    </>
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
  const locked = d.evaluation.status === "FINALIZED";
  const qmap = new Map(d.questions.map((q) => [q.id, q]));
  // Same buckets as the summary counts: questions with neither a mapped answer nor a suggestion.
  const missingIds = new Set(d.summary.missing_question_ids ?? []);
  const missing = d.questions.filter((q) => missingIds.has(q.id));
  const ocrErrors = d.document.pages.filter((p) => p.ocr_status !== "OK");

  const rows = d.answers.filter((a) => {
    switch (filter) {
      case "Mapped": return ["MAPPED", "EVALUATING", "EVALUATED", "APPROVED"].includes(a.status);
      case "Suggested": return a.status === "NEEDS_REVIEW" && a.mapping_candidates.length > 0;
      case "Unmapped": return a.status === "UNMAPPED";
      case "Needs review": return a.status === "NEEDS_REVIEW";
      case "Missing": case "OCR error": return false;
      default: return true;
    }
  });

  const act = async (a: StudentAnswer, json: object, key: string) => {
    setBusy(a.id + key); setErr(null);
    try { await api(`/evaluations/${d.evaluation.id}/mapping/${a.id}`, { method: "PATCH", json }); await reload(); } catch (e) { setErr(e); } finally { setBusy(null); }
  };
  const selected = d.answers.find((a) => a.id === sel);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
        <Stat label="Total questions" value={d.summary.total_questions} />
        <Stat label="Mapped" value={d.summary.mapped} />
        <Stat label="Suggested" value={d.summary.suggested ?? 0} tone={d.summary.suggested ? "pen" : undefined} />
        <Stat label="Needs review" value={d.summary.needs_review} tone={d.summary.needs_review ? "mark" : undefined} />
        <Stat label="Missing" value={d.summary.missing} tone={d.summary.missing ? "mark" : undefined} />
        <Stat label="OCR errors" value={ocrErrors.length} tone={ocrErrors.length ? "mark" : undefined} />
      </div>
      <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Filter answers">
        {FILTERS.map((f) => <button key={f} role="tab" aria-selected={filter === f} onClick={() => setFilter(f)} className={`rounded-full px-3 py-1 text-sm ${filter === f ? "bg-pen text-surface" : "bg-sunken hover:bg-line"}`}>{f}</button>)}
      </div>
      <ErrorPanel error={err} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="h-[calc(100vh-20rem)] min-h-[26rem] overflow-hidden">
          <PageViewer kind="answer-sheet" docId={d.document.id} pages={d.document.pages} page={page} onPage={setPage} highlight={selected?.page_number === page ? selected.bbox : null} />
        </Card>
        <div className="h-[calc(100vh-20rem)] min-h-[26rem] space-y-3 overflow-y-auto pr-1">
          {filter === "Missing" && (missing.length ? missing.map((q) => <Card key={q.id} className="border-warn/50 p-4"><p className="font-semibold">Question {q.display_number}: no answer detected</p><p className="doc-text mt-1 line-clamp-2 text-sm text-mute">{q.question_text}</p></Card>) : <Empty title="No missing answers" />)}
          {filter === "OCR error" && (ocrErrors.length ? ocrErrors.map((p) => <Card key={p.page_number} className="border-mark/50 p-4"><p className="font-semibold">Page {p.page_number}: {label(p.ocr_status)}</p><p className="text-sm text-mute">{p.ocr_error}</p></Card>) : <Empty title="No OCR errors" />)}
          {!["Missing", "OCR error"].includes(filter) && (rows.length === 0 ? <Empty title="Nothing here" /> : rows.map((a) => {
            const q = a.exam_question_id ? qmap.get(a.exam_question_id) : undefined;
            const topCandId = a.mapping_candidates?.[0];
            const topCand = topCandId ? qmap.get(topCandId) : undefined;
            const topDetail = a.mapping_candidate_details?.find((c) => c.id === topCandId);
            const needs = a.status === "UNMAPPED" || a.status === "NEEDS_REVIEW";
            return (
              <Card key={a.id} className={`p-4 ${sel === a.id ? "ring-2 ring-pen" : ""} ${needs ? "border-mark/50" : ""} ${a.status === "IGNORED" ? "opacity-60" : ""}`}>
                <button className="block w-full text-left" onClick={() => { setSel(a.id); if (a.page_number) setPage(a.page_number); }}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold">Student wrote “{a.raw_question_number ?? "no number"}”</span>
                    <div className="flex items-center gap-2">
                      {topCand && a.status === "NEEDS_REVIEW" && <Badge tone="pen">Suggested: Q{topCand.display_number}{topDetail ? ` (${pct(topDetail.score)})` : ""}</Badge>}
                      <Badge tone="mute">page {a.page_number}</Badge>
                      <Badge tone="mute">conf. {pct(a.ocr_confidence)}</Badge>
                      <StatusBadge status={a.status} />
                    </div>
                  </div>
                  <p className="mt-1 text-sm">{q ? <>Mapped to <b>Question {q.display_number}</b> <span className="text-mute">— {q.question_text.slice(0, 70)}</span></> : <span className="text-mark">Not mapped to a question</span>}</p>
                  {a.mapping_note && needs && <p className="mt-1 text-sm font-medium text-mark">{a.mapping_note}</p>}
                  {topDetail && a.status === "NEEDS_REVIEW" && <p className="mt-0.5 text-xs text-mute">Why Q{topCand?.display_number}: {topDetail.reason}</p>}
                  <p className="doc-text mt-2 line-clamp-4 text-[15px]">{a.answer_text || <em className="text-mute">(empty)</em>}</p>
                  {a.edited && <p className="mt-1 text-xs text-mute">Edited by you. Original OCR text is kept.</p>}
                </button>
                {sel === a.id && a.has_crop && <div className="mt-3 rounded border border-line bg-sunken p-2"><p className="mb-1 text-xs text-mute">What the model read (approximate crop)</p><AuthImage path={`/crops/student-answer/${a.id}`} alt="Crop of detected answer" className="max-h-48" /></div>}
                {!locked && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {a.status === "IGNORED" ? <Button small onClick={() => act(a, { restore: true }, "r")} busy={busy === a.id + "r"}>Restore</Button> : (<>
                      {topCand && a.status === "NEEDS_REVIEW" && (
                        <Button small variant="primary" busy={busy === a.id + "s"} onClick={() => act(a, { accept_suggestion: true }, "s")}>
                          Accept suggestion (Q{topCand.display_number})
                        </Button>
                      )}
                      <Button small onClick={() => setDlg(a)}>Change mapping</Button>
                      <Button small onClick={() => setDlg(a)}>Edit OCR</Button>
                      <Button small onClick={() => setSplitAns(a)}>Split</Button>
                      <Button small onClick={() => setMergeAns(a)}>Merge</Button>
                      <Button small variant="ghost" busy={busy === a.id + "i"} onClick={() => act(a, { ignore: true }, "i")}>Ignore</Button></>)}
                  </div>
                )}
              </Card>);
          }))}
        </div>
      </div>
      {dlg && <MapDlg a={dlg} d={d} onClose={() => setDlg(null)} onDone={reload} />}
      {splitAns && <SplitAnswerModal a={splitAns} evId={d.evaluation.id} onClose={() => setSplitAns(null)} onDone={reload} />}
      {mergeAns && <MergeAnswerModal a={mergeAns} evId={d.evaluation.id} allAnswers={d.answers} onClose={() => setMergeAns(null)} onDone={reload} />}
    </div>
  );
}

function MapDlg({ a, d, onClose, onDone }: { a: StudentAnswer; d: EvaluationDetail; onClose: () => void; onDone: () => Promise<void> }) {
  const [qid, setQid] = useState(a.exam_question_id ?? "");
  const [label_, setLabel] = useState(a.raw_question_number ?? "");
  const [text, setText] = useState(a.answer_text);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const hint = new Set(a.mapping_candidates);
  const save = async () => {
    setBusy(true); setErr(null);
    const json: Record<string, unknown> = { reason: reason || undefined };
    if (text !== a.answer_text) json.answer_text = text;
    if (qid && qid !== a.exam_question_id) json.exam_question_id = qid;
    else if (label_ !== (a.raw_question_number ?? "")) json.raw_question_number = label_;
    try { await api(`/evaluations/${d.evaluation.id}/mapping/${a.id}`, { method: "PATCH", json }); await onDone(); onClose(); } catch (e) { setErr(e); setBusy(false); }
  };
  return (
    <Modal title="Map or correct this answer" wide onClose={onClose} footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} onClick={save}>Save mapping</Button></>}>
      <div className="grid gap-5 md:grid-cols-2">
        <div className="h-80 overflow-hidden rounded border border-line">
          {a.page_number && <PageViewer kind="answer-sheet" docId={d.document.id} pages={d.document.pages} page={a.page_number} onPage={() => {}} highlight={a.bbox} />}
        </div>
        <div className="space-y-4">
          <Field label="Question number the student wrote" hint="Editing this re-runs the automatic match.">{(id) => <Input id={id} value={label_} onChange={(e) => setLabel(e.target.value)} />}</Field>
          <Field label="Exam question" hint={hint.size ? "Suggested questions are listed first." : undefined}>
            {(id) => <Select id={id} value={qid} onChange={(e) => setQid(e.target.value)}><option value="">Not mapped</option>
              {[...d.questions].sort((x, y) => Number(hint.has(y.id)) - Number(hint.has(x.id)) || x.position - y.position).map((q: EvalQuestion) =>
                <option key={q.id} value={q.id}>{hint.has(q.id) ? "★ " : ""}Q{q.display_number} — {q.question_text.slice(0, 60)}</option>)}</Select>}</Field>
          <Field label="Answer text (OCR)">{(id) => <Textarea id={id} rows={7} className="font-doc" value={text} onChange={(e) => setText(e.target.value)} />}</Field>
          <Field label="Reason (optional)">{(id) => <Input id={id} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>
          <ErrorPanel error={err} />
        </div>
      </div>
    </Modal>
  );
}

function SplitAnswerModal({ a, evId, onClose, onDone }: { a: StudentAnswer; evId: string; onClose: () => void; onDone: () => Promise<void> }) {
  const [pos, setPos] = useState(Math.floor(a.answer_text.length / 2));
  const [lbl, setLbl] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const head = a.answer_text.slice(0, pos);
  const tail = a.answer_text.slice(pos);

  const save = async () => {
    setBusy(true); setErr(null);
    try {
      await api(`/evaluations/${evId}/answers/${a.id}/split`, { method: "POST", json: { at_char: pos, new_label: lbl } });
      await onDone(); onClose();
    } catch (e) { setErr(e); setBusy(false); }
  };

  return (
    <Modal title={`Split answer “${a.raw_question_number ?? "no number"}”`} wide onClose={onClose} footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} disabled={pos <= 0 || !lbl.trim()} onClick={save}>Split here</Button></>}>
      <div className="space-y-4">
        <p className="text-sm text-mute">Drag slider to choose where to split this answer block into two separate answers.</p>
        <Field label="Question number for second answer (e.g. Q2 or 7(b))">{(id) => <Input id={id} value={lbl} onChange={(e) => setLbl(e.target.value)} />}</Field>
        <div>
          <input type="range" min={1} max={Math.max(1, a.answer_text.length - 1)} value={pos} onChange={(e) => setPos(Number(e.target.value))} className="w-full" />
          <p className="text-xs text-mute">Character {pos} of {a.answer_text.length}</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded border border-line bg-surface p-3 text-sm"><p className="mb-1 text-xs font-semibold text-mute">Kept in current answer ({a.raw_question_number ?? "none"})</p><p className="font-mono text-xs">{head}</p></div>
          <div className="rounded border border-line bg-sunken p-3 text-sm"><p className="mb-1 text-xs font-semibold text-mute">New answer ({lbl || "..."})</p><p className="font-mono text-xs">{tail}</p></div>
        </div>
        <ErrorPanel error={err} />
      </div>
    </Modal>
  );
}

function MergeAnswerModal({ a, evId, allAnswers, onClose, onDone }: { a: StudentAnswer; evId: string; allAnswers: StudentAnswer[]; onClose: () => void; onDone: () => Promise<void> }) {
  const [otherId, setOtherId] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const others = allAnswers.filter((x) => x.id !== a.id && x.status !== "IGNORED");

  const save = async () => {
    setBusy(true); setErr(null);
    try {
      await api(`/evaluations/${evId}/answers/${a.id}/merge`, { method: "POST", json: { other_id: otherId } });
      await onDone(); onClose();
    } catch (e) { setErr(e); setBusy(false); }
  };

  return (
    <Modal title={`Merge answer “${a.raw_question_number ?? "no number"}”`} onClose={onClose} footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} disabled={!otherId} onClick={save}>Merge</Button></>}>
      <div className="space-y-4">
        <p className="text-sm">Append another answer card's text into this one. The other answer will be deleted.</p>
        <Field label="Choose answer to merge into this one">
          {(id) => <Select id={id} value={otherId} onChange={(e) => setOtherId(e.target.value)}><option value="">Select answer...</option>
            {others.map((x) => <option key={x.id} value={x.id}>Answer {x.raw_question_number ?? "(no number)"} (p.{x.page_number}) — {x.answer_text.slice(0, 50)}</option>)}</Select>}</Field>
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
  const items = new Map(d.items.map((i) => [i.exam_question_id, i]));
  const ans = new Map(d.answers.filter((a) => a.exam_question_id && a.status !== "IGNORED").map((a) => [a.exam_question_id!, a]));
  const locked = ev.status === "FINALIZED";
  const call = async (key: string, fn: () => Promise<unknown>) => { setBusy(key); setErr(null); try { await fn(); await reload(); } catch (e) { setErr(e); } finally { setBusy(null); } };
  const total = d.questions.reduce((s, q) => s + (items.get(q.id)?.final_marks ?? 0), 0);
  const max = d.questions.reduce((s, q) => s + (q.max_marks ?? 0), 0);
  const unresolved = d.answers.some((a) => a.status === "UNMAPPED" || a.status === "NEEDS_REVIEW");
  const finalize = () => call("fin", async () => { await api(`/evaluations/${ev.id}/finalize`, { method: "POST" }); nav(`/results/${ev.id}`); });

  return (
    <div className="space-y-4">
      <div className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-surface p-3">
        <div className="flex items-center gap-4"><PenScore got={total} max={max} /><p className="text-sm text-mute">{ev.run_status === "RUNNING" ? "Evaluating…" : "Current marks (final only after approval)"}</p></div>
        {!locked && <div className="flex flex-wrap gap-2">
          <Button busy={busy === "run" || ev.run_status === "RUNNING"} onClick={() => call("run", () => api(`/evaluations/${ev.id}/run`, { method: "POST" }))}>{d.items.length ? "Re-run unapproved" : "Run AI evaluation"}</Button>
          <Button disabled={!d.items.some((i) => i.status === "EVALUATED")} busy={busy === "all"} onClick={() => call("all", () => api(`/evaluations/${ev.id}/items/approve-all`, { method: "POST" }))}>Approve all evaluated</Button>
          <Button variant="primary" busy={busy === "fin"} onClick={finalize}>Finalize</Button></div>}
      </div>
      {ev.run_status === "RUNNING" && <div><ProgressBar value={ev.run_progress} max={ev.run_total} /><p className="mt-1 text-sm text-mute" aria-live="polite">Question {ev.run_progress} of {ev.run_total}</p></div>}
      {ev.run_status === "ERROR" && <div role="alert" className="rounded-lg border border-mark/40 bg-mark-soft p-3 text-sm text-mark">InternVL3.5 4B is not available. Start Ollama and ensure blaifa/InternVL3_5:4B is installed, then run evaluation again.</div>}
      {unresolved && <div className="rounded-lg border border-warn/40 bg-warn-soft p-3 text-sm">Some answers are not mapped yet. Resolve them in the <b>Mapping review</b> tab before running evaluation.</div>}
      <ErrorPanel error={err} action={err instanceof ApiError && err.code === "EVALUATION_NOT_READY" ? <p className="text-sm">Fix these here, or open the Mapping review tab.</p> : undefined} />
      {!err && !locked && d.issues.length > 0 && d.items.length > 0 && (
        <details className="rounded-lg border border-line bg-surface p-3 text-sm"><summary className="cursor-pointer font-medium">{d.issues.length} thing(s) before this can be finalized</summary>
          <ul className="mt-2 space-y-1">{d.issues.map((i, k) => <li key={k}><b>{i.question}</b> · {i.reason}</li>)}</ul></details>)}
      {d.questions.length === 0 ? <Empty title="No questions" /> : d.questions.map((q) => {
        const it = items.get(q.id), a = ans.get(q.id);
        return (
          <Card key={q.id} className={`p-4 ${it && it.status === "EVALUATION_ERROR" ? "border-mark/50" : ""}`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1"><p className="font-semibold">Question {q.display_number} <span className="font-normal text-mute">· {fmt(q.max_marks)} marks</span></p>
                <p className="doc-text mt-1 line-clamp-2 text-sm text-mute">{q.question_text}</p></div>
              <div className="flex items-center gap-3">{it && <StatusBadge status={it.status} />}{it && it.final_marks !== null && <PenScore got={it.final_marks} max={q.max_marks} />}</div>
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <div><p className="mb-1 text-xs font-medium text-mute">Official answer</p><p className="doc-text rounded bg-sunken p-2 text-sm">{q.official_answer ?? "–"}</p></div>
              <div><p className="mb-1 text-xs font-medium text-mute">Student answer</p><p className="doc-text rounded bg-sunken p-2 text-sm">{a ? a.answer_text : <em className="text-mute">Unanswered (no response detected)</em>}</p></div>
            </div>
            {it?.error && <p className="mt-2 text-sm font-medium text-mark">{it.error}</p>}
            {it && it.ai_marks !== null && (
              <div className="mt-3 space-y-1 text-sm">
                <p><b>AI suggested {fmt(it.ai_marks)}/{fmt(q.max_marks)}</b> {it.ai_decision && <Badge tone={it.ai_decision === "UNANSWERED" ? "mute" : "pen"}>{label(it.ai_decision)}</Badge>} {it.ai_confidence !== null && <span className="text-xs text-mute">confidence {pct(it.ai_confidence)}</span>}</p>
                {it.ai_feedback && <p className="text-mute">{it.ai_feedback}</p>}
                {it.matched_points.length > 0 && <p><span className="text-ok">Matched:</span> {it.matched_points.join("; ")}</p>}
                {it.missing_points.length > 0 && <p><span className="text-mark">Missing:</span> {it.missing_points.join("; ")}</p>}
                {it.teacher_overridden && <p className="text-xs text-warn">You changed this from the AI's mark.</p>}
              </div>)}
            {it && !locked && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {it.status !== "APPROVED" && it.status !== "PENDING" && <Button small variant="primary" busy={busy === it.id} onClick={() => call(it.id, () => api(`/evaluations/${ev.id}/items/${it.id}`, { method: "PATCH", json: { approve: true } }))}>Approve</Button>}
                {it.status === "APPROVED" && <Button small busy={busy === it.id} onClick={() => call(it.id, () => api(`/evaluations/${ev.id}/items/${it.id}`, { method: "PATCH", json: { approve: false } }))}>Unapprove</Button>}
                {it.status !== "PENDING" && <Button small onClick={() => setEdit({ q, item: it })}>Change marks</Button>}
                {it.status !== "PENDING" && <Button small variant="ghost" busy={busy === it.id + "r"} onClick={() => call(it.id + "r", () => api(`/evaluations/${ev.id}/items/${it.id}/rerun`, { method: "POST" }))}>Re-evaluate</Button>}
              </div>)}
          </Card>);
      })}
      {edit && <MarksDlg q={edit.q} item={edit.item} evId={ev.id} onClose={() => setEdit(null)} onDone={reload} />}
    </div>
  );
}

function MarksDlg({ q, item, evId, onClose, onDone }: { q: EvalQuestion; item: EvalItem; evId: string; onClose: () => void; onDone: () => Promise<void> }) {
  const [marks, setMarks] = useState(item.final_marks !== null ? String(item.final_marks) : "");
  const [reason, setReason] = useState("");
  const [fb, setFb] = useState(item.teacher_feedback ?? "");
  const [na, setNa] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const save = async (approve: boolean) => {
    setBusy(true); setErr(null);
    const json: Record<string, unknown> = { reason: reason || undefined, teacher_feedback: fb || undefined };
    if (item.status === "MISSING" && na) json.confirm_not_attempted = true;
    if (marks !== "") json.final_marks = Number(marks);
    if (approve) json.approve = true;
    try { await api(`/evaluations/${evId}/items/${item.id}`, { method: "PATCH", json }); await onDone(); onClose(); } catch (e) { setErr(e); setBusy(false); }
  };
  return (
    <Modal title={`Marks for question ${q.display_number}`} onClose={onClose} footer={<><Button onClick={onClose}>Cancel</Button><Button busy={busy} onClick={() => save(false)}>Save</Button><Button variant="primary" busy={busy} onClick={() => save(true)}>Save and approve</Button></>}>
      <div className="space-y-4">
        {item.ai_marks !== null && <p className="text-sm">AI suggested <b>{fmt(item.ai_marks)}</b> of {fmt(q.max_marks)}. The AI's mark is always kept on record.</p>}
        {item.status === "MISSING" && <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={na} onChange={(e) => setNa(e.target.checked)} />I checked the sheet and this question was not attempted (0 marks). If an answer exists, cancel and map it in Mapping review.</label>}
        <Field label={`Final marks (0 to ${fmt(q.max_marks)})`}>{(id) => <Input id={id} type="number" min={0} max={q.max_marks ?? undefined} step={0.5} value={marks} onChange={(e) => setMarks(e.target.value)} />}</Field>
        <Field label="Reason for changing the AI's mark" hint="Required whenever the mark differs from the AI's.">{(id) => <Input id={id} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>
        <Field label="Feedback for the student (optional)">{(id) => <Textarea id={id} rows={3} value={fb} onChange={(e) => setFb(e.target.value)} />}</Field>
        <ErrorPanel error={err} />
      </div>
    </Modal>
  );
}
