import { useState, type FormEvent } from "react";
import { Link, Navigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../context/Auth";
import {
  Button,
  Card,
  ErrorPanel,
  Field,
  Input,
  Loading,
} from "../components/ui";

export default function Account() {
  const { teacher, loading, refresh, logout } = useAuth();
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<unknown>(null);
  if (loading) return <Loading />;
  if (!teacher) return <Navigate to="/login" replace />;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (password !== confirm) {
      setError(new Error("Passwords do not match."));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api("/auth/password", {
        method: "POST",
        json: { current_password: current, password },
      });
      await refresh();
      setSaved(true);
      setPassword("");
      setConfirm("");
      setCurrent("");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <main className="desk min-h-full p-6">
      <div className="mx-auto max-w-xl space-y-5">
        <div className="flex justify-between">
          <Link
            to={
              teacher.is_admin
                ? "/admin"
                : teacher.profile_complete
                  ? "/dashboard"
                  : "/onboarding"
            }
            className="underline"
          >
            Eval AI workspace
          </Link>
          <Button onClick={logout}>Sign out</Button>
        </div>
        <Card className="p-6">
          <h1 className="font-display text-2xl font-semibold">
            Account settings
          </h1>
          <p className="mt-2 text-sm text-mute">
            {teacher.name} · {teacher.email}
          </p>
          {teacher.must_change_password && (
            <p role="alert" className="mt-4 rounded bg-hover p-3 text-sm">
              Change your temporary password before opening your school
              workspace.
            </p>
          )}
          <form onSubmit={submit} className="mt-6 space-y-4">
            <Field label="Current password (leave blank for Google-only accounts)">
              {(id) => (
                <Input
                  id={id}
                  type="password"
                  autoComplete="current-password"
                  value={current}
                  onChange={(e) => setCurrent(e.target.value)}
                />
              )}
            </Field>
            <Field label="New password">
              {(id) => (
                <Input
                  id={id}
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={10}
                  maxLength={72}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              )}
            </Field>
            <Field label="Confirm new password">
              {(id) => (
                <Input
                  id={id}
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={10}
                  maxLength={72}
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                />
              )}
            </Field>
            <ErrorPanel error={error} />
            {saved && (
              <p role="status">
                Password updated.{" "}
                <Link
                  className="underline"
                  to={teacher.is_admin ? "/admin" : "/dashboard"}
                >
                  Open workspace
                </Link>
              </p>
            )}
            <Button type="submit" variant="primary" busy={busy}>
              Update password
            </Button>
          </form>
        </Card>
        <Card className="p-6">
          <h2 className="font-semibold">Google sign-in</h2>
          <p className="mt-2 text-sm text-mute">
            {teacher.email_verified
              ? "Your Google account is connected."
              : "Connect the Google account with the same email address to enable Google sign-in."}
          </p>
          {!teacher.email_verified && (
            <a
              href="/api/auth/google/link"
              className="mt-4 inline-block underline"
            >
              Connect Google account
            </a>
          )}
        </Card>
      </div>
    </main>
  );
}
