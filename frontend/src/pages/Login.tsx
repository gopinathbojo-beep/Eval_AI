import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/Auth";
import { Button, ErrorPanel, Field, Input } from "../components/ui";

export default function Login() {
  const { teacher, login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (teacher) return <Navigate to="/dashboard" replace />;
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setError(null);
    try { await login(email, password); nav((loc.state as { from?: string } | null)?.from ?? "/dashboard", { replace: true }); }
    catch (err) { setError(err); setBusy(false); }
  };
  return (
    <div className="flex h-full items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <h1 className="text-3xl font-semibold tracking-tight text-pen">Eval AI</h1>
        <p className="mb-6 mt-1 text-sm text-mute">Sign in with your teacher account to mark exams.</p>
        <form onSubmit={submit} className="space-y-4 rounded-lg border border-line bg-surface p-5">
          <Field label="Email">{(id) => <Input id={id} type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />}</Field>
          <Field label="Password">{(id) => <Input id={id} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />}</Field>
          <ErrorPanel error={error} />
          <Button type="submit" variant="primary" busy={busy} className="w-full">Sign in</Button>
        </form>
        <p className="mt-4 text-xs text-mute">Accounts are created by the administrator: <code>python -m app.create_teacher</code>.</p>
      </div>
    </div>
  );
}
