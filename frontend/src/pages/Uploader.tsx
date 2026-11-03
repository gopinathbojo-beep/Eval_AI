import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { api, ApiError } from "../api/client";
import { useApi } from "../hooks/useApi";
import { Button, Card, ErrorPanel, Field, Input, Loading, StatusBadge } from "../components/ui";
import { BrandLabel } from "../components/Brand";
import { IconUpload, IconX } from "../components/Icons";
import type { ScanSheet, UploaderSession } from "../types";
import { nameProblem } from "../utils/validation";

/** Centered card for the code sign-in, in the same style as the login page. */
function AuthShell({ title, sub, children }: { title: string; sub?: string; children: ReactNode }) {
  return (
    <main className="app-shell app-bg flex min-h-full flex-col items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm animate-rise">
        <div className="mb-8 flex justify-center"><BrandLabel onDark={false} /></div>
        <div className="rounded-lg border border-line bg-surface p-5 shadow-card sm:p-8">
          <h1 className="aurora-text font-display text-2xl font-semibold">{title}</h1>
          {sub && <p className="mt-1 text-sm text-mute">{sub}</p>}
          <div className="mt-6">{children}</div>
        </div>
        <p className="mt-6 text-center text-sm text-mute">
          School staff? <a href="/login" className="font-semibold text-pen underline">Sign in here</a>
        </p>
      </div>
    </main>
  );
}

const DONE = ["READY", "NEEDS_ATTENTION", "FAILED", "NEEDS_STUDENT", "CAPTURING"];

/** Uploaders sign in with the 6-character code the school gave them; they can only upload sheets to that exam.
 * Built for a phone: scan one student's sheet page by page while earlier sheets upload. */
export default function Uploader() {
  const [session, setSession] = useState<UploaderSession | null>(null);
  const [checking, setChecking] = useState(true);

  const load = useCallback(async () => {
    try {
      setSession(await api<UploaderSession>("/uploader/me"));
    } catch {
      setSession(null);
    } finally {
      setChecking(false);
    }
  }, []);
  useEffect(() => void load(), [load]);

  const [tab, setTab] = useState<"scan" | "papers">("scan");
  // every saved sheet of the exam; refreshed while any is still being read or evaluated
  const papers = useApi<{ papers: Paper[] }>(session?.uploader_name ? "/uploader/papers" : null,
    (d) => (d.papers.some((p) => !DONE.includes(p.status)) ? 5000 : null));

  // sheets move through reading on the server; refresh their status while any is in progress
  const inProgress = session?.uploads.some((u) => !DONE.includes(u.status));
  useEffect(() => {
    if (!inProgress) return;
    const t = window.setInterval(load, 5000);
    return () => window.clearInterval(t);
  }, [inProgress, load]);

  if (checking) return <Loading text="Checking your code..." />;
  if (!session) return <CodeLogin onIn={load} />;
  if (!session.uploader_name) return <NameStep exam={session.exam.name} onDone={load} />;

  const signOut = async () => {
    await api("/auth/code-logout", { method: "POST" }).catch(() => {});
    setSession(null);
  };
  const details = [session.exam.class_name && `Class ${session.exam.class_name}`, session.exam.subject]
    .filter(Boolean).join(" · ");

  return (
    <div className="app-shell app-bg min-h-full">
      <header className="sticky top-0 z-20 border-b border-line bg-surface/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-md items-center justify-between px-4">
          <span className="origin-left scale-90"><BrandLabel onDark={false} /></span>
          <Button variant="ghost" small onClick={signOut} className="min-h-[44px]">Sign out</Button>
        </div>
      </header>
      <main className="mx-auto max-w-md space-y-4 p-4 pb-10">
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wider text-mute">Uploading answer sheets for</p>
          <h1 className="mt-1 break-words font-display text-xl font-semibold text-ink">{session.exam.name}</h1>
          {details && <p className="mt-1 text-sm text-mute">{details}</p>}
          <p className="mt-2 inline-block rounded-full bg-pen-soft px-2.5 py-0.5 text-xs font-medium text-pen">
            {session.uploader_name}{session.label ? ` · ${session.label}` : ""}
          </p>
        </Card>

        <div className="grid grid-cols-2 gap-1 rounded-lg bg-sunken p-1" role="tablist" aria-label="Uploader">
          {(["scan", "papers"] as const).map((t) => (
            <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
                    className={`min-h-[44px] rounded-md text-sm font-semibold transition-ui ${
                      tab === t ? "bg-surface text-ink shadow-xs" : "text-mute hover:text-ink"}`}>
              {t === "scan" ? "Scan" : `Papers${papers.data ? ` (${papers.data.papers.length})` : ""}`}
            </button>
          ))}
        </div>

        {/* kept mounted while on Papers, so scans in progress keep uploading */}
        <div hidden={tab !== "scan"}>
          <SheetScanner onSent={async () => { await load(); await papers.reload(); }} />
        </div>
        {tab === "papers" && <PapersList data={papers.data} error={papers.error} />}
      </main>
    </div>
  );
}

type Paper = UploaderSession["uploads"][number] & { mine: boolean; uploaded_by: string };

/** Papers tab: every sheet saved for this exam, by roll number, with its progress (never marks). */
function PapersList({ data, error }: { data: { papers: Paper[] } | null; error: unknown }) {
  if (error) return <ErrorPanel error={error} />;
  if (!data) return <Loading text="Loading papers..." />;
  if (!data.papers.length)
    return <Card className="px-4 py-10 text-center text-sm text-mute">No papers yet. Scanned sheets appear here by roll number.</Card>;
  return (
    <Card>
      <ul className="divide-y divide-line">
        {data.papers.map((p) => (
          <li key={p.id} className="flex items-center justify-between gap-3 px-4 py-3">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-ink">
                {p.roll_number ? `Roll ${p.roll_number}` : "Roll not read yet"}
                {p.mine && <span className="ml-2 rounded bg-pen-soft px-1.5 py-0.5 text-[11px] font-medium text-pen">You</span>}
              </p>
              <p className="text-xs text-mute">
                {p.pages ? `${p.pages} page${p.pages > 1 ? "s" : ""} · ` : ""}{p.mine ? "by you" : `by ${p.uploaded_by}`} ·{" "}
                {new Date(p.uploaded_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </p>
              {p.note && <p className="mt-0.5 text-xs text-warn">{p.note}</p>}
            </div>
            <StatusBadge status={p.status} className="shrink-0" />
          </li>
        ))}
      </ul>
    </Card>
  );
}

/* ------------------------------------------------------------------ scanning, page by page

One student at a time: type the roll number, Start, photograph the details page (page 1), then each answer page
(Next page), End on the last one. Pages upload in the background while the next student is scanned ("bread
package"): each sheet's calls run in order, the details page of every sheet goes first, network and server errors
are retried with the photo kept until the server has it. */

type Job = { kind: "create" | "page" | "finish"; index: number; blob?: Blob };
interface QueuedSheet {
  key: number;
  roll: string;
  id: string | null;
  captured: number; // pages handed to the queue
  sent: number; // pages the server has
  ended: boolean;
  done: boolean;
  discarded: boolean;
  failed: string | null;
  jobs: Job[];
}

const sleep = (ms: number) => new Promise((r) => window.setTimeout(r, ms));
const retryable = (e: unknown) => !(e instanceof ApiError) || e.status === 0 || e.status >= 500;

function useScanQueue(onFinished: (sheet: QueuedSheet) => void) {
  const sheets = useRef<QueuedSheet[]>([]);
  const running = useRef(false);
  const seq = useRef(0);
  const [, render] = useState(0);
  const tick = () => render((n) => n + 1);
  const finished = useRef(onFinished);
  finished.current = onFinished;

  // details pages first: a sheet that is not created yet jumps ahead of other sheets' answer pages
  const next = (): QueuedSheet | undefined =>
    sheets.current.find((sh) => sh.discarded) ??
    sheets.current.find((sh) => !sh.failed && sh.id === null && sh.jobs[0]?.kind === "create") ??
    sheets.current.find((sh) => !sh.failed && sh.id !== null && sh.jobs.length > 0);

  const run = async () => {
    if (running.current) return;
    running.current = true;
    try {
      for (let sheet = next(); sheet; sheet = next()) {
        if (sheet.discarded) {  // between jobs, so no upload of this sheet is in flight
          if (sheet.id) await api(`/uploader/sheets/${sheet.id}`, { method: "DELETE" }).catch(() => {});
          const gone = sheet;
          sheets.current = sheets.current.filter((x) => x !== gone);
          tick();
          continue;
        }
        const job = sheet.jobs[0]!;
        for (let attempt = 0; ; attempt++) {
          try {
            await send(sheet, job);
            break;
          } catch (e) {
            if (!retryable(e) || attempt >= 8) {
              sheet.failed = e instanceof Error ? e.message : "Upload failed.";
              sheet.jobs = [];
              tick();
              break;
            }
            await sleep(Math.min(15000, 1000 * 2 ** attempt));
          }
        }
        if (!sheet.failed && sheet.jobs[0] === job) sheet.jobs.shift();
        tick();
      }
    } finally {
      running.current = false;
    }
  };

  const send = async (sheet: QueuedSheet, job: Job) => {
    if (job.kind === "create") {
      const form = new FormData();
      form.append("roll_number", sheet.roll);
      form.append("page", job.blob!, `roll-${sheet.roll}-p1.jpg`);
      const r = await api<ScanSheet>("/uploader/sheets", { method: "POST", form });
      sheet.id = r.id;
      sheet.sent = 1;
    } else if (job.kind === "page") {
      const form = new FormData();
      form.append("index", String(job.index));
      form.append("page", job.blob!, `roll-${sheet.roll}-p${job.index}.jpg`);
      await api(`/uploader/sheets/${sheet.id}/pages`, { method: "POST", form });
      sheet.sent = Math.max(sheet.sent, job.index);
    } else if (job.kind === "finish") {
      await api(`/uploader/sheets/${sheet.id}/finish`, { method: "POST" });
      sheet.done = true;
      finished.current(sheet);
    }
  };

  const start = (roll: string) => {
    const sheet: QueuedSheet = { key: ++seq.current, roll, id: null, captured: 0, sent: 0, ended: false, done: false,
                                 discarded: false, failed: null, jobs: [] };
    sheets.current.push(sheet);
    tick();
    return sheet;
  };
  const addPage = (sheet: QueuedSheet, blob: Blob) => {
    sheet.captured += 1;
    sheet.jobs.push({ kind: sheet.captured === 1 ? "create" : "page", index: sheet.captured, blob });
    tick();
    void run();
  };
  const end = (sheet: QueuedSheet) => {
    sheet.ended = true;
    sheet.jobs.push({ kind: "finish", index: 0 });
    tick();
    void run();
  };
  const discard = (sheet: QueuedSheet) => {
    // pages not sent yet are dropped; a sheet the server already has is deleted there (by the worker)
    sheet.discarded = true;
    sheet.ended = true;
    tick();
    void run();
  };
  const dismiss = (sheet: QueuedSheet) => {
    sheets.current = sheets.current.filter((x) => x !== sheet);
    tick();
  };
  const pending = sheets.current.some((sh) => sh.discarded || (!sh.failed && sh.jobs.length > 0));
  return { sheets: sheets.current, start, addPage, end, discard, dismiss, pending };
}

/** Longest side ≤ 2000px, JPEG 0.85: small enough to send over a phone connection, sharp enough to read. */
async function toJpeg(source: CanvasImageSource, width: number, height: number): Promise<Blob> {
  const k = Math.min(1, 2000 / Math.max(width, height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(width * k);
  canvas.height = Math.round(height * k);
  canvas.getContext("2d")!.drawImage(source, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Could not capture the photo."))), "image/jpeg", 0.85));
}

const ROLL = /^[A-Z0-9/-]{1,20}$/;

function SheetScanner({ onSent }: { onSent: () => Promise<void> }) {
  const [roll, setRoll] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [scanning, setScanning] = useState<QueuedSheet | null>(null);
  const rollInput = useRef<HTMLInputElement>(null);
  const filesInput = useRef<HTMLInputElement>(null);
  const queue = useScanQueue((sheet) => {
    setMessage(`Roll ${sheet.roll} sent (${sheet.sent} page${sheet.sent > 1 ? "s" : ""}). Enter the next roll number.`);
    void onSent();
  });

  useEffect(() => {
    if (!queue.pending) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [queue.pending]);

  const start = () => {
    const r = roll.trim();
    if (!ROLL.test(r)) return setError(new Error("Enter the student's roll number (letters and digits only)."));
    if (queue.sheets.some((sh) => sh.roll === r && !sh.failed && !sh.discarded))
      return setError(new Error(`Roll ${r} is already scanned in this session.`));
    setError(null);
    setMessage(null);
    setScanning(queue.start(r));
  };
  const finishCamera = (ended: boolean) => {
    const sheet = scanning!;
    setScanning(null);
    if (ended) {
      setMessage(`Roll ${sheet.roll}: ${sheet.captured} page${sheet.captured > 1 ? "s" : ""} captured, sending…`);
      setRoll("");
    }
    window.setTimeout(() => rollInput.current?.focus(), 50);
  };
  // one PDF is one student's whole sheet; photos (several pages, in order) follow the camera steps:
  // details page first, then each page, then finish. Either way: ask the roll number after.
  const [pdf, setPdf] = useState<File[] | null>(null);
  const [pdfRoll, setPdfRoll] = useState("");
  const pdfRollInput = useRef<HTMLInputElement>(null);
  const pickPdf = (list: FileList | null) => {
    const files = Array.from(list ?? []);
    if (!files.length) return;
    const images = files.filter((f) => f.type.startsWith("image/"));
    if (images.length && images.length !== files.length) {
      setError(new Error("Choose either one PDF, or the photos of one student's pages, not both."));
      return;
    }
    if (!images.length && files.length > 1) {
      setError(new Error("One PDF is one student's sheet. Choose one PDF at a time."));
      return;
    }
    setPdf(images.length ? images.sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true })) : files);
    setPdfRoll(roll);
    setError(null);
    setMessage(null);
    window.setTimeout(() => pdfRollInput.current?.focus(), 50);
  };
  const savePdf = async () => {
    const r = pdfRoll.trim();
    if (!pdf) return;
    if (!/^[A-Z0-9/-]{1,20}$/.test(r)) return setError(new Error("Enter the student's roll number for this PDF."));
    setBusy(true);
    setError(null);
    try {
      const isImages = pdf[0]!.type.startsWith("image/");
      if (isImages) {
        // same steps as the camera: details page first, then the other pages, then finish
        const first = new FormData();
        first.append("roll_number", r);
        first.append("page", pdf[0]!);
        const sheet = await api<{ id: string }>("/uploader/sheets", { method: "POST", form: first });
        for (let i = 1; i < pdf.length; i++) {
          const page = new FormData();
          page.append("index", String(i + 1));
          page.append("page", pdf[i]!);
          await api(`/uploader/sheets/${sheet.id}/pages`, { method: "POST", form: page });
        }
        await api(`/uploader/sheets/${sheet.id}/finish`, { method: "POST" });
      } else {
        const form = new FormData();
        form.append("files", pdf[0]!);
        form.append("roll_number", r);
        await api("/uploader/answer-sheets", { method: "POST", form });
      }
      setMessage(`Roll ${r}: ${isImages ? `${pdf.length} page${pdf.length > 1 ? "s" : ""}` : pdf[0]!.name} saved. It is in Papers and goes for evaluation.`);
      setPdf(null);
      setPdfRoll("");
      setRoll("");
      await onSent();
    } catch (e) {
      setError(e); // the file stays chosen, so it can be saved again
    } finally {
      setBusy(false);
    }
  };

  const active = queue.sheets.filter((sh) => !sh.done && !sh.discarded);
  return (
    <Card className="space-y-4 p-4">
      <div>
        <h2 className="text-base font-semibold text-ink">Scan answer sheets</h2>
        <p className="mt-1 text-sm text-mute">
          Enter the roll number and press Start. Photograph the details page first, then every answer page, and press
          End on the last page.
        </p>
      </div>
      <label className="block text-sm font-medium text-ink">
        Student roll number
        <input
          ref={rollInput}
          value={roll}
          onChange={(e) => setRoll(e.target.value.toUpperCase().replace(/[^A-Z0-9/-]/g, ""))}
          onKeyDown={(e) => e.key === "Enter" && start()}
          autoComplete="off"
          maxLength={20}
          placeholder="e.g. 24"
          className="mt-1 min-h-[48px] w-full rounded-md border border-line bg-surface px-3 text-base text-ink outline-none focus:border-pen focus:ring-2 focus:ring-pen/20"
        />
      </label>
      <Button variant="primary" className="min-h-[52px] w-full text-base" onClick={start} icon={<CameraIcon />}>
        Start scanning
      </Button>

      {active.length > 0 && (
        <ul className="space-y-1.5 rounded-md bg-sunken/70 px-3 py-2 text-sm" aria-live="polite" aria-label="Uploads in progress">
          {active.map((sh) => (
            <li key={sh.key} className="flex items-center justify-between gap-2">
              <span className={sh.failed ? "text-mark" : "text-ink"}>
                Roll {sh.roll}{" "}
                {sh.failed ? `· ${sh.failed}` : sh === scanning ? `· scanning (${sh.captured} page${sh.captured === 1 ? "" : "s"})`
                  : sh.sent === 0 ? "· waiting" : `· uploading ${sh.sent}/${sh.captured} pages`}
              </span>
              {sh.failed && (
                <button type="button" onClick={() => queue.dismiss(sh)} className="min-h-[36px] px-2 text-xs text-mute hover:text-mark">
                  Dismiss
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {message && <p role="status" className="rounded-md bg-ok-soft px-3 py-2 text-sm text-ok">{message}</p>}
      <ErrorPanel error={error} />

      <div className="border-t border-dashed border-line pt-4">
        <input ref={filesInput} type="file" accept=".pdf,.png,.jpg,.jpeg,.docx" multiple hidden
               onChange={(e) => { pickPdf(e.target.files); e.target.value = ""; }} />
        {pdf ? (
          <div className="space-y-3 rounded-md border border-line bg-surface p-3">
            <p className="truncate text-sm font-medium text-ink">
              {pdf[0]!.type.startsWith("image/")
                ? `${pdf.length} photo${pdf.length > 1 ? "s" : ""}: page 1 (details page) is ${pdf[0]!.name}`
                : pdf[0]!.name}
            </p>
            <label className="block text-sm font-medium text-ink">
              Which roll number is this sheet for?
              <input
                ref={pdfRollInput}
                value={pdfRoll}
                onChange={(e) => setPdfRoll(e.target.value.toUpperCase().replace(/[^A-Z0-9/-]/g, ""))}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), void savePdf())}
                autoComplete="off"
                maxLength={20}
                placeholder="e.g. 24"
                disabled={busy}
                className="mt-1 min-h-[48px] w-full rounded-md border border-line bg-surface px-3 text-base text-ink outline-none focus:border-pen focus:ring-2 focus:ring-pen/20"
              />
            </label>
            <div className="flex gap-2">
              <Button variant="primary" className="min-h-[48px] flex-1" busy={busy} onClick={savePdf}>
                {pdfRoll.trim() ? `Save under roll ${pdfRoll.trim()}` : "Save"}
              </Button>
              <Button variant="ghost" className="min-h-[48px]" disabled={busy} onClick={() => setPdf(null)}>Cancel</Button>
            </div>
          </div>
        ) : (
          <>
            <Button variant="soft" className="min-h-[48px] w-full" disabled={busy}
                    onClick={() => filesInput.current?.click()} icon={<IconUpload size={16} />}>
              Upload PDF or photos
            </Button>
            <p className="mt-2 text-center text-xs text-mute">
              Already scanned? Choose one student's sheet (one PDF, or the page photos in order with the details page
              first), then enter the roll number.
            </p>
          </>
        )}
      </div>

      {scanning && (
        <CameraOverlay
          sheet={scanning}
          onPage={(blob) => queue.addPage(scanning, blob)}
          onEnd={() => { queue.end(scanning); finishCamera(true); }}
          onDiscard={() => { queue.discard(scanning); finishCamera(false); }}
        />
      )}
    </Card>
  );
}

/** Full-screen camera: shutter, then Retake / Next page / End. Without a live camera (plain http, older phones)
 * each page is taken with the phone's own camera app instead. */
function CameraOverlay({ sheet, onPage, onEnd, onDiscard }: {
  sheet: QueuedSheet; onPage: (b: Blob) => void; onEnd: () => void; onDiscard: () => void;
}) {
  const live = typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia && window.isSecureContext;
  const video = useRef<HTMLVideoElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [still, setStill] = useState<{ blob: Blob; url: string } | null>(null);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [confirmClose, setConfirmClose] = useState(false);
  const page = sheet.captured + 1;

  useEffect(() => {
    if (!live) return;
    let stream: MediaStream | null = null;
    let stopped = false;
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 } }, audio: false })
      .then((s) => {
        if (stopped) return s.getTracks().forEach((t) => t.stop());
        stream = s;
        if (video.current) video.current.srcObject = s;
      })
      .catch(() => setCameraError("The camera could not be opened. Allow camera access for this site and try again."));
    return () => {
      stopped = true;
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [live]);
  useEffect(() => () => { if (still) URL.revokeObjectURL(still.url); }, [still]);

  // while a photo is being made, End and the shutter wait, so the page just taken is never lost
  const [capturing, setCapturing] = useState(false);
  const capture = async () => {
    const v = video.current;
    if (!v || !v.videoWidth || capturing) return;
    setCapturing(true);
    try {
      const blob = await toJpeg(v, v.videoWidth, v.videoHeight);
      setStill({ blob, url: URL.createObjectURL(blob) });
    } finally {
      setCapturing(false);
    }
  };
  const fromFile = async (file: File | undefined) => {
    if (!file) return;
    const bitmap = await createImageBitmap(file);
    const blob = await toJpeg(bitmap, bitmap.width, bitmap.height);
    setStill({ blob, url: URL.createObjectURL(blob) });
  };
  const keep = (thenEnd: boolean) => {
    onPage(still!.blob);
    setStill(null);
    if (thenEnd) onEnd();
  };
  const close = () => (sheet.captured > 0 || still ? setConfirmClose(true) : onDiscard());
  const big = "min-h-[52px] flex-1 rounded-full px-4 text-base font-semibold";

  return createPortal(
    <div className="fixed inset-0 z-50 flex flex-col bg-black text-white" role="dialog" aria-modal="true"
         aria-label={`Scanning roll ${sheet.roll}`}>
      <div className="flex items-center justify-between gap-3 px-4 pb-2 pt-[max(0.75rem,env(safe-area-inset-top))]">
        <p className="text-sm font-semibold">
          Roll {sheet.roll} · Page {page}{page === 1 ? " (details page)" : ""}
        </p>
        <button type="button" onClick={close} aria-label="Close camera"
                className="flex h-12 w-12 items-center justify-center rounded-full bg-white/10 hover:bg-white/20">
          <IconX size={22} />
        </button>
      </div>

      <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden">
        {/* the video stays mounted (the stream is attached once); a captured still covers it */}
        {live && !cameraError && (
          <video ref={video} playsInline muted autoPlay
                 className={`max-h-full max-w-full object-contain ${still ? "invisible" : ""}`} />
        )}
        {still ? (
          <img src={still.url} alt={`Page ${page}`} className="absolute inset-0 m-auto max-h-full max-w-full object-contain" />
        ) : live && !cameraError ? null : (
          <div className="max-w-xs px-6 text-center text-sm text-white/80">
            {cameraError ?? `Open https://${window.location.hostname}:5173 for the in-app camera. For now, each page opens your phone's camera.`}
          </div>
        )}
      </div>

      <div className="px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3">
        {still ? (
          <div className="flex gap-2">
            <button type="button" onClick={() => setStill(null)} className={`${big} bg-white/15`}>Retake</button>
            <button type="button" onClick={() => keep(false)} className={`${big} bg-white text-black`}>Next page</button>
            <button type="button" onClick={() => keep(true)} className={`${big} bg-pen text-on-pen`}>End</button>
          </div>
        ) : live && !cameraError ? (
          <div className="flex items-center justify-center gap-6">
            {sheet.captured > 0 ? (
              <button type="button" onClick={onEnd} disabled={capturing}
                      className="min-h-[48px] w-20 text-sm font-semibold text-white/80 disabled:opacity-40">End</button>
            ) : <span className="w-20" />}
            <button type="button" onClick={capture} disabled={capturing} aria-label="Take photo"
                    className="h-20 w-20 rounded-full border-4 border-white bg-white/20 active:bg-white/50 disabled:opacity-50" />
            <span className="w-20 text-center text-xs text-white/60">{sheet.captured} sent</span>
          </div>
        ) : (
          <div className="flex gap-2">
            <input ref={fileInput} type="file" accept="image/*" capture="environment" hidden
                   onChange={(e) => { void fromFile(e.target.files?.[0]); e.target.value = ""; }} />
            <button type="button" onClick={() => fileInput.current?.click()} className={`${big} bg-white text-black`}>
              Take photo of page {page}
            </button>
            {sheet.captured > 0 && <button type="button" onClick={onEnd} className={`${big} max-w-[7rem] bg-pen text-on-pen`}>End</button>}
          </div>
        )}
      </div>

      {confirmClose && (
        <div className="absolute inset-0 flex items-end justify-center bg-black/70 p-4 sm:items-center">
          <div className="w-full max-w-sm rounded-lg bg-surface p-5 text-ink">
            <p className="font-semibold">Discard this sheet?</p>
            <p className="mt-1 text-sm text-mute">The pages of roll {sheet.roll} taken so far will be removed.</p>
            <div className="mt-4 flex gap-2">
              <Button className="min-h-[48px] flex-1" onClick={() => setConfirmClose(false)}>Keep scanning</Button>
              <Button variant="danger" className="min-h-[48px] flex-1" onClick={onDiscard}>Discard</Button>
            </div>
          </div>
        </div>
      )}
    </div>,
    document.body,
  );
}

const CameraIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
    <circle cx="12" cy="13" r="4" />
  </svg>
);

/** Asked once per code: who is uploading. The school sees this name next to the code. */
function NameStep({ exam, onDone }: { exam: string; onDone: () => Promise<void> }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  return (
    <AuthShell title="Your name" sub={`You are uploading answer sheets for ${exam}.`}>
      <form
        className="space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          const problem = nameProblem(name, "Your name");
          if (problem) return setError(new Error(problem));
          setBusy(true);
          setError(null);
          try {
            await api("/uploader/name", { method: "PUT", json: { name: name.trim() } });
            await onDone();
          } catch (err) {
            setError(err);
            setBusy(false);
          }
        }}
      >
        <Field label="Your name">
          {(id) => (
            <Input id={id} autoFocus autoComplete="name" maxLength={100} placeholder="e.g. Kumar Swamy" value={name}
                   onChange={(e) => setName(e.target.value)} className="min-h-[48px] text-base" />
          )}
        </Field>
        <ErrorPanel error={error} />
        <Button type="submit" variant="primary" busy={busy} className="min-h-[52px] w-full text-base">Continue</Button>
      </form>
    </AuthShell>
  );
}

function CodeLogin({ onIn }: { onIn: () => Promise<void> }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/auth/code-login", { method: "POST", json: { code } });
      await onIn();
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };
  return (
    <AuthShell title="Upload answer sheets" sub="Enter the 6-character code from your school.">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Uploader code">
          {(id) => (
            <Input
              id={id}
              required
              autoFocus
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              inputMode="text"
              maxLength={6}
              placeholder="ABC234"
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ""))}
              className="h-14 text-center font-mono text-2xl tracking-[0.4em]"
            />
          )}
        </Field>
        <ErrorPanel error={error} />
        <Button type="submit" variant="primary" busy={busy} disabled={code.length !== 6} className="min-h-[52px] w-full text-base">
          Continue
        </Button>
      </form>
    </AuthShell>
  );
}
