import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/Auth";
import { Button, ErrorPanel, Field, Input } from "../components/ui";
import { BrandLabel } from "../components/Brand";
<<<<<<< 7c662e7:frontend/web/src/pages/Login.tsx
import { GoogleButton } from "../components/GoogleButton";
=======
import { useApi } from "../hooks/useApi";

const oauthErrors: Record<string, string> = {
  not_allowed: "This Google account does not have access. Ask the administrator to add or enable your email address.",
  failed: "Google sign-in could not be completed. Please try again.",
  unavailable: "Google sign-in is temporarily unavailable. Try email and password instead.",
  not_configured: "Google sign-in has not been configured yet. Use email and password.",
};
>>>>>>> kishore/Version2.0:frontend/src/pages/Login.tsx

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
  const { data: providers } = useApi<{ google: boolean; google_start_url: string }>("/auth/providers");
  const oauthError = new URLSearchParams(loc.search).get("oauth_error");

<<<<<<< 7c662e7:frontend/web/src/pages/Login.tsx
  if (user) return <Navigate to={(loc.state as { from?: string } | null)?.from ?? homeFor(user.role)} replace />;
=======
  const from = (loc.state as { from?: unknown } | null)?.from;
  const destination = typeof from === "string" && from.startsWith("/") && !from.startsWith("//") && !from.includes("\\") && from !== "/login"
    ? from : teacher?.is_admin ? "/admin" : "/dashboard";
  if (teacher) return <Navigate to={teacher.must_change_password ? "/account" : !teacher.is_admin && !teacher.profile_complete ? "/onboarding" : destination} replace />;
>>>>>>> kishore/Version2.0:frontend/src/pages/Login.tsx

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
<<<<<<< 7c662e7:frontend/web/src/pages/Login.tsx
      await fn();
=======
      const user = await login(email, password);
      nav(user.must_change_password ? "/account" : !user.is_admin && !user.profile_complete ? "/onboarding" : destination === "/dashboard" && user.is_admin ? "/admin" : destination, { replace: true });
>>>>>>> kishore/Version2.0:frontend/src/pages/Login.tsx
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

<<<<<<< 7c662e7:frontend/web/src/pages/Login.tsx
          <div className="mt-8">
            <GoogleButton onToken={google} />
          </div>
          <form onSubmit={submit} className="mt-4 space-y-5">
=======
          {oauthError && <p role="alert" className="mt-4 rounded-md bg-mark-soft p-3 text-sm text-mark">{oauthErrors[oauthError] ?? oauthErrors.failed}</p>}
          {providers?.google && (
            <div className="mt-6">
              <a className="flex w-full items-center justify-center gap-3 rounded-md border border-line bg-surface px-4 py-2.5 text-sm font-medium text-ink hover:bg-hover" href={providers.google_start_url}>
                <span aria-hidden className="font-bold text-pen">G</span> Continue with Google
              </a>
              <p className="mt-4 text-center text-xs text-mute">or sign in with email and password</p>
            </div>
          )}

          <form onSubmit={submit} className="mt-8 space-y-5">
>>>>>>> kishore/Version2.0:frontend/src/pages/Login.tsx
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

<<<<<<< 7c662e7:frontend/web/src/pages/Login.tsx
          <div className="mt-8 space-y-2 border-t border-dashed border-line pt-4 text-sm text-mute">
            <p>
              New school? <Link to="/signup" className="text-pen hover:underline">Register your school</Link>
            </p>
            <p className="text-xs">Teachers: your school management sends you an invitation by email.</p>
          </div>
=======
          <p className="mt-8 border-t border-dashed border-line pt-4 text-xs text-mute">
            New to Eval AI? <Link to="/register" className="font-semibold text-pen underline">Register your school or family</Link>.
          </p>
>>>>>>> kishore/Version2.0:frontend/src/pages/Login.tsx
        </div>
      </section>
    </div>
  );
}
