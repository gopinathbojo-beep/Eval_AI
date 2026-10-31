import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/Auth";
import { Button, ErrorPanel, Field, Input } from "../components/ui";
import { BrandLabel } from "../components/Brand";
import { GoogleButton } from "../components/GoogleButton";

/** Decorative graded answer sheet: ruled paper, red ticks and a circled score. */
function GradedSheet() {
  const rows = [
    { q: "Q1", w: "w-[78%]", tick: true, m: "4/4" },
    { q: "Q2", w: "w-[64%]", tick: true, m: "3/3" },
    { q: "Q3", w: "w-[86%]", tick: false, m: "2/5" },
    { q: "Q4", w: "w-[58%]", tick: true, m: "6/6" },
    { q: "Q5", w: "w-[72%]", tick: true, m: "5/6" },
  ];
  return (
    <div className="relative mx-auto w-full max-w-sm rotate-[-2.5deg]" aria-hidden>
      {/* sheet underneath */}
      <div className="absolute inset-0 translate-x-3 translate-y-3 rotate-[4deg] rounded-sm bg-surface/40" />
      <div className="ruled relative rounded-sm bg-surface px-6 pb-8 pl-14 pt-6 text-ink shadow-pop">
        <div className="mb-5 flex items-start justify-between">
          <div>
            <p className="font-display text-lg font-semibold">Answer Script</p>
            <p className="font-doc text-xs italic text-mute">Roll No. 24 · Mathematics</p>
          </div>
          <span className="pen-score text-2xl">
            20<small>/24</small>
          </span>
        </div>
        <ul className="space-y-[0.95rem]">
          {rows.map((r) => (
            <li key={r.q} className="flex items-center gap-3">
              <span className="w-6 font-display text-xs font-semibold text-pen">{r.q}</span>
              <span className={`h-[3px] rounded-full bg-pen/35 ${r.w}`} />
              <span className={`ml-auto font-doc text-sm font-semibold ${r.tick ? "text-mark" : "text-mark/80"}`}>
                {r.tick ? "✓" : "✗"} <span className="text-xs">{r.m}</span>
              </span>
            </li>
          ))}
        </ul>
        <span className="stamp absolute -bottom-3 right-6 animate-stamp border-ok/70 bg-surface px-2.5 py-1 text-ok">
          Verified
        </span>
      </div>
    </div>
  );
}

/** Where each role lands after signing in. */
export const homeFor = (role: string) => (role === "school_manager" ? "/school" : "/dashboard");

/** One sign-in for both: school management (who sign the school up) and the teachers they invite. */
export default function Login() {
  const { user, login, loginGoogle } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={(loc.state as { from?: string } | null)?.from ?? homeFor(user.role)} replace />;

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
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
        // a Google address with no account: school management can sign the school up with it
        if ((err as { code?: string }).code === "NEEDS_SIGNUP") { nav("/signup", { state: { idToken } }); return; }
        throw err;
      }
    });

  return (
    <div className="grid min-h-full lg:grid-cols-[1.05fr_1fr]">
      {/* Cover panel */}
      <section className="relative hidden flex-col justify-between overflow-hidden bg-cover p-12 text-cover-ink lg:flex">
        <div>
          <BrandLabel size="lg" />
        </div>
        <GradedSheet />
        <blockquote className="max-w-md">
          <p className="font-display text-2xl leading-snug text-white">
            Read every script. <span className="italic text-cover-ink/70">Mark it fairly.</span> Return it faster.
          </p>
          <p className="mt-3 text-xs uppercase tracking-[0.16em] text-cover-ink/50">
            Examination evaluation &amp; grading
          </p>
        </blockquote>
      </section>

      {/* Form */}
      <section className="desk flex items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-sm animate-rise">
          <div className="mb-8 lg:hidden">
            <BrandLabel onDark={false} />
            <p className="mt-2 text-xs uppercase tracking-[0.16em] text-mute">Examination evaluation &amp; grading</p>
          </div>

          <h1 className="font-display text-3xl font-semibold text-ink">
            Welcome to the <span className="hl">marking desk</span>
          </h1>
          <p className="mt-2 text-sm text-mute">School management and teachers sign in here.</p>

          <div className="mt-8">
            <GoogleButton onToken={google} />
          </div>
          <form onSubmit={submit} className="mt-4 space-y-5">
            <Field label="Email address">
              {(id) => (
                <Input
                  id={id}
                  type="email"
                  autoComplete="username"
                  required
                  placeholder="you@school.edu"
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
            <div className="-mt-2 text-right text-sm">
              <Link to="/forgot-password" className="text-pen hover:underline">Forgot password?</Link>
            </div>

            <ErrorPanel error={error} />

            <Button type="submit" variant="primary" busy={busy} className="w-full py-2.5">
              Sign in
            </Button>
          </form>

          <div className="mt-8 space-y-2 border-t border-dashed border-line pt-4 text-sm text-mute">
            <p>
              New school? <Link to="/signup" className="text-pen hover:underline">Register your school</Link>
            </p>
            <p className="text-xs">Teachers: your school management sends you an invitation by email.</p>
          </div>
        </div>
      </section>
    </div>
  );
}
