import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { BrandLabel } from "./Brand";
import { useAuth } from "../context/Auth";
import { Button, ErrorPanel, PasswordChecklist } from "./ui";
import { IconEye, IconEyeOff } from "./Icons";

export interface ChatField {
  key: string;
  label: string;
  placeholder?: string;
  autoComplete?: string;
  maxLength?: number;
  inputMode?: "text" | "numeric";
  /** grid span on wider screens */
  wide?: boolean;
}

export interface ChatStep {
  key: string;
  label: string;
  question: string;
  hint?: string;
  type?: "text" | "email" | "password" | "tel" | "number";
  autoComplete?: string;
  maxLength?: number;
  optional?: boolean;
  choices?: { value: string; label: string; description?: string }[];
  /** several inputs answered together in one card (e.g. a structured address); each is saved under its own key */
  fields?: ChatField[];
  /** the text shown as the user's answer for a fields step */
  format?: (values: Record<string, string>) => string;
  submitText?: string;
  /** heading of a fields card, e.g. "School address details" */
  cardTitle?: string;
  /** a line under the card heading, e.g. where pre-filled values came from */
  cardNote?: string;
  /** runs after the answer is accepted and before the next question (e.g. a lookup that pre-fills later steps) */
  onAnswered?(value: string): Promise<void>;
  /** shown while onAnswered runs */
  busyText?: string;
}

interface Props {
  steps: ChatStep[];
  values: Record<string, string>;
  onAnswer(key: string, value: string): void;
  onSubmit(): Promise<void>;
  validate?(key: string, value: string): string | undefined;
  title: string;
  intro: string;
  submitLabel: string;
  googleUrl?: string;
  welcome?: string;
  reviewText?: string;
}

export default function RegistrationChat({
  steps,
  values,
  onAnswer,
  onSubmit,
  validate,
  title,
  intro,
  submitLabel,
  googleUrl,
  welcome = "Hi! Welcome to Eval AI. I’ll help you set up your workspace. You can go back and edit any answer.",
  reviewText = "Everything looks ready. Review your answers above, then continue when you’re happy.",
}: Props) {
  const { teacher, logout } = useAuth();
  const [index, setIndex] = useState(0);
  const [draft, setDraft] = useState("");
  const [fieldDraft, setFieldDraft] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const card = useRef<HTMLFormElement>(null);
  const step = steps[index];
  const review = index >= steps.length;
  useEffect(() => {
    setDraft(step ? (values[step.key] ?? "") : "");
    setFieldDraft(Object.fromEntries((step?.fields ?? []).map((f) => [f.key, values[f.key] ?? ""])));
    if (step?.fields) card.current?.querySelector("input")?.focus();
    else input.current?.focus();
    bottom.current?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
    // Load an answer only when the active question changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, step?.key]);

  const answer = async (value: string) => {
    if (!step || busy) return;
    const clean = step.type === "password" ? value : value.trim();
    if (!clean && !step.optional) {
      setError(new Error("Please enter an answer to continue."));
      return;
    }
    const message = validate?.(step.key, clean);
    if (message) {
      setError(new Error(message));
      return;
    }
    onAnswer(step.key, clean);
    setError(null);
    if (step.onAnswered) {
      setBusy(true);
      try {
        await step.onAnswered(clean);
      } finally {
        setBusy(false);
      }
    }
    setIndex(index + 1);
  };
  const answerFields = (event: FormEvent) => {
    event.preventDefault();
    if (!step?.fields || busy) return;
    const clean = Object.fromEntries(step.fields.map((f) => [f.key, (fieldDraft[f.key] ?? "").trim()]));
    const missing = step.fields.find((f) => !clean[f.key]);
    if (missing) {
      setError(new Error(`Please enter the ${missing.label.toLowerCase()}.`));
      return;
    }
    for (const f of step.fields) {
      const message = validate?.(f.key, clean[f.key]!);
      if (message) {
        setError(new Error(message));
        return;
      }
    }
    Object.entries(clean).forEach(([k, v]) => onAnswer(k, v));
    onAnswer(step.key, step.format ? step.format({ ...values, ...clean }) : Object.values(clean).join(", "));
    setError(null);
    setIndex(index + 1);
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!review) {
      answer(draft);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSubmit();
    } catch (e) {
      setError(e); // every answer stays; the button retries
    } finally {
      setBusy(false);
    }
  };
  const display = (item: ChatStep) =>
    item.type === "password"
      ? "Password entered securely"
      : item.format
        ? item.format(values)
        : item.choices?.find((c) => c.value === values[item.key])?.label ||
          values[item.key] ||
          "Skipped";

  return (
    <main className="app-shell app-bg min-h-screen p-3 sm:p-6">
      <header className="mx-auto flex max-w-3xl items-center justify-between gap-4 py-3">
        <Link to="/" aria-label="Eval AI home">
          <BrandLabel onDark={false} />
        </Link>
        <div className="flex items-center gap-3">
          {teacher ? (
            <Button onClick={logout} variant="ghost">
              Sign out
            </Button>
          ) : (
            <Link to="/login" className="text-sm font-semibold text-pen hover:underline">
              Login
            </Link>
          )}
        </div>
      </header>

      {/* Introduction section moved to top of the page */}
      <div className="mx-auto mt-4 mb-6 max-w-2xl text-center sm:mt-6 sm:mb-8">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-pen">
          Your first step with Eval AI
        </p>
        <h1 className="aurora-text mt-3 font-display text-3xl font-semibold leading-tight sm:text-4xl">
          {title}
        </h1>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-relaxed text-mute">
          {intro}
        </p>
        <p className="mt-2 text-xs text-mute">
          Made for CBSE Classes 10 and 12.
        </p>
      </div>

      {/* Continuous unified layout */}
      <div className="mx-auto max-w-3xl pb-10">
        <section
          aria-label="Registration conversation"
          className="flex h-[min(720px,80dvh)] min-h-[460px] flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-card"
        >
          <div className="flex items-center gap-3 border-b border-line px-5 py-4">
            <span aria-hidden className="flex h-10 w-10 items-center justify-center rounded-xl bg-pen text-sm font-semibold text-on-pen">
              E
            </span>
            <div>
              <p className="text-sm font-semibold">Eval AI setup guide</p>
              <p className="text-xs text-mute">A few questions. One at a time.</p>
            </div>
          </div>
          <div className="flex-1 space-y-5 overflow-y-auto p-4 sm:p-6">
            <p className="max-w-[92%] rounded-2xl rounded-tl-sm bg-sunken px-4 py-3 text-sm leading-relaxed">{welcome}</p>
            {steps.slice(0, index).map((item) => (
              <div key={item.key} className="space-y-2">
                <p className="max-w-[92%] rounded-2xl rounded-tl-sm bg-sunken px-4 py-3 text-sm">{item.question}</p>
                <div className="ml-auto flex max-w-[90%] items-start justify-end gap-2">
                  <p className="whitespace-pre-wrap break-words rounded-2xl rounded-tr-sm bg-pen px-4 py-3 text-sm text-on-pen">
                    {display(item)}
                  </p>
                  <button
                    type="button"
                    disabled={busy}
                    aria-label={`Edit ${item.label}`}
                    onClick={() => {
                      setIndex(steps.indexOf(item));
                      setError(null);
                    }}
                    className="py-3 text-xs text-pen hover:underline disabled:opacity-50"
                  >
                    Edit
                  </button>
                </div>
              </div>
            ))}
            <div aria-live="polite" aria-atomic="true" className="rounded-2xl rounded-tl-sm bg-sunken px-4 py-3 text-sm leading-relaxed">
              {review ? (
                reviewText
              ) : (
                <>
                  <p id="chat-question">{step!.question}</p>
                  {step!.hint && (
                    <p id="chat-hint" className="mt-2 text-xs text-mute">
                      {step!.hint}
                    </p>
                  )}
                  {busy && step!.busyText && <p className="mt-2 text-xs font-semibold text-pen">{step!.busyText}</p>}
                </>
              )}
            </div>
            {!review && step!.fields && (
              <form
                ref={card}
                onSubmit={answerFields}
                aria-label={step!.label}
                noValidate
                className="max-w-xl rounded-2xl border border-line bg-surface p-4 shadow-sm sm:p-5"
              >
                {step!.cardTitle && (
                  <div className="mb-4 flex items-center justify-between gap-3 border-b border-line pb-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.12em] text-pen">{step!.cardTitle}</p>
                    <p className="text-xs text-mute">All fields required</p>
                  </div>
                )}
                {step!.cardNote && <p className="mb-4 text-xs leading-relaxed text-mute">{step!.cardNote}</p>}
                <div className="grid gap-3 sm:grid-cols-2">
                  {step!.fields.map((f) => (
                    <label key={f.key} className={`block text-xs font-semibold text-ink ${f.wide ? "sm:col-span-2" : ""}`}>
                      {f.label} <span className="text-mark">*</span>
                      <input
                        required
                        autoComplete={f.autoComplete ?? "off"}
                        inputMode={f.inputMode}
                        maxLength={f.maxLength ?? 200}
                        placeholder={f.placeholder}
                        value={fieldDraft[f.key] ?? ""}
                        onChange={(e) => setFieldDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                        className="mt-1.5 w-full rounded-lg border border-line bg-sunken/40 px-3 py-2.5 text-sm font-normal text-ink outline-none placeholder:text-mute/70 focus:border-pen focus:bg-surface focus:ring-2 focus:ring-pen/20"
                      />
                    </label>
                  ))}
                </div>
                <div className="mt-5 flex justify-end">
                  <Button type="submit" variant="primary" className="w-full sm:w-auto">
                    {step!.submitText ?? "Submit"}
                  </Button>
                </div>
              </form>
            )}
            <div ref={bottom} />
          </div>
          <form onSubmit={submit} noValidate className="space-y-4 border-t border-line p-4 sm:p-5">
            <ErrorPanel error={error} />
            {review ? (
              <p className="text-xs text-mute">
                Review your answers above. When you’re ready, continue to finish setup.
              </p>
            ) : step!.fields ? (
              <p className="text-xs text-mute">
                Please fill in the {step!.cardTitle?.toLowerCase() ?? "fields"} above and click {step!.submitText ?? "Submit"}.
              </p>
            ) : step!.choices ? (
              <div className="grid gap-3 sm:grid-cols-2">
                {step!.choices.map((choice) => (
                  <button
                    key={choice.value}
                    type="button"
                    onClick={() => answer(choice.value)}
                    className="rounded-xl border border-line p-4 text-left transition-colors hover:border-pen hover:bg-pen-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-pen"
                  >
                    <span className="block text-sm font-semibold">{choice.label}</span>
                    {choice.description && (
                      <span className="mt-1 block text-xs leading-relaxed text-mute">{choice.description}</span>
                    )}
                  </button>
                ))}
              </div>
            ) : (
              <div className="space-y-2">
                <div className="relative">
                  <input
                    ref={input}
                    key={step!.key}
                    aria-labelledby="chat-question"
                    aria-describedby={step!.hint ? "chat-hint" : undefined}
                    type={step!.type === "password" ? (showPassword ? "text" : "password") : (step!.type ?? "text")}
                    inputMode={step!.type === "number" ? "numeric" : undefined}
                    autoComplete={step!.autoComplete ?? "off"}
                    maxLength={step!.maxLength ?? 200}
                    required={!step!.optional}
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    placeholder={step!.type === "password" ? "Enter securely…" : "Type your answer…"}
                    className={`w-full rounded-lg border border-line bg-surface px-3 py-3 text-sm text-ink outline-none focus:border-pen focus:ring-2 focus:ring-pen/20 ${
                      step!.type === "password" ? "pr-11" : ""
                    }`}
                  />
                  {step!.type === "password" && (
                    <button
                      type="button"
                      onClick={() => setShowPassword((s) => !s)}
                      aria-label={showPassword ? "Hide password" : "Show password"}
                      className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-slate-400 hover:text-slate-600 cursor-pointer"
                    >
                      {showPassword ? <IconEyeOff size={18} /> : <IconEye size={18} />}
                    </button>
                  )}
                </div>
                {step!.type === "password" && step!.key === "password" && (
                  <PasswordChecklist value={draft} />
                )}
              </div>
            )}

            {/* Red-circled progress section: step description, step count, and progress bar */}
            {/* Placed below input fields and above action buttons */}
            <div className="pt-1">
              <div className="mb-2 flex justify-between text-xs text-mute">
                <span>{review ? "Ready to continue" : "Let’s get to know you"}</span>
                <span>
                  {Math.min(index, steps.length)} / {steps.length}
                </span>
              </div>
              <div
                role="progressbar"
                aria-label="Registration progress"
                aria-valuenow={Math.min(index, steps.length)}
                aria-valuemin={0}
                aria-valuemax={steps.length}
                className="h-1.5 overflow-hidden rounded-full bg-line"
              >
                <div
                  className="h-full rounded-full bg-pen transition-all"
                  style={{ width: `${(index / steps.length) * 100}%` }}
                />
              </div>
            </div>

            {/* Action buttons: Back on left, Skip and Send/Submit on right */}
            <div className="flex items-center justify-between gap-3 pt-1 text-xs text-mute">
              {index > 0 ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    setIndex(index - 1);
                    setError(null);
                  }}
                  className="text-pen hover:underline disabled:opacity-50 font-medium"
                >
                  ← Back
                </button>
              ) : (
                <span>{step?.choices ? "Choose an option to begin" : "Answer to begin"}</span>
              )}

              <div className="flex items-center gap-2">
                {!review && step!.optional && (
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={busy}
                    onClick={() => answer("")}
                    className="cursor-pointer"
                  >
                    Skip
                  </Button>
                )}

                {review ? (
                  <Button type="submit" variant="primary" busy={busy} className="py-2.5 px-6">
                    {error ? "Try again" : submitLabel}
                  </Button>
                ) : !step!.fields && !step!.choices ? (
                  <Button type="submit" variant="primary" busy={busy} className="py-2.5 px-6">
                    Send
                  </Button>
                ) : null}
              </div>
            </div>

            {googleUrl && index === 1 && (
              <a href={googleUrl} className="block border-t border-line pt-3 text-center text-sm font-semibold text-pen hover:underline">
                Continue with Google instead
              </a>
            )}
          </form>
        </section>
      </div>
    </main>
  );
}
