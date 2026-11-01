import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { BrandLabel } from "./Brand";
import { useAuth } from "../context/Auth";
import { Button, ErrorPanel } from "./ui";

export interface ChatStep {
  key: string;
  label: string;
  question: string;
  hint?: string;
  type?: "text" | "email" | "password" | "tel";
  autoComplete?: string;
  maxLength?: number;
  optional?: boolean;
  choices?: { value: string; label: string; description?: string }[];
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
}: Props) {
  const { teacher, logout } = useAuth();
  const [index, setIndex] = useState(0);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const step = steps[index];
  const review = index >= steps.length;
  useEffect(() => {
    setDraft(step ? (values[step.key] ?? "") : "");
    input.current?.focus();
    bottom.current?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
    // Load an answer only when the active question changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, step?.key]);

  const answer = (value: string) => {
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
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  const display = (item: ChatStep) =>
    item.type === "password"
      ? "Password entered securely"
      : item.choices?.find((c) => c.value === values[item.key])?.label ||
        values[item.key] ||
        "Skipped";

  return (
    <main className="desk min-h-screen p-3 sm:p-6">
      <header className="mx-auto flex max-w-6xl items-center justify-between gap-4 py-3">
        <Link to="/" aria-label="Eval AI home">
          <BrandLabel onDark={false} />
        </Link>
        {teacher ? (
          <Button onClick={logout} variant="ghost">
            Sign out
          </Button>
        ) : (
          <Link
            to="/login"
            className="text-sm font-semibold text-pen hover:underline"
          >
            Login
          </Link>
        )}
      </header>
      <div className="mx-auto mt-5 grid max-w-6xl gap-8 lg:grid-cols-[0.7fr_1.3fr] lg:gap-14">
        <aside className="py-3 lg:py-12">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-pen">
            Your first step with Eval AI
          </p>
          <h1 className="mt-4 font-display text-3xl font-semibold leading-tight sm:text-4xl">
            {title}
          </h1>
          <p className="mt-4 max-w-sm text-sm leading-relaxed text-mute">
            {intro}
          </p>
          <div className="mt-7 max-w-sm">
            <div className="mb-2 flex justify-between text-xs text-mute">
              <span>
                {review ? "Ready to continue" : "Let’s get to know you"}
              </span>
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
          <p className="mt-7 hidden max-w-xs text-xs leading-relaxed text-mute lg:block">
            Made for CBSE Classes 10 and 12. Teachers use the login provided by
            their school.
          </p>
        </aside>
        <section
          aria-label="Registration conversation"
          className="flex h-[min(720px,78dvh)] min-h-[460px] flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-card"
        >
          <div className="flex items-center gap-3 border-b border-line px-5 py-4">
            <span
              aria-hidden
              className="flex h-10 w-10 items-center justify-center rounded-xl bg-pen text-sm font-semibold text-on-pen"
            >
              E
            </span>
            <div>
              <p className="text-sm font-semibold">Eval AI setup guide</p>
              <p className="text-xs text-mute">
                A few questions. One at a time.
              </p>
            </div>
          </div>
          <div className="flex-1 space-y-5 overflow-y-auto p-4 sm:p-6">
            <p className="max-w-[92%] rounded-2xl rounded-tl-sm bg-sunken px-4 py-3 text-sm leading-relaxed">
              Hi! Welcome to Eval AI. I’ll help you set up your workspace. You
              can go back and edit any answer.
            </p>
            {steps.slice(0, index).map((item) => (
              <div key={item.key} className="space-y-2">
                <p className="max-w-[92%] rounded-2xl rounded-tl-sm bg-sunken px-4 py-3 text-sm">
                  {item.question}
                </p>
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
            <div
              aria-live="polite"
              aria-atomic="true"
              className="rounded-2xl rounded-tl-sm bg-sunken px-4 py-3 text-sm leading-relaxed"
            >
              {review ? (
                "Everything looks ready. Review your answers above, then continue when you’re happy."
              ) : (
                <>
                  <p id="chat-question">{step.question}</p>
                  {step.hint && (
                    <p id="chat-hint" className="mt-2 text-xs text-mute">
                      {step.hint}
                    </p>
                  )}
                </>
              )}
            </div>
            <div ref={bottom} />
          </div>
          <form
            onSubmit={submit}
            className="space-y-3 border-t border-line p-4 sm:p-5"
          >
            <ErrorPanel error={error} />
            {review ? (
              <Button
                type="submit"
                variant="primary"
                busy={busy}
                className="w-full py-3"
              >
                {submitLabel}
              </Button>
            ) : step.choices ? (
              <div className="grid gap-3 sm:grid-cols-2">
                {step.choices.map((choice) => (
                  <button
                    key={choice.value}
                    type="button"
                    onClick={() => answer(choice.value)}
                    className="rounded-xl border border-line p-4 text-left transition-colors hover:border-pen hover:bg-pen-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-pen"
                  >
                    <span className="block text-sm font-semibold">
                      {choice.label}
                    </span>
                    {choice.description && (
                      <span className="mt-1 block text-xs leading-relaxed text-mute">
                        {choice.description}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            ) : (
              <div className="flex gap-2">
                <input
                  ref={input}
                  key={step.key}
                  aria-labelledby="chat-question"
                  aria-describedby={step.hint ? "chat-hint" : undefined}
                  type={step.type ?? "text"}
                  autoComplete={step.autoComplete ?? "off"}
                  maxLength={step.maxLength ?? 200}
                  required={!step.optional}
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  placeholder={
                    step.type === "password"
                      ? "Enter securely…"
                      : "Type your answer…"
                  }
                  className="min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 py-3 text-sm text-ink outline-none focus:border-pen focus:ring-2 focus:ring-pen/20"
                />
                <Button type="submit" variant="primary">
                  Send
                </Button>
              </div>
            )}
            <div className="flex items-center justify-between gap-3 text-xs text-mute">
              {index > 0 ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    setIndex(index - 1);
                    setError(null);
                  }}
                  className="text-pen hover:underline"
                >
                  Back
                </button>
              ) : (
                <span>Choose an option to begin</span>
              )}
              {!review && step.optional && (
                <button
                  type="button"
                  onClick={() => answer("")}
                  className="text-pen hover:underline"
                >
                  Skip for now
                </button>
              )}
              {!review && step.type === "password" && (
                <span>Your password is hidden from this conversation.</span>
              )}
            </div>
            {googleUrl && index === 1 && (
              <a
                href={googleUrl}
                className="block border-t border-line pt-3 text-center text-sm font-semibold text-pen hover:underline"
              >
                Continue with Google instead
              </a>
            )}
          </form>
        </section>
      </div>
    </main>
  );
}
