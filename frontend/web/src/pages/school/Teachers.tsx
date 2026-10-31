import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api } from "../../api/client";
import { Badge, Button, Card, Confirm, Empty, ErrorPanel, Field, Input, Loading, Modal, PageHeader } from "../../components/ui";
import { IconPlus } from "../../components/Icons";
import { useToast } from "../../components/Toast";
import { date } from "../../utils/format";
import type { StaffRow } from "../../types";

const STATUS: Record<StaffRow["status"], { tone: "ok" | "warn" | "mute"; text: string }> = {
  active: { tone: "ok", text: "Active" },
  invited: { tone: "warn", text: "Invited" },
  suspended: { tone: "mute", text: "Suspended" },
};

function InviteModal({ onClose, onDone }: { onClose(): void; onDone(t: StaffRow): void }) {
  const [f, setF] = useState({ name: "", email: "", phone: "" });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onDone(await api<StaffRow>("/school/teachers", { method: "POST", json: f }));
    } catch (err) { setError(err); setBusy(false); }
  };
  return (
    <Modal title="Invite a teacher" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <p className="text-sm text-mute">We email them a link to join. They choose a password or continue with Google, then sign in on the same page as you.</p>
        <Field label="Name" required>{(id) => <Input id={id} required minLength={2} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />}</Field>
        <Field label="Email address" required>{(id) => <Input id={id} type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />}</Field>
        <Field label="Mobile number" hint="Optional">{(id) => <Input id={id} type="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} />}</Field>
        <ErrorPanel error={error} />
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" busy={busy}>Send invitation</Button>
        </div>
      </form>
    </Modal>
  );
}

type Pending = { kind: "cancel" | "suspend" | "activate"; t: StaffRow };

export default function Teachers() {
  const notify = useToast();
  const [rows, setRows] = useState<StaffRow[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [inviting, setInviting] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [resending, setResending] = useState<string | null>(null);

  const load = useCallback(() => api<StaffRow[]>("/school/teachers").then(setRows).catch(setError), []);
  useEffect(() => { load(); }, [load]);

  const resend = async (t: StaffRow) => {
    setResending(t.id);
    try {
      notify((await api<{ message: string }>(`/school/teachers/${t.id}/resend`, { method: "POST" })).message);
    } catch (err) { notify(err instanceof Error ? err.message : String(err), "mark"); }
    setResending(null);
  };

  const confirm = async () => {
    if (!pending) return;
    const { kind, t } = pending;
    if (kind === "cancel") await api(`/school/teachers/${t.id}/invite`, { method: "DELETE" });
    else await api(`/school/teachers/${t.id}/status`, { method: "PUT", json: { status: kind === "suspend" ? "suspended" : "active" } });
    notify(kind === "cancel" ? `Invitation to ${t.email} cancelled.` : kind === "suspend" ? `${t.name} is suspended.` : `${t.name} is active again.`);
    await load();
  };

  const invite = (
    <Button variant="primary" icon={<IconPlus size={16} />} onClick={() => setInviting(true)}>Invite teacher</Button>
  );

  return (
    <>
      <PageHeader title="Teachers" sub="Invite the teachers who set exams and mark answer sheets for your school." actions={invite} />
      <ErrorPanel error={error} />
      {!rows && !error && <Loading text="Loading teachers..." />}
      {rows && rows.length === 0 && (
        <Empty title="No teachers yet" hint="Invite your first teacher. They get an email with a link to join." action={invite} />
      )}
      {rows && rows.length > 0 && (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-line text-left text-xs uppercase tracking-[0.1em] text-mute">
              <tr>
                <th className="px-4 py-3 font-medium">Teacher</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Last sign-in</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((t) => (
                <tr key={t.id}>
                  <td className="px-4 py-3">
                    <p className="font-medium text-ink">{t.name}</p>
                    <p className="text-xs text-mute">{t.email}</p>
                  </td>
                  <td className="px-4 py-3"><Badge tone={STATUS[t.status].tone} withDot>{STATUS[t.status].text}</Badge></td>
                  <td className="px-4 py-3 text-mute">{t.status === "invited" ? "Not joined yet" : date(t.last_login_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-2">
                      {t.status === "invited" && (
                        <>
                          <Button small busy={resending === t.id} onClick={() => resend(t)}>Resend</Button>
                          <Button small variant="secondary" onClick={() => setPending({ kind: "cancel", t })}>Cancel invite</Button>
                        </>
                      )}
                      {t.status === "active" && <Button small variant="secondary" onClick={() => setPending({ kind: "suspend", t })}>Suspend</Button>}
                      {t.status === "suspended" && <Button small onClick={() => setPending({ kind: "activate", t })}>Reactivate</Button>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {inviting && (
        <InviteModal
          onClose={() => setInviting(false)}
          onDone={(t) => { setInviting(false); notify(`Invitation sent to ${t.email}.`); load(); }}
        />
      )}
      {pending && (
        <Confirm
          title={pending.kind === "cancel" ? "Cancel this invitation?" : pending.kind === "suspend" ? "Suspend this teacher?" : "Reactivate this teacher?"}
          body={
            pending.kind === "cancel" ? <p>The link we emailed to {pending.t.email} stops working. You can invite them again later.</p>
            : pending.kind === "suspend" ? <p>{pending.t.name} is signed out at once and cannot sign in until you reactivate them. Their exams and marks are kept.</p>
            : <p>{pending.t.name} can sign in again.</p>
          }
          confirmLabel={pending.kind === "cancel" ? "Cancel invitation" : pending.kind === "suspend" ? "Suspend" : "Reactivate"}
          danger={pending.kind !== "activate"}
          onConfirm={confirm}
          onClose={() => setPending(null)}
        />
      )}
    </>
  );
}
