import { useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { downloadFile } from "../api/client";
import { FilteredEmptyState, TablePagination, TableToolbar } from "../components/TableToolbar";
import { Badge, Button, Card, Empty, ErrorPanel, Loading, MathView, PageHeader, PenScore, StatusBadge } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useTableState } from "../hooks/useTableState";
import type { Evaluation, ResultResponse } from "../types";
import { OutcomeTables } from "../components/OutcomeTables";
import { date, fmt, kLabel } from "../utils/format";

export function EvaluationsList() {
  const { data, loading, error } = useApi<Evaluation[]>("/evaluations");

  return (
    <div className="space-y-4">
      <PageHeader
        title="Evaluations Queue"
        sub="Answer sheets being evaluated."
      />
      <ErrorPanel error={error} />
      {loading ? (
        <Loading />
      ) : !data?.length ? (
        <Empty title="No answer sheets uploaded" hint="Open an exam and upload student answer sheets to begin evaluation." />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((e) => (
            <Link
              key={e.id}
              to={e.status === "FINALIZED" ? `/results/${e.id}` : `/evaluations/${e.id}`}
              className="group block rounded-lg border border-line bg-surface p-4 shadow-soft transition-all hover:border-pen/40 hover:shadow-card"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-semibold text-ink group-hover:text-brown transition-colors">
                    {e.student.name}
                  </p>
                  <p className="font-mono text-xs text-mute">Roll: {e.student.roll_number}</p>
                </div>
                <StatusBadge status={e.status} />
              </div>
              <p className="mt-2 text-xs font-medium text-mute line-clamp-1">{e.exam_name}</p>
              <div className="mt-3 flex items-center justify-between border-t border-line/60 pt-2.5 text-xs">
                <span className="text-mute font-medium">
                  {e.status === "FINALIZED" ? "Evaluation Finalized" : "Evaluation in Progress"}
                </span>
                <span className="inline-flex items-center gap-1 font-semibold text-pen group-hover:translate-x-0.5 transition-transform">
                  {e.status === "FINALIZED" ? "View Results →" : "Review →"}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export function ResultsList() {
  const { data, loading, error } = useApi<Evaluation[]>("/results");

  const classOptions = useMemo(() => {
    if (!data) return [];
    const map = new Map<string, string>();
    for (const e of data) {
      const name = e.class_name || e.student.class_name;
      if (name) map.set(name, name);
    }
    return Array.from(map.entries())
      .map(([value, label]) => ({ value, label }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [data]);

  const subjectOptions = useMemo(() => {
    if (!data) return [];
    const map = new Map<string, string>();
    for (const e of data) {
      if (e.subject_name) map.set(e.subject_name, e.subject_name);
    }
    return Array.from(map.entries())
      .map(([value, label]) => ({ value, label }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [data]);

  const examOptions = useMemo(() => {
    if (!data) return [];
    const map = new Map<string, string>();
    for (const e of data) {
      if (e.exam_name) map.set(e.exam_name, e.exam_name);
    }
    return Array.from(map.entries())
      .map(([value, label]) => ({ value, label }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [data]);

  const table = useTableState<Evaluation>({
    data,
    searchFilter: (e, q) =>
      e.student.name.toLowerCase().includes(q) ||
      (e.exam_name || "").toLowerCase().includes(q),
    filters: {
      class: (e, val) => (e.class_name || e.student.class_name || "") === val,
      subject: (e, val) => (e.subject_name || "") === val,
      exam: (e, val) => (e.exam_name || "") === val,
    },
    sortFns: {
      student: (a, b) => a.student.name.localeCompare(b.student.name),
      marks: (a, b) => (a.total_marks ?? 0) - (b.total_marks ?? 0),
      percentage: (a, b) => (a.percentage ?? 0) - (b.percentage ?? 0),
      date: (a, b) => new Date(a.finalized_at || 0).getTime() - new Date(b.finalized_at || 0).getTime(),
    },
    defaultSort: "date",
    defaultOrder: "desc",
    initialPageSize: 10,
  });

  const sortOptions = [
    { value: "date", label: "Finalization date" },
    { value: "student", label: "Student name" },
    { value: "marks", label: "Marks" },
    { value: "percentage", label: "Percentage" },
  ];

  const filterConfigs = [
    {
      key: "class",
      label: "All Classes",
      options: classOptions,
      value: table.activeFilters.class || "",
      onChange: (val: string) => table.setFilter("class", val),
    },
    {
      key: "subject",
      label: "All Subjects",
      options: subjectOptions,
      value: table.activeFilters.subject || "",
      onChange: (val: string) => table.setFilter("subject", val),
    },
    {
      key: "exam",
      label: "All Exams",
      options: examOptions,
      value: table.activeFilters.exam || "",
      onChange: (val: string) => table.setFilter("exam", val),
    },
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Finalized Examination Results"
        sub="Finalized student results."
      />
      <ErrorPanel error={error} />
      {loading ? (
        <Loading />
      ) : !data?.length ? (
        <Empty title="No finalized results yet" hint="Results appear here once evaluations are finalized by teachers." />
      ) : (
        <>
          <TableToolbar
            searchPlaceholder="Search by student or exam name..."
            searchValue={table.search}
            onSearchChange={table.setSearch}
            filters={filterConfigs}
            sortOptions={sortOptions}
            sortValue={table.sortBy}
            onSortChange={table.setSortBy}
            sortOrder={table.sortOrder}
            onSortOrderToggle={table.toggleSortOrder}
            isFiltered={table.isFiltered}
            onClearFilters={table.clearFilters}
            totalCount={table.totalCount}
            filteredCount={table.filteredCount}
            itemLabel="results"
          />

          {table.filteredCount === 0 ? (
            <FilteredEmptyState
              title="No matching results found"
              message="No exam results match your current search and filter combination."
              onClearFilters={table.clearFilters}
            />
          ) : (
            <Card className="overflow-x-auto shadow-soft">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-line bg-surface text-xs font-semibold uppercase tracking-wider text-mute">
                  <tr>
                    <th className="px-4 py-3">Student</th>
                    <th className="px-4 py-3">Exam Name</th>
                    <th className="px-4 py-3">Class</th>
                    <th className="px-4 py-3">Subject</th>
                    <th className="px-4 py-3">Total Marks</th>
                    <th className="px-4 py-3">Score %</th>
                    <th className="px-4 py-3">Finalized Date</th>
                    <th className="px-4 py-3 text-right">Report</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line text-sm">
                  {table.paginatedData.map((e) => (
                    <tr key={e.id} className="hover:bg-hover">
                      <td className="px-4 py-3">
                        <Link className="font-semibold text-pen hover:underline block" to={`/results/${e.id}`}>
                          {e.student.name}
                        </Link>
                        <span className="font-mono text-xs text-mute">Roll: {e.student.roll_number}</span>
                      </td>
                      <td className="px-4 py-3 font-medium text-ink">{e.exam_name}</td>
                      <td className="px-4 py-3 text-mute">{e.class_name || e.student.class_name || "–"}</td>
                      <td className="px-4 py-3 text-mute">{e.subject_name || "–"}</td>
                      <td className="px-4 py-3 font-mono font-medium text-ink">
                        {fmt(e.total_marks)} / {fmt(e.maximum_marks)}
                      </td>
                      <td className="px-4 py-3 font-mono font-semibold text-ink">
                        <span className="rounded bg-ok-soft/70 px-2 py-0.5 text-xs text-ok">
                          {e.percentage}%
                        </span>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-mute">{date(e.finalized_at)}</td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <Link
                          to={`/results/${e.id}`}
                          className="inline-flex items-center gap-1 text-xs font-semibold text-pen hover:underline"
                        >
                          <span>View Report</span>
                          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                          </svg>
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <TablePagination
                currentPage={table.page}
                totalPages={table.totalPages}
                pageSize={table.pageSize}
                totalFilteredCount={table.filteredCount}
                itemLabel="results"
                onPageChange={table.setPage}
                onPageSizeChange={table.setPageSize}
              />
            </Card>
          )}
        </>
      )}
    </div>
  );
}

export function ResultPage() {
  const { id } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get("tab") === "detailed" ? "detailed" : "breakdown";
  const { data, loading, error } = useApi<ResultResponse>(`/evaluations/${id}/result`);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const handleTabChange = (tab: "breakdown" | "detailed") => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (tab === "detailed") {
          next.set("tab", "detailed");
        } else {
          next.delete("tab");
        }
        return next;
      },
      { replace: true }
    );
  };

  const handleDownloadReport = async () => {
    if (!id || !data) return;
    setDownloading(true);
    setDownloadError(null);
    try {
      const studentName = (data.evaluation.student.name || "Student").replace(/[^a-zA-Z0-9_-]/g, "_");
      const rollNumber = (data.evaluation.student.roll_number || "").replace(/[^a-zA-Z0-9_-]/g, "_");
      const examName = (data.exam.name || "Exam").replace(/[^a-zA-Z0-9_-]/g, "_");
      const fallbackFilename = `EvalAI_Report_${studentName}_${rollNumber}_${examName}.pdf`;
      await downloadFile(`/evaluations/${id}/report.pdf`, fallbackFilename);
    } catch (err: any) {
      setDownloadError(err?.message || "Failed to download evaluation report.");
    } finally {
      setDownloading(false);
    }
  };

  if (loading) return <Loading />;
  if (error || !data) return <ErrorPanel error={error} />;
  const s = data.evaluation.student;

  return (
    <div className="space-y-5">
      <PageHeader
        title={`${s.name} (${s.roll_number})`}
        sub={`${data.exam.name} · ${data.exam.subject} · ${data.exam.class}`}
        actions={
          <div className="flex flex-wrap items-center gap-2.5">
            {data.finalized ? (
              <>
                <StatusBadge status="FINALIZED" />
                <Button
                  variant="primary"
                  busy={downloading}
                  onClick={handleDownloadReport}
                  className="shadow-xs"
                  title="Download official PDF evaluation report"
                >
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                    />
                  </svg>
                  <span>Download Report (PDF)</span>
                </Button>
              </>
            ) : (
              <Link to={`/evaluations/${id}`}>
                <Button variant="primary">
                  <span>Continue Evaluation</span>
                  <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </Button>
              </Link>
            )}
          </div>
        }
      />

      {downloadError && (
        <div className="rounded-lg border border-mark/20 bg-mark-soft p-3.5 text-sm text-mark">
          {downloadError}
        </div>
      )}

      {/* Performance Summary Banner */}
      <Card className="flex flex-wrap items-center justify-between gap-6 p-6 shadow-soft">
        <div className="flex items-center gap-5">
          <PenScore got={data.total_marks} max={data.maximum_marks} />
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-mute">Total Marks Secured</p>
            <p className="text-2xl font-bold text-ink">
              {fmt(data.total_marks)} <span className="text-sm font-normal text-mute">/ {fmt(data.maximum_marks)}</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-6">
          <div className="text-right">
            <p className="text-xs font-semibold uppercase tracking-wider text-mute">Overall Percentage</p>
            <p className="text-2xl font-extrabold text-pen">{data.percentage}%</p>
          </div>
          <div>
            {data.finalized ? (
              <Badge tone="ok">Verified &amp; Finalized</Badge>
            ) : (
              <Badge tone="warn">Provisional</Badge>
            )}
          </div>
        </div>
      </Card>

      {/* Tabs Navigation */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
        <div className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface p-1.5 shadow-soft">
          {/* Tab 1: Marks Breakdown by Question */}
          <button
            type="button"
            onClick={() => handleTabChange("breakdown")}
            className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-xs sm:text-sm font-semibold transition-all select-none ${
              activeTab === "breakdown"
                ? "bg-pen text-white shadow-xs"
                : "text-mute hover:text-brown hover:bg-hover"
            }`}
          >
            <svg
              className="h-4 w-4 shrink-0"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.75}
                d="M3 10h18M3 14h18m-9-4v8m-7 4h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
              />
            </svg>
            <span>Marks Breakdown by Question</span>
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-mono font-bold ${
                activeTab === "breakdown"
                  ? "bg-white/20 text-white"
                  : "bg-sunken text-mute"
              }`}
            >
              {data.questions.length}
            </span>
          </button>

          {/* Tab 2: Detailed Question-by-Question Evaluation */}
          <button
            type="button"
            onClick={() => handleTabChange("detailed")}
            className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-xs sm:text-sm font-semibold transition-all select-none ${
              activeTab === "detailed"
                ? "bg-pen text-white shadow-xs"
                : "text-mute hover:text-brown hover:bg-hover"
            }`}
          >
            <svg
              className="h-4 w-4 shrink-0"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.75}
                d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
              />
            </svg>
            <span>Detailed Question-by-Question Evaluation</span>
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-mono font-bold ${
                activeTab === "detailed"
                  ? "bg-white/20 text-white"
                  : "bg-sunken text-mute"
              }`}
            >
              {data.questions.length}
            </span>
          </button>
        </div>
      </div>

      {/* Tab 1 Content: Marks Breakdown by Question */}
      {activeTab === "breakdown" && data.outcomes && <OutcomeTables outcomes={data.outcomes} />}
      {activeTab === "breakdown" && (
        <Card className="overflow-x-auto shadow-soft">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line bg-surface text-xs font-semibold uppercase tracking-wider text-mute">
              <tr>
                <th className="px-4 py-3">Question</th>
                <th className="px-4 py-3">Level</th>
                <th className="px-4 py-3">Marks Awarded</th>
                <th className="px-4 py-3">Max Marks</th>
                <th className="px-4 py-3">Evaluation Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line text-sm">
              {data.questions.map((q) => (
                <tr key={q.question_id} className="hover:bg-hover">
                  <td className="px-4 py-3 font-bold text-ink">Question {q.question}</td>
                  <td className="px-4 py-3 text-ink">{kLabel(q.k_level)}</td>
                  <td className="px-4 py-3 font-mono font-bold text-pen">{fmt(q.final_marks)}</td>
                  <td className="px-4 py-3 font-mono text-mute">{fmt(q.max_marks)}</td>
                  <td className="px-4 py-3">
                    {q.teacher_overridden ? (
                      <Badge tone="warn">Teacher Adjusted ({fmt(q.ai_marks)} &rarr; {fmt(q.final_marks)})</Badge>
                    ) : (
                      <Badge tone="ok">Evaluated</Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {/* Tab 2 Content: Detailed Question-by-Question Evaluation */}
      {activeTab === "detailed" && (
        <div className="space-y-4">
          {data.questions.map((q) => (
            <Card key={q.question_id} className="p-5 shadow-soft space-y-3.5">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line pb-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-base font-bold text-ink">Question {q.question}</span>
                    <Badge tone="pen">{fmt(q.max_marks)} Marks</Badge>
                    {q.teacher_overridden && (
                      <Badge tone="warn">Teacher Override</Badge>
                    )}
                  </div>
                  <div className="doc-text mt-1.5 text-sm text-ink/80">
                    <MathView text={q.question_text} />
                  </div>
                </div>
                <div className="text-right flex-shrink-0">
                  <PenScore got={q.final_marks} max={q.max_marks} />
                  {q.teacher_overridden && (
                    <p className="mt-1 font-mono text-[11px] text-warn font-medium">
                      Adjusted from {fmt(q.ai_marks)}
                    </p>
                  )}
                </div>
              </div>

              {/* Answer Comparison Cards */}
              <div className="grid gap-3.5 md:grid-cols-2">
                <div className="rounded-lg border border-line bg-sunken/50 p-3.5">
                  <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-mute">
                    Student's Written Answer
                  </p>
                  <div className="doc-text rounded-lg bg-surface border border-line/60 p-3 text-sm text-ink">
                    {q.student_answer ? (
                      <MathView text={q.student_answer} />
                    ) : (
                      <em className="text-mute">No answer written or detected</em>
                    )}
                  </div>
                </div>

                <div className="rounded-lg border border-line bg-pen-soft/20 p-3.5">
                  <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-pen">
                    Official Model Answer
                  </p>
                  <div className="doc-text rounded-lg bg-surface border border-pen/20 p-3 text-sm text-ink">
                    <MathView text={q.official_answer} />
                  </div>
                </div>
              </div>

              {/* AI Feedback */}
              {q.feedback && (
                <div className="rounded-lg bg-sunken p-3 text-xs sm:text-sm text-ink border border-line/60">
                  <span className="font-semibold text-pen">Evaluator Assessment: </span>
                  <span className="text-ink/90">{q.feedback}</span>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
