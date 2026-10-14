import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { useApi } from "../../hooks/useApi";
import type { AnswerKeyRow, DocInfo, GeneratedAnswerItem, KeysResponse } from "../../types";
import { BUSY_DOC, pct } from "../../utils/format";
import { Badge, Button, Card, Confirm, Empty, ErrorPanel, Field, Input, Loading, Modal, Select, StatusBadge, Textarea } from "../../components/ui";
import { DocProgress, UploadZone } from "../../components/DocPanel";
import { PageViewer } from "../../components/PageViewer";
import { CriteriaEditor } from "../../components/CriteriaEditor";
import { ExtractionDiagnosticsModal } from "../../components/ExtractionDiagnosticsModal";
import { SaveToVerifiedCollectionModal } from "../../components/SaveToVerifiedCollectionModal";
import { useExam } from "../ExamWorkspace";

const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);

export default function AnswerKey() {
  const { exam, reload: reloadExam } = useExam();
  const doc = useApi<DocInfo | null>(`/exams/${exam.id}/answer-key`, (d) => (d && BUSY_DOC.includes(d.status) ? 1500 : null));
  const keys = useApi<KeysResponse>(`/exams/${exam.id}/answer-keys`, () => (doc.data && BUSY_DOC.includes(doc.data.status) ? 1500 : null));
  const [page, setPage] = useState(1);
  const [sel, setSel] = useState<string | null>(null);
  const [dlg, setDlg] = useState<{ kind: "edit" | "delete" | "add" | "split" | "merge"; row?: AnswerKeyRow; qid?: string } | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [referenceTarget, setReferenceTarget] = useState<AnswerKeyRow | null>(null);

  // Two options state: "upload" or "ai"
  const [sourceMode, setSourceMode] = useState<"upload" | "ai">("upload");
  const [showReplace, setShowReplace] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiError, setAiError] = useState<unknown>(null);
  const [reviewAnswers, setReviewAnswers] = useState<GeneratedAnswerItem[] | null>(null);

  const after = async () => { await Promise.all([doc.reload(), keys.reload(), reloadExam()]); };
  const upload = async (file: File) => {
    const f = new FormData();
    f.append("file", file);
    await api(`/exams/${exam.id}/answer-key`, { method: "POST", form: f });
    setShowReplace(false);
    await after();
  };
  const verify = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api(`/exams/${exam.id}/answer-keys/verify`, { method: "POST" });
      await after();
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  };

  const generateAi = async () => {
    setAiBusy(true);
    setAiError(null);
    try {
      const res = await api<{ answers: GeneratedAnswerItem[] }>(`/exams/${exam.id}/answer-keys/generate-ai`, { method: "POST" });
      setReviewAnswers(res.answers);
    } catch (e) {
      setAiError(e);
    } finally {
      setAiBusy(false);
    }
  };

  const saveAiAnswers = async (reviewed: GeneratedAnswerItem[]) => {
    await api(`/exams/${exam.id}/answer-keys/save-ai`, {
      method: "POST",
      json: { answers: reviewed },
    });
    setReviewAnswers(null);
    setShowReplace(false);
    await after();
  };

  // Synchronize keys automatically when doc transitions to READY
  const prevDocStatus = useRef(doc.data?.status);
  useEffect(() => {
    if (prevDocStatus.current && BUSY_DOC.includes(prevDocStatus.current) && doc.data && ["READY", "NEEDS_ATTENTION"].includes(doc.data.status)) {
      keys.reload();
    }
    prevDocStatus.current = doc.data?.status;
  }, [doc.data?.status, keys]);

  if (exam.status === "DRAFT" || ["QUESTION_PAPER_UPLOADED", "QUESTIONS_EXTRACTED"].includes(exam.status))
    return <Empty title="Verify the questions first" hint="The answer key is mapped onto verified questions, so those come first." />;
  if (doc.loading || keys.loading) return <Loading />;
  const d = doc.data, k = keys.data;
  const isLocked = Boolean(k?.locked || ["ANSWER_KEY_VERIFIED", "READY_FOR_EVALUATION", "EVALUATING", "REVIEW_REQUIRED", "FINALIZED"].includes(exam.status));
  const qLabel = (id: string | null) => k?.questions?.find((q) => q.id === id)?.display_number;
  const selRow = k?.keys?.find((x) => x.id === sel);
  const hasKeys = (k?.keys?.length ?? 0) > 0;
  const ready = (d && ["READY", "NEEDS_ATTENTION"].includes(d.status)) || (!d && hasKeys);
  const showOptions = !isLocked && !(d && BUSY_DOC.includes(d.status)) && (!hasKeys || showReplace);

  return (
    <div className="space-y-4">
      <ErrorPanel error={doc.error || keys.error} />

      {isLocked && (
        <Card className="p-4 text-sm bg-ok-soft/30 border-ok/40 flex items-center justify-between">
          <div>
            <p className="font-semibold text-ok">Official Answer Key Verified & Locked</p>
            <p className="text-xs text-mute mt-0.5">The official answer key is verified and locked for student evaluation.</p>
          </div>
          <StatusBadge status="VERIFIED" />
        </Card>
      )}

      {showOptions && (
        <Card className="p-4 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
            <div>
              <h2 className="text-sm font-semibold">Answer Key Options</h2>
              <p className="text-xs text-mute">Choose how to provide the official answer key for this exam.</p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                small
                variant={sourceMode === "upload" ? "primary" : "soft"}
                onClick={() => setSourceMode("upload")}
              >
                📄 Upload Answer Key
              </Button>
              <Button
                small
                variant={sourceMode === "ai" ? "primary" : "soft"}
                onClick={() => setSourceMode("ai")}
              >
                ✨ Generate Answer Key with AI
              </Button>
              {hasKeys && (
                <Button small variant="ghost" onClick={() => setShowReplace(false)}>
                  Cancel
                </Button>
              )}
            </div>
          </div>

          {sourceMode === "upload" ? (
            <UploadZone
              accept=".pdf,.png,.jpg,.jpeg,.docx"
              onFile={upload}
              hint="PDF, DOCX, PNG or JPG. Answers are matched to your verified questions by question number only."
            />
          ) : (
            <div className="rounded-lg border border-dashed border-line p-6 text-center space-y-3">
              <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-pen-soft text-pen font-bold">
                ✨
              </div>
              <div>
                <p className="font-medium text-sm">Generate Answer Key with AI</p>
                <p className="text-xs text-mute max-w-md mx-auto mt-1">
                  Uses <code>blaifa/InternVL3_5:4B</code> through Ollama to read the verified question paper and propose model answers, marking criteria, and keywords for each question.
                </p>
              </div>
              <div>
                <Button
                  variant="primary"
                  busy={aiBusy}
                  onClick={generateAi}
                >
                  {aiBusy ? "Reading Question Paper & Generating…" : `Generate Answers for ${exam.question_count} Question(s)`}
                </Button>
              </div>
              <ErrorPanel error={aiError} />
            </div>
          )}
        </Card>
      )}

      {d && <DocProgress doc={d} onChanged={after} canRetry={exam.status === "ANSWER_KEY_UPLOADED"} rebuildWarning="Reading again rebuilds the answer key rows. Edits you made to extracted rows will be lost." />}

      {!hasKeys && !d && !showOptions && (
        <Card className="p-6 text-center text-sm text-mute">
          No answer key loaded yet. Use one of the options to either upload an answer key sheet or generate one automatically using AI.
        </Card>
      )}

      {k && ready && (
        <>
          <div className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-surface p-3">
            <p className="text-sm"><b>{k.keys.length}</b> answer rows · <span className={k.missing_question_ids.length ? "font-medium text-mark" : ""}>{k.missing_question_ids.length} question(s) without an answer</span></p>
            <div className="flex items-center gap-2">
              <Button variant="soft" onClick={() => setShowDiagnostics(true)}>📊 Diagnostics & Accuracy</Button>
              {!isLocked && (
                <Button small variant="soft" onClick={() => setShowReplace((v) => !v)}>
                  {showReplace ? "Hide Options" : "Replace / Re-generate"}
                </Button>
              )}
              {!isLocked && <Button variant="primary" busy={busy} onClick={verify}>Verify answer key</Button>}
              {isLocked && <StatusBadge status="VERIFIED" />}
            </div>
          </div>
          <ErrorPanel error={err} />
          {k.missing_question_ids.length > 0 && !isLocked && (
            <Card className="border-warn/50 p-4"><p className="mb-2 text-sm font-medium">No answer key found for:</p>
              <div className="flex flex-wrap gap-2">{k.missing_question_ids.map((id) => <Button key={id} small onClick={() => setDlg({ kind: "add", qid: id })}>Add answer for Question {qLabel(id)}</Button>)}</div></Card>
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            <Card className="h-[calc(100vh-18rem)] min-h-[26rem] overflow-hidden">
              {d && k.document_id ? (
                <PageViewer kind="answer-key" docId={k.document_id} pages={d.pages} page={page} onPage={setPage} highlight={selRow?.page_number === page ? selRow.bbox : null} />
              ) : exam.question_paper ? (
                <PageViewer kind="question-paper" docId={exam.question_paper.id} pages={exam.question_paper.pages} page={page} onPage={setPage} />
              ) : (
                <p className="p-4 text-sm text-mute">No document image to display.</p>
              )}
            </Card>
            <div className="h-[calc(100vh-18rem)] min-h-[26rem] space-y-3 overflow-y-auto pr-1">
              {k.keys.map((r) => (
                <Card key={r.id} className={`p-4 ${sel === r.id ? "ring-2 ring-pen" : ""} ${r.mapping_status !== "MAPPED" || r.mark_mismatch ? "border-mark/50" : ""}`}>
                  <button className="block w-full text-left" onClick={() => { setSel(r.id); if (r.page_number) setPage(r.page_number); }}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-semibold">Label “{r.raw_question_number ?? "none"}” → {r.exam_question_id ? `Question ${qLabel(r.exam_question_id)}` : "not mapped"}</span>
                      <div className="flex gap-2">{r.mark_mismatch && <Badge tone="mark">MARK MISMATCH</Badge>}<Badge tone="mute">{r.marks ?? "–"} marks</Badge><Badge tone="mute">conf. {pct(r.ocr_confidence)}</Badge><StatusBadge status={r.mapping_status} /></div>
                    </div>
                    {r.mapping_note && r.mapping_status !== "MAPPED" && <p className="mt-1 text-sm font-medium text-mark">{r.mapping_note}</p>}
                    <p className="doc-text mt-2 line-clamp-4 text-[15px]">{r.answer_text}</p>
                    {r.criteria.length > 0 && (
                      <div className="mt-2 space-y-1">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="text-xs text-mute font-medium">Criteria:</span>
                          {r.criteria.map((c, cIdx) => (
                            <span
                              key={cIdx}
                              className="inline-flex items-center gap-1 rounded bg-sunken px-2 py-0.5 text-xs text-ink border border-line/50"
                            >
                              <span className="font-semibold text-pen text-[11px]">Mark {cIdx + 1}:</span>
                              <span>{c}</span>
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </button>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {!isLocked && (
                      <>
                        <Button small onClick={() => setDlg({ kind: "edit", row: r })}>Edit</Button>
                        <Button small onClick={() => setDlg({ kind: "split", row: r })}>Split</Button>
                        <Button small onClick={() => setDlg({ kind: "merge", row: r })}>Merge</Button>
                        <Button small variant="ghost" onClick={() => setDlg({ kind: "delete", row: r })}>Delete</Button>
                      </>
                    )}
                    <Button small variant="soft" onClick={() => setReferenceTarget(r)} title="Add to verified local reference collection">Save as Reference</Button>
                  </div>
                </Card>
              ))}
            </div>
          </div>
        </>
      )}

      {reviewAnswers && (
        <ReviewGeneratedModal
          answers={reviewAnswers}
          onSave={saveAiAnswers}
          onClose={() => setReviewAnswers(null)}
        />
      )}

      {dlg?.kind === "edit" && dlg.row && k && <KeyDlg row={dlg.row} k={k} onClose={() => setDlg(null)} onDone={after} />}
      {dlg?.kind === "add" && k && <KeyDlg qid={dlg.qid} k={k} onClose={() => setDlg(null)} onDone={after} examId={exam.id} />}
      {dlg?.kind === "split" && dlg.row && <SplitKeyModal row={dlg.row} onClose={() => setDlg(null)} onDone={after} />}
      {dlg?.kind === "merge" && dlg.row && k && <MergeKeyModal row={dlg.row} allKeys={k.keys} onClose={() => setDlg(null)} onDone={after} />}
      {dlg?.kind === "delete" && dlg.row && <Confirm title="Delete answer row" danger confirmLabel="Delete" body={<p>Remove the row for “{dlg.row.raw_question_number}”? This is recorded in the audit log.</p>}
        onConfirm={async () => { await api(`/answer-keys/${dlg.row!.id}`, { method: "DELETE" }); await after(); }} onClose={() => setDlg(null)} />}

      {showDiagnostics && <ExtractionDiagnosticsModal onClose={() => setShowDiagnostics(false)} />}
      {referenceTarget && (
        <SaveToVerifiedCollectionModal
          initialData={{
            document_type: "answer_key",
            subject: exam.subject_name || "General",
            source_document: d?.original_filename || exam.name,
            page_number: referenceTarget.page_number || 1,
            question_number: referenceTarget.raw_question_number,
            normalized_number: referenceTarget.normalized_number,
            original_ocr: referenceTarget.answer_text,
            corrected_text: referenceTarget.answer_text,
            approved_marks: referenceTarget.marks,
            criteria: referenceTarget.criteria,
          }}
          onClose={() => setReferenceTarget(null)}
          onSuccess={after}
        />
      )}
    </div>
  );
}

function ReviewGeneratedModal({
  answers: initialAnswers,
  onSave,
  onClose,
}: {
  answers: GeneratedAnswerItem[];
  onSave: (reviewed: GeneratedAnswerItem[]) => Promise<void>;
  onClose: () => void;
}) {
  const [items, setItems] = useState<GeneratedAnswerItem[]>(() =>
    initialAnswers.map((ans) => {
      const target = Math.max(1, Math.round(Number(ans.marks ?? ans.max_marks ?? 1) || 1));
      const crit = ans.criteria && ans.criteria.length > 0 ? [...ans.criteria] : [];
      while (crit.length < target) {
        crit.push("");
      }
      return { ...ans, criteria: crit };
    })
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);

  const updateItem = (index: number, patch: Partial<GeneratedAnswerItem>) => {
    setItems((prev) => prev.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  };

  const handleSave = async () => {
    setBusy(true);
    setErr(null);
    try {
      const cleaned = items.map((it) => ({
        ...it,
        criteria: it.criteria.map((c) => c.trim()).filter(Boolean),
        keywords: it.keywords.map((k) => k.trim()).filter(Boolean),
        accepted_answers: it.accepted_answers.map((a) => a.trim()).filter(Boolean),
      }));
      await onSave(cleaned);
    } catch (e) {
      setErr(e);
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Review & Edit AI-Generated Answers"
      wide
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>Discard</Button>
          <Button variant="primary" busy={busy} onClick={handleSave}>
            Approve & Save Answer Key ({items.length} answers)
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="rounded-lg border border-pen/30 bg-pen-soft p-3 text-sm text-ink">
          <p className="font-semibold text-pen">Generated using blaifa/InternVL3_5:4B</p>
          <p className="text-xs text-mute mt-0.5">
            Review and adjust any model answers, marking criteria, or keywords before saving.
            Question numbers and deterministic IDs are preserved. Teacher approval is required before using the key for evaluation.
          </p>
        </div>
        <ErrorPanel error={err} />
        <div className="space-y-5 max-h-[60vh] overflow-y-auto pr-1">
          {items.map((item, idx) => (
            <Card key={item.exam_question_id || idx} className="p-4 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2">
                <span className="font-semibold text-base">Question {item.question_number}</span>
                <Badge tone="pen">{item.max_marks ?? "–"} marks</Badge>
              </div>
              {item.question_text && (
                <div className="rounded bg-sunken p-2.5 text-xs text-mute font-doc">
                  <span className="font-semibold text-ink block mb-0.5">Question text:</span>
                  {item.question_text}
                </div>
              )}
              <Field label="Suggested Answer Text">
                {(id) => (
                  <Textarea
                    id={id}
                    rows={4}
                    className="font-doc text-sm"
                    value={item.answer_text}
                    onChange={(e) => updateItem(idx, { answer_text: e.target.value })}
                  />
                )}
              </Field>
              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="Marks">
                  {(id) => (
                    <Input
                      id={id}
                      type="number"
                      step={0.5}
                      min={0}
                      value={item.marks != null ? item.marks : ""}
                      onChange={(e) => {
                        const val = e.target.value ? Number(e.target.value) : null;
                        const target = val ? Math.max(1, Math.round(val)) : 1;
                        let nextCrit = [...item.criteria];
                        if (val && nextCrit.length < target) {
                          while (nextCrit.length < target) nextCrit.push("");
                        } else if (val && nextCrit.length > target && nextCrit.slice(target).every((c) => !c.trim())) {
                          nextCrit = nextCrit.slice(0, target);
                        }
                        updateItem(idx, { marks: val, criteria: nextCrit });
                      }}
                    />
                  )}
                </Field>
                <Field label="Keywords (one per line)">
                  {(id) => (
                    <Textarea
                      id={id}
                      rows={3}
                      className="text-xs"
                      value={item.keywords.join("\n")}
                      onChange={(e) => updateItem(idx, { keywords: lines(e.target.value) })}
                    />
                  )}
                </Field>
                <Field label="Accepted Answers (one per line)">
                  {(id) => (
                    <Textarea
                      id={id}
                      rows={3}
                      className="text-xs"
                      value={item.accepted_answers.join("\n")}
                      onChange={(e) => updateItem(idx, { accepted_answers: lines(e.target.value) })}
                    />
                  )}
                </Field>
              </div>
              <CriteriaEditor
                criteria={item.criteria}
                marks={item.marks ?? item.max_marks}
                onChange={(newCrit) => updateItem(idx, { criteria: newCrit })}
              />
            </Card>
          ))}
        </div>
      </div>
    </Modal>
  );
}

function KeyDlg({ row, qid, k, examId, onClose, onDone }: { row?: AnswerKeyRow; qid?: string; k: KeysResponse; examId?: string; onClose: () => void; onDone: () => Promise<void> }) {
  const initialQid = row?.exam_question_id ?? qid ?? "";
  const initialQ = k.questions.find((x) => x.id === initialQid);
  const [question, setQuestion] = useState(initialQid);
  const [text, setText] = useState(row?.answer_text ?? "");
  const [marks, setMarks] = useState(row?.marks != null ? String(row.marks) : (initialQ?.max_marks != null ? String(initialQ.max_marks) : ""));

  const getInitialCriteria = () => {
    const initial = row?.criteria && row.criteria.length > 0 ? [...row.criteria] : [];
    const target = Math.max(1, Math.round(Number(row?.marks ?? initialQ?.max_marks ?? 1) || 1));
    while (initial.length < target) {
      initial.push("");
    }
    return initial;
  };

  const [criteriaList, setCriteriaList] = useState<string[]>(getInitialCriteria);
  const [keywords, setKeywords] = useState((row?.keywords ?? []).join("\n"));
  const [accepted, setAccepted] = useState((row?.accepted_answers ?? []).join("\n"));
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const q = k.questions.find((x) => x.id === question);

  const handleQuestionChange = (newQid: string) => {
    setQuestion(newQid);
    const selectedQ = k.questions.find((x) => x.id === newQid);
    if (selectedQ && selectedQ.max_marks != null) {
      if (!marks || Number(marks) === 0) {
        setMarks(String(selectedQ.max_marks));
        const target = Math.max(1, Math.round(selectedQ.max_marks));
        setCriteriaList((prev) => {
          if (prev.every((c) => !c.trim())) {
            return Array.from({ length: target }, () => "");
          }
          if (prev.length < target) {
            const next = [...prev];
            while (next.length < target) next.push("");
            return next;
          }
          return prev;
        });
      }
    }
  };

  const handleMarksChange = (val: string) => {
    setMarks(val);
    const num = Number(val);
    if (num && num > 0) {
      const target = Math.max(1, Math.round(num));
      setCriteriaList((prev) => {
        if (prev.length < target) {
          const next = [...prev];
          while (next.length < target) next.push("");
          return next;
        }
        if (prev.length > target && prev.slice(target).every((c) => !c.trim())) {
          return prev.slice(0, target);
        }
        return prev;
      });
    }
  };

  const call = async (fn: () => Promise<unknown>, close = true) => {
    setBusy(true); setErr(null);
    try { await fn(); await onDone(); if (close) onClose(); else setBusy(false); }
    catch (e) { setErr(e); setBusy(false); }
  };

  const save = () => {
    const cleanedCriteria = criteriaList.map((c) => c.trim()).filter(Boolean);
    return call(() => row
      ? api(`/answer-keys/${row.id}`, {
          method: "PATCH",
          json: {
            ...(question && question !== row.exam_question_id ? { exam_question_id: question } : {}),
            answer_text: text,
            marks: marks ? Number(marks) : null,
            criteria: cleanedCriteria,
            keywords: lines(keywords),
            accepted_answers: lines(accepted),
            reason: reason || undefined,
          },
        })
      : api(`/exams/${examId}/answer-keys`, {
          method: "POST",
          json: {
            exam_question_id: question,
            answer_text: text,
            marks: marks ? Number(marks) : null,
            criteria: cleanedCriteria,
            keywords: lines(keywords),
            accepted_answers: lines(accepted),
          },
        }));
  };

  const resolve = (choice: string) => call(() => api(`/answer-keys/${row!.id}`, { method: "PATCH", json: { mismatch_resolution: choice, reason: reason || undefined } }));

  return (
    <Modal title={row ? `Edit answer for “${row.raw_question_number}”` : "Add answer"} wide onClose={onClose} footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} disabled={!question || !text.trim()} onClick={save}>Save</Button></>}>
      <div className="space-y-4">
        <Field label="Maps to question" hint="Choose the question this answer belongs to. Nothing is matched by meaning, only by number or your choice.">
          {(id) => (
            <Select id={id} value={question} onChange={(e) => handleQuestionChange(e.target.value)}>
              <option value="">Choose a question</option>
              {k.questions.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.display_number} — {x.question_text.slice(0, 70)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        {row?.mark_mismatch && q && (
          <div className="rounded-lg border border-mark/50 bg-mark-soft p-3 text-sm">
            <p className="font-semibold text-mark">Mark mismatch: key says {row.marks}, question {q.display_number} is worth {q.max_marks}.</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button small busy={busy} onClick={() => resolve("keep_question_marks")}>Keep question's {q.max_marks} marks</Button>
              <Button small busy={busy} disabled={!reason} onClick={() => resolve("use_key_marks")}>Change question to {row.marks} marks (needs a reason)</Button>
            </div>
            <div className="mt-2"><Input aria-label="Reason" placeholder="Reason for changing marks" value={reason} onChange={(e) => setReason(e.target.value)} /></div>
          </div>
        )}
        <Field label="Official answer">
          {(id) => <Textarea id={id} rows={5} className="font-doc" value={text} onChange={(e) => setText(e.target.value)} />}
        </Field>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Marks">
            {(id) => (
              <Input
                id={id}
                type="number"
                min={0}
                step={0.5}
                value={marks}
                onChange={(e) => handleMarksChange(e.target.value)}
              />
            )}
          </Field>
          <Field label="Accepted answers (one per line)">
            {(id) => <Textarea id={id} rows={3} value={accepted} onChange={(e) => setAccepted(e.target.value)} placeholder="Alternative phrasing or spellings..." />}
          </Field>
          <Field label="Keywords (one per line)">
            {(id) => <Textarea id={id} rows={3} value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="Must-include terms..." />}
          </Field>
        </div>
        <CriteriaEditor
          criteria={criteriaList}
          marks={marks ? Number(marks) : q?.max_marks}
          onChange={setCriteriaList}
        />
        <ErrorPanel error={err} />
      </div>
    </Modal>
  );
}

function SplitKeyModal({ row, onClose, onDone }: { row: AnswerKeyRow; onClose: () => void; onDone: () => Promise<void> }) {
  const [pos, setPos] = useState(Math.floor(row.answer_text.length / 2));
  const [num, setNum] = useState("");
  const [marks, setMarks] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const head = row.answer_text.slice(0, pos);
  const tail = row.answer_text.slice(pos);

  const save = async () => {
    setBusy(true); setErr(null);
    try {
      await api(`/answer-keys/${row.id}/split`, { method: "POST", json: { at_char: pos, new_label: num, new_marks: marks ? Number(marks) : null } });
      await onDone(); onClose();
    } catch (e) { setErr(e); setBusy(false); }
  };

  return (
    <Modal title={`Split answer “${row.raw_question_number ?? "none"}”`} wide onClose={onClose} footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} disabled={pos <= 0 || !num.trim()} onClick={save}>Split here</Button></>}>
      <div className="space-y-4">
        <p className="text-sm text-mute">Drag slider to choose where to split this answer row into two.</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="New question label (e.g. Q4 or 4(b))">{(id) => <Input id={id} value={num} onChange={(e) => setNum(e.target.value)} />}</Field>
          <Field label="Marks for new row (optional)">{(id) => <Input id={id} type="number" min={0} step={0.5} value={marks} onChange={(e) => setMarks(e.target.value)} />}</Field>
        </div>
        <div>
          <input type="range" min={1} max={Math.max(1, row.answer_text.length - 1)} value={pos} onChange={(e) => setPos(Number(e.target.value))} className="w-full" />
          <p className="text-xs text-mute">Character {pos} of {row.answer_text.length}</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded border border-line bg-surface p-3 text-sm"><p className="mb-1 text-xs font-semibold text-mute">Kept in current row</p><p className="font-mono text-xs">{head}</p></div>
          <div className="rounded border border-line bg-sunken p-3 text-sm"><p className="mb-1 text-xs font-semibold text-mute">Moved to new row ({num || "..."})</p><p className="font-mono text-xs">{tail}</p></div>
        </div>
        <ErrorPanel error={err} />
      </div>
    </Modal>
  );
}

function MergeKeyModal({ row, allKeys, onClose, onDone }: { row: AnswerKeyRow; allKeys: AnswerKeyRow[]; onClose: () => void; onDone: () => Promise<void> }) {
  const [otherId, setOtherId] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const others = allKeys.filter((k) => k.id !== row.id);

  const save = async () => {
    setBusy(true); setErr(null);
    try {
      await api(`/answer-keys/${row.id}/merge`, { method: "POST", json: { other_id: otherId } });
      await onDone(); onClose();
    } catch (e) { setErr(e); setBusy(false); }
  };

  return (
    <Modal title={`Merge answer “${row.raw_question_number ?? "none"}”`} onClose={onClose} footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} disabled={!otherId} onClick={save}>Merge</Button></>}>
      <div className="space-y-4">
        <p className="text-sm">Append another row's answer text into this one. The other row will be deleted.</p>
        <Field label="Choose row to merge into this one">
          {(id) => <Select id={id} value={otherId} onChange={(e) => setOtherId(e.target.value)}><option value="">Select row...</option>
            {others.map((k) => <option key={k.id} value={k.id}>{k.raw_question_number ?? "(no number)"} — {k.answer_text.slice(0, 50)}</option>)}</Select>}</Field>
        <ErrorPanel error={err} />
      </div>
    </Modal>
  );
}
