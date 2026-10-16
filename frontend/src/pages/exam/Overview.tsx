import { Link } from "react-router-dom";
import { useApi } from "../../hooks/useApi";
import type { AuditRow } from "../../types";
import { date, label } from "../../utils/format";
import { Button, Card, Stat } from "../../components/ui";
import { useExam } from "../ExamWorkspace";

const NEXT: Record<string, [string, string, string]> = {
  DRAFT: ["Upload the Question Paper", "question-paper", "The model reads each page and proposes the extracted questions."],
  QUESTION_PAPER_UPLOADED: ["Wait for Paper Processing", "question-paper", "Or check status and fix any failed pages."],
  QUESTIONS_EXTRACTED: ["Review and Verify Questions", "questions", "Verify each question number, text, and marks against the page scan."],
  QUESTIONS_VERIFIED: ["Upload or Generate Answer Key", "answer-key", "Provide the official answers or generate model answers using AI."],
  ANSWER_KEY_UPLOADED: ["Review and Verify Answer Key", "answer-key", "Confirm every question has an approved answer and marking criteria."],
  ANSWER_KEY_VERIFIED: ["Upload Student Answer Sheets", "answer-sheets", "Upload scanned PDF or image sheets for each student."],
  READY_FOR_EVALUATION: ["Review Mapping and Run Evaluation", "evaluation", "Inspect question mapping and trigger AI grading."],
  EVALUATING: ["Evaluation is in Progress", "evaluation", "AI is assessing student answers against verified criteria."],
  REVIEW_REQUIRED: ["Review Marks & Finalize Students", "evaluation", "Inspect AI feedback, adjust marks if needed, and finalize."],
  FINALIZED: ["All Results Finalized", "results", "All student evaluations are final. Download marksheets and reports."],
};

export default function Overview() {
  const { exam } = useExam();
  const audit = useApi<AuditRow[]>(`/exams/${exam.id}/audit-logs`);
  const [title, to, hint] = NEXT[exam.status] || ["Continue Workflow", "", ""];

  return (
    <div className="space-y-6">
      {/* Recommended Next Action Banner */}
      <Card className="relative overflow-hidden border-pen/20 bg-gradient-to-r from-pen-soft/60 via-surface to-surface p-5 shadow-soft">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="inline-flex items-center gap-1.5 rounded-full bg-pen/10 px-2.5 py-0.5 text-xs font-semibold text-pen">
              <span className="h-1.5 w-1.5 rounded-full bg-pen animate-pulse" />
              Recommended Next Action
            </div>
            <h2 className="text-lg font-bold text-ink">{title}</h2>
            {hint && <p className="text-xs text-mute max-w-xl">{hint}</p>}
          </div>
          {to && (
            <Link to={to}>
              <Button variant="primary" className="shadow-xs">
                <span>Continue</span>
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
              </Button>
            </Link>
          )}
        </div>
      </Card>

      {/* Overview Stat Grid */}
      <div className="grid grid-cols-2 gap-3.5 sm:grid-cols-4">
        <Stat
          label="Total Questions"
          value={exam.question_count}
          icon={
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
        />
        <Stat
          label="Verified Questions"
          value={`${exam.verified_question_count} / ${exam.question_count}`}
          icon={
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
        />
        <Stat
          label="Answer Sheets"
          value={exam.evaluation_count}
          icon={
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          }
        />
        <Stat
          label="Finalized Evaluations"
          value={`${exam.finalized_count} / ${exam.evaluation_count}`}
          icon={
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M5 13l4 4L19 7" />
            </svg>
          }
        />
      </div>

      {/* Instructions if present */}
      {exam.instructions && (
        <Card className="space-y-1.5 p-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-mute">Exam Instructions</p>
          <div className="doc-text text-sm text-ink/90 whitespace-pre-wrap">{exam.instructions}</div>
        </Card>
      )}

      {/* Audit Log */}
      <section className="space-y-2.5">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink">Exam Activity & Audit History</h2>
          <span className="text-xs text-mute">{audit.data?.length ?? 0} log entries</span>
        </div>
        {audit.data?.length ? (
          <Card className="max-h-80 overflow-auto shadow-soft">
            <table className="w-full text-left text-sm">
              <thead className="sticky top-0 z-10 border-b border-line bg-surface text-xs font-semibold uppercase tracking-wider text-mute">
                <tr>
                  <th className="px-4 py-2.5">Timestamp</th>
                  <th className="px-4 py-2.5">User</th>
                  <th className="px-4 py-2.5">Action</th>
                  <th className="px-4 py-2.5">Change Summary</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line text-xs">
                {audit.data.map((a) => (
                  <tr key={a.id} className="align-top hover:bg-sunken/40">
                    <td className="whitespace-nowrap px-4 py-2.5 font-mono text-mute">{date(a.created_at)}</td>
                    <td className="px-4 py-2.5 font-medium text-ink">{a.user ?? "System"}</td>
                    <td className="px-4 py-2.5">
                      <span className="inline-block rounded bg-sunken px-2 py-0.5 font-medium text-ink border border-line/60">
                        {label(a.action)}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-mute">
                      {a.old_value != null && (
                        <span className="font-mono text-[11px] text-mark/80">
                          {JSON.stringify(a.old_value).slice(0, 60)} &rarr;{" "}
                        </span>
                      )}
                      {a.new_value != null && (
                        <span className="font-mono text-[11px] text-ok/90">
                          {JSON.stringify(a.new_value).slice(0, 60)}
                        </span>
                      )}
                      {a.reason && (
                        <span className="block mt-0.5 italic text-mute">
                          Reason: {a.reason}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        ) : (
          <p className="text-xs text-mute">No changes recorded yet in the audit log.</p>
        )}
      </section>
    </div>
  );
}
