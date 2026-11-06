import { useState } from "react";
import { api } from "../api/client";
import type { ExamDetail } from "../types";
import { BUSY_DOC } from "../utils/format";
import { ErrorPanel } from "./ui";
import { IconUpload } from "./Icons";

export type ExamFileKind = "question-paper" | "answer-key";

const LABEL: Record<ExamFileKind, string> = { "question-paper": "question paper", "answer-key": "answer key" };

/** The file a tab was read from, and replacing it. Replacing reads it again; the other file is kept (a new paper
 * re-maps the existing key). */
export default function ReplaceFileBar({ exam, kind, uploading, setUploading, onReload }: {
  exam: ExamDetail;
  kind: ExamFileKind;
  uploading: ExamFileKind | null;
  setUploading: (kind: ExamFileKind | null) => void;
  onReload: () => Promise<void>;
}) {
  const [error, setError] = useState<unknown>(null);
  const doc = kind === "question-paper" ? exam.question_paper : exam.answer_key_document;
  const generating = ["QUEUED", "GENERATING"].includes(exam.generation?.status ?? "");
  const blocked = !!uploading || generating || (!!doc && BUSY_DOC.includes(doc.status));

  const replace = async (file: File | undefined) => {
    if (!file) return;
    setUploading(kind);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      await api(`/exams/${exam.id}/${kind}`, { method: "POST", form });
      await onReload();
    } catch (e) {
      setError(e);
    } finally {
      setUploading(null);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-surface px-4 py-2.5">
        <p className="min-w-0 truncate text-xs text-mute">
          {doc ? <>Read from <span className="font-medium text-ink">{doc.original_filename}</span></>
               : `No ${LABEL[kind]} uploaded yet`}
        </p>
        <label className={`inline-flex min-h-[36px] cursor-pointer items-center gap-1.5 rounded-md border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink transition-ui hover:bg-hover ${
          blocked ? "pointer-events-none opacity-50" : ""}`}>
          <IconUpload size={14} />
          {uploading === kind ? "Uploading..." : `${doc ? "Re-upload" : "Upload"} ${LABEL[kind]}`}
          <input type="file" accept=".pdf,.png,.jpg,.jpeg,.docx" className="sr-only" disabled={blocked}
                 onChange={(e) => { void replace(e.target.files?.[0]); e.target.value = ""; }} />
        </label>
      </div>
      <ErrorPanel error={error} />
    </div>
  );
}
