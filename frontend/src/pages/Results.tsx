import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { downloadFile } from "../api/client";
import { FilteredEmptyState, TablePagination, TableToolbar } from "../components/TableToolbar";
import { Badge, Button, Card, Empty, ErrorPanel, Loading, PageHeader, PenScore, StatusBadge } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useTableState } from "../hooks/useTableState";
import type { Evaluation, ResultResponse } from "../types";
import { date, fmt } from "../utils/format";

export function EvaluationsList() {
  const { data, loading, error } = useApi<Evaluation[]>("/evaluations");
  return (
    <>
      <PageHeader title="Evaluations" />
      <ErrorPanel error={error} />
      {loading ? (
        <Loading />
      ) : !data?.length ? (
        <Empty title="No answer sheets yet" hint="Open an exam and upload answer sheets." />
      ) : (
        <Card className="divide-y divide-line">
          {data.map((e) => (
            <Link
              key={e.id}
              to={e.status === "FINALIZED" ? `/results/${e.id}` : `/evaluations/${e.id}`}
              className="flex flex-wrap items-center justify-between gap-2 p-4 hover:bg-sunken"
            >
              <div>
                <p className="font-medium">
                  {e.student.name} <span className="text-mute">({e.student.roll_number})</span>
                </p>
                <p className="text-xs text-mute">{e.exam_name}</p>
              </div>
              <StatusBadge status={e.status} />
            </Link>
          ))}
        </Card>
      )}
    </>
  );
}

export function ResultsList() {
  const { data, loading, error } = useApi<Evaluation[]>("/results");

  // Filter dropdown options derived from actual database data
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
    <>
      <PageHeader title="Results" />
      <ErrorPanel error={error} />
      {loading ? (
        <Loading />
      ) : !data?.length ? (
        <Empty title="No finalized results yet" hint="Results appear here once a teacher finalizes an evaluation." />
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
            <Card className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-line text-left text-mute">
                  <tr>
                    {["Student", "Exam", "Class", "Subject", "Marks", "Percentage", "Finalized", "Actions"].map((h) => (
                      <th key={h} className="px-4 py-2 font-medium">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {table.paginatedData.map((e) => (
                    <tr key={e.id} className="hover:bg-sunken">
                      <td className="px-4 py-2">
                        <Link className="font-medium text-pen hover:underline" to={`/results/${e.id}`}>
                          {e.student.name}
                        </Link>{" "}
                        <span className="text-mute">({e.student.roll_number})</span>
                      </td>
                      <td className="px-4 py-2">{e.exam_name}</td>
                      <td className="px-4 py-2 text-mute">{e.class_name || e.student.class_name || "–"}</td>
                      <td className="px-4 py-2 text-mute">{e.subject_name || "–"}</td>
                      <td className="px-4 py-2">
                        {fmt(e.total_marks)} / {fmt(e.maximum_marks)}
                      </td>
                      <td className="px-4 py-2">{e.percentage}%</td>
                      <td className="px-4 py-2 text-mute">{date(e.finalized_at)}</td>
                      <td className="px-4 py-2">
                        <Link
                          to={`/results/${e.id}`}
                          className="inline-flex items-center gap-1 text-xs font-medium text-pen hover:underline"
                        >
                          View &amp; Report &rarr;
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
    </>
  );
}

export function ResultPage() {
  const { id } = useParams();
  const { data, loading, error } = useApi<ResultResponse>(`/evaluations/${id}/result`);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const handleDownloadReport = async () => {
    if (!id || !data) return;
    setDownloading(true);
    setDownloadError(null);
    try {
      const studentName = (data.evaluation.student.name || "Student").replace(/[^a-zA-Z0-9_-]/g, "_");
      const rollNumber = (data.evaluation.student.roll_number || "").replace(/[^a-zA-Z0-9_-]/g, "_");
      const examName = (data.exam.name || "Exam").replace(/[^a-zA-Z0-9_-]/g, "_");
      const fallbackFilename = `ADEM_Report_${studentName}_${rollNumber}_${examName}.pdf`;
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
    <>
      <PageHeader
        title={`${s.name} (${s.roll_number})`}
        sub={`${data.exam.name} · ${data.exam.subject} · ${data.exam.class}`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {data.finalized ? (
              <>
                <StatusBadge status="FINALIZED" />
                <Button
                  variant="primary"
                  busy={downloading}
                  onClick={handleDownloadReport}
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
                  <span>Download Report</span>
                </Button>
              </>
            ) : (
              <Link to={`/evaluations/${id}`} className="text-sm text-pen hover:underline">
                Not final yet. Continue evaluating
              </Link>
            )}
          </div>
        }
      />
      {downloadError && (
        <div className="mb-4 rounded-md border border-mark/20 bg-mark-soft p-3 text-sm text-mark">
          {downloadError}
        </div>
      )}
      <Card className="mb-5 flex flex-wrap items-center gap-6 p-5">
        <PenScore got={data.total_marks} max={data.maximum_marks} />
        <div>
          <p className="text-sm text-mute">Percentage</p>
          <p className="text-2xl font-semibold">{data.percentage}%</p>
        </div>
        {!data.finalized && <Badge tone="warn">Provisional</Badge>}
      </Card>
      <Card className="mb-5 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-line text-left text-mute">
            <tr>
              <th className="px-4 py-2 font-medium">Question</th>
              <th className="px-4 py-2 font-medium">Marks</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {data.questions.map((q) => (
              <tr key={q.question_id}>
                <td className="px-4 py-2">Q{q.question}</td>
                <td className="px-4 py-2">
                  {fmt(q.final_marks)}/{fmt(q.max_marks)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <div className="space-y-3">
        {data.questions.map((q) => (
          <Card key={q.question_id} className="p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <p className="font-semibold">Question {q.question}</p>
                <p className="doc-text mt-1 text-sm text-mute">{q.question_text}</p>
              </div>
              <div className="text-right">
                <PenScore got={q.final_marks} max={q.max_marks} />
                {q.teacher_overridden && (
                  <p className="mt-1 text-xs text-warn">
                    Teacher changed AI mark {fmt(q.ai_marks)} → {fmt(q.final_marks)}
                  </p>
                )}
              </div>
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <div>
                <p className="mb-1 text-xs font-medium text-mute">Student answer</p>
                <p className="doc-text rounded bg-sunken p-2 text-sm">{q.student_answer ?? <em className="text-mute">No answer</em>}</p>
              </div>
              <div>
                <p className="mb-1 text-xs font-medium text-mute">Official answer</p>
                <p className="doc-text rounded bg-sunken p-2 text-sm">{q.official_answer ?? "–"}</p>
              </div>
            </div>
            {q.feedback && (
              <p className="mt-2 text-sm">
                <span className="font-medium">Feedback:</span> {q.feedback}
              </p>
            )}
          </Card>
        ))}
      </div>
    </>
  );
}
