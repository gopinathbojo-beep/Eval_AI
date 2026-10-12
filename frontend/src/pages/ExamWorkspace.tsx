import { NavLink, Outlet, useOutletContext, useParams } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import type { ExamDetail } from "../types";
import { BUSY_DOC, EXAM_STEPS } from "../utils/format";
import { ErrorPanel, Loading, PageHeader, StatusBadge } from "../components/ui";

export interface ExamCtx { exam: ExamDetail; reload: () => Promise<void> }
export const useExam = () => useOutletContext<ExamCtx>();

const TABS: [string, string][] = [
  ["", "Overview"], ["question-paper", "Question paper"], ["questions", "Questions"], ["answer-key", "Answer key"],
  ["students", "Students"], ["answer-sheets", "Answer sheets"], ["evaluation", "Evaluation"], ["results", "Results"],
];

export default function ExamWorkspace() {
  const { id } = useParams();
  const { data, error, loading, reload } = useApi<ExamDetail>(`/exams/${id}`, (d) =>
    [d.question_paper, d.answer_key_document].some((x) => x && BUSY_DOC.includes(x.status)) ? 2000 : null);
  if (loading) return <Loading />;
  if (error || !data) return <ErrorPanel error={error} />;
  const idx = EXAM_STEPS.findIndex((s) => s.key === data.status);
  return (
    <>
      <PageHeader title={data.name} sub={[data.class_name, data.subject_name, data.academic_year, `${data.total_marks} marks`].filter(Boolean).join(" · ")} actions={<StatusBadge status={data.status} />} />
      <ol className="mb-4 flex flex-wrap gap-x-1 gap-y-1 text-xs" aria-label="Exam progress">
        {EXAM_STEPS.map((s, i) => (
          <li key={s.key} className={`rounded px-2 py-0.5 ${i < idx ? "bg-ok-soft text-ok" : i === idx ? "bg-pen text-surface" : "bg-sunken text-mute"}`}>{s.label}</li>
        ))}
      </ol>
      <nav className="mb-5 flex gap-1 overflow-x-auto border-b border-line" aria-label="Exam sections">
        {TABS.map(([to, text]) => (
          <NavLink key={to} end to={to} className={({ isActive }) => `whitespace-nowrap border-b-2 px-3 py-2 text-sm ${isActive ? "border-pen font-medium text-pen" : "border-transparent text-mute hover:text-ink"}`}>{text}</NavLink>
        ))}
      </nav>
      <Outlet context={{ exam: data, reload: async () => { await reload(); } } satisfies ExamCtx} />
    </>
  );
}
