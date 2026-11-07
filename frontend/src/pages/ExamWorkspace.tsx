import { useState } from "react";
import { Navigate, NavLink, Outlet, useLocation, useNavigate, useOutletContext, useParams } from "react-router-dom";
import { api, downloadFile } from "../api/client";
import type { ExamFileKind } from "../components/ReplaceFileBar";
import { useApi } from "../hooks/useApi";
import { useCrumbName } from "../context/Crumbs";
import type { ExamDetail, UploaderCode } from "../types";
import { BUSY_DOC } from "../utils/format";
import { Button, Card, Confirm, ErrorPanel, Loading, PageCanvas, PageHeader, StatusBadge } from "../components/ui";
import { IconCheckCircle, IconDownload, IconPlus, IconTrash } from "../components/Icons";
import { UploaderCodesModal } from "./exam/Codes";

export interface ExamCtx {
  exam: ExamDetail;
  reload: () => Promise<void>;
  /** still choosing and checking the paper and key: their files can be replaced */
  inSetup: boolean;
  uploading: ExamFileKind | null;
  setUploading: (kind: ExamFileKind | null) => void;
}
export const useExam = () => useOutletContext<ExamCtx>();

const SETUP = ["DRAFT", "QUESTION_PAPER_UPLOADED", "QUESTIONS_EXTRACTED", "QUESTIONS_VERIFIED", "ANSWER_KEY_UPLOADED",
               "ANSWER_KEY_VERIFIED"];
const SETUP_PATHS = ["content", "overview", "question-paper", "questions", "answer-key"];
const SHEET_PATHS = ["submissions", "students", "answer-sheets", "evaluation", "results"];

const TABS: [string, string][] = [
  ["", "Review & Finalize"],
  ["upload", "Upload"],
  ["submissions", "Students"],
];

export default function ExamWorkspace() {
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [manageCodes, setManageCodes] = useState(false);
  const [uploading, setUploading] = useState<ExamFileKind | null>(null);
  const { data, error, loading, reload } = useApi<ExamDetail>(`/exams/${id}`, (d) =>
    [d.question_paper, d.answer_key_document].some((x) => x && BUSY_DOC.includes(x.status)) ||
    ["QUEUED", "GENERATING"].includes(d.generation?.status ?? "") ? 2000 : null
  );
  useCrumbName(id, data?.name);

  const openForUpload = ["READY_FOR_EVALUATION", "EVALUATING", "REVIEW_REQUIRED"].includes(data?.status ?? "");
  const codesQuery = useApi<UploaderCode[]>(openForUpload && data?.id ? `/exams/${data.id}/uploader-codes` : null);

  if (loading) return <Loading />;
  if (error || !data) return <ErrorPanel error={error} />;

  const sub = location.pathname.split("/")[3] ?? "";
  if (sub === "codes") return <Navigate to={`/exams/${data.id}/submissions`} replace />;

  const active = (to: string) =>
    to === "" ? sub === "" || SETUP_PATHS.includes(sub) : to === "submissions" ? SHEET_PATHS.includes(sub) : sub === to;
  // Creating an exam ends with verifying its paper and key: until it is finalized, only that step is shown
  const inSetup = SETUP.includes(data.status);
  if (inSetup && sub && !SETUP_PATHS.includes(sub)) return <Navigate to={`/exams/${data.id}`} replace />;

  return (
    <PageCanvas>
      <PageHeader
        title={data.name}
        top={inSetup ? <SetupSteps exam={data} /> : undefined}
        badge={
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={data.status} />
            {openForUpload && (
              <div className="inline-flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setManageCodes(true)}
                  className="inline-flex items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50/80 px-2.5 py-1 text-xs font-semibold text-blue-700 hover:bg-blue-100 hover:border-blue-300 transition-all cursor-pointer shadow-2xs"
                  title="Manage uploader codes"
                >
                  <span>Uploader Codes:</span>
                  <span className="inline-flex h-4 min-w-[1.1rem] items-center justify-center rounded-full bg-blue-600 px-1 text-[10px] font-bold text-white">
                    {codesQuery.data?.length ?? 0}
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => setManageCodes(true)}
                  aria-label="Add uploader code"
                  title="Add uploader code"
                  className="inline-flex h-6 w-6 items-center justify-center rounded-full border border-blue-200 bg-white text-blue-600 hover:bg-blue-600 hover:text-white hover:border-blue-600 transition-all cursor-pointer shadow-2xs"
                >
                  <IconPlus size={13} strokeWidth={2.5} />
                </button>
              </div>
            )}
          </div>
        }
        sub={[data.class_name && `Class ${data.class_name}`, data.subject_name, data.academic_year,
              `${data.total_marks} marks`].filter(Boolean).join(" · ")}
        actions={
          <Button small variant="ghost" className="text-mark hover:bg-mark-soft hover:text-mark"
                  onClick={() => setConfirmDelete(true)} icon={<IconTrash size={15} />}>
            Delete
          </Button>
        }
      />

      {inSetup && <FinalizeBanner exam={data} uploading={uploading}
                                  onDone={async () => { await reload(); navigate(`/exams/${data.id}/submissions`); }} />}

      {!inSetup && (
        <nav className="flex gap-2 overflow-x-auto border-b border-slate-100 pb-3" aria-label="Exam sections">
          {TABS.filter(([to]) => to !== "upload" || openForUpload).map(([to, tabText]) => {
            const isAct = active(to);
            return (
              <NavLink
                key={to}
                to={to ? `/exams/${id}/${to}` : `/exams/${id}`}
                end={to === ""}
                className={`whitespace-nowrap rounded-full px-4 py-2 text-xs sm:text-sm font-semibold transition-all ${
                  isAct
                    ? "bg-blue-600 text-white shadow-sm shadow-blue-500/25"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }`}
              >
                {tabText}
              </NavLink>
            );
          })}
        </nav>
      )}

      <div>
        <Outlet context={{ exam: data, reload: async () => { await reload(); }, inSetup, uploading, setUploading } satisfies ExamCtx} />
      </div>

      {manageCodes && (
        <UploaderCodesModal
          exam={data}
          onClose={() => {
            setManageCodes(false);
            void codesQuery.reload();
          }}
          onUpdated={() => {
            void codesQuery.reload();
          }}
        />
      )}

      {confirmDelete && (
        <Confirm
          title={`Delete exam “${data.name}”?`}
          danger
          confirmLabel="Delete exam"
          body={
            <div className="space-y-2 text-sm text-ink">
              <p>This permanently deletes <b>{data.name}</b>.</p>
              <p className="text-xs text-mute">
                Its questions, answer key, uploaded answer sheets and evaluations are removed too. This cannot be undone.
              </p>
            </div>
          }
          onConfirm={async () => {
            await api(`/exams/${data.id}`, { method: "DELETE" });
            navigate("/exams");
          }}
          onClose={() => setConfirmDelete(false)}
        />
      )}
    </PageCanvas>
  );
}

/** Where exam creation stands: details and files, then verifying both, then finalize. */
function SetupSteps({ exam }: { exam: ExamDetail }) {
  const docs = [exam.question_paper, exam.answer_key_document];
  const reading = docs.some((d) => !d || BUSY_DOC.includes(d.status));
  const steps = [
    { label: "Details & files", done: docs.every(Boolean) },
    { label: "Verify questions & answer key", done: false, current: true },
    { label: "Finalize & continue", done: false },
  ];
  return (
    <ol className="flex flex-wrap items-center gap-2 text-xs" aria-label="Exam creation steps">
      {steps.map((st, i) => (
        <li key={st.label} className="flex items-center gap-2">
          {i > 0 && <span aria-hidden className="h-px w-6 bg-line" />}
          <span className={`flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-semibold ${
            st.done ? "bg-ok text-white" : st.current ? "bg-pen text-on-pen" : "border border-line text-mute"}`}>
            {st.done ? "✓" : i + 1}
          </span>
          <span className={st.current ? "font-semibold text-ink" : "text-mute"}>
            {st.label}{st.current && reading ? " (reading…)" : ""}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** Setup is one step: both files are read in parallel; the school checks them below, then finalizes. */
function FinalizeBanner({ exam, onDone, uploading }: {
  exam: ExamDetail; onDone: () => Promise<void>; uploading: ExamFileKind | null;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const docs = [exam.question_paper, exam.answer_key_document];
  const generating = ["QUEUED", "GENERATING"].includes(exam.generation?.status ?? "");
  const reading = generating || docs.some((d) => d && BUSY_DOC.includes(d.status));
  const missing = !generating && docs.some((d) => !d);
  const finalize = async () => {
    setBusy(true);
    setError(null);
    try {
      await api(`/exams/${exam.id}/finalize-setup`, { method: "POST" });
      await onDone();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card className="p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-ink">
            {generating ? "Generating the question paper and answer key with AI..."
              : missing ? "Upload the question paper and answer key, or generate them with AI"
              : reading ? "Reading the question paper and answer key..." : "Check the questions and answer key, then finalize"}
          </p>
          <p className="mt-1 text-sm text-mute">
            {generating
              ? `${exam.generation?.stage || "Starting"}. The questions and answer key appear in the Questions tab when they are ready; a full paper takes about 3-5 minutes.`
              : missing
              ? "Both files are needed before the exam can be finalized. To have the AI write them, use \"Generate with AI\" in the Questions tab."
              : reading
                ? "Both are read at the same time. This page updates by itself."
                : `${exam.question_count} questions found. Check the questions and the answer key below and fix anything that looks wrong, then finalize to continue to answer sheets.`}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {(exam.question_paper || exam.answer_key_document) && (
            <Button small variant="soft" icon={<IconDownload size={14} />}
                    title="Everything the AI read from the paper and key, with its review notes"
                    onClick={() => downloadFile(`/exams/${exam.id}/extraction-report.pdf`,
                      `${exam.name.replace(/[^a-zA-Z0-9_-]/g, "_")}_Extraction_Report.pdf`).catch((e) => setError(e))}>
              Download extraction report
            </Button>
          )}
          <Button variant="primary" busy={busy} disabled={missing || reading || !!uploading} onClick={finalize}
                  icon={<IconCheckCircle size={16} />}>
            Finalize &amp; continue
          </Button>
        </div>
      </div>
      {error ? <div className="mt-4"><ErrorPanel error={error} /></div> : null}
    </Card>
  );
}
