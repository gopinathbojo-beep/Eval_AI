import { useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { DocInfo } from "../types";
import { BUSY_DOC } from "../utils/format";
import { Button, Card, Confirm, ErrorPanel, Modal, ProgressBar, StatusBadge } from "./ui";
import {
  IconUpload,
  IconCheck,
  IconAlertCircle,
  IconClock,
  IconRotateCcw,
  IconFileText,
} from "./Icons";

export function UploadZone({
  accept,
  disabled,
  onFile,
  hint,
}: {
  accept: string;
  disabled?: boolean;
  onFile: (f: File) => Promise<void>;
  hint?: ReactNode;
}) {
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const send = async (f: File | undefined) => {
    if (!f) return;
    setBusy(true);
    setError(null);
    try {
      await onFile(f);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          if (!disabled && e.dataTransfer.files[0]) {
            send(e.dataTransfer.files[0]);
          }
        }}
        className={`group relative flex flex-col items-center justify-center rounded-2xl border-2 border-dashed p-8 text-center transition-ui ${
          disabled
            ? "cursor-not-allowed bg-sunken/40 opacity-60 border-line"
            : drag
            ? "border-pen bg-pen-soft/40 shadow-inner scale-[1.005]"
            : "border-line bg-surface hover:border-pen/60 hover:bg-sunken/30 cursor-pointer"
        }`}
        onClick={() => {
          if (!disabled && !busy) fileInputRef.current?.click();
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          className="sr-only"
          accept={accept}
          disabled={disabled || busy}
          onChange={(e) => {
            send(e.target.files?.[0]);
            e.target.value = "";
          }}
        />

        <div
          className={`mb-3 flex h-14 w-14 items-center justify-center rounded-2xl transition-ui ${
            drag ? "bg-pen text-white shadow-md" : "bg-pen-soft text-pen group-hover:scale-105"
          }`}
        >
          <IconUpload size={26} />
        </div>

        <p className="text-base font-semibold text-ink">
          {busy ? "Uploading and submitting file..." : "Drag and drop document here"}
        </p>
        <p className="mt-1 text-xs text-mute max-w-sm">
          {hint || "Supported formats: PDF, PNG, or JPG"}
        </p>

        {!busy && !disabled && (
          <div className="mt-4">
            <span className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface px-3 py-1.5 text-xs font-semibold text-ink shadow-xs transition-ui group-hover:border-pen/40">
              Browse Files
            </span>
          </div>
        )}
      </div>

      <ErrorPanel error={error} />
    </div>
  );
}

const STEPS = [
  "Uploaded",
  "Rendering pages",
  "Reading pages (OCR)",
  "Checking results",
  "Ready to review",
];

function stepIndex(d: DocInfo) {
  switch (d.status) {
    case "UPLOADED":
      return 0;
    case "RENDERING":
      return 1;
    case "OCR_PROCESSING":
      return 2;
    case "EXTRACTING":
      return 3;
    case "READY":
    case "NEEDS_ATTENTION":
      return 4;
    default:
      return 2;
  }
}

export function DocProgress({
  doc,
  onChanged,
  rebuildWarning,
  canRetry = true,
  actions,
}: {
  doc: DocInfo;
  onChanged: () => void;
  rebuildWarning?: string;
  canRetry?: boolean;
  actions?: ReactNode;
}) {
  const [confirm, setConfirm] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [diag, setDiag] = useState<{
    page: number;
    status: string;
    error: string | null;
    raw: string;
  } | null>(null);
  const [diagErr, setDiagErr] = useState<unknown>(null);
  const busy = BUSY_DOC.includes(doc.status);
  const prevBusy = useRef(busy);

  useEffect(() => {
    if (prevBusy.current && !busy && (doc.status === "READY" || doc.status === "NEEDS_ATTENTION")) {
      onChanged();
    }
    prevBusy.current = busy;
  }, [busy, doc.status, onChanged]);

  const failedPages = doc.pages.filter(
    (p) => p.ocr_status && !["OK", "PENDING"].includes(p.ocr_status)
  );
  const step = stepIndex(doc);

  const retry = async () => {
    await api(`/documents/${doc.kind}/${doc.id}/reprocess`, { method: "POST" });
    onChanged();
  };

  const cancel = async () => {
    setCancelling(true);
    setDiagErr(null);
    try {
      await api(`/documents/${doc.kind}/${doc.id}/cancel`, { method: "POST" });
      onChanged();
    } catch (e) {
      setDiagErr(e);
    } finally {
      setCancelling(false);
    }
  };

  const openDiag = async (n: number) => {
    setDiagErr(null);
    try {
      setDiag({
        page: n,
        ...(await api<{ status: string; error: string | null; raw: string }>(
          `/documents/${doc.kind}/${doc.id}/pages/${n}/ocr`
        )),
      });
    } catch (e) {
      setDiagErr(e);
    }
  };

  return (
    <Card className="p-5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-pen-soft text-pen shadow-xs">
            <IconFileText size={20} />
          </div>
          <div>
            <p className="font-semibold text-sm text-ink">{doc.original_filename}</p>
            <p className="text-xs text-mute">{doc.pages.length || "?"} page(s) detected</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {actions}
          <StatusBadge status={doc.status} />
        </div>
      </div>

      {busy && (
        <div className="space-y-3 rounded-xl border border-line bg-sunken/40 p-4">
          <ol className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
            {STEPS.map((s, i) => {
              const isPast = i < step;
              const isCurrent = i === step;
              return (
                <li
                  key={s}
                  className={`flex items-center gap-1.5 font-medium ${
                    isPast
                      ? "text-ok"
                      : isCurrent
                      ? "font-bold text-pen"
                      : "text-mute/70"
                  }`}
                >
                  {isPast ? (
                    <IconCheck size={14} className="text-ok" />
                  ) : isCurrent ? (
                    <span className="h-2 w-2 rounded-full bg-pen animate-ping" />
                  ) : null}
                  <span>{s}</span>
                </li>
              );
            })}
          </ol>

          <ProgressBar
            value={doc.progress_current}
            max={Math.max(doc.progress_total, 1)}
          />

          <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-xs">
            <p className="text-mute font-medium flex items-center gap-1.5" aria-live="polite">
              <IconClock size={14} className="text-pen" />
              <span>{doc.stage || "Processing document pages..."}</span>
            </p>
            <Button
              small
              variant="danger"
              busy={cancelling}
              onClick={cancel}
              title="Stop ongoing OCR perception process"
            >
              Stop OCR
            </Button>
          </div>
        </div>
      )}

      {doc.status === "CANCELLED" && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warn/30 bg-warn-soft p-4 text-xs">
          <div>
            <p className="font-bold text-warn">OCR Processing Cancelled</p>
            <p className="text-mute mt-0.5">
              The process was interrupted. You can resume reading or upload a replacement file.
            </p>
          </div>
          <Button
            small
            variant="primary"
            onClick={() => (rebuildWarning ? setConfirm(true) : retry().catch(() => {}))}
            icon={<IconRotateCcw size={13} />}
          >
            Retry Reading
          </Button>
        </div>
      )}

      {doc.error_message && !busy && doc.status !== "CANCELLED" && (
        <div
          className="flex items-start gap-2.5 rounded-xl border border-mark/30 bg-mark-soft p-4 text-xs text-mark"
          role="alert"
        >
          <IconAlertCircle size={16} className="shrink-0 mt-0.5" />
          <p className="font-medium leading-relaxed">{doc.error_message}</p>
        </div>
      )}

      {failedPages.length > 0 && !busy && (
        <div className="space-y-2 rounded-xl border border-line bg-surface p-3.5 text-xs">
          <p className="font-semibold text-ink">Pages requiring attention:</p>
          <ul className="space-y-1.5">
            {failedPages.map((p) => (
              <li key={p.page_number} className="flex items-center justify-between">
                <span className="font-medium text-mute">Page {p.page_number}:</span>
                <div className="flex items-center gap-2">
                  <StatusBadge status={p.ocr_status!} />
                  <Button small variant="ghost" onClick={() => openDiag(p.page_number)}>
                    View Diagnostics
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <ErrorPanel error={diagErr} />

      {!busy &&
        canRetry &&
        doc.status !== "CANCELLED" &&
        ["AI_ERROR", "NEEDS_ATTENTION", "FAILED"].includes(doc.status) && (
          <div>
            <Button
              variant="primary"
              onClick={() => (rebuildWarning ? setConfirm(true) : retry().catch(() => {}))}
              icon={<IconRotateCcw size={15} />}
            >
              {doc.status === "AI_ERROR"
                ? "Retry (Now that Ollama is running)"
                : "Retry Failed Pages"}
            </Button>
          </div>
        )}

      {confirm && (
        <Confirm
          title="Rebuild and Retry Reading?"
          confirmLabel="Retry Reading"
          body={<p>{rebuildWarning}</p>}
          onConfirm={retry}
          onClose={() => setConfirm(false)}
        />
      )}

      {diag && (
        <Modal title={`Page ${diag.page} · Model Perception Output`} wide onClose={() => setDiag(null)}>
          <p className="mb-2 text-xs font-semibold text-mute">
            Perception Status: {diag.status}. {diag.error}
          </p>
          <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-xl border border-line bg-sunken p-4 font-mono text-xs text-ink/90">
            {diag.raw || "(empty response from model)"}
          </pre>
        </Modal>
      )}
    </Card>
  );
}
