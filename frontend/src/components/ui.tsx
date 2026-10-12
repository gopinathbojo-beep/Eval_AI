import { useEffect, useId, useRef, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { ApiError } from "../api/client";
import { label, toneOf, type Tone } from "../utils/format";

const toneCls: Record<Tone, string> = {
  ok: "bg-ok-soft text-ok", warn: "bg-warn-soft text-warn", mark: "bg-mark-soft text-mark",
  pen: "bg-pen-soft text-pen", mute: "bg-sunken text-mute",
};
export const Badge = ({ tone, children }: { tone: Tone; children: ReactNode }) => (
  <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${toneCls[tone]}`}>{children}</span>
);
export const StatusBadge = ({ status }: { status: string }) => <Badge tone={toneOf(status)}>{label(status)}</Badge>;

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" | "soft"; busy?: boolean; small?: boolean };
export function Button({ variant = "soft", busy, small, className = "", children, disabled, ...p }: BtnProps) {
  const v = {
    primary: "bg-pen text-surface hover:opacity-90", soft: "bg-sunken text-ink hover:bg-line",
    ghost: "text-pen hover:bg-pen-soft", danger: "bg-mark text-surface hover:opacity-90",
  }[variant];
  return (
    <button {...p} disabled={disabled || busy}
      className={`inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${small ? "px-2.5 py-1 text-xs" : "px-3.5 py-2 text-sm"} ${v} ${className}`}>
      {busy && <Spinner size={14} />}{children}
    </button>
  );
}

export const Spinner = ({ size = 18 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className="animate-spin" aria-label="Loading" role="img">
    <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="3" opacity=".25" />
    <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
  </svg>
);
export const Loading = ({ text = "Loading" }: { text?: string }) => (
  <div className="flex items-center gap-2 p-8 text-mute"><Spinner />{text}</div>
);

export const Card = ({ children, className = "" }: { children: ReactNode; className?: string }) => (
  <div className={`rounded-lg border border-line bg-surface ${className}`}>{children}</div>
);

export function ProgressBar({ value, max }: { value: number; max: number }) {
  const p = max > 0 ? Math.min(100, Math.round((100 * value) / max)) : 0;
  return (
    <div className="h-2 w-full overflow-hidden rounded bg-sunken" role="progressbar" aria-valuenow={p} aria-valuemin={0} aria-valuemax={100}>
      <div className="h-full bg-pen transition-all" style={{ width: `${p}%` }} />
    </div>
  );
}

export function PageHeader({ title, sub, actions }: { title: ReactNode; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div><h1 className="text-xl font-semibold">{title}</h1>{sub && <p className="mt-1 text-sm text-mute">{sub}</p>}</div>
      <div className="flex flex-wrap gap-2">{actions}</div>
    </div>
  );
}

export const Empty = ({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) => (
  <div className="rounded-lg border border-dashed border-line p-8 text-center">
    <p className="font-medium">{title}</p>{hint && <p className="mt-1 text-sm text-mute">{hint}</p>}
    {action && <div className="mt-3">{action}</div>}
  </div>
);

/** Shows API failures with status, backend message and every blocking issue, never a bare "400 Bad Request". */
export function ErrorPanel({ error, action }: { error: unknown; action?: ReactNode }) {
  if (!error) return null;
  const e = error instanceof ApiError ? error : new ApiError(0, "ERROR", error instanceof Error ? error.message : String(error));
  return (
    <div role="alert" className="rounded-lg border border-mark/40 bg-mark-soft p-4 text-sm">
      <p className="font-semibold text-mark">{e.message}</p>
      {e.status > 0 && <p className="mt-0.5 text-xs text-mute">HTTP {e.status} · {e.code}</p>}
      {e.issues.length > 0 && (
        <ul className="mt-2 space-y-1">
          {e.issues.map((i, k) => (
            <li key={k} className="flex gap-2"><span className="min-w-[3.5rem] font-semibold">{i.question}</span><span>{i.reason}</span></li>
          ))}
        </ul>
      )}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function Modal({ title, onClose, children, wide, footer }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean; footer?: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    ref.current?.focus();
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title}
        className={`flex max-h-[90vh] w-full flex-col rounded-lg border border-line bg-surface shadow-xl ${wide ? "max-w-4xl" : "max-w-lg"}`}>
        <div className="flex items-center justify-between border-b border-line px-5 py-3">
          <h2 className="font-semibold">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="rounded p-1 text-mute hover:bg-sunken">✕</button>
        </div>
        <div className="overflow-y-auto p-5">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

export function Confirm({ title, body, confirmLabel, danger, onConfirm, onClose }: {
  title: string; body: ReactNode; confirmLabel: string; danger?: boolean; onConfirm: () => Promise<void> | void; onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const go = async () => { setBusy(true); try { await onConfirm(); onClose(); } catch (e) { setErr(e); setBusy(false); } };
  return (
    <Modal title={title} onClose={onClose} footer={<><Button onClick={onClose}>Cancel</Button><Button variant={danger ? "danger" : "primary"} busy={busy} onClick={go}>{confirmLabel}</Button></>}>
      <div className="space-y-3 text-sm">{body}<ErrorPanel error={err} /></div>
    </Modal>
  );
}

const inputCls = "w-full rounded-md border border-line bg-surface px-3 py-2 text-sm placeholder:text-mute focus:border-pen";
export function Field({ label: l, hint, children }: { label: string; hint?: string; children: (id: string) => ReactNode }) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium">{l}</label>
      {children(id)}{hint && <p className="mt-1 text-xs text-mute">{hint}</p>}
    </div>
  );
}
export const Input = (p: InputHTMLAttributes<HTMLInputElement>) => <input {...p} className={`${inputCls} ${p.className ?? ""}`} />;
export const Select = (p: SelectHTMLAttributes<HTMLSelectElement>) => <select {...p} className={`${inputCls} ${p.className ?? ""}`} />;
export const Textarea = (p: TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...p} className={`${inputCls} ${p.className ?? ""}`} />;

export function PenScore({ got, max }: { got: number | null; max: number | null }) {
  const f = (n: number | null) => (n === null ? "–" : Number.isInteger(n) ? n : n.toFixed(1));
  return <span className="pen-score text-lg">{f(got)}<small>/{f(max)}</small></span>;
}

export function Stat({ label: l, value, tone }: { label: string; value: ReactNode; tone?: Tone }) {
  return (
    <Card className="p-4">
      <p className="text-sm text-mute">{l}</p>
      <p className={`mt-1 text-2xl font-semibold ${tone === "mark" ? "text-mark" : ""}`}>{value}</p>
    </Card>
  );
}
