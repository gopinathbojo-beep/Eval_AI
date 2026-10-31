import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../../api/client";
import { useAuth } from "../../context/Auth";
import { PORTAL } from "../../config/config";
import { Button, ErrorPanel, Field, Input, Loading } from "../../components/ui";
import { GoogleButton } from "../../components/GoogleButton";
import type { Session } from "../../types";
import { AuthShell } from "./AuthShell";

const back = <Link to="/login" className="text-pen hover:underline">Back to sign in</Link>;
const RULE = "At least 8 characters, with letters and numbers.";

function NewPassword({ value, onChange, label = "New password" }: { value: string; onChange(v: string): void; label?: string }) {
  return (
    <Field label={label} hint={RULE}>
      {(id) => <Input id={id} type="password" autoComplete="new-password" required minLength={8} value={value} onChange={(e) => onChange(e.target.value)} />}
    </Field>
  );
}

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ message: string }>("/auth/forgot-password", { method: "POST", json: { email, portal: PORTAL } });
      setDone(r.message);
    } catch (err) { setError(err); }
    setBusy(false);
  };
  return (
    <AuthShell title="Reset your password" sub="We will email you a link to choose a new password." footer={back}>
      {done ? <p className="rounded-md border border-ok/40 bg-ok-soft p-4 text-sm text-ink">{done}</p> : (
        <form onSubmit={submit} className="space-y-5">
          <Field label="Email address">
            {(id) => <Input id={id} type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />}
          </Field>
          <ErrorPanel error={error} />
          <Button type="submit" variant="primary" busy={busy} className="w-full py-2.5">Send reset link</Button>
        </form>
      )}
    </AuthShell>
  );
}

export function ResetPassword() {
  const [params] = useSearchParams();
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/auth/reset-password", { method: "POST", json: { token: params.get("token") ?? "", new_password: password } });
      setDone(true);
    } catch (err) { setError(err); }
    setBusy(false);
  };
  return (
    <AuthShell title="Choose a new password" footer={back}>
      {done ? <p className="rounded-md border border-ok/40 bg-ok-soft p-4 text-sm text-ink">Password changed. You can sign in now.</p> : (
        <form onSubmit={submit} className="space-y-5">
          <NewPassword value={password} onChange={setPassword} />
          <ErrorPanel error={error} />
          <Button type="submit" variant="primary" busy={busy} className="w-full py-2.5">Save password</Button>
        </form>
      )}
    </AuthShell>
  );
}

/** Shown while the account still has a password someone else chose (new console user, admin reset). */
export function ChangePassword() {
  const { user, adopt, logout } = useAuth();
  const nav = useNavigate();
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (!user) return <Navigate to="/login" replace />;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      adopt(await api<Session>("/auth/change-password", { method: "POST", json: { current_password: current, new_password: password } }));
      nav("/", { replace: true });
    } catch (err) { setError(err); setBusy(false); }
  };
  return (
    <AuthShell title="Set your own password" sub="Your password was set by someone else. Choose a new one to continue."
      footer={<button className="text-pen hover:underline" onClick={logout}>Sign out</button>}>
      <form onSubmit={submit} className="space-y-5">
        {user.has_password && (
          <Field label="Current password">
            {(id) => <Input id={id} type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />}
          </Field>
        )}
        <NewPassword value={password} onChange={setPassword} />
        <ErrorPanel error={error} />
        <Button type="submit" variant="primary" busy={busy} className="w-full py-2.5">Save and continue</Button>
      </form>
    </AuthShell>
  );
}

/** Accept an emailed invitation: choose a password, or continue with the invited Google account. */
export function AcceptInvite() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const { adopt } = useAuth();
  const nav = useNavigate();
  const [info, setInfo] = useState<{ name: string; email: string; school: string | null } | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<{ name: string; email: string; school: string | null }>(`/auth/invite?token=${encodeURIComponent(token)}`).then(setInfo).catch(setError);
  }, [token]);
  const accept = async (body: { password?: string; id_token?: string }) => {
    setBusy(true);
    setError(null);
    try {
      adopt(await api<Session>("/auth/invite/accept", { method: "POST", json: { token, ...body } }));
      nav("/", { replace: true });
    } catch (err) { setError(err); setBusy(false); }
  };
  if (!info && !error) return <Loading text="Opening your invitation..." />;
  return (
    <AuthShell title="Accept your invitation" sub={info ? `${info.name}, set up your account for ${info.email}${info.school ? ` at ${info.school}` : ""}.` : undefined} footer={back}>
      {info && (
        <>
          <GoogleButton onToken={(id_token) => accept({ id_token })} />
          <form onSubmit={(e) => { e.preventDefault(); accept({ password }); }} className="mt-4 space-y-5">
            <NewPassword value={password} onChange={setPassword} label="Choose a password" />
            <ErrorPanel error={error} />
            <Button type="submit" variant="primary" busy={busy} className="w-full py-2.5">Create my account</Button>
          </form>
        </>
      )}
      {!info && <ErrorPanel error={error} />}
    </AuthShell>
  );
}
