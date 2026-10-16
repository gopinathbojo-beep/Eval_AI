import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/Auth";
import { Button, Card, ErrorPanel, Field, Input } from "../components/ui";

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
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      nav((loc.state as { from?: string } | null)?.from ?? "/dashboard", { replace: true });
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-[85vh] items-center justify-center p-4 sm:p-6">
      <div className="w-full max-w-md space-y-6">
        {/* Brand Header */}
        <div className="text-center space-y-2">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-pen text-surface shadow-card">
            <svg className="h-7 w-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
            </svg>
          </div>
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-ink sm:text-3xl">Eval AI</h1>
            <p className="mt-1 text-xs text-mute font-medium uppercase tracking-wider">
              Examination Evaluation &amp; Grading Platform
            </p>
          </div>
        </div>

        {/* Login Card */}
        <Card className="p-6 sm:p-8 shadow-card border-line/80">
          <form onSubmit={submit} className="space-y-4">
            <div>
              <h2 className="text-base font-semibold text-ink">Sign in to your account</h2>
              <p className="text-xs text-mute mt-0.5">Enter your teacher credentials to access your exam workspace.</p>
            </div>

            <Field label="Email Address">
              {(id) => (
                <Input
                  id={id}
                  type="email"
                  autoComplete="username"
                  required
                  placeholder="teacher@institution.edu"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              )}
            </Field>

            <Field label="Password">
              {(id) => (
                <Input
                  id={id}
                  type="password"
                  autoComplete="current-password"
                  required
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              )}
            </Field>

            <ErrorPanel error={error} />

            <div className="pt-1">
              <Button type="submit" variant="primary" busy={busy} className="w-full shadow-xs">
                Sign in to Eval AI
              </Button>
            </div>
          </form>
        </Card>

        {/* Admin hint */}
        <p className="text-center text-xs text-mute">
          Account management is maintained by the institution administrator.
        </p>
      </div>
    </div>
  );
}
