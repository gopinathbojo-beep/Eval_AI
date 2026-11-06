import {
  useEffect,
  type KeyboardEvent as ReactKeyboardEvent,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { Link, type LinkProps } from "react-router-dom";
import { ApiError } from "../api/client";
import { label, toneOf, type Tone } from "../utils/format";
import { IconAlertCircle, IconAlertTriangle, IconX, IconHome, IconEye, IconEyeOff, IconCheck } from "./Icons";
import { passwordRules } from "../utils/validation";

const toneCls: Record<Tone, { badge: string; dot: string }> = {
  ok: { badge: "bg-emerald-50 text-emerald-700 border-emerald-200/60 shadow-xs", dot: "bg-emerald-500" },
  warn: { badge: "bg-amber-50 text-amber-700 border-amber-200/60 shadow-xs", dot: "bg-amber-500" },
  mark: { badge: "bg-rose-50 text-rose-700 border-rose-200/60 shadow-xs", dot: "bg-rose-500" },
  pen: { badge: "bg-blue-50 text-blue-700 border-blue-200/60 shadow-xs", dot: "bg-blue-500" },
  mute: { badge: "bg-slate-100 text-slate-700 border-slate-200 shadow-xs", dot: "bg-slate-400" },
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
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold border ${t.badge} ${className}`}
    >
      {withDot && <span className={`h-1.5 w-1.5 rounded-full ${t.dot}`} />}
      {children}
    </span>
  );
};

export const StatusBadge = ({
  status,
  withDot = false,
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

export function PageCanvas({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className="w-full">
      <div className={`glass-canvas p-5 sm:p-7 lg:p-8 space-y-6 ${className}`}>
        {children}
      </div>
    </div>
  );
}

type BtnVariant = "primary" | "secondary" | "soft" | "ghost" | "danger" | "outline";
type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: BtnVariant;
  busy?: boolean;
  small?: boolean;
  icon?: ReactNode;
};

const btnVariant: Record<BtnVariant, string> = {
  primary:
    "aurora-fill text-white border border-transparent shadow-md shadow-indigo-500/25 active:scale-[0.98] font-semibold focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2",
  secondary:
    "bg-white text-slate-700 border border-slate-200/90 shadow-xs hover:bg-slate-50 hover:border-slate-300 active:scale-[0.98] font-semibold focus-visible:ring-2 focus-visible:ring-blue-500/40",
  soft: "bg-slate-50 text-slate-700 border border-slate-200/70 hover:bg-slate-100 hover:border-slate-300 active:scale-[0.98] font-medium focus-visible:ring-2 focus-visible:ring-blue-500/40",
  ghost: "text-blue-600 border border-transparent hover:bg-blue-50/70 active:scale-[0.98] font-semibold focus-visible:ring-2 focus-visible:ring-blue-500/40",
  danger:
    "bg-rose-600 text-white border border-transparent shadow-md shadow-rose-600/20 hover:bg-rose-700 active:scale-[0.98] font-semibold focus-visible:ring-2 focus-visible:ring-rose-500 focus-visible:ring-offset-2",
  outline: "border-2 border-blue-600 text-blue-600 hover:bg-blue-50 active:scale-[0.98] font-semibold focus-visible:ring-2 focus-visible:ring-blue-500",
};

/** Class string shared by <Button> and <LinkButton> so links that act as buttons look identical. */
export const buttonCls = (variant: BtnVariant = "soft", small?: boolean, className = "") =>
  `inline-flex items-center justify-center gap-2 rounded-full font-medium whitespace-nowrap transition-all duration-150 select-none disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none cursor-pointer ${
    small ? "px-4 py-1.5 text-xs min-h-[32px]" : "px-5 py-2.5 text-sm min-h-[38px]"
  } ${btnVariant[variant]} ${className}`;

export function Button({
  variant = "soft",
  busy,
  small,
  icon,
  className = "",
  children,
  disabled,
  type = "button",
  ...p
}: BtnProps) {
  return (
    <button
      {...p}
      type={type}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={buttonCls(variant, small, className)}
    >
      {busy ? <Spinner size={small ? 13 : 15} /> : icon ? <span className="shrink-0">{icon}</span> : null}
      {children}
    </button>
  );
}

/** A router link styled as a button. Use instead of wrapping <Button> in <Link> (nested interactive elements). */
export function LinkButton({
  variant = "soft",
  small,
  icon,
  className = "",
  children,
  ...p
}: LinkProps & { variant?: BtnVariant; small?: boolean; icon?: ReactNode }) {
  return (
    <Link {...p} className={buttonCls(variant, small, className)}>
      {icon && <span className="shrink-0">{icon}</span>}
      {children}
    </Link>
  );
}

/** A small "More" button that opens a list of less-used actions. Closes on outside click or Escape; arrow keys move between items. */
export function MoreMenu({
  items,
  label: text = "More",
}: {
  items: { label: string; onClick: () => void; danger?: boolean; hidden?: boolean }[];
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    menu.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent) {
        if (e.key !== "Escape") return;
        ref.current?.querySelector<HTMLElement>("[aria-haspopup]")?.focus();
      } else if (ref.current?.contains(e.target as Node)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  const onMenuKey = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    const els = Array.from(menu.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);
    const i = els.indexOf(document.activeElement as HTMLElement);
    const go = (n: number) => {
      e.preventDefault();
      els[(n + els.length) % els.length]?.focus();
    };
    if (e.key === "ArrowDown") go(i + 1);
    else if (e.key === "ArrowUp") go(i - 1);
    else if (e.key === "Home") go(0);
    else if (e.key === "End") go(els.length - 1);
    else if (e.key === "Tab") setOpen(false);
  };
  const shown = items.filter((i) => !i.hidden);
  if (!shown.length) return null;
  return (
    <div ref={ref} className="relative">
      <Button small variant="ghost" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {text} <span aria-hidden className={`text-[10px] transition-transform ${open ? "rotate-180" : ""}`}>▾</span>
      </Button>
      {open && (
        <div
          ref={menu}
          role="menu"
          onKeyDown={onMenuKey}
          className="absolute right-0 z-20 mt-1.5 min-w-44 animate-rise overflow-hidden rounded-xl border border-line bg-surface py-1.5 shadow-pop"
        >
          {shown.map((i) => (
            <button
              key={i.label}
              role="menuitem"
              type="button"
              onClick={() => {
                setOpen(false);
                i.onClick();
              }}
              className={`block w-full px-3.5 py-2 text-left text-xs font-medium outline-none transition-colors hover:bg-hover focus-visible:bg-hover ${i.danger ? "text-mark" : "text-ink hover:text-pen"}`}
            >
              {i.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export const Spinner = ({ size = 18 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className="animate-spin text-current" aria-hidden>
    <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="3" opacity=".25" />
    <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
  </svg>
);

export const Loading = ({ text = "Loading data..." }: { text?: string }) => (
  <div role="status" aria-live="polite" className="flex flex-col items-center justify-center gap-3 py-16 text-center text-mute">
    <div className="flex h-11 w-11 items-center justify-center rounded-full border-2 border-dashed border-pen/40 text-pen">
      <Spinner size={20} />
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
    className={`rounded-2xl border border-blue-100/70 bg-white shadow-xs ${
      hover ? "transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md hover:border-blue-200" : ""
    } ${className}`}
  >
    {children}
  </div>
);

export function ProgressBar({ value, max }: { value: number; max: number }) {
  const p = max > 0 ? Math.min(100, Math.round((100 * value) / max)) : 0;
  return (
    <div
      className="h-2 w-full overflow-hidden rounded-full bg-sunken ring-1 ring-inset ring-line"
      role="progressbar"
      aria-valuenow={p}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className="h-full rounded-full bg-pen transition-all duration-500 ease-out"
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
  top,
}: {
  title: ReactNode;
  sub?: ReactNode;
  actions?: ReactNode;
  badge?: ReactNode;
  breadcrumbs?: { label: string; to?: string }[];
  /** beside the breadcrumbs, at the top of the page (progress through a multi-step flow) */
  top?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-4 border-b border-slate-100 pb-6 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0 flex-1">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
        {breadcrumbs && breadcrumbs.length > 0 ? (
          <nav aria-label="Breadcrumbs" className="flex items-center gap-2 text-xs font-semibold text-slate-600">
            <div className="aurora-fill flex h-7 w-7 items-center justify-center rounded-lg text-white shadow-sm shadow-indigo-500/30">
              <IconHome size={14} />
            </div>
            <Link to="/dashboard" className="text-slate-800 hover:text-blue-600 transition-colors">Eval AI</Link>
            {breadcrumbs.map((b, i) => (
              <span key={i} className="flex items-center gap-2">
                <span className="text-slate-400 font-bold">&gt;</span>
                {b.to ? (
                  <Link to={b.to} className="text-slate-700 hover:text-blue-600 transition-colors">
                    {b.label}
                  </Link>
                ) : (
                  <span aria-current="page" className="aurora-text font-bold">{b.label}</span>
                )}
              </span>
            ))}
          </nav>
        ) : (
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-600">
            <div className="aurora-fill flex h-7 w-7 items-center justify-center rounded-lg text-white shadow-sm shadow-indigo-500/30">
              <IconHome size={14} />
            </div>
            <Link to="/dashboard" className="text-slate-800 hover:text-blue-600 transition-colors">Eval AI</Link>
            <span className="text-slate-400 font-bold">&gt;</span>
            <span className="font-bold text-blue-600 truncate max-w-[240px]">
              {typeof title === "string" ? title : "Workspace"}
            </span>
          </div>
        )}
        {top}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="aurora-text text-2xl sm:text-3xl font-extrabold tracking-tight">{title}</h1>
          {badge}
        </div>
        {sub && <div className="mt-1.5 text-sm font-medium text-slate-500 leading-relaxed">{sub}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2.5 pt-1 sm:pt-0 shrink-0">{actions}</div>}
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
  <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-line bg-surface/70 px-10 py-12 text-center">
    <div className="mb-3.5 flex h-12 w-12 items-center justify-center rounded-xl border border-line bg-surface text-pen shadow-sm">
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
    <h3 className="text-lg font-bold text-ink">{title}</h3>
    {hint && <p className="mt-1.5 max-w-sm text-sm text-mute">{hint}</p>}
    {action && <div className="mt-5">{action}</div>}
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
      className="rounded-xl border border-mark/25 border-l-4 border-l-mark bg-mark-soft/60 p-4 text-sm transition-all"
    >
      <div className="flex items-start gap-3">
        <IconAlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-mark" />
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-semibold text-mark">{e.message}</p>
            {e.status > 0 && (
              <span className="rounded-md bg-mark/10 px-2 py-0.5 text-xs font-mono font-medium text-mark">
                HTTP {e.status} · {e.code}
              </span>
            )}
          </div>
          {e.issues.length > 0 && (
            <ul className="mt-2.5 space-y-1.5 border-t border-mark/20 pt-2">
              {e.issues.map((i, k) => (
                <li key={k} className="flex items-baseline gap-2 text-xs">
                  {i.question && <span className="rounded bg-mark/10 px-1.5 py-0.5 font-semibold text-mark">Q{i.question}</span>}
                  <span className="text-ink">{i.reason || i.message || i.code || "Review this validation issue."}{i.page ? ` (page ${i.page})` : ""}</span>
                </li>
              ))}
            </ul>
          )}
          {action && <div className="mt-3.5">{action}</div>}
        </div>
      </div>
    </div>
  );
}

/** Open dialogs, innermost last: only the top one reacts to Escape and owns the focus trap. */
const modalStack: HTMLElement[] = [];
const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

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
  wide?: boolean | "xl";
  footer?: ReactNode;
  icon?: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const el = ref.current!;
    const opener = document.activeElement as HTMLElement | null;
    modalStack.push(el);
    if (!el.contains(document.activeElement)) el.focus();
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKey = (e: KeyboardEvent) => {
      if (modalStack[modalStack.length - 1] !== el) return;
      if (e.key === "Escape") {
        e.stopPropagation();
        closeRef.current();
      } else if (e.key === "Tab") {
        const items = Array.from(el.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((n) => n.offsetParent !== null);
        if (!items.length) return e.preventDefault();
        const a = items[0]!;
        const z = items[items.length - 1]!;
        if (e.shiftKey && (document.activeElement === a || document.activeElement === el)) {
          e.preventDefault();
          z.focus();
        } else if (!e.shiftKey && document.activeElement === z) {
          e.preventDefault();
          a.focus();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      modalStack.splice(modalStack.indexOf(el), 1);
      if (!modalStack.length) document.body.style.overflow = prevOverflow;
      if (opener?.isConnected) opener.focus();
    };
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex animate-fadeIn items-end justify-center bg-slate-900/60 backdrop-blur-sm sm:items-center sm:p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`flex max-h-[92dvh] w-full animate-rise flex-col overflow-hidden rounded-t-2xl border border-line bg-surface shadow-pop outline-none sm:rounded-2xl ${
          wide === "xl" ? "max-w-7xl" : wide ? "max-w-4xl" : "max-w-lg"
        }`}
      >
        <div className="flex items-center justify-between gap-3 border-b border-line px-6 py-4.5">
          <div className="flex min-w-0 items-center gap-2.5">
            {icon && <span className="shrink-0 text-pen">{icon}</span>}
            <h2 id={titleId} className="truncate text-lg font-bold text-ink">
              {title}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="shrink-0 rounded-lg p-1.5 text-mute transition-colors hover:bg-hover hover:text-ink"
          >
            <IconX size={18} />
          </button>
        </div>
        <div className="overflow-y-auto overscroll-contain p-6">{children}</div>
        {footer && (
          <div className="flex flex-wrap justify-end gap-3 border-t border-line bg-sunken/40 px-6 py-4">
            {footer}
          </div>
        )}
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
          <Button variant="secondary" onClick={onClose} autoFocus={danger}>
            Cancel
          </Button>
          <Button variant={danger ? "danger" : "primary"} busy={busy} onClick={go} autoFocus={!danger}>
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
  "w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 shadow-xs transition-all duration-150 hover:border-slate-300 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 focus:outline-none";

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
        <label htmlFor={id} className="block text-[13px] font-semibold text-ink">
          {l} {required && <span className="text-mark font-bold">*</span>}
        </label>
        {hint && <span className="text-xs text-mute">{hint}</span>}
      </div>
      {children(id)}
      {error && (
        <p role="alert" className="flex items-center gap-1.5 text-xs font-medium text-mark">
          <IconAlertCircle size={14} className="shrink-0" />
          {error}
        </p>
      )}
    </div>
  );
}

export const Input = (p: InputHTMLAttributes<HTMLInputElement>) => (
  <input {...p} className={`${inputCls} ${p.className ?? ""}`} />
);

/** Password field with an eye button to show or hide what is typed. */
export function PasswordInput(p: Omit<InputHTMLAttributes<HTMLInputElement>, "type">) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <input {...p} type={show ? "text" : "password"} className={`${inputCls} pr-11 ${p.className ?? ""}`} />
      <button
        type="button"
        onClick={() => setShow((s) => !s)}
        aria-label={show ? "Hide password" : "Show password"}
        aria-pressed={show}
        className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-slate-400 transition-colors hover:text-slate-600 cursor-pointer"
      >
        {show ? <IconEyeOff size={18} /> : <IconEye size={18} />}
      </button>
    </div>
  );
}

/** Live checklist of the new-password rules; each line turns green once it is met. */
export function PasswordChecklist({ value }: { value: string }) {
  return (
    <ul className="mt-2 grid gap-1 text-xs sm:grid-cols-2" aria-label="Password requirements">
      {passwordRules.map((r) => {
        const ok = r.ok(value);
        return (
          <li key={r.label} className={`flex items-center gap-1.5 transition-colors ${ok ? "text-emerald-700" : "text-slate-500"}`}>
            <span
              className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border transition-colors ${
                ok ? "border-emerald-500 bg-emerald-500 text-white" : "border-slate-300"
              }`}
              aria-hidden
            >
              {ok && <IconCheck size={10} />}
            </span>
            {r.label}
            <span className="sr-only">{ok ? " (met)" : " (not met)"}</span>
          </li>
        );
      })}
    </ul>
  );
}

export const Select = (p: SelectHTMLAttributes<HTMLSelectElement>) => (
  <select {...p} className={`${inputCls} cursor-pointer pr-8 ${p.className ?? ""}`} />
);

export const Textarea = (p: TextareaHTMLAttributes<HTMLTextAreaElement>) => (
  <textarea {...p} className={`${inputCls} leading-relaxed ${p.className ?? ""}`} />
);

export function PenScore({ got, max }: { got: number | null; max: number | null }) {
  const f = (n: number | null) => (n === null ? "–" : Number.isInteger(n) ? n : n.toFixed(1));
  return (
    <span className="pen-score" title={`Total score: ${f(got)} out of ${f(max)}`}>
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
  const t = tone || "mute";
  const num = { ok: "text-ok", warn: "text-warn", mark: "text-mark", pen: "text-pen", mute: "text-ink" }[t];

  return (
    <Card className={`relative overflow-hidden p-5 ${className}`}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-mute">{l}</p>
        {icon && <span className="text-mute/80">{icon}</span>}
      </div>
      <p className={`mt-3 text-3xl font-bold tracking-tight ${num}`}>{value}</p>
      {hint && <p className="mt-2.5 border-t border-line/60 pt-2 text-xs text-mute">{hint}</p>}
    </Card>
  );
}

export { MathView } from "./MathView";
export { MathTextarea } from "./MathTextarea";
export { SearchableCombobox, type ComboboxOption } from "./SearchableCombobox";

/** A plain data table: header labels, then rows of cells. Rows with onClick are clickable. */
export function Table({
  head,
  rows,
  empty,
}: {
  head: ReactNode[];
  rows: { key: string; cells: ReactNode[]; onClick?: () => void }[];
  empty?: ReactNode;
}) {
  if (!rows.length && empty) return <>{empty}</>;
  return (
    <div className="overflow-hidden rounded-2xl border border-blue-100/60 bg-white shadow-xs">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-blue-100/60 bg-blue-50/20 text-xs font-extrabold uppercase tracking-wider text-blue-950">
            <tr>{head.map((h, i) => <th key={i} className="px-6 py-4">{h}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r) => (
              <tr key={r.key} onClick={r.onClick} className={r.onClick ? "cursor-pointer hover:bg-blue-50/30 transition-colors duration-150" : "hover:bg-blue-50/30 transition-colors duration-150"}>
                {r.cells.map((c, i) => <td key={i} className="px-6 py-4 align-middle text-slate-700 font-medium">{c}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
