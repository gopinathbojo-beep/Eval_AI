import { useState } from "react";
import { Link } from "react-router-dom";
import { api, downloadFile } from "../../api/client";
import { useApi } from "../../hooks/useApi";
import type { DocInfo } from "../../types";
import { BUSY_DOC } from "../../utils/format";
import { Button, Card, ErrorPanel, Loading } from "../../components/ui";
import { DocProgress, UploadZone } from "../../components/DocPanel";
import { useExam } from "../ExamWorkspace";

interface QuestionPaperProps {
  onReviewQuestions?: () => void;
}

export default function QuestionPaper({ onReviewQuestions }: QuestionPaperProps) {
  const { exam, reload } = useExam();
  const { data: doc, loading, reload: reloadDoc } = useApi<DocInfo | null>(`/exams/${exam.id}/question-paper`, (d) => (d && BUSY_DOC.includes(d.status) ? 1500 : null));
  const [downloading, setDownloading] = useState(false);
  const [downloadErr, setDownloadErr] = useState<unknown>(null);
  const locked = !["DRAFT", "QUESTION_PAPER_UPLOADED", "QUESTIONS_EXTRACTED"].includes(exam.status);

  const upload = async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    await api(`/exams/${exam.id}/question-paper`, { method: "POST", form });
    await Promise.all([reloadDoc(), reload()]);
  };

  const changed = async () => {
    await Promise.all([reloadDoc(), reload()]);
  };

  const download = async () => {
    if (!doc) return;
    setDownloading(true);
    setDownloadErr(null);
    try {
      await downloadFile(`/exams/${exam.id}/question-paper/pdf`, doc.original_filename || "question-paper.pdf");
    } catch (e) {
      setDownloadErr(e);
    } finally {
      setDownloading(false);
    }
  };

  if (loading) return <Loading />;

  return (
    <div className="max-w-3xl space-y-5">
      {locked ? (
        <Card className="flex items-center gap-3 p-4 text-sm text-mute border-ok/30 bg-ok-soft/30 shadow-soft">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-ok text-surface font-bold text-xs">
            ✓
          </span>
          <div>
            <p className="font-semibold text-ok">Question Paper Verified &amp; Locked</p>
            <p className="text-xs text-mute mt-0.5">Questions for this exam have been verified, so the question paper source is locked.</p>
          </div>
        </Card>
      ) : (
        <Card className="p-5 shadow-soft space-y-3">
          <div>
            <h2 className="text-base font-semibold text-ink">Upload Question Paper Document</h2>
            <p className="text-xs text-mute">
              Upload the printed or digital examination question paper. OCR will detect and extract individual questions, sections, and marks.
            </p>
          </div>
          <UploadZone
            accept=".pdf,.png,.jpg,.jpeg,.docx"
            onFile={upload}
            disabled={!!doc && BUSY_DOC.includes(doc.status)}
            hint="PDF, PNG, JPG or DOCX. Each page is processed independently. Original source files are retained securely."
          />
        </Card>
      )}

      <ErrorPanel error={downloadErr} />

      {doc && (
        <DocProgress
          doc={doc}
          onChanged={changed}
          rebuildWarning="Re-reading the document will rebuild the extracted question list from all pages. Any custom edits made to extracted questions will be reset."
          actions={
            <Button
              small
              variant="soft"
              busy={downloading}
              onClick={download}
              title="Download original uploaded question paper as PDF"
            >
              <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              <span>Download PDF</span>
            </Button>
          }
        />
      )}

      {doc && ["READY", "NEEDS_ATTENTION"].includes(doc.status) && (
        <div className="pt-2">
          {onReviewQuestions ? (
            <Button variant="primary" className="shadow-xs" onClick={onReviewQuestions}>
              <span>Review {exam.question_count} Extracted Questions</span>
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
              </svg>
            </Button>
          ) : (
            <Link to={`/exams/${exam.id}/questions`}>
              <Button variant="primary" className="shadow-xs">
                <span>Review {exam.question_count} Extracted Questions</span>
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
              </Button>
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
