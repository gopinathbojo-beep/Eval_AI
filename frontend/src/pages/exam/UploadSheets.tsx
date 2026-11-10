import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { Button, Card, ErrorPanel } from "../../components/ui";
import { IconCheckCircle, IconTrash, IconUpload } from "../../components/Icons";
import { useExam } from "../ExamWorkspace";

const TAKES_SHEETS = ["ANSWER_KEY_VERIFIED", "READY_FOR_EVALUATION", "EVALUATING", "REVIEW_REQUIRED"];
const FILE_TYPES = /\.(pdf|docx)$/i;
const PHOTO_TYPES = /\.(png|jpe?g)$/i;

interface Row {
  key: number;
  files: File[];
  photos: boolean;
  roll: string;
  state: "waiting" | "sending" | "sent" | "failed";
  error?: unknown;
}

const cleanRoll = (v: string) => v.toUpperCase().replace(/[^A-Z0-9/-]/g, "");
const byName = (a: File, b: File) => a.name.localeCompare(b.name, undefined, { numeric: true });

/** The school's own way to send answer sheets, beside the uploader app. One row is one student: a PDF or Word file,
 * or the photos of their pages. A typed roll number decides the student; left blank, it is read from the sheet. */
export default function UploadSheets() {
  const { exam, reload } = useExam();
  const [rows, setRows] = useState<Row[]>([]);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const nextKey = useRef(1);

  // leaving the page would cancel the file being sent
  useEffect(() => {
    if (!busy) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [busy]);

  const addFiles = (chosen: File[]) => {
    const photos = chosen.filter((f) => PHOTO_TYPES.test(f.name)).sort(byName);
    const others = chosen.filter((f) => FILE_TYPES.test(f.name));
    const skipped = chosen.length - photos.length - others.length;
    setError(skipped ? new Error(`${skipped} file${skipped > 1 ? "s were" : " was"} skipped. Use PDF, Word, JPG or PNG files.`) : null);
    setRows((now) => {
      const isNew = (f: File) => !now.some((r) => r.state !== "sent" && r.files.some((x) => x.name === f.name && x.size === f.size));
      const next = [...now];
      for (const f of others.filter(isNew)) {
        next.push({ key: nextKey.current++, files: [f], photos: false, roll: "", state: "waiting" });
      }
      const newPhotos = photos.filter(isNew);
      if (newPhotos.length) {
        const open = next.findIndex((r) => r.photos && r.state !== "sent" && r.state !== "sending");
        if (open >= 0) next[open] = { ...next[open]!, files: [...next[open]!.files, ...newPhotos].sort(byName) };
        else next.push({ key: nextKey.current++, files: newPhotos, photos: true, roll: "", state: "waiting" });
      }
      return next;
    });
  };

  const patch = (key: number, change: Partial<Row>) =>
    setRows((now) => now.map((r) => (r.key === key ? { ...r, ...change } : r)));

  const send = async (row: Row) => {
    const form = new FormData();
    if (row.roll) form.append("roll_number", row.roll);
    if (row.photos) {
      row.files.forEach((f) => form.append("files", f));
      await api(`/exams/${exam.id}/answer-sheets/photos`, { method: "POST", form });
    } else {
      form.append("file", row.files[0]!);
      await api(`/exams/${exam.id}/answer-sheets`, { method: "POST", form });
    }
  };

  const pending = rows.filter((r) => r.state === "waiting" || r.state === "failed");
  const sent = rows.filter((r) => r.state === "sent").length;

  const uploadAll = async () => {
    const rolls = pending.map((r) => r.roll).filter(Boolean);
    const twice = rolls.find((r, i) => rolls.indexOf(r) !== i);
    if (twice) return setError(new Error(`Roll number ${twice} is listed twice. Each student has one answer sheet.`));
    setError(null);
    setBusy(true);
    for (const row of pending) {  // one at a time, so a slow connection is not swamped and each row reports its own result
      patch(row.key, { state: "sending", error: undefined });
      try {
        await send(row);
        patch(row.key, { state: "sent" });
      } catch (e) {
        patch(row.key, { state: "failed", error: e });  // stays chosen, so it can be fixed and sent again
      }
    }
    setBusy(false);
    await reload();
  };

  if (!TAKES_SHEETS.includes(exam.status)) {
    return (
      <Card className="p-5 text-sm text-mute">
        {exam.status === "FINALIZED" ? "This exam is finalized, so it no longer takes answer sheets."
                                     : "Answer sheets can be uploaded once the exam questions and answer key are verified."}
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      <Card className="space-y-1 p-5 shadow-soft">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1 space-y-1">
            <h2 className="text-lg font-semibold text-ink">Upload answer sheets</h2>
            <p className="text-xs text-mute">
              Choose one PDF or Word file per student, or all the photos of one student's pages. Enter each roll number,
              or leave it blank to have it read from the sheet. If it can't be read, the sheet waits in Students for you
              to choose the student.
            </p>
          </div>
          <BulkUpload examId={exam.id} disabled={busy} onDone={reload} />
        </div>
      </Card>

      <label
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); addFiles([...e.dataTransfer.files]); }}
        className={`flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed p-8 text-center transition-ui ${
          dragging ? "border-pen bg-pen/5" : "border-line bg-surface hover:bg-hover"}`}
      >
        <IconUpload size={22} />
        <span className="text-sm font-semibold text-ink">Choose files or drop them here</span>
        <span className="text-xs text-mute">PDF, Word, JPG or PNG</span>
        <input
          type="file"
          multiple
          accept=".pdf,.docx,.png,.jpg,.jpeg"
          className="sr-only"
          aria-label="Choose answer sheets"
          onChange={(e) => { addFiles([...(e.target.files ?? [])]); e.target.value = ""; }}
        />
      </label>

      <ErrorPanel error={error} />

      {rows.length > 0 && (
        <Card className="divide-y divide-line shadow-soft">
          {rows.map((row) => {
            const locked = busy || row.state === "sent";
            return (
              <div key={row.key} className="space-y-2 px-4 py-3">
                <div className="flex flex-wrap items-center gap-3">
                  <p className="min-w-[10rem] flex-1 truncate text-sm text-ink">
                    {row.photos ? `${row.files.length} photo${row.files.length > 1 ? "s" : ""} of one student` : row.files[0]!.name}
                  </p>
                  <input
                    value={row.roll}
                    disabled={locked}
                    maxLength={20}
                    placeholder="Roll no. (optional)"
                    aria-label={`Roll number for ${row.files[0]!.name}`}
                    onChange={(e) => patch(row.key, { roll: cleanRoll(e.target.value) })}
                    className="min-h-[36px] w-40 rounded-md border border-line bg-surface px-3 text-sm text-ink outline-none focus:border-pen focus:ring-2 focus:ring-pen/20 disabled:opacity-60"
                  />
                  <span className="w-20 text-xs text-mute">
                    {row.state === "sending" ? "Uploading..." : row.state === "failed" ? "Not sent" : row.state === "sent" ? (
                      <span className="inline-flex items-center gap-1 text-ok"><IconCheckCircle size={14} /> Sent</span>
                    ) : "Ready"}
                  </span>
                  <Button
                    small
                    variant="soft"
                    disabled={locked}
                    aria-label={`Remove ${row.files[0]!.name}`}
                    icon={<IconTrash size={14} />}
                    onClick={() => setRows((now) => now.filter((r) => r.key !== row.key))}
                  >
                    Remove
                  </Button>
                </div>
                {row.state === "failed" && <ErrorPanel error={row.error} />}
              </div>
            );
          })}
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
            <p className="text-xs text-mute">
              {sent > 0 && !busy ? (
                <>
                  {sent} sent. Reading and grading has started; follow them in{" "}
                  <Link className="font-semibold text-pen underline" to={`/exams/${exam.id}/submissions`}>Students</Link>.
                </>
              ) : busy ? "Keep this page open until every file is sent." : ""}
            </p>
            <Button variant="primary" busy={busy} disabled={!pending.length} icon={<IconUpload size={16} />} onClick={uploadAll}>
              Upload {pending.length || ""} {pending.length === 1 ? "sheet" : "sheets"}
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}


const BULK_BATCH = 20; // files per request, so one slow request never holds the whole batch

/** Many students' sheets at once, one PDF or Word file per student (photos go through the picker below): nothing to type, each roll number and name is read from
 * its sheet. A sheet whose roll number can't be read waits in Students for the school to choose the student. */
function BulkUpload({ examId, disabled, onDone }: { examId: string; disabled: boolean; onDone: () => Promise<void> | void }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    if (!busy) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [busy]);

  const upload = async (chosen: File[]) => {
    const files = chosen.filter((f) => FILE_TYPES.test(f.name)); // no photos: one student's pages need the picker below
    const skipped = chosen.length - files.length;
    setError(null);
    setNote(null);
    if (!files.length) return setError(new Error("Bulk upload takes PDF or Word files only. Upload photos with the picker below."));
    setBusy(true);
    let sentCount = 0;
    try {
      for (let i = 0; i < files.length; i += BULK_BATCH) {
        const form = new FormData();
        files.slice(i, i + BULK_BATCH).forEach((f) => form.append("files", f));
        setNote(`Uploading ${Math.min(i + BULK_BATCH, files.length)} of ${files.length}...`);
        const r = await api<{ uploaded: number }>(`/exams/${examId}/answer-sheets/bulk`, { method: "POST", form });
        sentCount += r.uploaded;
      }
      setNote(
        `${sentCount} sheet${sentCount === 1 ? "" : "s"} uploaded. Roll numbers are being read from the sheets` +
          (skipped ? `; ${skipped} file${skipped > 1 ? "s were" : " was"} skipped (bulk upload takes PDF or Word files only; upload photos with the picker below).` : "."),
      );
    } catch (e) {
      setError(e);
      if (sentCount) setNote(`${sentCount} sheet${sentCount === 1 ? "" : "s"} uploaded before the error.`);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
      await onDone();
    }
  };

  return (
    <div className="flex max-w-xs flex-col items-end gap-1 text-right">
      <Button variant="primary" busy={busy} disabled={disabled} icon={<IconUpload size={16} />} onClick={() => input.current?.click()}>
        Bulk upload
      </Button>
      <span className="text-xs text-mute">PDF or Word, one file per student. No roll numbers to enter: they are read from each sheet.</span>
      <input
        ref={input}
        type="file"
        multiple
        accept=".pdf,.docx"
        className="sr-only"
        aria-label="Bulk upload answer sheets"
        onChange={(e) => upload([...(e.target.files ?? [])])}
      />
      {note && <span className="text-xs text-ink">{note}</span>}
      <ErrorPanel error={error} />
    </div>
  );
}
