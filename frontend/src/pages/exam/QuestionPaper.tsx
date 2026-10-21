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
  onOpenAnswerKey?: () => void;
}

const QP_EDITABLE = ["DRAFT", "QUESTION_PAPER_UPLOADED", "QUESTIONS_EXTRACTED"];
const KEY_REPLACEABLE = [...QP_EDITABLE, "QUESTIONS_VERIFIED", "ANSWER_KEY_UPLOADED"];

function LockedCard({ title, text }: { title: string; text: string }) {
  return (
    <Card className="flex items-center gap-3 p-4 text-sm text-mute border-ok/30 bg-ok-soft/30 shadow-soft">
      <span className="flex h-7 w-7 items-center justify-center rounded-full bg-ok text-surface font-bold text-xs">✓</span>
      <div>
        <p className="font-semibold text-ok">{title}</p>
        <p className="text-xs text-mute mt-0.5">{text}</p>
      </div>
    </Card>
  );
}

export default function QuestionPaper({ onReviewQuestions, onOpenAnswerKey }: QuestionPaperProps) {
  const { exam, reload } = useExam();
  const { data: doc, loading, reload: reloadDoc } = useApi<DocInfo | null>(`/exams/${exam.id}/question-paper`, (d) => (d && BUSY_DOC.includes(d.status) ? 1500 : null));
  const { data: keyDoc, loading: keyLoading, reload: reloadKey } = useApi<DocInfo | null>(`/exams/${exam.id}/answer-key`, (d) => (d && BUSY_DOC.includes(d.status) ? 1500 : null));
  const [downloading, setDownloading] = useState(false);
  const [downloadErr, setDownloadErr] = useState<unknown>(null);
  const locked = !QP_EDITABLE.includes(exam.status);
  const keyLocked = !KEY_REPLACEABLE.includes(exam.status);
  const keyWaiting = keyDoc?.status === "WAITING";

  const upload = async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    await api(`/exams/${exam.id}/question-paper`, { method: "POST", form });
    await Promise.all([reloadDoc(), reload()]);
  };

  const uploadKey = async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    await api(`/exams/${exam.id}/answer-key`, { method: "POST", form });
    await Promise.all([reloadKey(), reload()]);
  };

  const changed = async () => {
    await Promise.all([reloadDoc(), reloadKey(), reload()]);
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

  if (loading || keyLoading) return <Loading />;

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      {/* Question paper */}
      <div className="space-y-5 min-w-0">
        {locked ? (
          <LockedCard title="Question Paper Verified &amp; Locked" text="Questions for this exam have been verified, so the question paper source is locked." />
        ) : (
          <Card className="p-5 shadow-soft space-y-3">
            <div>
              <h2 className="text-lg font-semibold text-ink">Question Paper</h2>
              <p className="text-xs text-mute">
                Questions, sections and marks are read from it.
              </p>
            </div>
            <UploadZone
              accept=".pdf,.png,.jpg,.jpeg,.docx"
              onFile={upload}
              disabled={!!doc && BUSY_DOC.includes(doc.status)}
              hint="PDF, Word, PNG or JPG."
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

      {/* Answer key: may be dropped together with the paper; it is read once the questions are verified */}
      <div className="space-y-5 min-w-0">
        {keyLocked ? (
          <LockedCard title="Answer Key Verified &amp; Locked" text="The official answer key is verified and locked for student evaluation." />
        ) : (
          <Card className="p-5 shadow-soft space-y-3">
            <div>
              <h2 className="text-lg font-semibold text-ink">Answer Key</h2>
              <p className="text-xs text-mute">
                Upload now or later. It is read once the questions are verified.
              </p>
            </div>
            <UploadZone
              accept=".pdf,.png,.jpg,.jpeg,.docx"
              onFile={uploadKey}
              disabled={!!keyDoc && BUSY_DOC.includes(keyDoc.status)}
              hint="PDF, Word, PNG or JPG."
            />
          </Card>
        )}

        {keyDoc && keyWaiting && (
          <Card className="p-4 shadow-soft">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-ink truncate">{keyDoc.original_filename}</p>
              <p className="text-xs text-mute mt-0.5">
                Starts reading when you verify the questions.
              </p>
            </div>
          </Card>
        )}

        {keyDoc && !keyWaiting && (
          <DocProgress
            doc={keyDoc}
            onChanged={changed}
            canRetry={exam.status === "ANSWER_KEY_UPLOADED"}
            rebuildWarning="Reading again rebuilds the answer key rows. Edits you made to extracted rows will be lost."
          />
        )}

        {keyDoc && ["READY", "NEEDS_ATTENTION"].includes(keyDoc.status) && onOpenAnswerKey && (
          <div className="pt-2">
            <Button variant="primary" className="shadow-xs" onClick={onOpenAnswerKey}>
              <span>Review Answer Key</span>
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
              </svg>
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
