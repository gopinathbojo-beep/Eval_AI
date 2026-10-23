import { useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate, useOutletContext, useParams } from "react-router-dom";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useCrumbName } from "../context/Crumbs";
import type { ExamDetail } from "../types";
import { BUSY_DOC } from "../utils/format";
import { Button, Confirm, ErrorPanel, Loading, PageHeader } from "../components/ui";

export interface ExamCtx { exam: ExamDetail; reload: () => Promise<void> }
export const useExam = () => useOutletContext<ExamCtx>();

const TABS: [string, string][] = [
  ["", "Setup"],
  ["submissions", "Answer Sheets"],
  ["evaluation", "Evaluation"],
  ["results", "Results"],
];

export default function ExamWorkspace() {
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const { data, error, loading, reload } = useApi<ExamDetail>(`/exams/${id}`, (d) =>
    [d.question_paper, d.answer_key_document].some((x) => x && BUSY_DOC.includes(x.status)) ? 2000 : null
  );
  useCrumbName(id, data?.name);

  if (loading) return <Loading />;
  if (error || !data) return <ErrorPanel error={error} />;

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

      {/* Tabs Navigation */}
      <nav className="-mb-5 flex items-end gap-1.5 overflow-x-auto border-b border-line px-1" aria-label="Exam sections">
        {TABS.map(([to, text], step) => {
          const tabPath = to ? `/exams/${id}/${to}` : `/exams/${id}`;
          const isTabActive = (() => {
            if (to === "") {
              return (
                location.pathname === `/exams/${id}` ||
                location.pathname.startsWith(`/exams/${id}/content`) ||
                location.pathname.startsWith(`/exams/${id}/overview`) ||
                location.pathname.startsWith(`/exams/${id}/question-paper`) ||
                location.pathname.startsWith(`/exams/${id}/questions`) ||
                location.pathname.startsWith(`/exams/${id}/answer-key`)
              );
            }
            if (to === "submissions") {
              return (
                location.pathname.startsWith(`/exams/${id}/submissions`) ||
                location.pathname.startsWith(`/exams/${id}/students`) ||
                location.pathname.startsWith(`/exams/${id}/answer-sheets`)
              );
            }
            return location.pathname.startsWith(`/exams/${id}/${to}`);
          })();

          return (
            <NavLink
              key={to}
              to={tabPath}
              className={`group relative -mb-px flex items-center gap-2 whitespace-nowrap rounded-t-md border px-4 py-2.5 text-sm font-medium transition-ui ${
                isTabActive
                  ? "border-line border-b-surface border-t-2 border-t-pen bg-surface text-ink"
                  : "border-transparent text-mute hover:bg-hover hover:text-brown"
              }`}
            >
              <span
                className={`flex h-5 w-5 items-center justify-center rounded-full border font-display text-[11px] font-semibold ${
                  isTabActive ? "border-mark text-mark" : "border-line text-mute group-hover:border-ink/30"
                }`}
              >
                {step + 1}
              </span>
              <span>{text}</span>
            </NavLink>
          );
        })}
      </nav>

      {/* Tab Content */}
      <div className="rounded-b-lg border border-t-0 border-line bg-surface/60 p-4 pt-6 sm:p-6 sm:pt-7">
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
