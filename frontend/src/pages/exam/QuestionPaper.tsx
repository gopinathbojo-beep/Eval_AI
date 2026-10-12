import { useState } from "react";
import { Link } from "react-router-dom";
import { api, downloadFile } from "../../api/client";
import { useApi } from "../../hooks/useApi";
import type { DocInfo } from "../../types";
import { BUSY_DOC } from "../../utils/format";
import { Button, Card, ErrorPanel, Loading } from "../../components/ui";
import { DocProgress, UploadZone } from "../../components/DocPanel";
import { useExam } from "../ExamWorkspace";

export default function QuestionPaper() {
  const { exam, reload } = useExam();
  const { data: doc, loading, reload: reloadDoc } = useApi<DocInfo | null>(`/exams/${exam.id}/question-paper`, (d) => (d && BUSY_DOC.includes(d.status) ? 1500 : null));
  const [downloading, setDownloading] = useState(false);
  const [downloadErr, setDownloadErr] = useState<unknown>(null);
  const locked = !["DRAFT", "QUESTION_PAPER_UPLOADED", "QUESTIONS_EXTRACTED"].includes(exam.status);
  const upload = async (file: File) => {
    const form = new FormData(); form.append("file", file);
    await api(`/exams/${exam.id}/question-paper`, { method: "POST", form });
    await Promise.all([reloadDoc(), reload()]);
  };
  const changed = async () => { await Promise.all([reloadDoc(), reload()]); };
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
    <div className="max-w-3xl space-y-4">
      {locked ? <Card className="p-4 text-sm">Questions are verified, so the question paper is locked.</Card> : (
        <UploadZone accept=".pdf,.png,.jpg,.jpeg,.docx" onFile={upload} disabled={!!doc && BUSY_DOC.includes(doc.status)}
          hint="PDF, PNG, JPG or DOCX. Each page is read separately. Your original file is never changed." />
      )}
      <ErrorPanel error={downloadErr} />
      {doc && (
        <DocProgress
          doc={doc}
          onChanged={changed}
          rebuildWarning="Reading again rebuilds the extracted question list from all pages. Any edits you made to extracted questions will be lost."
          actions={
            <Button
              small
              variant="soft"
              busy={downloading}
              onClick={download}
              title="Download original uploaded question paper as PDF"
            >
              Download PDF
            </Button>
          }
        />
      )}
      {doc && ["READY", "NEEDS_ATTENTION"].includes(doc.status) && (
        <Link to="../questions"><Button variant="primary">Review {exam.question_count} extracted questions</Button></Link>
      )}
    </div>
  );
}
