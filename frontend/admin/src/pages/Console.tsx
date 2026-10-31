import { useState, type ReactNode } from "react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useAuth } from "../context/Auth";
import { useToast } from "../components/Toast";
import {
  Button, Card, Confirm, Empty, ErrorPanel, Field, Input, Loading, Modal, PageHeader, Select, Stat, StatusBadge, Textarea,
} from "../components/ui";
import { date } from "../utils/format";

// ---------- shared bits
type Row = Record<string, unknown>;

/** A simple table: columns are [heading, cell renderer]. */
function Table<T>({ rows, cols, empty }: { rows: T[]; cols: [string, (r: T) => ReactNode][]; empty: string }) {
  if (!rows.length) return <Empty title={empty} />;
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="w-full text-sm">
        <thead className="bg-sunken/60 text-left text-xs uppercase tracking-wide text-mute">
          <tr>{cols.map(([h]) => <th key={h} className="px-3 py-2 font-semibold">{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-line align-top">
              {cols.map(([h, f]) => <td key={h} className="px-3 py-2">{f(r)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Page<T>({ title, sub, path, actions, children }: {
  title: string; sub?: string; path: string; actions?: ReactNode;
  children: (data: T, reload: () => Promise<void>) => ReactNode;
}) {
  const { data, error, loading, reload } = useApi<T>(path);
  return (
    <>
      <PageHeader title={title} sub={sub} actions={actions} />
      {loading && !data ? <Loading /> : error ? <ErrorPanel error={error} /> : data ? children(data, reload) : null}
    </>
  );
}

const useCanWrite = () => useAuth().user?.admin_role !== "viewer";
const inr = (n: number) => `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

/** Runs an action, shows a toast and reloads; errors become toasts too. */
function useAct(reload: () => Promise<void>) {
  const toast = useToast();
  return async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); toast(ok, "ok"); await reload(); } catch (e) { toast((e as Error).message, "mark"); }
  };
}

function AdjustModal({ walletId, onClose, onDone }: { walletId: string; onClose: () => void; onDone: () => void }) {
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      await api(`/admin/wallets/${walletId}/adjust`, { method: "POST", json: { amount: Number(amount), reason } });
      onDone(); onClose();
    } catch (e) { setErr(e); setBusy(false); }
  };
  return (
    <Modal title="Adjust credits" onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button variant="primary" busy={busy} disabled={!Number(amount) || reason.trim().length < 3} onClick={save}>Save</Button></>}>
      <div className="space-y-4">
        <Field label="Credits" hint="Negative to deduct" required>{(id) =>
          <Input id={id} type="number" value={amount} onChange={(e) => setAmount(e.target.value)} />}</Field>
        <Field label="Reason" required>{(id) => <Input id={id} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>
        <ErrorPanel error={err} />
      </div>
    </Modal>
  );
}

// ---------- dashboard
interface Dash {
  schools: number; parents: number; teachers: number; evaluations_today: number; evaluations_month: number;
  credits_sold: number; credits_used: number; revenue_inr: number; attention: Record<string, number>;
}

export function Dashboard() {
  return (
    <Page<Dash> title="Dashboard" path="/admin/dashboard">
      {(d) => (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <Stat label="Schools" value={d.schools} />
            <Stat label="Parents" value={d.parents} />
            <Stat label="Teachers" value={d.teachers} />
            <Stat label="Evaluations today" value={d.evaluations_today} hint={`${d.evaluations_month} this month`} />
            <Stat label="Credits sold" value={d.credits_sold} tone="pen" />
            <Stat label="Credits used" value={d.credits_used} />
            <Stat label="Revenue" value={inr(d.revenue_inr)} tone="ok" />
          </div>
          <Card>
            <h2 className="mb-3 font-display text-lg font-semibold">Needs attention</h2>
            <ul className="grid gap-2 text-sm sm:grid-cols-2">
              {Object.entries(d.attention).map(([k, v]) => (
                <li key={k} className="flex justify-between border-b border-dashed border-line py-1">
                  <span className="capitalize">{k.replace(/_/g, " ")}</span>
                  <span className={v ? "font-semibold text-mark" : "text-mute"}>{v}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      )}
    </Page>
  );
}

// ---------- schools
interface School extends Row {
  id: string; name: string; status: string; city: string; state: string; teachers: number; exams: number; balance: number;
  wallet_id: string | null; manager: { id: string; name: string; email: string } | null; created_at: string;
}

export function Schools() {
  const [status, setStatus] = useState("");
  const [adjust, setAdjust] = useState<string | null>(null);
  const canWrite = useCanWrite();
  return (
    <Page<School[]> title="Schools" path={`/admin/schools${status ? `?status=${status}` : ""}`}
      actions={<Select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
        <option value="">All</option><option value="PENDING">Pending</option><option value="ACTIVE">Active</option>
        <option value="SUSPENDED">Suspended</option></Select>}>
      {(rows, reload) => <SchoolTable rows={rows} reload={reload} canWrite={canWrite} adjust={adjust} setAdjust={setAdjust} />}
    </Page>
  );
}

function SchoolTable({ rows, reload, canWrite, adjust, setAdjust }: {
  rows: School[]; reload: () => Promise<void>; canWrite: boolean; adjust: string | null; setAdjust: (w: string | null) => void;
}) {
  const act = useAct(reload);
  return (
    <>
      <Table rows={rows} empty="No schools" cols={[
        ["School", (s) => <><p className="font-semibold">{s.name}</p><p className="text-xs text-mute">{[s.city, s.state].filter(Boolean).join(", ")}</p></>],
        ["Manager", (s) => s.manager ? <><p>{s.manager.name}</p><p className="text-xs text-mute">{s.manager.email}</p></> : "–"],
        ["Status", (s) => <StatusBadge status={s.status} />],
        ["Teachers / exams", (s) => `${s.teachers} / ${s.exams}`],
        ["Credits", (s) => s.balance],
        ["", (s) => canWrite && (
          <div className="flex flex-wrap gap-1.5">
            {s.status === "PENDING" && <Button small variant="primary" onClick={() =>
              act(() => api(`/admin/schools/${s.id}/approve`, { method: "POST" }), `${s.name} approved`)}>Approve</Button>}
            {s.status === "ACTIVE" && <Button small onClick={() =>
              act(() => api(`/admin/schools/${s.id}/status`, { method: "POST", json: { status: "SUSPENDED" } }), "Suspended")}>Suspend</Button>}
            {s.status === "SUSPENDED" && <Button small onClick={() =>
              act(() => api(`/admin/schools/${s.id}/status`, { method: "POST", json: { status: "ACTIVE" } }), "Reactivated")}>Reactivate</Button>}
            {s.wallet_id && <Button small onClick={() => setAdjust(s.wallet_id)}>Credits</Button>}
            {s.manager && <Button small variant="ghost" onClick={() =>
              act(() => api(`/admin/accounts/${s.manager!.id}/reset-password`, { method: "POST" }), "Reset link sent")}>Reset password</Button>}
          </div>
        )],
      ]} />
      {adjust && <AdjustModal walletId={adjust} onClose={() => setAdjust(null)} onDone={reload} />}
    </>
  );
}

// ---------- parents
interface Parent extends Row { id: string; name: string; email: string; is_active?: boolean; balance: number; wallet_id: string | null; exams: number }

export function Parents() {
  const [q, setQ] = useState("");
  const [adjust, setAdjust] = useState<string | null>(null);
  const canWrite = useCanWrite();
  return (
    <Page<Parent[]> title="Parents" path={`/admin/parents?q=${encodeURIComponent(q)}`}
      actions={<Input placeholder="Search name or email" value={q} onChange={(e) => setQ(e.target.value)} />}>
      {(rows, reload) => <ParentTable rows={rows} reload={reload} canWrite={canWrite} adjust={adjust} setAdjust={setAdjust} />}
    </Page>
  );
}

function ParentTable({ rows, reload, canWrite, adjust, setAdjust }: {
  rows: Parent[]; reload: () => Promise<void>; canWrite: boolean; adjust: string | null; setAdjust: (w: string | null) => void;
}) {
  const act = useAct(reload);
  return (
    <>
      <Table rows={rows} empty="No parents" cols={[
        ["Parent", (p) => <><p className="font-semibold">{p.name}</p><p className="text-xs text-mute">{p.email}</p></>],
        ["Exams", (p) => p.exams],
        ["Credits", (p) => p.balance],
        ["Status", (p) => <StatusBadge status={p.is_active === false ? "SUSPENDED" : "ACTIVE"} />],
        ["", (p) => canWrite && (
          <div className="flex flex-wrap gap-1.5">
            <Button small onClick={() => act(() => api(`/admin/parents/${p.id}/status`, { method: "POST",
              json: { status: p.is_active === false ? "ACTIVE" : "SUSPENDED" } }), "Saved")}>
              {p.is_active === false ? "Reactivate" : "Suspend"}</Button>
            {p.wallet_id && <Button small onClick={() => setAdjust(p.wallet_id)}>Credits</Button>}
            <Button small variant="ghost" onClick={() => act(() => api(`/admin/accounts/${p.id}/unlock`, { method: "POST" }), "Unlocked")}>Unlock</Button>
          </div>
        )],
      ]} />
      {adjust && <AdjustModal walletId={adjust} onClose={() => setAdjust(null)} onDone={reload} />}
    </>
  );
}

// ---------- credits: packs, settings, ledger
interface Pack { id: string; name: string; credits: number; price_inr: number; active: boolean; sort_order?: number }
interface Ledger { id: string; type: string; amount: number; balance_after: number; note: string | null; created_at: string; wallet_id: string }

export function Credits() {
  const canWrite = useCanWrite();
  return (
    <>
      <Page<Pack[]> title="Credits" sub="Packs for sale, what an answer sheet costs, and every credit movement." path="/admin/credit-packs">
        {(packs, reload) => <Packs packs={packs} reload={reload} canWrite={canWrite} />}
      </Page>
      <div className="mt-8"><CreditSettings canWrite={canWrite} /></div>
      <div className="mt-8">
        <h2 className="mb-3 font-display text-lg font-semibold">Ledger</h2>
        <LedgerTable />
      </div>
    </>
  );
}

function Packs({ packs, reload, canWrite }: { packs: Pack[]; reload: () => Promise<void>; canWrite: boolean }) {
  const [edit, setEdit] = useState<Partial<Pack> | null>(null);
  const act = useAct(reload);
  return (
    <>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-display text-lg font-semibold">Credit packs</h2>
        {canWrite && <Button variant="primary" small onClick={() => setEdit({ name: "", credits: 100, price_inr: 0, active: true })}>New pack</Button>}
      </div>
      <Table rows={packs} empty="No packs yet" cols={[
        ["Name", (p) => p.name], ["Credits", (p) => p.credits], ["Price", (p) => inr(p.price_inr)],
        ["Status", (p) => <StatusBadge status={p.active ? "ACTIVE" : "RETIRED"} />],
        ["", (p) => canWrite && <div className="flex gap-1.5">
          <Button small onClick={() => setEdit(p)}>Edit</Button>
          {p.active && <Button small variant="ghost" onClick={() => act(() => api(`/admin/credit-packs/${p.id}`, { method: "DELETE" }), "Retired")}>Retire</Button>}
        </div>],
      ]} />
      {edit && <PackModal pack={edit} onClose={() => setEdit(null)} onDone={reload} />}
    </>
  );
}

function PackModal({ pack, onClose, onDone }: { pack: Partial<Pack>; onClose: () => void; onDone: () => Promise<void> }) {
  const [p, setP] = useState(pack);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      const json = { name: p.name, credits: Number(p.credits), price_inr: Number(p.price_inr), active: p.active ?? true, sort_order: p.sort_order ?? 0 };
      await api(p.id ? `/admin/credit-packs/${p.id}` : "/admin/credit-packs", { method: p.id ? "PUT" : "POST", json });
      await onDone(); onClose();
    } catch (e) { setErr(e); setBusy(false); }
  };
  return (
    <Modal title={p.id ? "Edit pack" : "New pack"} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} onClick={save}>Save</Button></>}>
      <div className="space-y-4">
        <Field label="Name" required>{(id) => <Input id={id} value={p.name ?? ""} onChange={(e) => setP({ ...p, name: e.target.value })} />}</Field>
        <Field label="Credits" required>{(id) => <Input id={id} type="number" min={1} value={p.credits ?? ""} onChange={(e) => setP({ ...p, credits: Number(e.target.value) })} />}</Field>
        <Field label="Price (₹, before GST)" required>{(id) => <Input id={id} type="number" min={0} value={p.price_inr ?? ""} onChange={(e) => setP({ ...p, price_inr: Number(e.target.value) })} />}</Field>
        <ErrorPanel error={err} />
      </div>
    </Modal>
  );
}

const SETTING_LABEL: Record<string, string> = {
  eval_per_sheet: "Credits per answer sheet", paper_fixed: "Credits per parent sample paper",
};

function CreditSettings({ canWrite }: { canWrite: boolean }) {
  const { data, error, reload } = useApi<Record<string, number>>("/admin/credit-settings");
  const [draft, setDraft] = useState<Record<string, number> | null>(null);
  const act = useAct(reload);
  if (error) return <ErrorPanel error={error} />;
  if (!data) return <Loading />;
  const v = draft ?? data;
  return (
    <Card>
      <h2 className="mb-3 font-display text-lg font-semibold">Pricing settings</h2>
      <div className="grid gap-4 sm:grid-cols-2">
        {Object.keys(data).map((k) => (
          <Field key={k} label={SETTING_LABEL[k] ?? k.replace(/_/g, " ")}>{(id) =>
            <Input id={id} type="number" min={0} disabled={!canWrite} value={v[k]} onChange={(e) => setDraft({ ...v, [k]: Number(e.target.value) })} />}</Field>
        ))}
      </div>
      {canWrite && draft && <div className="mt-4"><Button variant="primary" onClick={() =>
        act(() => api("/admin/credit-settings", { method: "PUT", json: draft }).then(() => setDraft(null)), "Settings saved")}>Save settings</Button></div>}
    </Card>
  );
}

function LedgerTable() {
  const { data, error } = useApi<Ledger[]>("/admin/ledger?limit=300");
  if (error) return <ErrorPanel error={error} />;
  if (!data) return <Loading />;
  return <Table rows={data} empty="No credit movements yet" cols={[
    ["When", (r) => date(r.created_at)], ["Type", (r) => <StatusBadge status={r.type} />],
    ["Amount", (r) => <span className={r.amount < 0 ? "text-mark" : "text-ok"}>{r.amount > 0 ? "+" : ""}{r.amount}</span>],
    ["Balance after", (r) => r.balance_after], ["Note", (r) => r.note ?? "–"],
  ]} />;
}

// ---------- payments
interface Payment { id: string; credits: number; amount_inr: number; gst_amount: number; status: string; razorpay_order_id: string | null; invoice_no: string | null; created_at: string }

export function Payments() {
  const [status, setStatus] = useState("");
  const [refund, setRefund] = useState<Payment | null>(null);
  const canWrite = useCanWrite();
  return (
    <Page<Payment[]> title="Payments" path={`/admin/payments${status ? `?status=${status}` : ""}`}
      actions={<Select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
        <option value="">All</option><option value="PAID">Paid</option><option value="CREATED">Created</option>
        <option value="FAILED">Failed</option><option value="REFUNDED">Refunded</option></Select>}>
      {(rows, reload) => (
        <>
          <Table rows={rows} empty="No payments" cols={[
            ["When", (p) => date(p.created_at)], ["Order", (p) => <span className="font-mono text-xs">{p.razorpay_order_id ?? "–"}</span>],
            ["Credits", (p) => p.credits], ["Amount", (p) => inr(p.amount_inr)], ["GST", (p) => inr(p.gst_amount)],
            ["Invoice", (p) => p.invoice_no ?? "–"], ["Status", (p) => <StatusBadge status={p.status} />],
            ["", (p) => canWrite && p.status === "PAID" && <Button small variant="ghost" onClick={() => setRefund(p)}>Refund</Button>],
          ]} />
          {refund && <Confirm title="Refund this payment?" danger confirmLabel="Refund"
            body={<p>{refund.credits} credits are taken back from the wallet. Return {inr(refund.amount_inr)} in the Razorpay dashboard.</p>}
            onConfirm={async () => { await api(`/admin/payments/${refund.id}/refund`, { method: "POST" }); await reload(); }}
            onClose={() => setRefund(null)} />}
        </>
      )}
    </Page>
  );
}

// ---------- evaluations monitor
interface EvalRow { id: string; exam: string | null; run_status: string; status: string; created_at: string }

export function Evaluations() {
  const [state, setState] = useState("ERROR");
  const canWrite = useCanWrite();
  return (
    <Page<EvalRow[]> title="Evaluations monitor" path={`/admin/evaluations?state=${state}`}
      actions={<Select value={state} onChange={(e) => setState(e.target.value)} aria-label="Run state">
        <option value="ERROR">Failed</option><option value="RUNNING">Running</option><option value="QUEUED">Queued</option>
        <option value="DONE">Done</option></Select>}>
      {(rows, reload) => <EvalTable rows={rows} reload={reload} canWrite={canWrite} />}
    </Page>
  );
}

function EvalTable({ rows, reload, canWrite }: { rows: EvalRow[]; reload: () => Promise<void>; canWrite: boolean }) {
  const act = useAct(reload);
  return <Table rows={rows} empty="Nothing here" cols={[
    ["When", (r) => date(r.created_at)], ["Exam", (r) => r.exam ?? "–"],
    ["Run", (r) => <StatusBadge status={r.run_status} />], ["Status", (r) => <StatusBadge status={r.status} />],
    ["", (r) => canWrite && r.run_status === "ERROR" && <Button small onClick={() =>
      act(() => api(`/admin/evaluations/${r.id}/retry`, { method: "POST" }), "Retry started")}>Retry</Button>],
  ]} />;
}

// ---------- question paper bank
interface BankPaper { id: string; standard: number; subject: string; units: string[]; total_marks: number | null; duration_minutes: number; questions: number; disabled: boolean }

export function Papers() {
  const [adding, setAdding] = useState(false);
  const canWrite = useCanWrite();
  return (
    <Page<BankPaper[]> title="Question papers" sub="Sample papers parents can choose. Add one from a verified exam."
      path="/admin/papers" actions={canWrite && <Button variant="primary" onClick={() => setAdding(true)}>Add paper</Button>}>
      {(rows, reload) => (
        <>
          <PaperTable rows={rows} reload={reload} canWrite={canWrite} />
          {adding && <AddPaper onClose={() => setAdding(false)} onDone={reload} />}
        </>
      )}
    </Page>
  );
}

function PaperTable({ rows, reload, canWrite }: { rows: BankPaper[]; reload: () => Promise<void>; canWrite: boolean }) {
  const act = useAct(reload);
  return <Table rows={rows} empty="No sample papers yet" cols={[
    ["Class", (p) => p.standard], ["Subject", (p) => p.subject], ["Units", (p) => p.units.join(", ") || "All"],
    ["Questions", (p) => p.questions], ["Marks", (p) => p.total_marks ?? "–"], ["Minutes", (p) => p.duration_minutes],
    ["Status", (p) => <StatusBadge status={p.disabled ? "DISABLED" : "ACTIVE"} />],
    ["", (p) => canWrite && !p.disabled && <Button small variant="ghost" onClick={() =>
      act(() => api(`/admin/papers/${p.id}`, { method: "DELETE" }), "Paper disabled")}>Disable</Button>],
  ]} />;
}

function AddPaper({ onClose, onDone }: { onClose: () => void; onDone: () => Promise<void> }) {
  const [f, setF] = useState({ exam_id: "", standard: "10", subject: "", units: "" });
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      await api("/admin/papers", { method: "POST", json: { exam_id: f.exam_id.trim(), standard: Number(f.standard), subject: f.subject.trim(),
        units: f.units.split(",").map((u) => u.trim()).filter(Boolean) } });
      await onDone(); onClose();
    } catch (e) { setErr(e); setBusy(false); }
  };
  return (
    <Modal title="Add sample paper" onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button variant="primary" busy={busy} disabled={!f.exam_id || !f.subject} onClick={save}>Add</Button></>}>
      <div className="space-y-4">
        <Field label="Exam ID" hint="An exam whose answer key is verified" required>{(id) =>
          <Input id={id} value={f.exam_id} onChange={(e) => setF({ ...f, exam_id: e.target.value })} />}</Field>
        <Field label="Class" required>{(id) => <Select id={id} value={f.standard} onChange={(e) => setF({ ...f, standard: e.target.value })}>
          <option value="10">10</option><option value="12">12</option></Select>}</Field>
        <Field label="Subject" required>{(id) => <Input id={id} value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} />}</Field>
        <Field label="Units" hint="Comma separated, optional">{(id) => <Input id={id} value={f.units} onChange={(e) => setF({ ...f, units: e.target.value })} />}</Field>
        <ErrorPanel error={err} />
      </div>
    </Modal>
  );
}

// ---------- disputes
interface Dispute { id: string; evaluation_id: string; reason: string; status: string; resolution: string | null; refund_credits: number; created_at: string }

export function Disputes() {
  const [status, setStatus] = useState("OPEN");
  const [open, setOpen] = useState<Dispute | null>(null);
  const canWrite = useCanWrite();
  return (
    <Page<Dispute[]> title="Disputes" path={`/admin/disputes?status=${status}`}
      actions={<Select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
        <option value="OPEN">Open</option><option value="UPHELD">Upheld</option><option value="REJECTED">Rejected</option></Select>}>
      {(rows, reload) => (
        <>
          <Table rows={rows} empty="No disputes" cols={[
            ["Raised", (d) => date(d.created_at)], ["Reason", (d) => <p className="max-w-md whitespace-pre-wrap">{d.reason}</p>],
            ["Status", (d) => <StatusBadge status={d.status} />], ["Resolution", (d) => d.resolution ?? "–"],
            ["", (d) => canWrite && d.status === "OPEN" && <Button small variant="primary" onClick={() => setOpen(d)}>Resolve</Button>],
          ]} />
          {open && <ResolveModal d={open} onClose={() => setOpen(null)} onDone={reload} />}
        </>
      )}
    </Page>
  );
}

function ResolveModal({ d, onClose, onDone }: { d: Dispute; onClose: () => void; onDone: () => Promise<void> }) {
  const [status, setStatus] = useState("UPHELD");
  const [resolution, setResolution] = useState("");
  const [refund, setRefund] = useState("0");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      await api(`/admin/disputes/${d.id}/resolve`, { method: "POST", json: { status, resolution, refund_credits: Number(refund) } });
      await onDone(); onClose();
    } catch (e) { setErr(e); setBusy(false); }
  };
  return (
    <Modal title="Resolve dispute" onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button variant="primary" busy={busy} disabled={resolution.trim().length < 3} onClick={save}>Save</Button></>}>
      <div className="space-y-4">
        <p className="rounded-md bg-sunken/60 p-3 text-sm whitespace-pre-wrap">{d.reason}</p>
        <Field label="Decision">{(id) => <Select id={id} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="UPHELD">Upheld</option><option value="REJECTED">Rejected</option></Select>}</Field>
        <Field label="Resolution" required>{(id) => <Textarea id={id} rows={3} value={resolution} onChange={(e) => setResolution(e.target.value)} />}</Field>
        {status === "UPHELD" && <Field label="Refund credits">{(id) =>
          <Input id={id} type="number" min={0} value={refund} onChange={(e) => setRefund(e.target.value)} />}</Field>}
        <ErrorPanel error={err} />
      </div>
    </Modal>
  );
}

// ---------- support
interface Ticket { id: string; subject: string; message: string; status: string; reply: string | null; created_at: string }

export function Support() {
  const [status, setStatus] = useState("OPEN");
  const [open, setOpen] = useState<Ticket | null>(null);
  const canWrite = useCanWrite();
  return (
    <Page<Ticket[]> title="Support tickets" path={`/admin/support?status=${status}`}
      actions={<Select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
        <option value="OPEN">Open</option><option value="ANSWERED">Answered</option><option value="CLOSED">Closed</option></Select>}>
      {(rows, reload) => (
        <>
          <Table rows={rows} empty="No tickets" cols={[
            ["Raised", (t) => date(t.created_at)], ["Subject", (t) => <p className="font-semibold">{t.subject}</p>],
            ["Message", (t) => <p className="max-w-md whitespace-pre-wrap">{t.message}</p>],
            ["Status", (t) => <StatusBadge status={t.status} />],
            ["", (t) => canWrite && t.status !== "CLOSED" && <Button small variant="primary" onClick={() => setOpen(t)}>Reply</Button>],
          ]} />
          {open && <ReplyModal t={open} onClose={() => setOpen(null)} onDone={reload} />}
        </>
      )}
    </Page>
  );
}

function ReplyModal({ t, onClose, onDone }: { t: Ticket; onClose: () => void; onDone: () => Promise<void> }) {
  const [reply, setReply] = useState(t.reply ?? "");
  const [close, setClose] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try { await api(`/admin/support/${t.id}/reply`, { method: "POST", json: { reply, close } }); await onDone(); onClose(); }
    catch (e) { setErr(e); setBusy(false); }
  };
  return (
    <Modal title={t.subject} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button variant="primary" busy={busy} disabled={!reply.trim()} onClick={save}>Send reply</Button></>}>
      <div className="space-y-4">
        <p className="rounded-md bg-sunken/60 p-3 text-sm whitespace-pre-wrap">{t.message}</p>
        <Field label="Reply" required>{(id) => <Textarea id={id} rows={5} value={reply} onChange={(e) => setReply(e.target.value)} />}</Field>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={close} onChange={(e) => setClose(e.target.checked)} />Close the ticket</label>
        <ErrorPanel error={err} />
      </div>
    </Modal>
  );
}

// ---------- audit log
interface AuditRow { id: string; action: string; actor_id: string | null; entity_type: string; entity_id: string; ip: string | null; new: unknown; created_at: string }

export function Audit() {
  const [action, setAction] = useState("");
  return (
    <Page<AuditRow[]> title="Audit log" path={`/admin/audit-logs?limit=500&action=${encodeURIComponent(action)}`}
      actions={<Input placeholder="Filter by action" value={action} onChange={(e) => setAction(e.target.value)} />}>
      {(rows) => <Table rows={rows} empty="No entries" cols={[
        ["When", (r) => date(r.created_at)], ["Action", (r) => <span className="font-mono text-xs">{r.action}</span>],
        ["On", (r) => `${r.entity_type} ${r.entity_id.slice(0, 8)}`], ["By", (r) => r.actor_id?.slice(0, 8) ?? "system"],
        ["IP", (r) => r.ip || "–"],
        ["Details", (r) => r.new ? <code className="block max-w-sm truncate text-xs" title={JSON.stringify(r.new)}>{JSON.stringify(r.new)}</code> : "–"],
      ]} />}
    </Page>
  );
}

// ---------- settings: platform configuration and console users
interface ConsoleUser { id: string; name: string; email: string; admin_role: string; is_active?: boolean }

export function Settings() {
  const { user } = useAuth();
  const isSuper = user?.admin_role === "super_admin";
  const toast = useToast();
  const { data: cfg, error } = useApi<Record<string, unknown>>("/admin/settings");
  return (
    <>
      <PageHeader title="Settings" />
      {error ? <ErrorPanel error={error} /> : !cfg ? <Loading /> : (
        <Card>
          <h2 className="mb-3 font-display text-lg font-semibold">Platform</h2>
          <dl className="grid gap-2 text-sm sm:grid-cols-2">
            <dt className="text-mute">Email</dt><dd>{cfg.smtp_configured ? `Configured (${cfg.smtp_from})` : "Not configured"}</dd>
            <dt className="text-mute">Google sign-in</dt><dd>{cfg.google_client_id ? "On" : "Off"}</dd>
            <dt className="text-mute">Payments</dt><dd className="capitalize">{String(cfg.razorpay)}</dd>
            <dt className="text-mute">GST</dt><dd>{String(cfg.gst_percent)}%</dd>
            <dt className="text-mute">Invoice name</dt><dd>{String(cfg.invoice_legal_name || "–")}</dd>
            <dt className="text-mute">GSTIN</dt><dd>{String(cfg.invoice_gstin || "–")}</dd>
          </dl>
          <div className="mt-4"><Button small onClick={async () => {
            try { await api("/admin/settings/test-email", { method: "POST" }); toast(`Test email sent to ${user?.email}`, "ok"); }
            catch (e) { toast((e as Error).message, "mark"); }
          }}>Send test email</Button></div>
        </Card>
      )}
      <div className="mt-8"><ConsoleUsers isSuper={isSuper} /></div>
    </>
  );
}

function ConsoleUsers({ isSuper }: { isSuper: boolean }) {
  const { data, error, reload } = useApi<ConsoleUser[]>("/admin/console-users");
  const [invite, setInvite] = useState(false);
  const act = useAct(reload);
  if (error) return <ErrorPanel error={error} />;
  if (!data) return <Loading />;
  return (
    <>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-display text-lg font-semibold">Console users</h2>
        {isSuper && <Button small variant="primary" onClick={() => setInvite(true)}>Invite</Button>}
      </div>
      <Table rows={data} empty="No console users" cols={[
        ["Name", (u) => <><p className="font-semibold">{u.name}</p><p className="text-xs text-mute">{u.email}</p></>],
        ["Role", (u) => isSuper ? (
          <Select value={u.admin_role} aria-label="Role" onChange={(e) =>
            act(() => api(`/admin/console-users/${u.id}`, { method: "PATCH", json: { admin_role: e.target.value } }), "Role changed")}>
            <option value="super_admin">Super Admin</option><option value="admin">Admin</option><option value="viewer">Viewer</option>
          </Select>) : u.admin_role],
        ["Status", (u) => <StatusBadge status={u.is_active === false ? "SUSPENDED" : "ACTIVE"} />],
        ["", (u) => isSuper && <Button small variant="ghost" onClick={() =>
          act(() => api(`/admin/console-users/${u.id}`, { method: "PATCH", json: { active: u.is_active === false } }), "Saved")}>
          {u.is_active === false ? "Enable" : "Disable"}</Button>],
      ]} />
      {invite && <InviteModal onClose={() => setInvite(false)} onDone={reload} />}
    </>
  );
}

function InviteModal({ onClose, onDone }: { onClose: () => void; onDone: () => Promise<void> }) {
  const [f, setF] = useState({ name: "", email: "", admin_role: "viewer" });
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try { await api("/admin/console-users", { method: "POST", json: f }); await onDone(); onClose(); }
    catch (e) { setErr(e); setBusy(false); }
  };
  return (
    <Modal title="Invite console user" onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button variant="primary" busy={busy} disabled={f.name.length < 2 || !f.email} onClick={save}>Send invite</Button></>}>
      <div className="space-y-4">
        <Field label="Name" required>{(id) => <Input id={id} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />}</Field>
        <Field label="Email" required>{(id) => <Input id={id} type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />}</Field>
        <Field label="Role">{(id) => <Select id={id} value={f.admin_role} onChange={(e) => setF({ ...f, admin_role: e.target.value })}>
          <option value="viewer">Viewer</option><option value="admin">Admin</option><option value="super_admin">Super Admin</option></Select>}</Field>
        <ErrorPanel error={err} />
      </div>
    </Modal>
  );
}
