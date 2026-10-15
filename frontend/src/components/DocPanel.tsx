import { useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { DocInfo } from "../types";
import { BUSY_DOC } from "../utils/format";
import { Button, Card, Confirm, ErrorPanel, Modal, ProgressBar, StatusBadge } from "./ui";

export function UploadZone({ accept, disabled, onFile, hint }: { accept: string; disabled?: boolean; onFile: (f: File) => Promise<void>; hint?: ReactNode }) {
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const send = async (f: File | undefined) => {
    if (!f) return;
    setBusy(true); setError(null);
    try { await onFile(f); } catch (e) { setError(e); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-3">
      <label onDragOver={(e) => { e.preventDefault(); if (!disabled) setDrag(true); }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); if (!disabled) send(e.dataTransfer.files[0]); }}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 text-center transition-colors ${disabled ? "cursor-not-allowed opacity-50" : "hover:border-pen"} ${drag ? "border-pen bg-pen-soft" : "border-line"}`}>
        <input type="file" className="sr-only" accept={accept} disabled={disabled || busy} onChange={(e) => { send(e.target.files?.[0]); e.target.value = ""; }} />
        <span className="font-medium">{busy ? "Uploading…" : "Drag a file here, or choose one"}</span>
        <span className="mt-1 text-sm text-mute">{hint}</span>
      </label>
      <ErrorPanel error={error} />
    </div>
  );
}

const STEPS = ["Uploaded", "Rendering pages", "Reading pages", "Checking results", "Ready to review"];
function stepIndex(d: DocInfo) {
  switch (d.status) {
    case "UPLOADED": return 0; case "RENDERING": return 1; case "OCR_PROCESSING": return 2; case "EXTRACTING": return 3;
    case "READY": case "NEEDS_ATTENTION": return 4; default: return 2;
  }
}

export function DocProgress({ doc, onChanged, rebuildWarning, canRetry = true, actions }: { doc: DocInfo; onChanged: () => void; rebuildWarning?: string; canRetry?: boolean; actions?: ReactNode }) {
  const [confirm, setConfirm] = useState(false);
  const [diag, setDiag] = useState<{ page: number; status: string; error: string | null; raw: string } | null>(null);
  const [diagErr, setDiagErr] = useState<unknown>(null);
  const busy = BUSY_DOC.includes(doc.status);
  const prevBusy = useRef(busy);

  useEffect(() => {
    if (prevBusy.current && !busy && (doc.status === "READY" || doc.status === "NEEDS_ATTENTION")) {
      onChanged();
    }
    prevBusy.current = busy;
  }, [busy, doc.status, onChanged]);
  const failedPages = doc.pages.filter((p) => p.ocr_status && !["OK", "PENDING"].includes(p.ocr_status));
  const step = stepIndex(doc);
  const retry = async () => { await api(`/documents/${doc.kind}/${doc.id}/reprocess`, { method: "POST" }); onChanged(); };
  const [cancelling, setCancelling] = useState(false);
  const [cancelErr, setCancelErr] = useState<unknown>(null);
  const cancel = async () => {
    setCancelling(true); setCancelErr(null);
    try { await api(`/documents/${doc.kind}/${doc.id}/cancel`, { method: "POST" }); onChanged(); }
    catch (e) { setCancelErr(e); }
    finally { setCancelling(false); }
  };
  const openDiag = async (n: number) => {
    setDiagErr(null);
    try { setDiag({ page: n, ...(await api<{ status: string; error: string | null; raw: string }>(`/documents/${doc.kind}/${doc.id}/pages/${n}/ocr`)) }); }
    catch (e) { setDiagErr(e); }
  };
  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><p className="font-medium">{doc.original_filename}</p><p className="text-xs text-mute">{doc.pages.length || "?"} page(s)</p></div>
        <div className="flex items-center gap-2">
          {actions}
          <StatusBadge status={doc.status} />
        </div>
      </div>
      {busy && (
        <div className="mt-4 space-y-2">
          <ol className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
            {STEPS.map((s, i) => <li key={s} className={i < step ? "text-ok" : i === step ? "font-semibold text-pen" : "text-mute"}>{i < step ? "✓ " : ""}{s}</li>)}
          </ol>
          <ProgressBar value={doc.progress_current} max={Math.max(doc.progress_total, 1)} />
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm text-mute" aria-live="polite">{doc.stage}</p>
            {["UPLOADED", "RENDERING", "OCR_PROCESSING"].includes(doc.status) && <Button small busy={cancelling} onClick={cancel}>Cancel</Button>}
          </div>
          <ErrorPanel error={cancelErr} />
        </div>
      )}
      {doc.error_message && !busy && (
        <div className="mt-3 rounded border border-mark/40 bg-mark-soft p-3 text-sm text-mark" role="alert">{doc.error_message}</div>
      )}
      {failedPages.length > 0 && !busy && (
        <ul className="mt-3 space-y-1 text-sm">
          {failedPages.map((p) => (
            <li key={p.page_number} className="flex items-center gap-2">
              <span>Page {p.page_number}:</span><StatusBadge status={p.ocr_status!} />
              <Button small variant="ghost" onClick={() => openDiag(p.page_number)}>Show diagnostics</Button>
            </li>
          ))}
        </ul>
      )}
      <ErrorPanel error={diagErr} />
      {!busy && canRetry && ["AI_ERROR", "NEEDS_ATTENTION", "FAILED", "CANCELLED"].includes(doc.status) && (
        <div className="mt-3"><Button variant="primary" onClick={() => (rebuildWarning ? setConfirm(true) : retry().catch(() => {}))}>
          {doc.status === "AI_ERROR" ? "Retry now that Ollama is running" : doc.status === "CANCELLED" ? "Continue reading" : "Retry failed pages"}</Button></div>
      )}
      {confirm && <Confirm title="Retry reading" confirmLabel="Retry" body={<p>{rebuildWarning}</p>} onConfirm={retry} onClose={() => setConfirm(false)} />}
      {diag && (
        <Modal title={`Page ${diag.page} · model output`} wide onClose={() => setDiag(null)}>
          <p className="mb-2 text-sm text-mute">Status {diag.status}. {diag.error}</p>
          <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded bg-sunken p-3 text-xs">{diag.raw || "(empty response)"}</pre>
        </Modal>
      )}
    </Card>
  );
}
