import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, downloadFile } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useCrumbName } from "../context/Crumbs";
import type { EvaluationDetail } from "../types";
import { BUSY_DOC, nameIsRoll } from "../utils/format";
import {
  Button,
  ErrorPanel,
  Loading,
  PageHeader,
  StatusBadge,
} from "../components/ui";
import { MappingTab } from "./evaluation/MappingTab";
import { MarksTab } from "./evaluation/MarksTab";
import { DocProgress } from "../components/DocPanel";
import { DeleteSheetConfirm } from "../components/DeleteSheetConfirm";
import {
  IconCheckCircle,
  IconFileText,
  IconRotateCcw,
  IconDownload,
  IconTrash,
} from "../components/Icons";

type Tab = "mapping" | "marks";

export default function EvaluationPage() {
  const { id } = useParams();
  const { data, error, loading, reload } = useApi<EvaluationDetail>(
    `/evaluations/${id}`,
    (d) => (d.evaluation.run_status === "RUNNING" || BUSY_DOC.includes(d.document.status) ? 1500 : null)
  );
  const [tab, setTab] = useState<Tab>("mapping");
  const [deleting, setDeleting] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloadErr, setDownloadErr] = useState<unknown>(null);
  const [reopening, setReopening] = useState(false);
  const nav = useNavigate();
  useCrumbName(id, data?.evaluation.student.name);

  if (loading) return <Loading text="Loading evaluation workspace..." />;
  if (error || !data) return <ErrorPanel error={error} />;

  const ev = data.evaluation;
  const reading = BUSY_DOC.includes(data.document.status);

  const reopen = async () => {
    setReopening(true);
    setDownloadErr(null);
    try {
      await api(`/evaluations/${ev.id}/reopen`, { method: "POST" });
      await reload();
      setTab("marks");
    } catch (e) {
      setDownloadErr(e);
    } finally {
      setReopening(false);
    }
  };

  const download = async () => {
    setDownloading(true);
    setDownloadErr(null);
    try {
      const roll = (ev.student.roll_number || "sheet").replace(/[^A-Za-z0-9_-]/g, "_");
      await downloadFile(
        `/evaluations/${ev.id}/extraction-report.pdf?part=${tab}`,
        `${roll}_${tab === "mapping" ? "Mapping_Review" : "Marks_Review"}.pdf`
      );
    } catch (e) {
      setDownloadErr(e);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="space-y-5">
      {/* Page Header */}
      <PageHeader
        title={
          <div className="flex flex-wrap items-center gap-2.5">
            <span>{ev.student.name}</span>
            {!nameIsRoll(ev.student) && (
              <span className="inline-flex items-center rounded-lg bg-pen-soft px-2.5 py-1 text-xs font-bold text-pen border border-pen/30">
                Roll {ev.student.roll_number}
              </span>
            )}
          </div>
        }
        sub={
          <div className="flex items-center gap-2 text-sm text-mute">
            <span>{data.exam.name}</span>
            <span>•</span>
            <Link
              className="text-pen font-medium hover:underline flex items-center gap-1"
              to={`/exams/${ev.exam_id}/answer-sheets`}
            >
              <span>Back to students</span>
            </Link>
          </div>
        }
        actions={
          <div className="flex items-center gap-2">
            <StatusBadge status={ev.status} />
            {ev.status === "FINALIZED" && data.exam.status !== "FINALIZED" && (
              <Button
                small
                variant="secondary"
                busy={reopening}
                onClick={reopen}
                icon={<IconRotateCcw size={15} />}
                title="Open this result again to change a mark; finalize it again when done"
              >
                Reopen to change marks
              </Button>
            )}
            {ev.part_b_option && (
              <span className="rounded-full border border-blue-100 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700"
                    title="The AI read this from the answer sheet. Part B is marked against this option only.">
                Part B: {ev.part_b_option === "computerised" ? "Option II, Computerised Accounting" : "Option I, Analysis of Financial Statements"}
              </span>
            )}
            <Button
              small
              variant="ghost"
              className="text-mark hover:bg-mark-soft hover:text-mark"
              disabled={reading || ev.run_status === "RUNNING"}
              onClick={() => setDeleting(true)}
              icon={<IconTrash size={15} />}
              title={reading || ev.run_status === "RUNNING" ? "Wait for reading or grading to finish" : "Delete this answer sheet"}
            >
              Delete sheet
            </Button>
          </div>
        }
      />

      {deleting && (
        <DeleteSheetConfirm
          ev={ev}
          onDeleted={() => nav(`/exams/${ev.exam_id}/answer-sheets`)}
          onClose={() => setDeleting(false)}
        />
      )}

      {/* OCR Ingestion Progress if document is still processing */}
      {(reading || data.document.status !== "READY") && (
        <DocProgress
          doc={data.document}
          onChanged={reload}
          canRetry={ev.status !== "FINALIZED" && data.items.length === 0}
          rebuildWarning="Reading again rebuilds the detected answers for this sheet. Edits and mapping decisions will be lost."
        />
      )}

      {/* Main Tabs Navigation */}
      {!reading && (
        <div className="space-y-4">
          {/* stays at the top of the page while scrolling */}
          <div className="sticky top-0 z-30 -mx-1 flex h-12 items-center gap-2 border-b border-line bg-paper/95 px-2 backdrop-blur">
            <button
              onClick={() => setTab("mapping")}
              className={`flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-bold transition-all ${
                tab === "mapping"
                  ? "bg-pen text-on-pen shadow-sm"
                  : "text-mute hover:bg-hover hover:text-ink"
              }`}
            >
              <IconFileText size={16} />
              <span>1. Mapping Review</span>
              {data.summary.needs_review > 0 && (
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${tab === "mapping" ? "bg-white text-pen" : "bg-warn-soft text-warn"}`}>
                  {data.summary.needs_review}
                </span>
              )}
            </button>
            <button
              onClick={() => setTab("marks")}
              className={`flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-bold transition-all ${
                tab === "marks"
                  ? "bg-pen text-on-pen shadow-sm"
                  : "text-mute hover:bg-hover hover:text-ink"
              }`}
            >
              <IconCheckCircle size={16} />
              <span>2. Marks & Finalize</span>
              {data.items.length > 0 && (
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${tab === "marks" ? "bg-white text-pen" : "bg-pen-soft text-pen"}`}>
                  {data.items.filter((i) => i.status === "APPROVED").length}/{data.questions.length}
                </span>
              )}
            </button>
            <Button
              small
              variant="secondary"
              className="ml-auto"
              busy={downloading}
              onClick={download}
              icon={<IconDownload size={15} />}
              title={tab === "mapping"
                ? "PDF of every answer as read and the question it is mapped to"
                : "PDF of the marks per question, the current total and the AI's grading notes"}
            >
              {tab === "mapping" ? "Download mapping" : "Download marks"}
            </Button>
          </div>
          <ErrorPanel error={downloadErr} />

          {tab === "mapping" ? (
            <MappingTab d={data} reload={reload} />
          ) : (
            <MarksTab d={data} reload={reload} />
          )}
        </div>
      )}
    </div>
  );
}
