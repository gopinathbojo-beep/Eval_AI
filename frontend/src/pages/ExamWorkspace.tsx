import { useState } from "react";
import { NavLink, Outlet, useNavigate, useOutletContext, useParams } from "react-router-dom";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import type { ExamDetail } from "../types";
import { BUSY_DOC, EXAM_STEPS } from "../utils/format";
import { Button, Confirm, ErrorPanel, Loading, PageHeader, StatusBadge } from "../components/ui";

export interface ExamCtx { exam: ExamDetail; reload: () => Promise<void> }
export const useExam = () => useOutletContext<ExamCtx>();

const TABS: [string, string][] = [
  ["", "1. Content & Key"],
  ["submissions", "2. Submissions"],
  ["evaluation", "3. Evaluation"],
  ["results", "4. Results & Marksheet"],
];

export default function ExamWorkspace() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const { data, error, loading, reload } = useApi<ExamDetail>(`/exams/${id}`, (d) =>
    [d.question_paper, d.answer_key_document].some((x) => x && BUSY_DOC.includes(x.status)) ? 2000 : null
  );

  if (loading) return <Loading />;
  if (error || !data) return <ErrorPanel error={error} />;

  const idx = EXAM_STEPS.findIndex((s) => s.key === data.status);

  return (
    <div className="space-y-5">
      {/* Exam Header */}
      <PageHeader
        title={data.name}
        sub={[
          data.class_name,
          data.subject_name,
          data.academic_year,
          data.exam_type,
          `${data.total_marks} Marks`,
        ].filter(Boolean).join(" · ")}
        actions={
          <div className="flex items-center gap-2.5">
            <StatusBadge status={data.status} />
            <Button
              small
              variant="ghost"
              className="text-mark hover:bg-mark-soft hover:text-mark"
              onClick={() => setConfirmDelete(true)}
              title={`Delete exam ${data.name}`}
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
              <span>Delete Exam</span>
            </Button>
          </div>
        }
      />

      {/* Modern Academic Step Stepper */}
      <div className="rounded-xl border border-line bg-surface p-3.5 shadow-soft">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-mute">Workflow Progress</span>
          <span className="text-xs font-medium text-ink">
            Step {Math.max(1, idx + 1)} of {EXAM_STEPS.length}
          </span>
        </div>
        <ol className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs" aria-label="Exam progress steps">
          {EXAM_STEPS.map((s, i) => {
            const isDone = i < idx;
            const isCurrent = i === idx;
            return (
              <li
                key={s.key}
                className={`flex flex-shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 transition-colors ${
                  isDone
                    ? "bg-ok-soft/60 text-ok font-medium"
                    : isCurrent
                    ? "bg-pen text-surface font-semibold shadow-xs"
                    : "bg-sunken text-mute"
                }`}
              >
                <span
                  className={`flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-bold ${
                    isDone
                      ? "bg-ok text-surface"
                      : isCurrent
                      ? "bg-surface text-pen"
                      : "bg-line text-mute"
                  }`}
                >
                  {isDone ? "✓" : i + 1}
                </span>
                <span className="whitespace-nowrap">{s.label}</span>
              </li>
            );
          })}
        </ol>
      </div>

      {/* Tabs Navigation */}
      <nav className="flex gap-1 overflow-x-auto border-b border-line pb-px" aria-label="Exam sections">
        {TABS.map(([to, text]) => (
          <NavLink
            key={to}
            end
            to={to}
            className={({ isActive }) =>
              `group relative flex items-center gap-2 whitespace-nowrap px-4 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? "text-pen"
                  : "text-mute hover:text-ink hover:bg-sunken/60 rounded-t-lg"
              }`
            }
          >
            {({ isActive }) => (
              <>
                <span>{text}</span>
                {isActive && (
                  <span className="absolute bottom-0 left-0 right-0 h-0.5 rounded-t bg-pen" />
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Tab Content */}
      <div className="pt-1">
        <Outlet context={{ exam: data, reload: async () => { await reload(); } } satisfies ExamCtx} />
      </div>

      {/* Delete Exam Confirmation Modal */}
      {confirmDelete && (
        <Confirm
          title={`Delete exam “${data.name}”?`}
          danger
          confirmLabel="Delete Exam"
          body={
            <div className="space-y-2 text-sm text-ink">
              <p>
                Are you sure you want to permanently delete exam <b>{data.name}</b>?
              </p>
              <p className="text-xs text-mute">
                This will permanently remove all extracted questions, answer keys, uploaded student answer sheets, and evaluation records. This action cannot be reversed.
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
    </div>
  );
}
