import {
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { ApiError } from "../api/client";
import { label, toneOf, type Tone } from "../utils/format";
import { IconAlertCircle, IconAlertTriangle, IconX } from "./Icons";

const toneCls: Record<Tone, { badge: string; dot: string }> = {
  ok: { badge: "bg-ok-soft text-ok border-ok/20", dot: "bg-ok" },
  warn: { badge: "bg-warn-soft text-warn border-warn/25", dot: "bg-warn" },
  mark: { badge: "bg-mark-soft text-mark border-mark/20", dot: "bg-mark" },
  pen: { badge: "bg-pen-soft text-pen border-pen/20", dot: "bg-pen" },
  mute: { badge: "bg-sunken text-mute border-line", dot: "bg-mute" },
};

export const Badge = ({
  tone,
  children,
  withDot = false,
  className = "",
}: {
  tone: Tone;
  children: ReactNode;
  withDot?: boolean;
  className?: string;
}) => {
  const t = toneCls[tone] || toneCls.mute;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium tracking-tight ${t.badge} ${className}`}
    >
      {withDot && <span className={`h-1.5 w-1.5 rounded-full ${t.dot}`} />}
      {children}
    </span>
  );
};

export const StatusBadge = ({
  status,
  withDot = true,
  className = "",
}: {
  status?: string | null;
  withDot?: boolean;
  className?: string;
}) => (
  <Badge tone={toneOf(status)} withDot={withDot} className={className}>
    {label(status)}
  </Badge>
);

type BtnVariant = "primary" | "secondary" | "soft" | "ghost" | "danger" | "outline";
type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: BtnVariant;
  busy?: boolean;
  small?: boolean;
  icon?: ReactNode;
};

export function Button({
  variant = "soft",
  busy,
  small,
  icon,
  className = "",
  children,
  disabled,
  ...p
}: BtnProps) {
  const v: Record<BtnVariant, string> = {
    primary:
      "bg-pen text-white hover:bg-pen/95 shadow-sm active:scale-[0.99] border border-transparent focus-visible:ring-pen",
    secondary:
      "bg-surface text-ink border border-line hover:bg-sunken shadow-sm active:scale-[0.99] focus-visible:ring-pen",
    soft: "bg-sunken text-ink hover:bg-line/60 active:scale-[0.99] border border-transparent focus-visible:ring-pen",
    ghost: "text-pen hover:bg-pen-soft/80 active:scale-[0.99] border border-transparent",
    danger:
      "bg-mark text-white hover:bg-mark/95 shadow-sm active:scale-[0.99] border border-transparent focus-visible:ring-mark",
    outline: "border border-pen text-pen hover:bg-pen-soft/70 active:scale-[0.99]",
  };

  return (
    <button
      {...p}
      disabled={disabled || busy}
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-ui select-none disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none ${
        small ? "px-2.5 py-1 text-xs" : "px-3.5 py-2 text-sm"
      } ${v[variant]} ${className}`}
    >
      {busy ? <Spinner size={small ? 13 : 15} /> : icon ? <span className="shrink-0">{icon}</span> : null}
      {children}
    </button>
  );
}

export const Spinner = ({ size = 18 }: { size?: number }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    className="animate-spin text-current"
    aria-label="Loading"
    role="img"
  >
    <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="3" opacity=".25" />
    <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
  </svg>
);

export const Loading = ({ text = "Loading data..." }: { text?: string }) => (
  <div className="flex flex-col items-center justify-center gap-3 py-16 text-center text-mute">
    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-pen-soft text-pen shadow-sm">
      <Spinner size={22} />
    </div>
    <p className="text-sm font-medium">{text}</p>
  </div>
);

export const Card = ({
  children,
  className = "",
  hover = false,
}: {
  children: ReactNode;
  className?: string;
  hover?: boolean;
}) => (
  <div
    className={`rounded-xl border border-line bg-surface shadow-sm ${
      hover ? "transition-ui hover:border-pen/40 hover:shadow-md" : ""
    } ${className}`}
  >
    {children}
  </div>
);

export function ProgressBar({ value, max }: { value: number; max: number }) {
  const p = max > 0 ? Math.min(100, Math.round((100 * value) / max)) : 0;
  return (
    <div
      className="h-2 w-full overflow-hidden rounded-full bg-sunken"
      role="progressbar"
      aria-valuenow={p}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className="h-full rounded-full bg-pen transition-all duration-300 ease-out"
        style={{ width: `${p}%` }}
      />
    </div>
  );
}

export function PageHeader({
  title,
  sub,
  actions,
  badge,
  breadcrumbs,
}: {
  title: ReactNode;
  sub?: ReactNode;
  actions?: ReactNode;
  badge?: ReactNode;
  breadcrumbs?: { label: string; to?: string }[];
}) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0 flex-1">
        {breadcrumbs && breadcrumbs.length > 0 && (
          <nav aria-label="Breadcrumbs" className="mb-1.5 flex items-center gap-1.5 text-xs text-mute">
            {breadcrumbs.map((b, i) => (
              <span key={i} className="flex items-center gap-1.5">
                {i > 0 && <span className="opacity-40">/</span>}
                {b.to ? (
                  <a href={b.to} className="hover:text-ink transition-colors">
                    {b.label}
                  </a>
                ) : (
                  <span className="font-medium text-ink">{b.label}</span>
                )}
              </span>
            ))}
          </nav>
        )}
        <div className="flex flex-wrap items-center gap-2.5">
          <h1 className="text-2xl font-bold tracking-tight text-ink sm:text-3xl">{title}</h1>
          {badge}
        </div>
        {sub && <div className="mt-1 text-sm text-mute leading-relaxed">{sub}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2 pt-1 sm:pt-0 shrink-0">{actions}</div>}
    </div>
  );
}

export const Empty = ({
  title,
  hint,
  action,
  icon,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
  icon?: ReactNode;
}) => (
  <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-line bg-surface/50 p-10 text-center">
    <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-sunken text-mute">
      {icon ?? (
        <svg className="h-6 w-6 opacity-60" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"
          />
        </svg>
      )}
    </div>
    <h3 className="text-base font-semibold text-ink">{title}</h3>
    {hint && <p className="mt-1 max-w-sm text-sm text-mute">{hint}</p>}
    {action && <div className="mt-4">{action}</div>}
  </div>
);

export function ErrorPanel({ error, action }: { error: unknown; action?: ReactNode }) {
  if (!error) return null;
  const e =
    error instanceof ApiError
      ? error
      : new ApiError(0, "ERROR", error instanceof Error ? error.message : String(error));
  return (
    <div
      role="alert"
      className="rounded-xl border border-mark/30 bg-mark-soft/60 p-4 text-sm shadow-sm transition-ui"
    >
      <div className="flex items-start gap-3">
        <IconAlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-mark" />
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-semibold text-mark">{e.message}</p>
            {e.status > 0 && (
              <span className="rounded bg-mark/10 px-1.5 py-0.5 text-xs font-mono font-medium text-mark">
                HTTP {e.status} · {e.code}
              </span>
            )}
          </div>
          {e.issues.length > 0 && (
            <ul className="mt-2.5 space-y-1.5 border-t border-mark/20 pt-2">
              {e.issues.map((i, k) => (
                <li key={k} className="flex items-baseline gap-2 text-xs">
                  <span className="rounded bg-mark/10 px-1 py-0.5 font-semibold text-mark">{i.question}</span>
                  <span className="text-ink">{i.reason}</span>
                </li>
              ))}
            </ul>
          )}
          {action && <div className="mt-3">{action}</div>}
        </div>
      </div>
    </div>
  );
}

export function Modal({
  title,
  onClose,
  children,
  wide,
  footer,
  icon,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
  footer?: ReactNode;
  icon?: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    ref.current?.focus();
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-sm"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`flex max-h-[92vh] w-full flex-col rounded-2xl border border-line bg-surface shadow-2xl transition-ui ${
          wide ? "max-w-4xl" : "max-w-lg"
        }`}
      >
        <div className="flex items-center justify-between border-b border-line px-6 py-4">
          <div className="flex items-center gap-2.5">
            {icon && <span className="text-pen">{icon}</span>}
            <h2 className="text-lg font-semibold text-ink">{title}</h2>
          </div>
          <button
            onClick={onClose}
            aria-label="Close dialog"
            className="rounded-lg p-1.5 text-mute transition-colors hover:bg-sunken hover:text-ink focus-visible:ring-1 focus-visible:ring-pen"
          >
            <IconX size={18} />
          </button>
        </div>
        <div className="overflow-y-auto p-6">{children}</div>
        {footer && <div className="flex justify-end gap-2.5 border-t border-line bg-sunken/40 px-6 py-4">{footer}</div>}
      </div>
    </div>
  );
}

export function Confirm({
  title,
  body,
  confirmLabel,
  danger,
  onConfirm,
  onClose,
}: {
  title: string;
  body: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => Promise<void> | void;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const go = async () => {
    setBusy(true);
    try {
      await onConfirm();
      onClose();
    } catch (e) {
      setErr(e);
      setBusy(false);
    }
  };
  return (
    <Modal
      title={title}
      onClose={onClose}
      icon={danger ? <IconAlertTriangle className="text-mark" size={20} /> : undefined}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button variant={danger ? "danger" : "primary"} busy={busy} onClick={go}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="space-y-3 text-sm text-ink/90 leading-relaxed">
        {body}
        <ErrorPanel error={err} />
      </div>
    </Modal>
  );
}

const inputCls =
  "w-full rounded-lg border border-line bg-surface px-3.5 py-2 text-sm text-ink placeholder:text-mute shadow-sm transition-ui focus:border-pen focus:ring-2 focus:ring-pen/20 focus:outline-none";

export function Field({
  label: l,
  hint,
  required,
  error,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  error?: string;
  children: (id: string) => ReactNode;
}) {
  const id = useId();
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <label htmlFor={id} className="block text-sm font-medium text-ink">
          {l} {required && <span className="text-mark font-bold">*</span>}
        </label>
        {hint && <span className="text-xs text-mute">{hint}</span>}
      </div>
      {children(id)}
      {error && <p className="text-xs font-medium text-mark">{error}</p>}
    </div>
  );
}

export const Input = (p: InputHTMLAttributes<HTMLInputElement>) => (
  <input {...p} className={`${inputCls} ${p.className ?? ""}`} />
);

export const Select = (p: SelectHTMLAttributes<HTMLSelectElement>) => (
  <select {...p} className={`${inputCls} cursor-pointer pr-8 ${p.className ?? ""}`} />
);

export const Textarea = (p: TextareaHTMLAttributes<HTMLTextAreaElement>) => (
  <textarea {...p} className={`${inputCls} leading-relaxed ${p.className ?? ""}`} />
);

export function PenScore({ got, max }: { got: number | null; max: number | null }) {
  const f = (n: number | null) => (n === null ? "–" : Number.isInteger(n) ? n : n.toFixed(1));
  return (
    <span className="pen-score text-lg" title={`Total score: ${f(got)} out of ${f(max)}`}>
      {f(got)}
      <small>/{f(max)}</small>
    </span>
  );
}

export function Stat({
  label: l,
  value,
  tone,
  icon,
  hint,
  className = "",
}: {
  label: string;
  value: ReactNode;
  tone?: Tone;
  icon?: ReactNode;
  hint?: string;
  className?: string;
}) {
  const toneBorder = {
    ok: "border-l-4 border-l-ok",
    warn: "border-l-4 border-l-warn",
    mark: "border-l-4 border-l-mark",
    pen: "border-l-4 border-l-pen",
    mute: "",
  }[tone || "mute"];

  return (
    <Card className={`p-4 transition-ui hover:border-line/80 ${toneBorder} ${className}`}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wider text-mute">{l}</p>
        {icon && <span className="text-mute/80">{icon}</span>}
      </div>
      <p
        className={`mt-1.5 text-2xl font-bold tracking-tight ${
          tone === "mark" ? "text-mark" : tone === "ok" ? "text-ok" : "text-ink"
        }`}
      >
        {value}
      </p>
      {hint && <p className="mt-1 text-xs text-mute">{hint}</p>}
    </Card>
  );
}

export { MathView } from "./MathView";
export { MathTextarea } from "./MathTextarea";
export { SearchableCombobox, type ComboboxOption } from "./SearchableCombobox";

