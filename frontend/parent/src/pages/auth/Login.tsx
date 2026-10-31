import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/Auth";
import { Button, ErrorPanel, Field, Input } from "../../components/ui";
import { GoogleButton } from "../../components/GoogleButton";
import { AuthShell } from "./AuthShell";

export default function Login({ footer, onNeedsSignup }: { footer?: ReactNode; onNeedsSignup?(idToken: string): void }) {
  const { user, login, loginGoogle } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={(loc.state as { from?: string } | null)?.from ?? "/"} replace />;

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      nav((loc.state as { from?: string } | null)?.from ?? "/", { replace: true });
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };
  const submit = (e: FormEvent) => { e.preventDefault(); run(() => login(email, password)); };
  const google = (idToken: string) =>
    run(async () => {
      try { await loginGoogle(idToken); }
      catch (err) {
        if (onNeedsSignup && (err as { code?: string }).code === "NEEDS_SIGNUP") { onNeedsSignup(idToken); return; }
        throw err;
      }
    });

  return (
    <AuthShell title="Sign in" sub="Welcome back. Sign in to continue." footer={footer}>
      <GoogleButton onToken={google} />
      <form onSubmit={submit} className="mt-4 space-y-5">
        <Field label="Email address">
          {(id) => <Input id={id} type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />}
        </Field>
        <Field label="Password">
          {(id) => <Input id={id} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />}
        </Field>
        <div className="-mt-2 text-right text-sm"><Link to="/forgot-password" className="text-pen hover:underline">Forgot password?</Link></div>
        <ErrorPanel error={error} />
        <Button type="submit" variant="primary" busy={busy} className="w-full py-2.5">Sign in</Button>
      </form>
    </AuthShell>
  );
}
