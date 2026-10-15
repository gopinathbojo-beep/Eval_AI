import { useRef, useState } from "react";
import { api, ApiError, downloadFile } from "../../api/client";
import { useApi } from "../../hooks/useApi";
import type { Question, QuestionsResponse } from "../../types";
import { fmt, pct } from "../../utils/format";
import { Badge, Button, Card, Confirm, Empty, ErrorPanel, Field, Input, Loading, Modal, Select, StatusBadge, Textarea } from "../../components/ui";
import { PageViewer } from "../../components/PageViewer";
import { AuthImage } from "../../components/AuthImage";
import { ExtractionDiagnosticsModal } from "../../components/ExtractionDiagnosticsModal";
import { SaveToVerifiedCollectionModal } from "../../components/SaveToVerifiedCollectionModal";
import { useExam } from "../ExamWorkspace";

type Dlg = { kind: "edit" | "split" | "merge" | "delete" | "review" | "add"; q?: Question } | null;

export default function Questions() {
  const { exam, reload: reloadExam } = useExam();
  const { data, error, loading, reload } = useApi<QuestionsResponse>(`/exams/${exam.id}/questions`);
  const [page, setPage] = useState(1);
  const [sel, setSel] = useState<string | null>(null);
  const [dlg, setDlg] = useState<Dlg>(null);
  const [actionErr, setActionErr] = useState<unknown>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [referenceTarget, setReferenceTarget] = useState<Question | null>(null);
  const [marksConfirm, setMarksConfirm] = useState<string | null>(null);
  const after = async () => { await Promise.all([reload(), reloadExam()]); };
  const run = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key); setActionErr(null);
    try { await fn(); await after(); } catch (e) { setActionErr(e); } finally { setBusy(null); }
  };
  const download = async () => {
    if (!doc) return;
    setDownloading(true);
    setActionErr(null);
    try {
      await downloadFile(`/exams/${exam.id}/question-paper/pdf`, doc.original_filename || "question-paper.pdf");
    } catch (e) {
      setActionErr(e);
    } finally {
      setDownloading(false);
    }
  };
  if (loading) return <Loading />;
  if (error || !data) return <ErrorPanel error={error} />;
  const doc = exam.question_paper;
  const qs = data.questions;
  const verified = exam.status !== "QUESTION_PAPER_UPLOADED" && exam.status !== "QUESTIONS_EXTRACTED";
  if (!qs.length && !verified) return <Empty title="No questions extracted yet" hint="Upload the question paper first, or add questions by hand." action={<Button onClick={() => setDlg({ kind: "add" })}>Add a question</Button>} />;
  const counts = { ok: qs.filter((q) => q.verification_status === "VERIFIED").length, review: qs.filter((q) => q.verification_status === "NEEDS_REVIEW").length };
  const selected = qs.find((q) => q.id === sel);

  return (
    <div className="space-y-4">
      <div className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-surface p-3">
        <p className="text-sm"><b>{counts.ok}</b> of {qs.length} accepted · <span className={counts.review ? "font-medium text-mark" : ""}>{counts.review} need review</span> · marks add up to <b>{fmt(data.sum_of_marks)}</b> of {fmt(data.exam_total_marks)}</p>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="soft" onClick={() => setShowDiagnostics(true)}>📊 Diagnostics & Accuracy</Button>
          {!data.locked && (
            <>
              <Button onClick={() => setDlg({ kind: "add" })}>Add question</Button>
              <Button busy={busy === "bulk"} onClick={() => run("bulk", () => api(`/exams/${exam.id}/questions/accept-valid`, { method: "POST" }))}>Accept all complete questions</Button>
              <Button variant="primary" busy={busy === "verify"} onClick={() => run("verify", async () => {
                try { await api(`/exams/${exam.id}/questions/verify`, { method: "POST" }); }
                catch (e) { if (e instanceof ApiError && e.code === "MARKS_TOTAL_MISMATCH") setMarksConfirm(e.message); else throw e; }
              })}>Verify questions</Button>
            </>
          )}
        </div>
      </div>
      {data.marks_warning && <div className="rounded-lg border border-warn/40 bg-warn-soft p-3 text-sm">{data.marks_warning} You will be asked to confirm this when verifying, since some papers let students choose which questions to answer.</div>}
      {marksConfirm && (
        <Confirm title="Marks do not add up" confirmLabel="Verify anyway" onClose={() => setMarksConfirm(null)}
          body={<p>{marksConfirm}</p>}
          onConfirm={async () => { await api(`/exams/${exam.id}/questions/verify`, { method: "POST", json: { confirm_marks_mismatch: true } }); await after(); }} />
      )}
      <ErrorPanel error={actionErr} />
      {data.locked && <div className="rounded-lg border border-ok/40 bg-ok-soft p-3 text-sm">Questions are verified and locked.</div>}

      <div className="grid gap-4 lg:grid-cols-2" style={{ minHeight: "60vh" }}>
        <Card className="h-[calc(100vh-15rem)] min-h-[28rem] overflow-hidden">
          {doc && data.document_id ? (
            <PageViewer
              kind="question-paper"
              docId={data.document_id}
              pages={doc.pages}
              page={page}
              onPage={setPage}
              highlight={selected?.page_start === page ? selected.bbox : null}
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
          ) : (
            <p className="p-4 text-sm text-mute">No document page to show (questions were added by hand).</p>
          )}
        </Card>
        <div className="h-[calc(100vh-15rem)] min-h-[28rem] space-y-3 overflow-y-auto pr-1">
          {qs.map((q) => (
            <Card key={q.id} className={`p-4 ${sel === q.id ? "ring-2 ring-pen" : ""} ${q.verification_status === "NEEDS_REVIEW" ? "border-mark/50" : ""}`}>
              <button className="block w-full text-left" onClick={() => { setSel(q.id); if (q.page_start) setPage(q.page_start); }}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-lg font-semibold">Question {q.display_number}</span>
                  <div className="flex items-center gap-2"><Badge tone="mute">{fmt(q.max_marks)} marks</Badge><Badge tone="mute">conf. {pct(q.ocr_confidence)}</Badge><StatusBadge status={q.verification_status} /></div>
                </div>
                {q.review_reason && <p className="mt-1 text-sm font-medium text-mark">{q.review_reason}</p>}
                <p className="doc-text mt-2 line-clamp-5 text-[15px]">{q.question_text || <em className="text-mute">(empty)</em>}</p>
              </button>
              {sel === q.id && q.has_crop && <div className="mt-3 rounded border border-line bg-sunken p-2"><p className="mb-1 text-xs text-mute">What the model read (approximate crop)</p><AuthImage path={`/crops/question/${q.id}`} alt={`Crop of question ${q.display_number}`} className="max-h-48" /></div>}
              <div className="mt-3 flex flex-wrap gap-1.5">
                {!data.locked && (
                  <>
                    <Button small variant="primary" disabled={q.verification_status === "VERIFIED"} busy={busy === q.id} onClick={() => run(q.id, () => api(`/exam-questions/${q.id}`, { method: "PATCH", json: { verification_status: "VERIFIED" } }))}>Accept</Button>
                    <Button small onClick={() => setDlg({ kind: "edit", q })}>Edit</Button>
                    <Button small onClick={() => setDlg({ kind: "split", q })}>Split</Button>
                    <Button small onClick={() => setDlg({ kind: "merge", q })}>Merge</Button>
                    <Button small onClick={() => setDlg({ kind: "review", q })}>Mark as review</Button>
                    <Button small variant="ghost" onClick={() => setDlg({ kind: "delete", q })}>Delete</Button>
                  </>
                )}
                <Button small variant="soft" onClick={() => setReferenceTarget(q)} title="Add to verified local reference collection">Save as Reference</Button>
              </div>
            </Card>
          ))}
        </div>
      </div>

      {dlg?.kind === "edit" && dlg.q && <EditDlg q={dlg.q} onClose={() => setDlg(null)} onDone={after} />}
      {dlg?.kind === "add" && <EditDlg onClose={() => setDlg(null)} onDone={after} examId={exam.id} />}
      {dlg?.kind === "split" && dlg.q && <SplitDlg q={dlg.q} onClose={() => setDlg(null)} onDone={after} />}
      {dlg?.kind === "merge" && dlg.q && <MergeDlg q={dlg.q} all={qs} onClose={() => setDlg(null)} onDone={after} />}
      {dlg?.kind === "review" && dlg.q && <ReviewDlg q={dlg.q} onClose={() => setDlg(null)} onDone={after} />}
      {dlg?.kind === "delete" && dlg.q && <Confirm title={`Delete question ${dlg.q.display_number}`} danger confirmLabel="Delete" body={<p>This removes the question from the exam. The deletion is recorded in the audit log.</p>}
        onConfirm={async () => { await api(`/exam-questions/${dlg.q!.id}`, { method: "DELETE" }); await after(); }} onClose={() => setDlg(null)} />}

      {showDiagnostics && <ExtractionDiagnosticsModal onClose={() => setShowDiagnostics(false)} />}
      {referenceTarget && (
        <SaveToVerifiedCollectionModal
          initialData={{
            document_type: "question_paper",
            subject: exam.subject_name || "General",
            source_document: doc?.original_filename || exam.name,
            page_number: referenceTarget.page_start || 1,
            question_number: referenceTarget.display_number,
            normalized_number: referenceTarget.normalized_number,
            original_ocr: referenceTarget.raw_ocr_text || referenceTarget.question_text,
            corrected_text: referenceTarget.question_text,
            approved_marks: referenceTarget.max_marks,
          }}
          onClose={() => setReferenceTarget(null)}
          onSuccess={after}
        />
      )}
    </div>
  );
}

function useSubmit(onDone: () => Promise<void>, onClose: () => void) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const go = async (fn: () => Promise<unknown>) => { setBusy(true); setErr(null); try { await fn(); await onDone(); onClose(); } catch (e) { setErr(e); setBusy(false); } };
  return { busy, err, go };
}

function EditDlg({ q, examId, onClose, onDone }: { q?: Question; examId?: string; onClose: () => void; onDone: () => Promise<void> }) {
  const [num, setNum] = useState(q?.display_number ?? "");
  const [text, setText] = useState(q?.question_text ?? "");
  const [marks, setMarks] = useState(q?.max_marks != null ? String(q.max_marks) : "");
  const [section, setSection] = useState(q?.section ?? "");
  const [reason, setReason] = useState("");
  const { busy, err, go } = useSubmit(onDone, onClose);
  const save = () => go(() => q
    ? api(`/exam-questions/${q.id}`, { method: "PATCH", json: { display_number: num, question_text: text, max_marks: marks ? Number(marks) : undefined, section: section || undefined, reason: reason || undefined } })
    : api(`/exams/${examId}/questions`, { method: "POST", json: { display_number: num, question_text: text, max_marks: marks ? Number(marks) : null, section: section || null } }));
  return (
    <Modal title={q ? `Edit question ${q.display_number}` : "Add question"} wide onClose={onClose} footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} onClick={save}>Save</Button></>}>
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Question number" hint="For example 1, 3(a), 4(i)">{(id) => <Input id={id} value={num} onChange={(e) => setNum(e.target.value)} />}</Field>
          <Field label="Maximum marks">{(id) => <Input id={id} type="number" min={0.5} step={0.5} value={marks} onChange={(e) => setMarks(e.target.value)} />}</Field>
          <Field label="Section">{(id) => <Input id={id} value={section} onChange={(e) => setSection(e.target.value)} />}</Field>
        </div>
        <Field label="Question text">{(id) => <Textarea id={id} rows={8} className="font-doc" value={text} onChange={(e) => setText(e.target.value)} />}</Field>
        {q && q.raw_ocr_text && q.raw_ocr_text !== text && <p className="text-xs text-mute">Original transcribed text is kept separately and is never overwritten.</p>}
        {q && <Field label="Reason for change (optional)">{(id) => <Input id={id} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>}
        <ErrorPanel error={err} />
      </div>
    </Modal>
  );
}

function SplitDlg({ q, onClose, onDone }: { q: Question; onClose: () => void; onDone: () => Promise<void> }) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const [pos, setPos] = useState(0);
  const [num, setNum] = useState("");
  const [marks, setMarks] = useState("");
  const { busy, err, go } = useSubmit(onDone, onClose);
  return (
    <Modal title={`Split question ${q.display_number}`} wide onClose={onClose} footer={<><Button onClick={onClose}>Cancel</Button>
      <Button variant="primary" busy={busy} disabled={pos <= 0 || !num} onClick={() => go(() => api(`/exam-questions/${q.id}/split`, { method: "POST", json: { at_char: pos, new_number: num, new_marks: marks ? Number(marks) : null } }))}>Split here</Button></>}>
      <div className="space-y-4">
        <p className="text-sm text-mute">Click in the text where the new question begins.</p>
        <textarea ref={ref} readOnly rows={8} value={q.question_text} className="doc-text w-full rounded-md border border-line bg-surface p-3 font-doc text-sm"
          onClick={(e) => setPos(e.currentTarget.selectionStart)} onKeyUp={(e) => setPos(e.currentTarget.selectionStart)} />
        <p className="text-sm">Split position: <b>{pos}</b> characters</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Number for the new question">{(id) => <Input id={id} value={num} onChange={(e) => setNum(e.target.value)} />}</Field>
          <Field label="Marks for the new question">{(id) => <Input id={id} type="number" min={0.5} step={0.5} value={marks} onChange={(e) => setMarks(e.target.value)} />}</Field>
        </div>
        <ErrorPanel error={err} />
      </div>
    </Modal>
  );
}

function MergeDlg({ q, all, onClose, onDone }: { q: Question; all: Question[]; onClose: () => void; onDone: () => Promise<void> }) {
  const [other, setOther] = useState("");
  const { busy, err, go } = useSubmit(onDone, onClose);
  return (
    <Modal title={`Merge into question ${q.display_number}`} onClose={onClose} footer={<><Button onClick={onClose}>Cancel</Button>
      <Button variant="primary" busy={busy} disabled={!other} onClick={() => go(() => api(`/exam-questions/${q.id}/merge`, { method: "POST", json: { other_id: other } }))}>Merge</Button></>}>
      <div className="space-y-4">
        <p className="text-sm text-mute">The chosen question's text is added to the end of this one, then it is removed. Use this when a question continued onto the next page.</p>
        <Field label="Question to absorb">{(id) => <Select id={id} value={other} onChange={(e) => setOther(e.target.value)}><option value="">Choose</option>
          {all.filter((x) => x.id !== q.id).map((x) => <option key={x.id} value={x.id}>{x.display_number} — {x.question_text.slice(0, 60)}</option>)}</Select>}</Field>
        <ErrorPanel error={err} />
      </div>
    </Modal>
  );
}

function ReviewDlg({ q, onClose, onDone }: { q: Question; onClose: () => void; onDone: () => Promise<void> }) {
  const [reason, setReason] = useState("");
  const { busy, err, go } = useSubmit(onDone, onClose);
  return (
    <Modal title={`Flag question ${q.display_number} for review`} onClose={onClose} footer={<><Button onClick={onClose}>Cancel</Button>
      <Button variant="primary" busy={busy} onClick={() => go(() => api(`/exam-questions/${q.id}`, { method: "PATCH", json: { verification_status: "NEEDS_REVIEW", reason: reason || "Flagged by teacher" } }))}>Flag</Button></>}>
      <div className="space-y-4"><Field label="What looks wrong?">{(id) => <Input id={id} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field><ErrorPanel error={err} /></div>
    </Modal>
  );
}
