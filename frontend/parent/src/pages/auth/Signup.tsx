import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../../api/client";
import { useAuth } from "../../context/Auth";
import { Button, ErrorPanel, Field, Input, Loading } from "../../components/ui";
import { GoogleButton } from "../../components/GoogleButton";
import type { Session } from "../../types";
import { AuthShell } from "./AuthShell";

const signIn = <>Already have an account? <Link to="/login" className="text-pen hover:underline">Sign in</Link></>;

function Consent({ checked, onChange, children }: { checked: boolean; onChange(v: boolean): void; children: React.ReactNode }) {
  return (
    <label className="flex items-start gap-2.5 text-sm text-ink">
      <input type="checkbox" required checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-1 accent-[rgb(var(--pen-fill))]" />
      <span>{children}</span>
    </label>
  );
}

/** Parent signup. With a password: we email a confirmation link. With Google: the account is created at once.
 * Arriving from "Continue with Google" on the sign-in page (no account yet) carries the Google token in state. */
export default function Signup() {
  const { user, adopt } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const pendingGoogle = (loc.state as { idToken?: string } | null)?.idToken ?? null;
  const [googleToken, setGoogleToken] = useState<string | null>(pendingGoogle);
  const [f, setF] = useState({ name: "", email: "", phone: "", password: "" });
  const [agree, setAgree] = useState({ terms: false, privacy: false, child: false });
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/" replace />;

  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  const consents = { accept_terms: agree.terms, accept_privacy: agree.privacy, accept_child_data: agree.child };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (googleToken) {
        const parent = { name: f.name, phone: f.phone, ...consents };
        adopt(await api<Session>("/public/signup/google", { method: "POST", json: { id_token: googleToken, kind: "parent", parent } }));
        nav("/", { replace: true });
      } else {
        const r = await api<{ message: string }>("/public/signup/parent", { method: "POST", json: { ...f, ...consents } });
        setSent(r.message);
      }
    } catch (err) { setError(err); }
    setBusy(false);
  };

  if (sent) {
    return (
      <AuthShell title="Check your email" footer={signIn}>
        <p className="rounded-md border border-ok/40 bg-ok-soft p-4 text-sm text-ink">{sent} Open the link to finish creating your account.</p>
      </AuthShell>
    );
  }
  return (
    <AuthShell title="Create your account" sub="Free to start: your account comes with 10 credits, enough to mark 10 answer sheets." footer={signIn}>
      {!googleToken && <GoogleButton text="signup_with" onToken={setGoogleToken} />}
      {googleToken && <p className="mb-4 rounded-md border border-pen/30 bg-pen-soft p-3 text-sm text-ink">Signing up with your Google account. Add your details below.</p>}
      <form onSubmit={submit} className="mt-4 space-y-4">
        <Field label="Your name">{(id) => <Input id={id} required minLength={2} value={f.name} onChange={set("name")} />}</Field>
        {!googleToken && (
          <Field label="Email address">{(id) => <Input id={id} type="email" required value={f.email} onChange={set("email")} />}</Field>
        )}
        <Field label="Mobile number">{(id) => <Input id={id} type="tel" required minLength={6} value={f.phone} onChange={set("phone")} />}</Field>
        {!googleToken && (
          <Field label="Password" hint="8+ characters, letters and numbers">
            {(id) => <Input id={id} type="password" autoComplete="new-password" required minLength={8} value={f.password} onChange={set("password")} />}
          </Field>
        )}
        <div className="space-y-2 pt-1">
          <Consent checked={agree.terms} onChange={(v) => setAgree({ ...agree, terms: v })}>I accept the Terms of Use.</Consent>
          <Consent checked={agree.privacy} onChange={(v) => setAgree({ ...agree, privacy: v })}>I accept the Privacy Policy.</Consent>
          <Consent checked={agree.child} onChange={(v) => setAgree({ ...agree, child: v })}>
            As the parent or guardian, I consent to ADEM processing my children's answer sheets and results.
          </Consent>
        </div>
        <ErrorPanel error={error} />
        <Button type="submit" variant="primary" busy={busy} className="w-full py-2.5">Create account</Button>
      </form>
    </AuthShell>
  );
}

/** The link from the confirmation email: creates the account and signs the parent in. */
export function VerifyEmail() {
  const [params] = useSearchParams();
  const { adopt } = useAuth();
  const nav = useNavigate();
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    api<Session>("/public/signup/verify-email", { method: "POST", json: { token: params.get("token") ?? "" } })
      .then((s) => { adopt(s); nav("/", { replace: true }); })
      .catch(setError);
  }, [params, adopt, nav]);
  if (!error) return <Loading text="Confirming your email..." />;
  return (
    <AuthShell title="We could not confirm your email" footer={signIn}>
      <ErrorPanel error={error} />
    </AuthShell>
  );
}
