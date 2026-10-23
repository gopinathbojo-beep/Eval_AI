import { useEffect, useRef, useState } from "react";
import { api, downloadFile } from "../../api/client";
import { useApi } from "../../hooks/useApi";
import type { Question, QuestionsResponse } from "../../types";
import { BUSY_DOC, K_LEVELS, fmt, pct } from "../../utils/format";
import { Badge, Button, Card, Confirm, Empty, ErrorPanel, Field, Input, Loading, MathTextarea, MathView, Modal, MoreMenu, Select, StatusBadge } from "../../components/ui";
import { PageViewer } from "../../components/PageViewer";
import { AuthImage } from "../../components/AuthImage";
import { ExtractionDiagnosticsModal } from "../../components/ExtractionDiagnosticsModal";
import { SaveToVerifiedCollectionModal } from "../../components/SaveToVerifiedCollectionModal";
import { useExam } from "../ExamWorkspace";

type Dlg = { kind: "edit" | "split" | "merge" | "delete" | "review" | "add"; q?: Question } | null;

export default function Questions() {
  const { exam, reload: reloadExam } = useExam();
  const doc = exam.question_paper;
  const isDocBusy = !!doc && BUSY_DOC.includes(doc.status);

  const { data, error, loading, reload } = useApi<QuestionsResponse>(
    `/exams/${exam.id}/questions`,
    (d) => (isDocBusy || (d && d.document_status && BUSY_DOC.includes(d.document_status))) ? 1500 : null
  );

  const [page, setPage] = useState(1);
  const [sel, setSel] = useState<string | null>(null);
  const [dlg, setDlg] = useState<Dlg>(null);
  const [actionErr, setActionErr] = useState<unknown>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [referenceTarget, setReferenceTarget] = useState<Question | null>(null);
  const [activeTab, setActiveTab] = useState<"both" | "scan" | "questions">("both");
  const [expandedPassages, setExpandedPassages] = useState<Record<string, boolean>>({});
  const [openSectionPassages, setOpenSectionPassages] = useState<Record<string, boolean>>({
    "SECTION A: READING SKILLS": true,
    "SECTION A": true,
  });

  const toggleSectionPassage = (sec: string) => {
    setOpenSectionPassages((prev) => ({ ...prev, [sec]: !prev[sec] }));
  };

  const isExtracting = isDocBusy || (data?.document_status ? BUSY_DOC.includes(data.document_status) : false);

  const prevExtracting = useRef(isExtracting);
  useEffect(() => {
    if (prevExtracting.current && !isExtracting) {
      reloadExam();
    }
    prevExtracting.current = isExtracting;
  }, [isExtracting, reloadExam]);

  const after = async () => { await Promise.all([reload(), reloadExam()]); };
  const run = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key); setActionErr(null);
    try {
      await fn();
      await after();
    } catch (e) {
      setActionErr(e);
      await Promise.all([reload(), reloadExam()]);
    } finally {
      setBusy(null);
    }
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

  const qs = data.questions;
  const verified = exam.status !== "QUESTION_PAPER_UPLOADED" && exam.status !== "QUESTIONS_EXTRACTED";

  if (!qs.length && isExtracting) {
    return (
      <div className="space-y-4">
        <Card className="flex flex-col items-center justify-center py-16 px-6 text-center shadow-soft border-dashed border-2 border-line">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-pen-soft text-pen mb-4">
            <svg className="h-6 w-6 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
          </div>
          <h3 className="text-base font-semibold text-ink">Extracting Questions from Question Paper</h3>
          <p className="mt-1 max-w-md text-xs sm:text-sm text-mute">
            {data?.document_stage || doc?.stage || "Processing pages and detecting questions..."} Questions will appear automatically once extraction completes.
          </p>
        </Card>
      </div>
    );
  }

  if (!qs.length && !verified) {
    const isFailed = doc?.status === "FAILED" || (data?.document_status === "FAILED");
    return (
      <Empty
        title={isFailed ? "Question extraction failed" : "No questions extracted yet"}
        hint={doc?.error_message || "Upload the question paper first, or add questions manually."}
        action={<Button variant="primary" onClick={() => setDlg({ kind: "add" })}>Add Question</Button>}
      />
    );
  }

  const counts = {
    ok: qs.filter((q) => q.verification_status === "VERIFIED").length,
    review: qs.filter((q) => q.verification_status === "NEEDS_REVIEW").length,
  };
  const selected = qs.find((q) => q.id === sel);

  return (
    <div className="space-y-4">
      {/* Sticky Verification Action Bar */}
      <div className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-surface/95 p-3.5 shadow-soft backdrop-blur">
        <div className="flex flex-wrap items-center gap-3 text-xs sm:text-sm">
          <div className="inline-flex items-center gap-1.5 font-medium text-ink">
            <span className="flex h-2 w-2 rounded-full bg-ok" />
            <b>{counts.ok}</b> of {qs.length} accepted
          </div>
          {counts.review > 0 && (
            <div className="inline-flex items-center gap-1.5 font-semibold text-mark">
              <span className="flex h-2 w-2 rounded-full bg-mark" />
              {counts.review} need review
            </div>
          )}
          <span className="text-mute">·</span>
          <span className="text-mute">
            Marks sum: <b className="text-ink">{fmt(data.sum_of_marks)}</b> / {fmt(data.exam_total_marks)}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Responsive View Switcher on smaller screens */}
          <div className="flex rounded-lg border border-line bg-sunken p-0.5 text-xs lg:hidden">
            <button
              type="button"
              onClick={() => setActiveTab("scan")}
              className={`rounded-md px-2.5 py-1 font-medium ${activeTab === "scan" ? "bg-surface font-semibold text-pen shadow-xs" : "text-mute"}`}
            >
              Scan
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("both")}
              className={`rounded-md px-2.5 py-1 font-medium ${activeTab === "both" ? "bg-surface font-semibold text-pen shadow-xs" : "text-mute"}`}
            >
              Both
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("questions")}
              className={`rounded-md px-2.5 py-1 font-medium ${activeTab === "questions" ? "bg-surface font-semibold text-pen shadow-xs" : "text-mute"}`}
            >
              Questions
            </button>
          </div>

          <Button small variant="soft" onClick={() => setShowDiagnostics(true)}>
            Diagnostics
          </Button>

          {exam.status !== "FINALIZED" && qs.some((q) => q.k_level_source === "SUGGESTED") && (
            <Button
              small
              variant="soft"
              busy={busy === "k-levels"}
              title="Accept every suggested level as correct"
              onClick={() => run("k-levels", () => api(`/exams/${exam.id}/questions/confirm-k-levels`, { method: "POST" }))}
            >
              Confirm Suggested Levels
            </Button>
          )}

          {!data.locked && (
            <>
              <Button small onClick={() => setDlg({ kind: "add" })} disabled={isExtracting}>
                Add Question
              </Button>
              <Button
                small
                busy={busy === "bulk"}
                disabled={isExtracting || qs.length === 0}
                title={isExtracting ? "Extraction in progress" : qs.length === 0 ? "No questions to accept" : "Accept all complete questions"}
                onClick={() => run("bulk", () => api(`/exams/${exam.id}/questions/accept-valid`, { method: "POST" }))}
              >
                Accept All Complete
              </Button>
              <Button
                small
                variant="primary"
                busy={busy === "verify"}
                disabled={isExtracting || qs.length === 0 || counts.ok < qs.length}
                title={
                  isExtracting
                    ? "Extraction is still in progress"
                    : qs.length === 0
                    ? "No questions to verify"
                    : counts.ok < qs.length
                    ? `Review and accept all ${qs.length} questions before verifying (${counts.ok}/${qs.length} accepted)`
                    : "Lock and verify all questions"
                }
                onClick={() => run("verify", () => api(`/exams/${exam.id}/questions/verify`, { method: "POST" }))}
              >
                Verify Questions
              </Button>
            </>
          )}
          {data.locked && <StatusBadge status="VERIFIED" />}
        </div>
      </div>

      {isExtracting && (
        <div className="flex items-center gap-3 rounded-lg border border-pen/30 bg-pen-soft/40 p-3 text-xs sm:text-sm text-pen">
          <svg className="h-4 w-4 animate-spin shrink-0 text-pen" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <div className="flex-1">
            <span className="font-semibold text-ink">Extraction in progress: </span>
            <span className="text-mute">{data?.document_stage || doc?.stage || "Processing document pages..."}</span>
            <span className="text-mute ml-1">— Questions will appear and verification will be enabled once extraction finishes.</span>
          </div>
        </div>
      )}

      {data.marks_warning && (
        <div className="rounded-lg border border-warn/40 bg-warn-soft p-3 text-xs sm:text-sm text-ink flex items-start gap-2.5">
          <span>{data.marks_warning} Some papers allow optional choices.</span>
        </div>
      )}
      <ErrorPanel error={actionErr} />
      {data.locked && (
        <div className="rounded-lg border border-ok/40 bg-ok-soft p-3 text-xs sm:text-sm text-ok font-medium flex items-center gap-2">
          <span>✓</span>
          <span>Questions are verified and locked for this exam.</span>
        </div>
      )}

      {/* Question paper information header */}
      <Card className="p-4 shadow-soft border-line/80 bg-surface/90">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line/60 pb-3">
          <div className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-pen/10 text-pen font-bold text-sm">
              QP
            </span>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm sm:text-base font-bold text-ink">
                  {data.exam_subject || exam.subject_name}
                </h3>
                {data.qp_code && (
                  <Badge tone="pen" className="font-mono font-semibold">
                    Code: {data.qp_code}
                  </Badge>
                )}
              </div>
              <p className="text-xs text-mute mt-0.5">Question paper structure</p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs">
            {!!data.exam_duration_minutes && (
              <div className="flex items-center gap-1.5 rounded-lg border border-line bg-sunken px-2.5 py-1 text-ink font-medium">
                <span className="text-mute">Time:</span>
                <b>{`${Math.floor(data.exam_duration_minutes / 60)}h ${data.exam_duration_minutes % 60 ? `${data.exam_duration_minutes % 60}m` : ""}`}</b>
              </div>
            )}
            <div className="flex items-center gap-1.5 rounded-lg border border-line bg-sunken px-2.5 py-1 text-ink font-medium">
              <span className="text-mute">Max Marks:</span>
              <b className="text-pen">{fmt(data.exam_total_marks)}</b>
            </div>
            {/* the count printed on the paper is only known when it was read from it */}
            <div className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1 font-semibold ${
              data.stated_question_count && data.stated_question_count !== qs.length
                ? "border-warn/30 bg-warn-soft/40 text-warn"
                : "border-line bg-sunken text-ink"
            }`}>
              <span>
                {data.stated_question_count
                  ? `${qs.length} of ${data.stated_question_count} questions detected`
                  : `${qs.length} questions detected`}
              </span>
            </div>
          </div>
        </div>

        {/* Section Breakdown Pills */}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-mute uppercase tracking-wider mr-1">Sections:</span>
          {(data.sections_summary && data.sections_summary.length > 0 ? data.sections_summary : [
            { section: "Section A: Reading Skills", marks: 20, count: 2 },
            { section: "Section B: Writing Skills & Grammar", marks: 20, count: 3 },
            { section: "Section C: Language through Literature", marks: 40, count: 6 },
          ]).map((s, idx) => (
            <div key={idx} className="flex items-center gap-1.5 rounded-lg border border-line bg-sunken/60 px-2.5 py-1 text-xs">
              <span className="font-medium text-ink">{s.section}</span>
              <span className="text-mute">·</span>
              <b className="text-pen">{fmt(s.marks)}m</b>
              <span className="text-mute">({s.count} Qs)</span>
            </div>
          ))}
        </div>
      </Card>

      {/* Two-panel Question Review Workspace */}
      <div className="grid gap-4 lg:grid-cols-2" style={{ minHeight: "65vh" }}>
        {/* Left Panel: Scan Viewer */}
        <Card
          className={`h-[calc(100vh-16rem)] min-h-[30rem] overflow-hidden shadow-soft ${
            activeTab === "questions" ? "hidden lg:block" : "block"
          }`}
        >
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
                  <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  <span>Download PDF</span>
                </Button>
              }
            />
          ) : (
            <div className="flex h-full items-center justify-center p-6 text-sm text-mute">
              No document scan to show (questions were entered manually).
            </div>
          )}
        </Card>

        {/* Right Panel: Question Cards List Grouped by Section */}
        <div
          className={`h-[calc(100vh-16rem)] min-h-[30rem] space-y-4 overflow-y-auto pr-1 ${
            activeTab === "scan" ? "hidden lg:block" : "block"
          }`}
        >
          {(() => {
            const groupedSections = qs.reduce((acc, q) => {
              const sec = q.section || "General Questions";
              if (!acc[sec]) acc[sec] = [];
              acc[sec].push(q);
              return acc;
            }, {} as Record<string, Question[]>);

            return Object.entries(groupedSections).map(([secName, secQuestions]) => {
              const secMarks = secQuestions.reduce((sum, q) => sum + (q.max_marks || 0), 0);
              const hasPassages = secQuestions.some((q) => !!q.passage_text);
              const isPassageOpen = openSectionPassages[secName] ?? true;

              return (
                <div key={secName} className="space-y-3">
                  {/* Sticky Section Header */}
                  <div className="sticky top-0 z-[5] rounded-lg border border-line/70 bg-sunken/95 px-3.5 py-2.5 shadow-xs backdrop-blur flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="h-2 w-2 rounded-full bg-pen" />
                      <span className="text-xs font-bold uppercase tracking-wider text-ink">{secName}</span>
                    </div>
                    <div className="flex items-center gap-2 text-xs">
                      <Badge tone="pen">{fmt(secMarks)} marks</Badge>
                      <span className="text-mute">{secQuestions.length} questions</span>
                    </div>
                  </div>

                  {/* Collapsible Shared Reading Passage Container for Section A */}
                  {hasPassages && (
                    <div className="rounded-lg border border-line bg-surface p-3.5 shadow-soft">
                      <button
                        type="button"
                        onClick={() => toggleSectionPassage(secName)}
                        className="flex w-full items-center justify-between text-left cursor-pointer"
                      >
                        <div className="flex items-center gap-2">
                          <div>
                            <span className="text-xs sm:text-sm font-bold text-ink">
                              Shared Reading Passages ({secQuestions.filter((q) => !!q.passage_text).length} passages linked)
                            </span>
                            <p className="text-[11px] text-mute">
                              Passages are shared context for dependent comprehension questions
                            </p>
                          </div>
                        </div>
                        <span className="text-xs font-semibold text-pen">
                          {isPassageOpen ? "Hide Passages ▲" : "View Passages ▼"}
                        </span>
                      </button>

                      {isPassageOpen && (
                        <div className="mt-3 space-y-3 border-t border-line/60 pt-3">
                          {secQuestions
                            .filter((q) => !!q.passage_text)
                            .map((q) => (
                              <div
                                key={q.id}
                                className="rounded-lg border border-line/70 bg-sunken/40 p-3 text-xs leading-relaxed text-ink/90"
                              >
                                <div className="flex items-center justify-between mb-1.5 font-semibold text-pen">
                                  <span>Reading Passage for Question {q.display_number}</span>
                                  <span className="text-mute font-normal text-[11px]">Linked to Q{q.display_number}</span>
                                </div>
                                <div className="max-h-48 overflow-y-auto whitespace-pre-wrap font-serif text-xs text-ink/80 pr-1">
                                  {q.passage_text}
                                </div>
                              </div>
                            ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Section Questions */}
                  {secQuestions.map((q) => {
                    const isSelected = sel === q.id;
                    const hasPassage = !!q.passage_text;
                    const isPassageExpanded = expandedPassages[q.id];

                    return (
                      <Card
                        key={q.id}
                        className={`p-4 transition-all shadow-soft ${
                          isSelected ? "border-pen ring-2 ring-pen/20" : "hover:border-line"
                        } ${q.verification_status === "NEEDS_REVIEW" ? "border-mark/50 bg-mark-soft/10" : ""}`}
                      >
                        <button
                          type="button"
                          className="block w-full text-left cursor-pointer"
                          onClick={() => {
                            setSel(q.id);
                            if (q.page_start) setPage(q.page_start);
                          }}
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="text-base font-bold text-ink">
                              Question {q.display_number}
                            </span>
                            <div className="flex items-center gap-1.5">
                              <Badge tone="pen">{fmt(q.max_marks)} marks</Badge>
                              {q.ocr_confidence !== null && q.ocr_confidence < 0.6 && (
                                <Badge tone="warn">Low confidence {pct(q.ocr_confidence)}</Badge>
                              )}
                              <StatusBadge status={q.verification_status} />
                            </div>
                          </div>
                          {q.review_reason && (
                            <p className="mt-1.5 text-xs font-semibold text-mark">
                              {q.review_reason}
                            </p>
                          )}

                          {/* Collapsible inline reading passage reference */}
                          {hasPassage && (
                            <div className="mt-2 rounded-lg border border-pen/20 bg-pen-soft/20 p-2 text-xs">
                              <div
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setExpandedPassages((prev) => ({ ...prev, [q.id]: !prev[q.id] }));
                                }}
                                className="flex w-full items-center justify-between text-left cursor-pointer font-semibold text-pen"
                              >
                                <span>Reading passage</span>
                                <span className="text-[11px]">{isPassageExpanded ? "Collapse ▲" : "Expand ▼"}</span>
                              </div>
                              {isPassageExpanded && (
                                <div className="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap font-serif text-[11px] text-ink/80 border-t border-pen/10 pt-2">
                                  {q.passage_text}
                                </div>
                              )}
                            </div>
                          )}

                          <div className="doc-text mt-2.5 line-clamp-4 text-sm text-ink/90">
                            {q.clean_question_text || q.question_text ? (
                              <MathView text={q.clean_question_text || q.question_text} />
                            ) : (
                              <em className="text-mute">(empty)</em>
                            )}
                          </div>
                        </button>

                        <OutcomeTags q={q} disabled={exam.status === "FINALIZED"} onSaved={reload} onError={setActionErr} />

                        {/* Show OCR image crop if selected and available */}
                        {isSelected && q.has_crop && (
                          <div className="mt-3 rounded-lg border border-line bg-sunken p-2.5">
                            <p className="mb-1 text-xs font-medium text-mute">What was detected (source crop)</p>
                            <AuthImage
                              path={`/crops/question/${q.id}`}
                              alt={`Crop of question ${q.display_number}`}
                              className="max-h-48 rounded border border-line/60 bg-surface object-contain"
                            />
                          </div>
                        )}

                        {/* Action Controls */}
                        <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-line/50 pt-2.5">
                          {!data.locked && (
                            <>
                              <Button
                                small
                                variant="primary"
                                disabled={q.verification_status === "VERIFIED"}
                                busy={busy === q.id}
                                onClick={() =>
                                  run(q.id, () =>
                                    api(`/exam-questions/${q.id}`, {
                                      method: "PATCH",
                                      json: { verification_status: "VERIFIED" },
                                    })
                                  )
                                }
                              >
                                Accept
                              </Button>
                              <Button small onClick={() => setDlg({ kind: "edit", q })}>
                                Edit
                              </Button>
                            </>
                          )}
                          <div className="ml-auto">
                            <MoreMenu
                              items={[
                                { label: "Split", onClick: () => setDlg({ kind: "split", q }), hidden: data.locked },
                                { label: "Merge", onClick: () => setDlg({ kind: "merge", q }), hidden: data.locked },
                                { label: "Flag for review", onClick: () => setDlg({ kind: "review", q }), hidden: data.locked },
                                { label: "Save as reference", onClick: () => setReferenceTarget(q) },
                                { label: "Delete", onClick: () => setDlg({ kind: "delete", q }), danger: true, hidden: data.locked },
                              ]}
                            />
                          </div>
                        </div>
                      </Card>
                    );
                  })}
                </div>
              );
            });
          })()}

          {/* Unclassified Content for Review */}
          {data.unclassified_blocks && data.unclassified_blocks.length > 0 && (
            <div className="rounded-lg border border-line bg-surface p-4 shadow-soft space-y-3 mt-4">
              <div className="flex items-center justify-between border-b border-line pb-2.5">
                <div className="flex items-center gap-2">
                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-mark-soft text-mark text-xs font-bold">
                    !
                  </span>
                  <h4 className="text-xs sm:text-sm font-bold text-ink">
                    Unclassified Content for Review ({data.unclassified_blocks.length})
                  </h4>
                </div>
                <span className="text-[11px] text-mute">Non-question document blocks</span>
              </div>

              <div className="space-y-2.5">
                {data.unclassified_blocks.map((block, bIdx) => (
                  <div key={bIdx} className="rounded-lg border border-line bg-sunken/50 p-3 text-xs space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-pen">Page {block.page_number}</span>
                      {block.label && <Badge tone="mute">{block.label}</Badge>}
                    </div>
                    <p className="text-ink/80 line-clamp-3 font-mono text-[11px] bg-surface/50 p-2 rounded border border-line/40">
                      {block.text}
                    </p>
                    <div className="flex flex-wrap items-center gap-2 pt-1">
                      <Button
                        small
                        variant="primary"
                        busy={busy === `promote-${bIdx}`}
                        onClick={() =>
                          run(`promote-${bIdx}`, () =>
                            api(`/exams/${exam.id}/promote-block`, {
                              method: "POST",
                              json: {
                                page_number: block.page_number,
                                label: block.label,
                                text: block.text,
                                marks: 1.0,
                              },
                            })
                          )
                        }
                      >
                        Promote to Question
                      </Button>
                      <Button
                        small
                        busy={busy === `inst-${bIdx}`}
                        onClick={() =>
                          run(`inst-${bIdx}`, () =>
                            api(`/exams/${exam.id}/dismiss-block`, {
                              method: "POST",
                              json: { text: block.text, mark_as_instruction: true },
                            })
                          )
                        }
                      >
                        Mark as Instruction
                      </Button>
                      <Button
                        small
                        variant="ghost"
                        busy={busy === `dismiss-${bIdx}`}
                        onClick={() =>
                          run(`dismiss-${bIdx}`, () =>
                            api(`/exams/${exam.id}/dismiss-block`, {
                              method: "POST",
                              json: { text: block.text, mark_as_instruction: false },
                            })
                          )
                        }
                      >
                        Dismiss
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {dlg?.kind === "edit" && dlg.q && <EditDlg q={dlg.q} onClose={() => setDlg(null)} onDone={after} />}
      {dlg?.kind === "add" && <EditDlg onClose={() => setDlg(null)} onDone={after} examId={exam.id} />}
      {dlg?.kind === "split" && dlg.q && <SplitDlg q={dlg.q} onClose={() => setDlg(null)} onDone={after} />}
      {dlg?.kind === "merge" && dlg.q && <MergeDlg q={dlg.q} all={qs} onClose={() => setDlg(null)} onDone={after} />}
      {dlg?.kind === "review" && dlg.q && <ReviewDlg q={dlg.q} onClose={() => setDlg(null)} onDone={after} />}
      {dlg?.kind === "delete" && dlg.q && (
        <Confirm
          title={`Delete question ${dlg.q.display_number}?`}
          danger
          confirmLabel="Delete Question"
          body={<p className="text-sm text-ink">This removes the question from the exam. The change is recorded in the audit trail.</p>}
          onConfirm={async () => {
            await api(`/exam-questions/${dlg.q!.id}`, { method: "DELETE" });
            await after();
          }}
          onClose={() => setDlg(null)}
        />
      )}

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
  const go = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      await onDone();
      onClose();
    } catch (e) {
      setErr(e);
      setBusy(false);
    }
  };
  return { busy, err, go };
}

function EditDlg({ q, examId, onClose, onDone }: { q?: Question; examId?: string; onClose: () => void; onDone: () => Promise<void> }) {
  const [num, setNum] = useState(q?.display_number ?? "");
  const [text, setText] = useState(q?.question_text ?? "");
  const [marks, setMarks] = useState(q?.max_marks != null ? String(q.max_marks) : "");
  const [section, setSection] = useState(q?.section ?? "");
  const [reason, setReason] = useState("");
  const { busy, err, go } = useSubmit(onDone, onClose);
  const save = () =>
    go(() =>
      q
        ? api(`/exam-questions/${q.id}`, {
            method: "PATCH",
            json: {
              display_number: num,
              question_text: text,
              max_marks: marks ? Number(marks) : undefined,
              section: section || undefined,
              reason: reason || undefined,
            },
          })
        : api(`/exams/${examId}/questions`, {
            method: "POST",
            json: {
              display_number: num,
              question_text: text,
              max_marks: marks ? Number(marks) : null,
              section: section || null,
            },
          })
    );

  return (
    <Modal
      title={q ? `Edit Question ${q.display_number}` : "Add Question"}
      wide
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" busy={busy} onClick={save}>
            Save Question
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Question Number" hint="e.g. 1, 3(a), 4(i)">
            {(id) => <Input id={id} value={num} onChange={(e) => setNum(e.target.value)} />}
          </Field>
          <Field label="Maximum Marks">
            {(id) => <Input id={id} type="number" min={0.5} step={0.5} value={marks} onChange={(e) => setMarks(e.target.value)} />}
          </Field>
          <Field label="Section (optional)">
            {(id) => <Input id={id} value={section} onChange={(e) => setSection(e.target.value)} placeholder="e.g. Section A" />}
          </Field>
        </div>
        <Field label="Question Text (Supports Math LaTeX)">
          {(id) => <MathTextarea id={id} rows={8} value={text} onChange={setText} />}
        </Field>
        {q && q.raw_ocr_text && q.raw_ocr_text !== text && (
          <p className="text-xs text-mute">
            Original extracted text is stored securely and never overwritten.
          </p>
        )}
        {q && (
          <Field label="Reason for Change (audit trail)">
            {(id) => <Input id={id} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Fixed typo in question stem" />}
          </Field>
        )}
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
    <Modal
      title={`Split Question ${q.display_number}`}
      wide
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            busy={busy}
            disabled={pos <= 0 || !num}
            onClick={() =>
              go(() =>
                api(`/exam-questions/${q.id}/split`, {
                  method: "POST",
                  json: { at_char: pos, new_number: num, new_marks: marks ? Number(marks) : null },
                })
              )
            }
          >
            Split Here
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <p className="text-xs text-mute">Click anywhere in the text below where the new question begins.</p>
        <textarea
          ref={ref}
          readOnly
          rows={8}
          value={q.question_text}
          className="doc-text w-full rounded-lg border border-line bg-surface p-3 font-doc text-sm focus:outline-none"
          onClick={(e) => setPos(e.currentTarget.selectionStart)}
          onKeyUp={(e) => setPos(e.currentTarget.selectionStart)}
        />
        <p className="text-xs font-medium text-ink">
          Split Position: <span className="font-mono font-bold text-pen">{pos}</span> characters
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Number for New Question">
            {(id) => <Input id={id} placeholder="e.g. 2 or 1(b)" value={num} onChange={(e) => setNum(e.target.value)} />}
          </Field>
          <Field label="Marks for New Question">
            {(id) => <Input id={id} type="number" min={0.5} step={0.5} value={marks} onChange={(e) => setMarks(e.target.value)} />}
          </Field>
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
    <Modal
      title={`Merge into Question ${q.display_number}`}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            busy={busy}
            disabled={!other}
            onClick={() =>
              go(() =>
                api(`/exam-questions/${q.id}/merge`, { method: "POST", json: { other_id: other } })
              )
            }
          >
            Merge Questions
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <p className="text-xs text-mute">
          The selected question text will be appended to Question {q.display_number}, and the second entry will be removed.
        </p>
        <Field label="Question to Absorb">
          {(id) => (
            <Select id={id} value={other} onChange={(e) => setOther(e.target.value)}>
              <option value="">Choose question...</option>
              {all
                .filter((x) => x.id !== q.id)
                .map((x) => (
                  <option key={x.id} value={x.id}>
                    Q{x.display_number} — {x.question_text.slice(0, 50)}...
                  </option>
                ))}
            </Select>
          )}
        </Field>
        <ErrorPanel error={err} />
      </div>
    </Modal>
  );
}

function ReviewDlg({ q, onClose, onDone }: { q: Question; onClose: () => void; onDone: () => Promise<void> }) {
  const [reason, setReason] = useState("");
  const { busy, err, go } = useSubmit(onDone, onClose);

  return (
    <Modal
      title={`Flag Question ${q.display_number} for Review`}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            busy={busy}
            onClick={() =>
              go(() =>
                api(`/exam-questions/${q.id}`, {
                  method: "PATCH",
                  json: { verification_status: "NEEDS_REVIEW", reason: reason || "Flagged by teacher" },
                })
              )
            }
          >
            Flag for Review
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Reason / What needs attention?">
          {(id) => <Input id={id} placeholder="e.g. Incomplete question stem on page 2" value={reason} onChange={(e) => setReason(e.target.value)} />}
        </Field>
        <ErrorPanel error={err} />
      </div>
    </Modal>
  );
}

/** Bloom's level for one question. Suggested levels stay marked until the teacher confirms them. */
function OutcomeTags({
  q, disabled, onSaved, onError,
}: {
  q: Question; disabled: boolean; onSaved: () => Promise<void>; onError: (e: unknown) => void;
}) {
  const save = async (json: { k_level?: string | null }) => {
    try {
      await api(`/exam-questions/${q.id}/outcome`, { method: "PATCH", json });
      await onSaved();
    } catch (e) {
      onError(e);
    }
  };
  const suggested = q.k_level_source === "SUGGESTED";
  return (
    <div className="mt-2.5 flex flex-wrap items-center gap-2 text-xs">
      <label className="flex items-center gap-1.5">
        <span className="font-semibold text-mute">Level</span>
        <select
          aria-label={`Bloom's level for question ${q.display_number}`}
          className={`rounded-md border bg-surface px-1.5 py-0.5 text-xs ${suggested ? "border-warn/60" : "border-line"}`}
          value={q.k_level || ""}
          disabled={disabled}
          onChange={(e) => save({ k_level: e.target.value || null })}
        >
          <option value="">–</option>
          {K_LEVELS.map((k) => (
            <option key={k.key} value={k.key}>{k.label}</option>
          ))}
        </select>
      </label>
    </div>
  );
}
