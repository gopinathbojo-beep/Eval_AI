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
import { IconAlertCircle, IconAlertTriangle, IconX } from "./Icons";

const toneCls: Record<Tone, { badge: string; dot: string }> = {
  ok: { badge: "bg-ok-soft/70 text-ok border-ok/45", dot: "bg-ok" },
  warn: { badge: "bg-warn-soft/70 text-warn border-warn/45", dot: "bg-warn" },
  mark: { badge: "bg-mark-soft/70 text-mark border-mark/45", dot: "bg-mark" },
  pen: { badge: "bg-pen-soft/70 text-pen border-pen/40", dot: "bg-pen" },
  mute: { badge: "bg-sunken/60 text-mute border-mute/30", dot: "bg-mute" },
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
      className={`stamp inline-flex items-center gap-1.5 px-2 py-0.5 ${t.badge} ${className}`}
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

type BtnVariant = "primary" | "secondary" | "soft" | "ghost" | "danger" | "outline";
type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: BtnVariant;
  busy?: boolean;
  small?: boolean;
  icon?: ReactNode;
};

const btnVariant: Record<BtnVariant, string> = {
  primary:
    "bg-pen text-on-pen border border-transparent shadow-[inset_0_-2px_0_rgb(0_0_0/0.22)] hover:bg-pen/90 active:translate-y-px active:shadow-none",
  secondary:
    "bg-surface text-ink border border-line shadow-[inset_0_-2px_0_rgb(var(--line))] hover:border-ink/30 hover:bg-hover active:translate-y-px active:shadow-none",
  soft: "bg-sunken text-ink border border-transparent hover:bg-hover active:translate-y-px",
  ghost: "text-pen border border-transparent hover:bg-hover active:translate-y-px",
  danger:
    "bg-mark text-white border border-mark shadow-[inset_0_-2px_0_rgb(0_0_0/0.22)] hover:bg-mark/90 active:translate-y-px active:shadow-none",
  outline: "border border-pen/70 text-pen hover:bg-hover hover:border-pen active:translate-y-px",
};

/** Class string shared by <Button> and <LinkButton> so links that act as buttons look identical. */
export const buttonCls = (variant: BtnVariant = "soft", small?: boolean, className = "") =>
  `inline-flex items-center justify-center gap-1.5 rounded-md font-medium whitespace-nowrap transition-ui select-none disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none ${
    small ? "px-2.5 py-1 text-xs" : "px-3.5 py-2 text-sm"
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
          className="absolute right-0 z-20 mt-1 min-w-40 animate-rise overflow-hidden rounded-md border border-line bg-surface py-1 shadow-pop"
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
              className={`block w-full px-3 py-1.5 text-left text-xs font-medium outline-none hover:bg-hover focus-visible:bg-hover ${i.danger ? "text-mark" : "text-ink hover:text-brown focus-visible:text-brown"}`}
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
    <p className="font-doc text-sm italic">{text}</p>
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
    className={`rounded-lg border border-line bg-surface shadow-card ${
      hover ? "transition-ui hover:-translate-y-0.5 hover:border-pen/40 hover:shadow-[0_1px_0_0_rgb(var(--line)),5px_5px_0_0_rgb(var(--pen)/0.18)]" : ""
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
        className="h-full rounded-full bg-[repeating-linear-gradient(115deg,rgb(var(--pen))_0_8px,rgb(var(--pen)/0.82)_8px_12px)] transition-all duration-500 ease-out"
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
    <div className="mb-7 flex flex-col gap-3 border-b border-dashed border-line pb-5 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0 flex-1">
        {breadcrumbs && breadcrumbs.length > 0 && (
          <nav aria-label="Breadcrumbs" className="mb-2 flex items-center gap-1.5 pl-3.5 text-[11px] font-medium uppercase tracking-[0.12em] text-mute">
            {breadcrumbs.map((b, i) => (
              <span key={i} className="flex items-center gap-1.5">
                {i > 0 && <span className="text-mark/60">/</span>}
                {b.to ? (
                  <Link to={b.to} className="hover:text-brown transition-colors">
                    {b.label}
                  </Link>
                ) : (
                  <span aria-current="page" className="font-medium text-ink">{b.label}</span>
                )}
              </span>
            ))}
          </nav>
        )}
        <div className="flex flex-wrap items-center gap-3 pl-3.5">
          <h1 className="margin-rule font-display text-2xl font-semibold text-ink sm:text-[2rem] sm:leading-tight">{title}</h1>
          {badge}
        </div>
        {sub && <div className="mt-1.5 pl-3.5 text-sm text-mute leading-relaxed">{sub}</div>}
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
  <div className="ruled flex flex-col items-center justify-center rounded-lg border border-dashed border-line bg-surface/70 px-10 py-12 text-center">
    <div className="mb-3 flex h-12 w-12 -rotate-3 items-center justify-center rounded-md border border-line bg-surface text-pen shadow-card">
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
    <h3 className="font-display text-lg font-semibold text-ink">{title}</h3>
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
      className="rounded-md border border-mark/30 border-l-4 border-l-mark bg-mark-soft/60 p-4 text-sm transition-ui"
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
  // Callers usually pass an inline onClose; keep the latest in a ref so the mount effect runs
  // once and focus is not pulled back to the dialog (away from its inputs) on every re-render.
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
      className="fixed inset-0 z-50 flex animate-fadeIn items-end justify-center bg-cover/55 backdrop-blur-[3px] sm:items-center sm:p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`flex max-h-[92dvh] w-full animate-rise flex-col overflow-hidden rounded-t-xl border border-line border-t-4 border-t-pen bg-surface shadow-pop outline-none sm:rounded-lg ${
          wide === "xl" ? "max-w-7xl" : wide ? "max-w-4xl" : "max-w-lg"
        }`}
      >
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-2.5">
            {icon && <span className="shrink-0 text-pen">{icon}</span>}
            <h2 id={titleId} className="truncate font-display text-xl font-semibold text-ink">
              {title}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="shrink-0 rounded-lg p-1.5 text-mute transition-colors hover:bg-hover hover:text-brown"
          >
            <IconX size={18} />
          </button>
        </div>
        <div className="overflow-y-auto overscroll-contain p-5 sm:p-6">{children}</div>
        {footer && (
          <div className="flex flex-wrap justify-end gap-2.5 border-t border-dashed border-line bg-paper/60 px-5 py-4 sm:px-6">
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
  "w-full rounded-md border border-line bg-surface px-3.5 py-2 text-sm text-ink placeholder:text-mute/70 shadow-[inset_0_1px_2px_rgb(var(--ink)/0.04)] transition-ui hover:border-ink/25 focus:border-pen focus:ring-[3px] focus:ring-pen/15 focus:outline-none";

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
        <p role="alert" className="flex items-center gap-1 text-xs font-medium text-mark">
          <IconAlertCircle size={13} className="shrink-0" />
          {error}
        </p>
      )}
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
  const t = tone || "mute";
  const tab = { ok: "bg-ok", warn: "bg-warn", mark: "bg-mark", pen: "bg-pen", mute: "bg-line" }[t];
  const num = { ok: "text-ok", warn: "text-warn", mark: "text-mark", pen: "text-pen", mute: "text-ink" }[t];

  return (
    <Card className={`relative overflow-hidden p-4 pt-5 ${className}`}>
      {/* Index-card tab colour */}
      <span aria-hidden className={`absolute inset-x-0 top-0 h-1 ${tab}`} />
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-mute">{l}</p>
        {icon && <span className="text-mute/70">{icon}</span>}
      </div>
      <p className={`mt-2 font-display text-[2rem] font-semibold leading-none ${num}`}>{value}</p>
      {hint && <p className="mt-2 border-t border-dashed border-line pt-2 text-xs text-mute">{hint}</p>}
    </Card>
  );
}

export { MathView } from "./MathView";
export { MathTextarea } from "./MathTextarea";
export { SearchableCombobox, type ComboboxOption } from "./SearchableCombobox";

