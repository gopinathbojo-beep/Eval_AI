import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, downloadFile, fetchBlobUrl } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useAuth } from "../context/Auth";
import { useToast } from "../components/Toast";
import {
  Button, Card, Confirm, Empty, ErrorPanel, Field, Input, Loading, Modal, PageHeader, Select, Stat, StatusBadge, Textarea,
} from "../components/ui";
import { date } from "../utils/format";

// ---------- shapes
interface Child { id: string; name: string; standard: number; subjects: string[] }
interface Paper { id: string; standard: number; subject: string; units: string[]; total_marks: number | null; duration_minutes: number; questions: number }
interface PExam {
  id: string; child_id: string; status: string; subject: string | null; standard: number | null; total_marks: number | null;
  duration_minutes: number; pages: number; server_time: string; started_at: string | null; ends_at: string | null;
  upload_closes_at: string | null; uploaded_at: string | null; evaluation_id: string | null;
}
interface Report {
  exam: PExam; score: number; max: number | null; percentage: number | null; weak: string[];
  questions: { question: string | null; max_marks: number | null; marks: number | null; feedback: string | null }[];
}
interface Wallet { balance: number; eval_per_sheet: number; paper_fixed: number; low: boolean; ledger: { id: string; amount: number; note: string | null; type: string; created_at: string }[] }

const BUSY = ["EVALUATING"];
const inr = (n: number) => `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

function Loaded<T>({ path, poll, children }: { path: string; poll?: (d: T) => number | null; children: (d: T, reload: () => Promise<void>) => ReactNode }) {
  const { data, error, loading, reload } = useApi<T>(path, poll);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorPanel error={error} />;
  return data ? <>{children(data, reload)}</> : null;
}

// ---------- dashboard
export function Dashboard() {
  const { user } = useAuth();
  return (
    <>
      <PageHeader title={`Hello${user?.name ? `, ${user.name.split(" ")[0]}` : ""}`} sub="Your children's recent exams and your credits." />
      <Loaded<Wallet> path="/credits">{(w) => (
        <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-3">
          <Stat label="Credits" value={w.balance} tone={w.low ? "mark" : "ok"} hint={`${w.eval_per_sheet} per answer sheet`} />
        </div>
      )}</Loaded>
      <Loaded<Child[]> path="/parent/children">{(kids) => kids.length ? (
        <Loaded<PExam[]> path="/parent/exams">{(exams) => (
          <div className="grid gap-4 md:grid-cols-2">
            {kids.map((c) => {
              const mine = exams.filter((e) => e.child_id === c.id);
              return (
                <Card key={c.id}>
                  <h2 className="font-display text-lg font-semibold">{c.name} <span className="text-sm text-mute">· Class {c.standard}</span></h2>
                  {mine.length ? (
                    <ul className="mt-3 space-y-2 text-sm">
                      {mine.slice(0, 5).map((e) => (
                        <li key={e.id} className="flex items-center justify-between">
                          <Link to={`/exams/${e.id}`} className="text-pen hover:underline">{e.subject}</Link>
                          <StatusBadge status={e.status} />
                        </li>
                      ))}
                    </ul>
                  ) : <p className="mt-2 text-sm text-mute">No exams yet.</p>}
                  <Link to="/exams" className="mt-3 inline-block text-sm text-pen hover:underline">Start an exam →</Link>
                </Card>
              );
            })}
          </div>
        )}</Loaded>
      ) : <Empty title="Add your child to begin" action={<Link to="/children" className="text-pen hover:underline">Add a child</Link>} />}</Loaded>
    </>
  );
}

// ---------- children
export function Children() {
  const [edit, setEdit] = useState<Partial<Child> | null>(null);
  return (
    <Loaded<Child[]> path="/parent/children">{(kids, reload) => (
      <>
        <PageHeader title="Children" sub="ADEM supports CBSE Class 10 and Class 12."
          actions={<Button variant="primary" onClick={() => setEdit({ name: "", standard: 10, subjects: [] })}>Add child</Button>} />
        {kids.length ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {kids.map((c) => (
              <Card key={c.id}>
                <p className="font-semibold">{c.name}</p>
                <p className="text-sm text-mute">Class {c.standard}{c.subjects.length ? ` · ${c.subjects.join(", ")}` : ""}</p>
                <Button small className="mt-3" onClick={() => setEdit(c)}>Edit</Button>
              </Card>
            ))}
          </div>
        ) : <Empty title="No children yet" />}
        {edit && <ChildModal child={edit} onClose={() => setEdit(null)} onDone={reload} />}
      </>
    )}</Loaded>
  );
}

function ChildModal({ child, onClose, onDone }: { child: Partial<Child>; onClose: () => void; onDone: () => Promise<void> }) {
  const [c, setC] = useState({ name: child.name ?? "", standard: child.standard ?? 10, subjects: (child.subjects ?? []).join(", ") });
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      const json = { name: c.name.trim(), standard: Number(c.standard), subjects: c.subjects.split(",").map((s) => s.trim()).filter(Boolean) };
      await api(child.id ? `/parent/children/${child.id}` : "/parent/children", { method: child.id ? "PATCH" : "POST", json });
      await onDone(); onClose();
    } catch (e) { setErr(e); setBusy(false); }
  };
  return (
    <Modal title={child.id ? "Edit child" : "Add child"} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} disabled={!c.name.trim()} onClick={save}>Save</Button></>}>
      <div className="space-y-4">
        <Field label="Name" required>{(id) => <Input id={id} value={c.name} onChange={(e) => setC({ ...c, name: e.target.value })} />}</Field>
        <Field label="Class" required>{(id) => <Select id={id} value={c.standard} onChange={(e) => setC({ ...c, standard: Number(e.target.value) })}>
          <option value={10}>Class 10</option><option value={12}>Class 12</option></Select>}</Field>
        <Field label="Subjects" hint="Comma separated">{(id) => <Input id={id} value={c.subjects} onChange={(e) => setC({ ...c, subjects: e.target.value })} />}</Field>
        <ErrorPanel error={err} />
      </div>
    </Modal>
  );
}

// ---------- exams: choose a paper, list of exams
export function Exams() {
  const [childId, setChildId] = useState("");
  const nav = useNavigate();
  const toast = useToast();
  const kids = useApi<Child[]>("/parent/children");
  const child = kids.data?.find((c) => c.id === (childId || kids.data?.[0]?.id));
  const papers = useApi<{ papers: Paper[]; paper_charge: number }>(child ? `/parent/papers?standard=${child.standard}` : null);
  const exams = useApi<PExam[]>("/parent/exams", (d) => (d.some((e) => BUSY.includes(e.status)) ? 5000 : null));
  const [choosing, setChoosing] = useState<string | null>(null);

  const choose = async (p: Paper) => {
    if (!child) return;
    setChoosing(p.id);
    try {
      const pe = await api<PExam>("/parent/exams", { method: "POST", json: { child_id: child.id, paper_id: p.id } });
      nav(`/exams/${pe.id}`);
    } catch (e) { toast((e as Error).message, "mark"); setChoosing(null); }
  };

  if (kids.loading && !kids.data) return <Loading />;
  if (kids.error) return <ErrorPanel error={kids.error} />;
  if (!kids.data?.length) return <><PageHeader title="Exams" /><Empty title="Add your child first" action={<Link to="/children" className="text-pen hover:underline">Add a child</Link>} /></>;
  return (
    <>
      <PageHeader title="Exams" sub="Choose a paper. Your child writes it on paper while the timer runs, then you upload photos of the answer sheet within 1 hour."
        actions={kids.data.length > 1 && <Select aria-label="Child" value={child?.id} onChange={(e) => setChildId(e.target.value)}>
          {kids.data.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>} />
      <h2 className="mb-3 font-display text-lg font-semibold">Papers for Class {child?.standard}</h2>
      {papers.error ? <ErrorPanel error={papers.error} /> : !papers.data ? <Loading /> : papers.data.papers.length ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {papers.data.papers.map((p) => (
            <Card key={p.id}>
              <p className="font-semibold">{p.subject}</p>
              <p className="text-sm text-mute">{p.units.length ? p.units.join(", ") : "Full syllabus"}</p>
              <p className="mt-1 text-sm">{p.questions} questions · {p.total_marks ?? "–"} marks · {p.duration_minutes} min</p>
              {papers.data!.paper_charge > 0 && <p className="text-xs text-mute">{papers.data!.paper_charge} credit(s) to choose</p>}
              <Button className="mt-3" small variant="primary" busy={choosing === p.id} disabled={!!choosing} onClick={() => choose(p)}>Choose</Button>
            </Card>
          ))}
        </div>
      ) : <Empty title="No papers for this class yet" />}

      <h2 className="mb-3 mt-8 font-display text-lg font-semibold">{child?.name}'s exams</h2>
      {exams.data?.filter((e) => e.child_id === child?.id).length ? (
        <ul className="space-y-2">
          {exams.data.filter((e) => e.child_id === child?.id).map((e) => (
            <li key={e.id}>
              <Link to={`/exams/${e.id}`} className="flex items-center justify-between rounded-lg border border-line bg-surface px-4 py-3 text-sm hover:border-pen">
                <span>{e.subject} · {e.total_marks ?? "–"} marks{e.started_at ? ` · ${date(e.started_at)}` : ""}</span>
                <StatusBadge status={e.status} />
              </Link>
            </li>
          ))}
        </ul>
      ) : <Empty title="No exams yet" />}
    </>
  );
}

// ---------- one exam: start, timer and paper, upload, result
const two = (n: number) => String(Math.max(0, Math.floor(n))).padStart(2, "0");
const clock = (ms: number) => { const s = Math.max(0, ms / 1000); return `${two(s / 3600)}:${two((s % 3600) / 60)}:${two(s % 60)}`; };

/** The time left until `until`, using the server's clock (offset measured when the exam was loaded). */
function useCountdown(until: string | null, serverTime: string) {
  const offset = useRef(0);
  useEffect(() => { offset.current = new Date(serverTime).getTime() - Date.now(); }, [serverTime]);
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(t); }, []);
  return until ? new Date(until).getTime() - (now + offset.current) : 0;
}

export function ExamRun() {
  const { id } = useParams();
  const poll = (e: PExam) => (BUSY.includes(e.status) ? 5000 : e.status === "IN_PROGRESS" || e.status === "AWAITING_UPLOAD" ? 30000 : null);
  return (
    <Loaded<PExam> path={`/parent/exams/${id}`} poll={poll}>{(e, reload) => <ExamBody e={e} reload={reload} />}</Loaded>
  );
}

function ExamBody({ e, reload }: { e: PExam; reload: () => Promise<void> }) {
  const left = useCountdown(e.status === "IN_PROGRESS" ? e.ends_at : e.upload_closes_at, e.server_time);
  const [starting, setStarting] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const toast = useToast();
  const expired = useRef(false);
  useEffect(() => {  // the clock ran out: let the server move the exam on
    if ((e.status === "IN_PROGRESS" || e.status === "AWAITING_UPLOAD") && left <= 0 && !expired.current) { expired.current = true; reload(); }
    if (left > 0) expired.current = false;
  }, [left, e.status, reload]);

  const start = async () => {
    setStarting(true);
    try { await api(`/parent/exams/${e.id}/start`, { method: "POST" }); await reload(); }
    catch (err) { toast((err as Error).message, "mark"); } finally { setStarting(false); }
  };

  const header = <PageHeader title={`${e.subject ?? "Exam"} · Class ${e.standard ?? ""}`} badge={<StatusBadge status={e.status} />}
    breadcrumbs={[{ label: "Exams", to: "/exams" }, { label: e.subject ?? "Exam" }]} />;

  if (e.status === "PAPER_SELECTED") return (
    <>{header}
      <Card>
        <h2 className="font-display text-lg font-semibold">Before you start</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
          <li>The exam lasts {e.duration_minutes} minutes and the timer cannot be paused or restarted.</li>
          <li>Your child writes the answers on paper. The question paper is shown here only while the timer runs.</li>
          <li>After the time ends you have 1 hour to upload clear photos of every answer page.</li>
        </ul>
        <Button className="mt-4" variant="primary" onClick={() => setConfirm(true)}>Start the exam</Button>
      </Card>
      {confirm && <Confirm title="Start now?" body={<p>The {e.duration_minutes}-minute timer starts immediately.</p>} confirmLabel="Start"
        onConfirm={start} onClose={() => setConfirm(false)} />}
      {starting && <Loading text="Starting..." />}
    </>
  );

  if (e.status === "IN_PROGRESS") return (
    <>{header}
      <div className="sticky top-0 z-20 mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-paper/95 px-4 py-3 backdrop-blur">
        <span className="text-sm text-mute">Time left</span>
        <span className={`font-mono text-2xl font-semibold ${left < 5 * 60000 ? "text-mark" : "text-ink"}`} aria-live="polite">{clock(left)}</span>
      </div>
      <PaperPages examId={e.id} pages={e.pages} />
      <Card className="mt-6"><p className="mb-3 text-sm">Finished early? Upload the answer sheet now.</p><Upload examId={e.id} onDone={reload} /></Card>
    </>
  );

  if (e.status === "AWAITING_UPLOAD") return (
    <>{header}
      <Card>
        <p className="text-sm">Time is up. Upload photos of every answer page, in order.</p>
        <p className="mt-1 text-sm">Upload closes in <span className={`font-mono font-semibold ${left < 10 * 60000 ? "text-mark" : ""}`}>{clock(left)}</span>.</p>
        <div className="mt-4"><Upload examId={e.id} onDone={reload} /></div>
      </Card>
    </>
  );

  if (e.status === "EVALUATING") return <>{header}<Card><Loading text="The answer sheet is being marked. This usually takes a few minutes." /></Card></>;
  if (e.status === "COMPLETED") return <>{header}<ReportView examId={e.id} /></>;
  if (e.status === "MISSED") return <>{header}<Empty title="The upload window closed" hint="No answer sheet was uploaded within 1 hour of the exam ending." /></>;
  return <>{header}<Empty title="This sheet could not be marked" hint="Our team has been alerted. Contact support from Help if it is not fixed soon." /></>;
}

/** The question paper, one watermarked image per page; never cached, and only available while the exam runs. */
function PaperPages({ examId, pages }: { examId: string; pages: number }) {
  const [urls, setUrls] = useState<string[]>([]);
  const [err, setErr] = useState<unknown>(null);
  useEffect(() => {
    let alive = true;
    const made: string[] = [];
    (async () => {
      try {
        for (let n = 1; n <= pages; n++) { const u = await fetchBlobUrl(`/parent/exams/${examId}/pages/${n}`); made.push(u); if (alive) setUrls([...made]); }
      } catch (e) { if (alive) setErr(e); }
    })();
    return () => { alive = false; made.forEach((u) => URL.revokeObjectURL(u)); };
  }, [examId, pages]);
  if (err) return <ErrorPanel error={err} />;
  if (!pages) return <Empty title="The paper has no pages" />;
  return (
    <div className="space-y-4" onContextMenu={(ev) => ev.preventDefault()}>
      {urls.map((u, i) => <img key={u} src={u} alt={`Question paper page ${i + 1}`} draggable={false} className="w-full select-none rounded-lg border border-line bg-white" />)}
      {urls.length < pages && <Loading text="Loading the paper..." />}
    </div>
  );
}

function Upload({ examId, onDone }: { examId: string; onDone: () => Promise<void> }) {
  const [files, setFiles] = useState<File[]>([]);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const quote = useApi<{ credits: number; balance: number; enough: boolean }>(`/parent/exams/${examId}/quote`);
  const send = async () => {
    setBusy(true); setErr(null);
    try {
      const form = new FormData();
      files.forEach((f) => form.append("files", f));
      await api(`/parent/exams/${examId}/upload`, { method: "POST", form });
      await onDone();
    } catch (e) { setErr(e); setBusy(false); }
  };
  return (
    <div className="space-y-3">
      <input type="file" multiple accept="image/jpeg,image/png,application/pdf" aria-label="Answer sheet photos or PDF"
        onChange={(ev) => setFiles(Array.from(ev.target.files ?? []))} className="block text-sm" />
      {files.length > 0 && <ol className="list-decimal pl-5 text-sm text-mute">{files.map((f) => <li key={f.name}>{f.name}</li>)}</ol>}
      {quote.data && <p className={`text-xs ${quote.data.enough ? "text-mute" : "font-semibold text-mark"}`}>
        Marking uses {quote.data.credits} credit(s). Your balance: {quote.data.balance}.{!quote.data.enough && <> <Link to="/credits" className="underline">Buy credits</Link></>}</p>}
      <ErrorPanel error={err} />
      <Button variant="primary" busy={busy} disabled={!files.length} onClick={send}>Upload answer sheet</Button>
    </div>
  );
}

function ReportView({ examId }: { examId: string }) {
  const [dispute, setDispute] = useState(false);
  return (
    <Loaded<Report> path={`/parent/exams/${examId}/report`}>{(r) => (
      <>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
          <Stat label="Score" value={`${r.score} / ${r.max ?? "–"}`} tone="pen" />
          <Stat label="Percentage" value={r.percentage === null ? "–" : `${r.percentage}%`} />
        </div>
        {r.weak.length > 0 && <Card className="mt-6"><h2 className="font-display text-lg font-semibold">Needs practice</h2>
          <p className="mt-1 text-sm">Questions {r.weak.join(", ")} scored under half marks.</p></Card>}
        <div className="mt-6 overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full text-sm">
            <thead className="bg-sunken/60 text-left text-xs uppercase text-mute"><tr><th className="px-3 py-2">Q</th><th className="px-3 py-2">Marks</th><th className="px-3 py-2">Feedback</th></tr></thead>
            <tbody>
              {r.questions.map((q, i) => (
                <tr key={i} className="border-t border-line align-top">
                  <td className="px-3 py-2 font-semibold">{q.question}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{q.marks ?? "–"} / {q.max_marks ?? "–"}</td>
                  <td className="px-3 py-2">{q.feedback ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {r.exam.evaluation_id && <Button className="mt-4" variant="ghost" onClick={() => setDispute(true)}>Question a mark</Button>}
        {dispute && r.exam.evaluation_id && <DisputeModal evaluationId={r.exam.evaluation_id} onClose={() => setDispute(false)} />}
      </>
    )}</Loaded>
  );
}

function DisputeModal({ evaluationId, onClose }: { evaluationId: string; onClose: () => void }) {
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const send = async () => {
    setBusy(true);
    try { await api("/disputes", { method: "POST", json: { evaluation_id: evaluationId, reason } }); toast("Sent. We will review it.", "ok"); onClose(); }
    catch (e) { setErr(e); setBusy(false); }
  };
  return (
    <Modal title="Question a mark" onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} disabled={reason.trim().length < 5} onClick={send}>Send</Button></>}>
      <Field label="Which question, and why" required>{(id) => <Textarea id={id} rows={4} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>
      <ErrorPanel error={err} />
    </Modal>
  );
}

// ---------- reports: every finished exam
export function Reports() {
  return (
    <>
      <PageHeader title="Reports" sub="Every marked exam." />
      <Loaded<PExam[]> path="/parent/exams">{(rows) => {
        const done = rows.filter((e) => e.status === "COMPLETED");
        return done.length ? (
          <ul className="space-y-2">
            {done.map((e) => (
              <li key={e.id}><Link to={`/exams/${e.id}`} className="flex justify-between rounded-lg border border-line bg-surface px-4 py-3 text-sm hover:border-pen">
                <span>{e.subject} · Class {e.standard}</span><span className="text-mute">{date(e.uploaded_at)}</span></Link></li>
            ))}
          </ul>
        ) : <Empty title="No marked exams yet" />;
      }}</Loaded>
    </>
  );
}

// ---------- credits
interface Pack { id: string; name: string; credits: number; price_inr: number }
interface Order { order_id: string; payment_id: string; amount_paise: number; key_id: string | null; simulation: boolean }
interface Payment { id: string; credits: number; amount_inr: number; status: string; invoice_no: string | null; created_at: string }
declare global { interface Window { Razorpay?: new (o: Record<string, unknown>) => { open(): void } } }

function loadRazorpay(): Promise<void> {
  if (window.Razorpay) return Promise.resolve();
  return new Promise((ok, fail) => {
    const s = document.createElement("script");
    s.src = "https://checkout.razorpay.com/v1/checkout.js";
    s.onload = () => ok();
    s.onerror = () => fail(new Error("The payment window could not be loaded. Check your connection."));
    document.body.appendChild(s);
  });
}

export function Credits() {
  const w = useApi<Wallet>("/credits");
  const packs = useApi<Pack[]>("/public/credit-packs");
  const payments = useApi<Payment[]>("/credits/payments");
  const toast = useToast();
  const [buying, setBuying] = useState<string | null>(null);
  const verify = async (order_id: string, payment_id: string, signature: string) => {
    await api("/credits/verify", { method: "POST", json: { order_id, payment_id, signature } });
    toast("Credits added", "ok");
    await Promise.all([w.reload(), payments.reload()]);
  };
  const buy = async (p: Pack) => {
    setBuying(p.id);
    try {
      const o = await api<Order>("/credits/order", { method: "POST", json: { pack_id: p.id } });
      if (o.simulation) await verify(o.order_id, `pay_sim_${o.payment_id.slice(0, 8)}`, "simulated");
      else {
        await loadRazorpay();
        new window.Razorpay!({ key: o.key_id, order_id: o.order_id, amount: o.amount_paise, currency: "INR", name: "ADEM", description: p.name,
          handler: (r: { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string }) =>
            verify(r.razorpay_order_id, r.razorpay_payment_id, r.razorpay_signature).catch((e) => toast(e.message, "mark")) }).open();
      }
    } catch (e) { toast((e as Error).message, "mark"); } finally { setBuying(null); }
  };
  if (w.error) return <ErrorPanel error={w.error} />;
  if (!w.data) return <Loading />;
  return (
    <>
      <PageHeader title="Credits" sub={`Marking one answer sheet uses ${w.data.eval_per_sheet} credit(s).`} />
      <Stat label="Balance" value={w.data.balance} tone={w.data.low ? "mark" : "ok"} className="max-w-xs" />
      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        {(packs.data ?? []).map((p) => (
          <Card key={p.id}>
            <p className="font-semibold">{p.name}</p>
            <p className="mt-1 font-display text-2xl">{p.credits} <span className="text-sm text-mute">credits</span></p>
            <p className="text-sm text-mute">{inr(p.price_inr)} incl. GST</p>
            <Button className="mt-3 w-full" variant="primary" busy={buying === p.id} disabled={!!buying} onClick={() => buy(p)}>Buy</Button>
          </Card>
        ))}
      </div>
      {!!payments.data?.length && (
        <>
          <h2 className="mb-3 mt-8 font-display text-lg font-semibold">Payments and invoices</h2>
          <ul className="space-y-2">
            {payments.data.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line bg-surface px-4 py-3 text-sm">
                <span>{date(p.created_at)} · {p.credits} credits · {inr(p.amount_inr)}</span>
                <span className="flex items-center gap-2"><StatusBadge status={p.status} />
                  {p.invoice_no && <Button small variant="ghost" onClick={() => downloadFile(`/credits/invoices/${p.id}`, `${p.invoice_no}.pdf`).catch((e) => toast(e.message, "mark"))}>Invoice</Button>}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      <h2 className="mb-3 mt-8 font-display text-lg font-semibold">History</h2>
      {w.data.ledger.length ? (
        <ul className="space-y-1 text-sm">
          {w.data.ledger.map((r) => (
            <li key={r.id} className="flex justify-between border-b border-dashed border-line py-1">
              <span>{date(r.created_at)} · {r.note || r.type}</span>
              <span className={r.amount < 0 ? "text-mark" : "text-ok"}>{r.amount > 0 ? "+" : ""}{r.amount}</span>
            </li>
          ))}
        </ul>
      ) : <Empty title="No credit movements yet" />}
    </>
  );
}

// ---------- help: support tickets and deleting the account
interface Ticket { id: string; subject: string; message: string; status: string; reply: string | null; created_at: string }

export function Help() {
  const [f, setF] = useState({ subject: "", message: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [del, setDel] = useState(false);
  const { logout } = useAuth();
  const toast = useToast();
  const tickets = useApi<Ticket[]>("/support");
  const send = async () => {
    setBusy(true); setErr(null);
    try { await api("/support", { method: "POST", json: f }); setF({ subject: "", message: "" }); toast("Sent. We will reply here.", "ok"); await tickets.reload(); }
    catch (e) { setErr(e); } finally { setBusy(false); }
  };
  return (
    <>
      <PageHeader title="Help and support" />
      <Card>
        <h2 className="mb-3 font-display text-lg font-semibold">Contact support</h2>
        <div className="space-y-4">
          <Field label="Subject" required>{(id) => <Input id={id} value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} />}</Field>
          <Field label="Message" required>{(id) => <Textarea id={id} rows={4} value={f.message} onChange={(e) => setF({ ...f, message: e.target.value })} />}</Field>
          <ErrorPanel error={err} />
          <Button variant="primary" busy={busy} disabled={!f.subject.trim() || !f.message.trim()} onClick={send}>Send</Button>
        </div>
      </Card>
      {!!tickets.data?.length && (
        <div className="mt-6 space-y-3">
          {tickets.data.map((t) => (
            <Card key={t.id}>
              <div className="flex items-center justify-between"><p className="font-semibold">{t.subject}</p><StatusBadge status={t.status} /></div>
              <p className="mt-1 whitespace-pre-wrap text-sm">{t.message}</p>
              {t.reply && <p className="mt-2 whitespace-pre-wrap rounded-md bg-sunken/60 p-3 text-sm"><span className="font-semibold">Reply: </span>{t.reply}</p>}
            </Card>
          ))}
        </div>
      )}
      <Card className="mt-8">
        <h2 className="font-display text-lg font-semibold text-mark">Delete my data</h2>
        <p className="mt-1 text-sm">Deletes your children, exams, answer sheets and reports, and closes your account. Unused credits are lost. This cannot be undone.</p>
        <Button className="mt-3" variant="danger" onClick={() => setDel(true)}>Delete my data</Button>
      </Card>
      {del && <Confirm title="Delete everything?" danger confirmLabel="Delete" body={<p>Your account will be closed and you will be signed out.</p>}
        onConfirm={async () => { await api("/parent/delete-my-data", { method: "POST" }); logout(); }} onClose={() => setDel(false)} />}
    </>
  );
}
