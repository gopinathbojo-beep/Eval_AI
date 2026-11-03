import { useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/Auth";
import { api } from "../api/client";
import { ErrorPanel, Modal, Spinner } from "../components/ui";
import { BrandLabel } from "../components/Brand";
import {
  IconArrowRight,
  IconEye,
  IconEyeOff,
  IconLock,
  IconLogIn,
  IconMail,
  IconShield,
  IconX,
} from "../components/Icons";
import { useApi } from "../hooks/useApi";
import { emailProblem } from "../utils/validation";
import loginMortarboard from "../assets/login-mortarboard.png";

const oauthErrors: Record<string, string> = {
  not_allowed:
    "This Google account does not have access. Ask the administrator to add or enable your email address.",
  failed: "Google sign-in could not be completed. Please try again.",
  unavailable:
    "Google sign-in is temporarily unavailable. Try email and password instead.",
  not_configured:
    "Google sign-in has not been configured yet. Use email and password.",
};

/** The Google "G" mark in its authentic brand colours. */
function GoogleLogo() {
  return (
    <svg aria-hidden width="18" height="18" viewBox="0 0 48 48" className="shrink-0">
      <path
        fill="#FFC107"
        d="M43.611 20.083H42V20H24v8h11.303c-1.649 4.657-6.08 8-11.303 8-6.627 0-12-5.373-12-12s5.373-12 12-12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 12.955 4 4 12.955 4 24s8.955 20 20 20 20-8.955 20-20c0-1.341-.138-2.65-.389-3.917z"
      />
      <path
        fill="#FF3D00"
        d="M6.306 14.691l6.571 4.819C14.655 15.108 18.961 12 24 12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 16.318 4 9.656 8.337 6.306 14.691z"
      />
      <path
        fill="#4CAF50"
        d="M24 44c5.166 0 9.86-1.977 13.409-5.192l-6.19-5.238A11.91 11.91 0 0 1 24 36c-5.202 0-9.619-3.317-11.283-7.946l-6.522 5.025C9.505 39.556 16.227 44 24 44z"
      />
      <path
        fill="#1976D2"
        d="M43.611 20.083H42V20H24v8h11.303a12.04 12.04 0 0 1-4.087 5.571l.003-.002 6.19 5.238C36.971 39.205 44 34 44 24c0-1.341-.138-2.65-.389-3.917z"
      />
    </svg>
  );
}

/** Four-point twinkling star placed around the mortarboard. */
function Sparkle({ className, delay }: { className: string; delay: string }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      className={`animate-twinkle pointer-events-none absolute text-blue-600 ${className}`}
      style={{ animationDelay: delay }}
    >
      <path fill="currentColor" d="M12 0c.6 6.2 5.8 11.4 12 12-6.2.6-11.4 5.8-12 12-.6-6.2-5.8-11.4-12-12C6.2 11.4 11.4 6.2 12 0z" />
    </svg>
  );
}

/** Uploaders sign in with the 6-character code created for an exam to upload answer sheets only. */
function UploaderLogin({ onClose }: { onClose: () => void }) {
  const nav = useNavigate();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!/^[A-Z0-9]{6}$/.test(code))
      return setError(new Error("The uploader code has 6 letters and digits."));
    setBusy(true);
    setError(null);
    try {
      await api("/auth/code-login", { method: "POST", json: { code } });
      nav("/upload");
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="uploader-login-title"
      onKeyDown={(e) => e.key === "Escape" && onClose()}
    >
      <div
        className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm animate-fadeIn"
        onClick={onClose}
        aria-hidden
      />
      <div className="relative w-full max-w-md animate-rise overflow-hidden rounded-3xl border border-white/60 bg-white/95 p-8 shadow-2xl backdrop-blur-xl">
        <div className="flex items-center justify-between border-b border-slate-100 pb-4">
          <h2 id="uploader-login-title" className="text-xl font-bold text-slate-900">
            Exam Uploader Login
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-full p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors"
          >
            <IconX size={20} />
          </button>
        </div>
        <form onSubmit={submit} className="mt-6 space-y-4">
          <p className="text-sm text-slate-600">
            Enter the 6-character access code provided by your institution for this exam.
          </p>
          <input
            autoFocus
            autoComplete="off"
            spellCheck={false}
            maxLength={6}
            placeholder="ABC234"
            value={code}
            onChange={(e) =>
              setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ""))
            }
            className="h-14 w-full rounded-2xl border border-blue-200 bg-blue-50/40 text-center font-mono text-2xl font-bold tracking-[0.4em] text-slate-800 placeholder:text-slate-300 focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-4 focus:ring-blue-500/15 transition-all"
          />
          <ErrorPanel error={error} />
          <button
            type="submit"
            disabled={busy || code.length !== 6}
            className="w-full rounded-full aurora-fill py-3 text-sm font-bold text-white shadow-md shadow-blue-500/25 transition-all hover:from-blue-700 hover:to-indigo-700 disabled:opacity-50 cursor-pointer"
          >
            {busy ? "Checking code..." : "Continue to Upload"}
          </button>
          <p className="text-center text-xs text-slate-500">
            You will only have access to upload sheets for the assigned exam.
          </p>
        </form>
      </div>
    </div>,
    document.body
  );
}

export default function Login() {
  const { teacher, login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [uploaderOpen, setUploaderOpen] = useState(false);
  const [forgotOpen, setForgotOpen] = useState(false);

  const { data: providers } = useApi<{
    google: boolean;
    google_start_url: string;
  }>("/auth/providers");

  const oauthError = new URLSearchParams(loc.search).get("oauth_error");

  const from = (loc.state as { from?: unknown } | null)?.from;
  const destination =
    typeof from === "string" &&
    from.startsWith("/") &&
    !from.startsWith("//") &&
    !from.includes("\\") &&
    from !== "/login"
      ? from
      : teacher?.is_admin
        ? "/admin"
        : "/dashboard";

  if (teacher)
    return (
      <Navigate
        to={
          !teacher.is_admin && !teacher.profile_complete
              ? "/onboarding"
              : destination
        }
        replace
      />
    );

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const problem = emailProblem(email) ?? (password ? null : "Enter your password.");
    if (problem) {
      setError(new Error(problem));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const user = await login(email, password);
      nav(
        !user.is_admin && !user.profile_complete
            ? "/onboarding"
            : destination === "/dashboard" && user.is_admin
              ? "/admin"
              : destination,
        { replace: true }
      );
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };

  return (
    <div className="app-shell app-bg relative flex min-h-screen w-full flex-col items-center justify-center p-4 sm:p-6 overflow-hidden select-none">
      {/* Same brand as the dashboard sidebar */}
      <Link to="/" aria-label="Eval AI home" className="absolute left-6 top-5">
        <BrandLabel onDark={false} />
      </Link>

      {/* Sign-in card: the dashboard's glass panel */}
      <div className="glass-canvas login-card relative w-full max-w-[430px] animate-rise p-7 sm:p-9">
        {/* 3D Mortarboard & Book Illustration */}
        <div className="relative flex justify-center">
          <Sparkle className="left-[22%] top-8 h-5 w-5" delay="0s" />
          <Sparkle className="left-[27%] top-[4.5rem] h-2.5 w-2.5" delay="1.1s" />
          <Sparkle className="right-[22%] top-10 h-5 w-5" delay="0.6s" />
          <Sparkle className="right-[27%] top-2 h-2.5 w-2.5" delay="1.7s" />
          <img
            src={loginMortarboard}
            alt="Eval AI"
            className="animate-bob h-32 w-auto object-contain drop-shadow-md select-none pointer-events-none"
          />
        </div>

        {/* Heading & Subtitle */}
        <div className="mt-2 text-center">
          <h1 className="text-2xl font-extrabold tracking-tight text-blue-950 sm:text-[1.75rem]">
            <span className="aurora-text">Sign in</span> to your account
          </h1>
          <p className="mt-1 text-xs sm:text-sm font-medium text-blue-800/80">
            Continue your journey with Eval AI
          </p>
        </div>

        {oauthError && (
          <div
            role="alert"
            className="mt-4 rounded-xl bg-rose-50 border border-rose-200/80 p-3 text-xs font-medium text-rose-600"
          >
            {oauthErrors[oauthError] ?? oauthErrors.failed}
          </div>
        )}

        {/* Sign In Form */}
        <form onSubmit={submit} className="mt-6 space-y-4">
          {/* Email Field */}
          <div className="relative flex items-center rounded-xl border border-slate-200 bg-white shadow-xs transition-all duration-150 hover:border-slate-300 focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-100">
            <span className="pointer-events-none absolute left-4 text-blue-600">
              <IconMail size={19} />
            </span>
            <input
              type="email"
              autoComplete="username"
              required
              placeholder="Email address"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-transparent py-3.5 pl-12 pr-4 text-sm font-medium text-slate-800 placeholder:text-slate-400 focus:outline-none"
            />
          </div>

          {/* Password Field */}
          <div className="relative flex items-center rounded-xl border border-slate-200 bg-white shadow-xs transition-all duration-150 hover:border-slate-300 focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-100">
            <span className="pointer-events-none absolute left-4 text-blue-600">
              <IconLock size={19} />
            </span>
            <input
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              required
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-transparent py-3.5 pl-12 pr-12 text-sm font-medium text-slate-800 placeholder:text-slate-400 focus:outline-none"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              aria-label={showPassword ? "Hide password" : "Show password"}
              className="absolute right-3.5 rounded-lg p-1 text-slate-400 hover:text-slate-600 transition-colors focus:outline-none cursor-pointer"
            >
              {showPassword ? <IconEyeOff size={18} /> : <IconEye size={18} />}
            </button>
          </div>

          {/* Options Row: Remember me & Forgot password */}
          <div className="flex items-center justify-between pt-0.5 text-xs font-semibold text-slate-600">
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-blue-600 accent-blue-600 focus:ring-blue-500 cursor-pointer"
              />
              <span>Remember me</span>
            </label>
            <button
              type="button"
              onClick={() => setForgotOpen(true)}
              className="text-blue-600 hover:text-blue-700 hover:underline cursor-pointer"
            >
              Forgot password?
            </button>
          </div>

          <ErrorPanel error={error} />

          {/* Primary Gradient Sign In Button */}
          <button
            type="submit"
            disabled={busy}
            className="shine group relative flex w-full items-center justify-center rounded-full aurora-fill py-3.5 px-6 text-sm font-bold text-white shadow-md shadow-indigo-500/25 transition-all duration-200 hover:shadow-indigo-500/40 active:scale-[0.98] disabled:opacity-60 cursor-pointer"
          >
            {busy ? (
              <Spinner size={18} />
            ) : (
              <div className="relative z-10 flex items-center gap-2">
                <IconLogIn size={18} />
                <span>Sign in</span>
              </div>
            )}
            <span
              aria-hidden
              className="absolute right-2 top-1/2 z-10 -translate-y-1/2 flex h-8 w-8 items-center justify-center rounded-full text-blue-600 shadow-sm transition-transform group-hover:translate-x-0.5"
              style={{ backgroundColor: "#fff" }}
            >
              <IconArrowRight size={15} />
            </span>
          </button>
        </form>

        {/* Divider */}
        <div className="my-5 flex items-center gap-3 text-xs font-medium text-slate-400">
          <span className="h-px flex-1 border-t border-slate-200" />
          <span>or</span>
          <span className="h-px flex-1 border-t border-slate-200" />
        </div>

        {/* Google Sign In */}
        <div>
          {providers?.google ? (
            <a
              href={providers.google_start_url}
              className="flex w-full items-center justify-center gap-2.5 rounded-full border border-slate-200/90 bg-white py-3 px-5 text-sm font-semibold text-slate-700 shadow-xs transition-all duration-150 hover:bg-slate-50 hover:border-slate-300 active:scale-[0.98] cursor-pointer"
            >
              <GoogleLogo />
              <span>Continue with Google</span>
            </a>
          ) : (
            <button
              type="button"
              disabled
              title={providers ? "Google sign-in is not configured." : "Checking Google sign-in..."}
              className="flex w-full items-center justify-center gap-2.5 rounded-full border border-slate-200/90 bg-white py-3 px-5 text-sm font-semibold text-slate-400 shadow-xs opacity-75 cursor-not-allowed"
            >
              <GoogleLogo />
              <span>Continue with Google</span>
            </button>
          )}
        </div>

        {/* Footer Notice matching reference image */}
        <div className="mt-6 flex items-center justify-center gap-1.5 text-center text-[11px] font-medium text-slate-500">
          <IconShield size={14} className="shrink-0 text-blue-600" />
          <span>Accounts are managed by your institution administrator.</span>
        </div>

        {/* Secondary options (Register school & Uploader code) */}
        <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3 text-xs text-slate-500">
          <Link
            to="/register"
            className="font-semibold text-blue-600 hover:underline"
          >
            Register your school
          </Link>
          <button
            type="button"
            onClick={() => setUploaderOpen(true)}
            className="font-medium text-slate-500 hover:text-slate-700 hover:underline cursor-pointer"
          >
            Exam uploader code
          </button>
        </div>
      </div>

      {/* Forgot Password Dialog */}
      {forgotOpen && (
        <Modal title="Forgot your password?" onClose={() => setForgotOpen(false)}>
          <div className="space-y-4 text-sm text-slate-600">
            <p>
              For security reasons in educational institutions, password resets are handled directly by your school or institution administrator.
            </p>
            <p>
              Please contact your exam coordinator or IT administrator to reset your credentials. If you are a school administrator who forgot your password, use the server recovery console.
            </p>
            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={() => setForgotOpen(false)}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-700"
              >
                Understood
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Uploader Code Login Modal */}
      {uploaderOpen && <UploaderLogin onClose={() => setUploaderOpen(false)} />}
    </div>
  );
}
