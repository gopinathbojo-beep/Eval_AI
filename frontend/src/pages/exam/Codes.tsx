import { useState } from "react";
import { api } from "../../api/client";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import { Button, Confirm, Empty, ErrorPanel, Field, Input, Loading, Modal, Table } from "../../components/ui";
import { IconCheckCircle, IconCopy, IconPlus } from "../../components/Icons";
import type { ExamDetail, UploaderCode } from "../../types";

const OPEN = ["READY_FOR_EVALUATION", "EVALUATING", "REVIEW_REQUIRED"];

export interface UploaderCodesModalProps {
  exam: ExamDetail;
  onClose: () => void;
  onUpdated?: () => void;
}

/** Modal dialog to manage uploader codes for an exam */
export function UploaderCodesModal({ exam, onClose, onUpdated }: UploaderCodesModalProps) {
  const toast = useToast();
  const open = OPEN.includes(exam.status);
  const codes = useApi<UploaderCode[]>(`/exams/${exam.id}/uploader-codes`);
  const [tab, setTab] = useState<"single" | "multiple">("single");
  const [singleLabel, setSingleLabel] = useState("");
  const [multipleText, setMultipleText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [removing, setRemoving] = useState<UploaderCode | null>(null);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);

  const parsedMultiple = multipleText
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);

  const createSingle = async () => {
    setBusy(true);
    setError(null);
    try {
      const name = singleLabel.trim() || "Uploader";
      await api(`/exams/${exam.id}/uploader-codes`, {
        method: "POST",
        json: { labels: [name] },
      });
      setSingleLabel("");
      toast(`Created uploader code for ${name}.`);
      await codes.reload();
      onUpdated?.();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const createMultiple = async () => {
    if (parsedMultiple.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/exams/${exam.id}/uploader-codes`, {
        method: "POST",
        json: { labels: parsedMultiple },
      });
      setMultipleText("");
      toast(`Successfully created ${parsedMultiple.length} uploader ${parsedMultiple.length === 1 ? "code" : "codes"}.`);
      await codes.reload();
      onUpdated?.();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const regenerate = async (c: UploaderCode) => {
    try {
      await api(`/uploader-codes/${c.id}/regenerate`, { method: "POST" });
      toast("New code created. The previous code no longer works.");
      await codes.reload();
      onUpdated?.();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Could not regenerate the code.", "mark");
    }
  };

  const copy = async (code: string) => {
    await navigator.clipboard?.writeText(code).catch(() => {});
    setCopiedCode(code);
    setTimeout(() => setCopiedCode((prev) => (prev === code ? null : prev)), 2000);
    toast(`Copied ${code}`);
  };

  const remove = async () => {
    if (!removing) return;
    try {
      await api(`/uploader-codes/${removing.id}`, { method: "DELETE" });
      toast(`Removed code ${removing.code}`);
      setRemoving(null);
      await codes.reload();
      onUpdated?.();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Could not remove code.", "mark");
    }
  };

  return (
    <Modal
      title="Manage Uploader Codes"
      wide
      onClose={onClose}
      footer={
        <Button variant="secondary" onClick={onClose}>
          Done
        </Button>
      }
    >
      <div className="space-y-5">
        {/* Portal link banner */}
        <div className="rounded-xl border border-blue-100 bg-blue-50/70 p-4 text-xs sm:text-sm text-slate-700">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <p className="font-semibold text-slate-900">Uploader Portal</p>
              <p className="text-slate-600 mt-0.5">
                Uploaders open <span className="font-semibold text-blue-700">{window.location.origin}/upload</span> and sign in with their 6-character code. They can only upload answer sheets to this exam.
              </p>
            </div>
            <button
              type="button"
              onClick={() => copy(`${window.location.origin}/upload`)}
              className="inline-flex items-center gap-1.5 self-start sm:self-auto rounded-lg border border-blue-200 bg-white px-3 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-50 transition-colors shadow-2xs cursor-pointer shrink-0"
            >
              <IconCopy size={13} />
              <span>Copy Link</span>
            </button>
          </div>
        </div>

        {!open ? (
          <Empty
            title={exam.status === "FINALIZED" ? "This exam is closed" : "Finalize the exam first"}
            hint={
              exam.status === "FINALIZED"
                ? "Uploader codes stopped working when the exam was closed."
                : "Uploader codes can be created once the questions and answer key are finalized."
            }
          />
        ) : (
          <>
            {/* Create uploader(s) form */}
            <div className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-4 space-y-3.5">
              <div className="flex items-center justify-between border-b border-slate-200/80 pb-2.5">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setTab("single");
                      setError(null);
                    }}
                    className={`rounded-lg px-3 py-1 text-xs font-semibold transition-all cursor-pointer ${
                      tab === "single"
                        ? "bg-white text-blue-700 shadow-xs border border-blue-200"
                        : "text-slate-600 hover:text-slate-900 hover:bg-slate-200/50"
                    }`}
                  >
                    Single Uploader
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setTab("multiple");
                      setError(null);
                    }}
                    className={`rounded-lg px-3 py-1 text-xs font-semibold transition-all cursor-pointer ${
                      tab === "multiple"
                        ? "bg-white text-blue-700 shadow-xs border border-blue-200"
                        : "text-slate-600 hover:text-slate-900 hover:bg-slate-200/50"
                    }`}
                  >
                    Add Multiple Uploaders
                  </button>
                </div>
              </div>

              {tab === "single" ? (
                <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                  <div className="flex-1">
                    <Field label="Uploader Name or Room" hint="Who will use this code">
                      {(id) => (
                        <Input
                          id={id}
                          maxLength={100}
                          placeholder="e.g. Room 4 invigilator, Mr. Kumar"
                          value={singleLabel}
                          onChange={(e) => setSingleLabel(e.target.value)}
                          onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), void createSingle())}
                        />
                      )}
                    </Field>
                  </div>
                  <Button variant="primary" busy={busy} onClick={createSingle} icon={<IconPlus size={16} />}>
                    Create code
                  </Button>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label className="text-[13px] font-semibold text-slate-800">
                        Multiple Uploader Names
                      </label>
                      <span className="text-xs text-slate-500">Separated by line breaks or commas</span>
                    </div>
                    <textarea
                      rows={3}
                      aria-label="Multiple uploader names"
                      placeholder={`Room 101\nRoom 102\nRoom 103\nMr. Sharma`}
                      value={multipleText}
                      onChange={(e) => setMultipleText(e.target.value)}
                      className="w-full rounded-xl border border-slate-200 bg-white p-3 text-sm text-slate-800 placeholder:text-slate-400 shadow-xs focus:border-blue-500 focus:ring-2 focus:ring-blue-100 focus:outline-none"
                    />
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs font-medium text-slate-500">
                      {parsedMultiple.length === 0
                        ? "No names entered yet"
                        : `${parsedMultiple.length} uploader ${parsedMultiple.length === 1 ? "code" : "codes"} will be created`}
                    </span>
                    <Button
                      variant="primary"
                      busy={busy}
                      disabled={parsedMultiple.length === 0}
                      onClick={createMultiple}
                      icon={<IconPlus size={16} />}
                    >
                      Create {parsedMultiple.length > 0 ? `${parsedMultiple.length} ` : ""}codes
                    </Button>
                  </div>
                </div>
              )}

              {error ? <ErrorPanel error={error} /> : null}
            </div>

            {/* Existing codes table */}
            <div>
              <div className="flex items-center justify-between mb-2.5">
                <h3 className="text-sm font-bold text-slate-900">
                  Active Uploader Codes ({codes.data?.length ?? 0})
                </h3>
              </div>
              {codes.loading ? (
                <Loading text="Loading uploader codes..." />
              ) : codes.error ? (
                <ErrorPanel error={codes.error} />
              ) : (
                <Table
                  head={["Uploader", "Code", "Signed in as", "Sheets uploaded", ""]}
                  rows={(codes.data ?? []).map((c) => ({
                    key: c.id,
                    cells: [
                      <span className="font-semibold text-slate-900">{c.label || "Uploader"}</span>,
                      <button
                        type="button"
                        onClick={() => copy(c.code)}
                        title="Copy code"
                        className="group inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1 font-mono text-xs font-bold tracking-[0.25em] text-slate-800 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 transition-colors cursor-pointer"
                      >
                        <span>{c.code}</span>
                        {copiedCode === c.code ? (
                          <IconCheckCircle size={13} className="text-emerald-600" />
                        ) : (
                          <IconCopy size={13} className="text-slate-400 group-hover:text-blue-600" />
                        )}
                      </button>,
                      c.uploader_name ? (
                        <span className="font-medium text-slate-800">{c.uploader_name}</span>
                      ) : (
                        <span className="text-xs text-slate-400 italic">Not yet</span>
                      ),
                      <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">
                        {c.uploads}
                      </span>,
                      <div className="flex justify-end gap-1">
                        <Button small variant="ghost" onClick={() => regenerate(c)} title="Generate replacement code">
                          Regenerate
                        </Button>
                        <Button
                          small
                          variant="ghost"
                          className="text-red-600 hover:bg-red-50 hover:text-red-700"
                          onClick={() => setRemoving(c)}
                        >
                          Remove
                        </Button>
                      </div>,
                    ],
                  }))}
                  empty={
                    <Empty
                      title="No uploader codes yet"
                      hint="Create one code for each person or room who will upload answer sheets."
                    />
                  }
                />
              )}
            </div>
          </>
        )}

        {removing && (
          <Confirm
            title={`Remove code ${removing.code}?`}
            danger
            confirmLabel="Remove"
            body={<p>The code stops working at once. Sheets it already uploaded stay in the exam.</p>}
            onConfirm={remove}
            onClose={() => setRemoving(null)}
          />
        )}
      </div>
    </Modal>
  );
}
