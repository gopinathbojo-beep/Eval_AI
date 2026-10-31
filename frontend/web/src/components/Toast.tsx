import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import type { Tone } from "../utils/format";
import { IconAlertCircle, IconCheckCircle, IconInfo, IconX } from "./Icons";

type Toast = { id: number; tone: Tone; text: string };
type Notify = (text: string, tone?: Tone) => void;

const ToastCtx = createContext<Notify>(() => {});

/** Short, non-blocking feedback ("Marksheet downloaded", "Download failed") in place of window.alert. */
export const useToast = () => useContext(ToastCtx);

const toneCls: Record<Tone, string> = {
  ok: "border-l-ok text-ok",
  warn: "border-l-warn text-warn",
  mark: "border-l-mark text-mark",
  pen: "border-l-pen text-pen",
  mute: "border-l-line text-mute",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seq = useRef(0);

  const dismiss = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const notify = useCallback<Notify>(
    (text, tone = "ok") => {
      const id = ++seq.current;
      setToasts((t) => [...t.slice(-3), { id, tone, text }]);
      setTimeout(() => dismiss(id), tone === "mark" ? 8000 : 4500);
    },
    [dismiss]
  );

  return (
    <ToastCtx.Provider value={notify}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-x-4 bottom-20 z-[60] lg:bottom-4 flex flex-col items-center gap-2 sm:inset-x-auto sm:right-6 sm:items-end"
      >
        {toasts.map((t) => {
          const Icon = t.tone === "mark" || t.tone === "warn" ? IconAlertCircle : t.tone === "ok" ? IconCheckCircle : IconInfo;
          return (
            <div
              key={t.id}
              role={t.tone === "mark" ? "alert" : "status"}
              className={`pointer-events-auto flex w-full max-w-sm animate-rise items-start gap-2.5 rounded-md border border-line border-l-4 bg-surface px-3.5 py-3 text-sm shadow-pop ${toneCls[t.tone]}`}
            >
              <Icon size={17} className="mt-0.5 shrink-0" />
              <p className="flex-1 text-ink">{t.text}</p>
              <button
                type="button"
                onClick={() => dismiss(t.id)}
                aria-label="Dismiss notification"
                className="-m-1 rounded p-1 text-mute transition-ui hover:bg-hover hover:text-brown"
              >
                <IconX size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastCtx.Provider>
  );
}
