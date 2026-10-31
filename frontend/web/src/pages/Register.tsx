import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../context/Auth";
import { useApi } from "../hooks/useApi";
import { BrandLabel } from "../components/Brand";
import { Button, ErrorPanel, Field, Input, Select } from "../components/ui";

export default function Register() {
  const { teacher, refresh } = useAuth();
  const navigate = useNavigate();
  const { data: providers } = useApi<{ google: boolean; google_start_url: string }>("/auth/providers");
  const [name, setName] = useState("");
  const [role, setRole] = useState("MANAGEMENT");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  if (teacher) return <Navigate to={teacher.is_admin ? "/admin" : teacher.profile_complete ? "/dashboard" : "/onboarding"} replace />;
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError(null);
    if (password !== confirm) { setError(new Error("Passwords do not match.")); return; }
    setBusy(true);
    try { await api("/auth/register", { method: "POST", json: { name, email, password, role } }); await refresh(); navigate("/onboarding", { replace: true }); }
    catch (e) { setError(e); }
    finally { setBusy(false); }
  };
  return <main className="desk flex min-h-full items-center justify-center p-6"><section className="w-full max-w-md rounded-lg border border-line bg-surface p-6 shadow-pop">
    <BrandLabel onDark={false} /><h1 className="mt-6 font-display text-3xl font-semibold">Start with Eval AI</h1>
    <p className="mt-2 text-sm text-mute">CBSE Class 10 and 12 answer sheet evaluation for schools and families. Complete your profile to begin.</p>
    {providers?.google && <a href={providers.google_start_url} className="mt-5 flex justify-center rounded-md border border-line px-4 py-3 text-sm font-semibold text-pen hover:bg-hover">Continue with Google</a>}
    <form onSubmit={submit} className="mt-5 space-y-4">
      <Field label="I am registering as">{(id) => <Select id={id} value={role} onChange={e => setRole(e.target.value)}><option value="MANAGEMENT">School management</option><option value="PARENT">Parent</option></Select>}</Field>
      <p className="text-xs text-mute">Teachers sign in with credentials provided by their school.</p>
      <Field label="Full name">{(id) => <Input id={id} autoComplete="name" required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
      <Field label="Email address">{(id) => <Input id={id} type="email" autoComplete="email" required maxLength={200} value={email} onChange={(e) => setEmail(e.target.value)} />}</Field>
      <Field label="Password">{(id) => <Input id={id} type="password" autoComplete="new-password" required minLength={10} maxLength={72} value={password} onChange={(e) => setPassword(e.target.value)} />}</Field>
      <Field label="Confirm password">{(id) => <Input id={id} type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />}</Field>
      <ErrorPanel error={error} /><Button type="submit" variant="primary" busy={busy} className="w-full">Create account</Button>
    </form><p className="mt-5 text-sm text-mute">Already registered? <Link to="/login" className="text-pen underline">Sign in</Link></p>
  </section></main>;
}
