import { useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { FilteredEmptyState, TablePagination, TableToolbar } from "../components/TableToolbar";
import {
  Button,
  Card,
  Confirm,
  Empty,
  ErrorPanel,
  Field,
  Input,
  Loading,
  PageHeader,
  Select,
  StatusBadge,
  Textarea,
} from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useTableState } from "../hooks/useTableState";
import type { ClassRow, Exam, Subject } from "../types";
import { EXAM_STEPS } from "../utils/format";

export function ExamsList() {
  const { data, error, loading, reload } = useApi<Exam[]>("/exams");
  const [deletingExam, setDeletingExam] = useState<Exam | null>(null);

  const classOptions = useMemo(() => {
    if (!data) return [];
    const map = new Map<string, string>();
    for (const e of data) {
      if (e.class_name) map.set(e.class_name, e.class_name);
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

  const statusOptions = useMemo(() => {
    return EXAM_STEPS.map((s) => ({ value: s.key, label: s.label }));
  }, []);

  const table = useTableState<Exam>({
    data,
    searchFilter: (e, q) => e.name.toLowerCase().includes(q),
    filters: {
      class: (e, val) => (e.class_name || "") === val,
      subject: (e, val) => (e.subject_name || "") === val,
      status: (e, val) => e.status === val,
    },
    sortFns: {
      name: (a, b) => a.name.localeCompare(b.name),
      date: (a, b) => new Date(a.exam_date || 0).getTime() - new Date(b.exam_date || 0).getTime(),
      marks: (a, b) => (a.total_marks ?? 0) - (b.total_marks ?? 0),
    },
    defaultSort: "name",
    defaultOrder: "asc",
    initialPageSize: 10,
  });

  const sortOptions = [
    { value: "name", label: "Exam name" },
    { value: "date", label: "Exam date" },
    { value: "marks", label: "Total marks" },
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
      key: "status",
      label: "All Statuses",
      options: statusOptions,
      value: table.activeFilters.status || "",
      onChange: (val: string) => table.setFilter("status", val),
    },
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Exams Management"
        sub="Organize and monitor all examination workflows from question verification to final marks."
        actions={
          <Link to="/exams/new">
            <Button variant="primary" className="shadow-xs">
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              <span>Create New Exam</span>
            </Button>
          </Link>
        }
      />
      <ErrorPanel error={error} />
      {loading ? (
        <Loading />
      ) : !data?.length ? (
        <Empty
          title="No exams created yet"
          hint="Create an examination to upload its question paper and begin automated evaluation."
          action={
            <Link to="/exams/new">
              <Button variant="primary">Create Exam</Button>
            </Link>
          }
        />
      ) : (
        <>
          <TableToolbar
            searchPlaceholder="Search by exam name..."
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
            itemLabel="exams"
          />

          {table.filteredCount === 0 ? (
            <FilteredEmptyState
              title="No matching exams found"
              message="No exams match your search and filter criteria."
              onClearFilters={table.clearFilters}
            />
          ) : (
            <Card className="overflow-x-auto shadow-soft">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-line bg-surface text-xs font-semibold uppercase tracking-wider text-mute">
                  <tr>
                    <th className="px-4 py-3">Exam Details</th>
                    <th className="px-4 py-3">Class</th>
                    <th className="px-4 py-3">Subject</th>
                    <th className="px-4 py-3">Total Marks</th>
                    <th className="px-4 py-3">Workflow Status</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line text-sm">
                  {table.paginatedData.map((e) => (
                    <tr key={e.id} className="hover:bg-sunken/40">
                      <td className="px-4 py-3">
                        <Link
                          className="font-semibold text-pen hover:underline text-base block"
                          to={`/exams/${e.id}`}
                        >
                          {e.name}
                        </Link>
                        <div className="font-mono text-xs text-mute mt-0.5">
                          {e.academic_year ? `${e.academic_year} · ` : ""}
                          {e.exam_type}
                        </div>
                      </td>
                      <td className="px-4 py-3 font-medium text-ink">{e.class_name}</td>
                      <td className="px-4 py-3 font-medium text-ink">{e.subject_name}</td>
                      <td className="px-4 py-3 font-mono font-medium text-ink">{e.total_marks}</td>
                      <td className="px-4 py-3">
                        <StatusBadge status={e.status} />
                      </td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <div className="flex items-center justify-end gap-1.5">
                          <Link to={`/exams/${e.id}`}>
                            <Button small variant="soft">
                              <span>Open</span>
                              <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                              </svg>
                            </Button>
                          </Link>
                          <Button
                            small
                            variant="ghost"
                            className="text-mark hover:bg-mark-soft hover:text-mark"
                            onClick={() => setDeletingExam(e)}
                            title={`Delete exam ${e.name}`}
                          >
                            <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          </Button>
                        </div>
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
                itemLabel="exams"
                onPageChange={table.setPage}
                onPageSizeChange={table.setPageSize}
              />
            </Card>
          )}

          {deletingExam && (
            <Confirm
              title={`Delete exam “${deletingExam.name}”?`}
              danger
              confirmLabel="Delete Exam"
              body={
                <div className="space-y-2 text-sm text-ink">
                  <p>
                    Are you sure you want to permanently delete exam <b>{deletingExam.name}</b>?
                  </p>
                  <p className="text-xs text-mute">
                    All extracted questions, answer keys, uploaded answer sheets, and student evaluation results will be permanently removed. This action cannot be reversed.
                  </p>
                </div>
              }
              onConfirm={async () => {
                await api(`/exams/${deletingExam.id}`, { method: "DELETE" });
                await reload();
                setDeletingExam(null);
              }}
              onClose={() => setDeletingExam(null)}
            />
          )}
        </>
      )}
    </div>
  );
}

export function ExamNew() {
  const nav = useNavigate();
  const classes = useApi<ClassRow[]>("/classes");
  const subjects = useApi<Subject[]>("/subjects");
  const [f, setF] = useState({
    name: "",
    class_id: "",
    subject_id: "",
    exam_type: "Unit test",
    exam_date: "",
    duration_minutes: "",
    total_marks: "",
    instructions: "",
  });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) =>
    setF({ ...f, [k]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const ex = await api<Exam>("/exams", {
        method: "POST",
        json: {
          ...f,
          exam_date: f.exam_date || null,
          instructions: f.instructions || null,
          duration_minutes: f.duration_minutes ? Number(f.duration_minutes) : null,
          total_marks: Number(f.total_marks),
        },
      });
      nav(`/exams/${ex.id}`);
    } catch (x) {
      setError(x);
      setBusy(false);
    }
  };

  const noRefs = classes.data && subjects.data && (!classes.data.length || !subjects.data.length);

  return (
    <div className="max-w-3xl space-y-5">
      <PageHeader
        title="Create New Examination"
        sub="Set up exam details, select class & subject, and configure evaluation criteria."
        actions={
          <Link to="/exams">
            <Button variant="ghost">Cancel &amp; Return</Button>
          </Link>
        }
      />

      {noRefs && (
        <div className="rounded-xl border border-warn/40 bg-warn-soft p-4 text-sm text-ink flex items-start gap-3">
          <span className="text-warn font-bold text-base">⚠</span>
          <div>
            <p className="font-semibold text-warn">Prerequisites Required</p>
            <p className="text-xs text-mute mt-0.5">
              Please create at least one <Link className="underline font-medium text-pen" to="/classes">class</Link> and one{" "}
              <Link className="underline font-medium text-pen" to="/subjects">subject</Link> first before setting up an exam.
            </p>
          </div>
        </div>
      )}

      <form onSubmit={submit} className="space-y-4">
        <Card className="grid gap-4 p-6 shadow-soft sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Field label="Exam Name" hint="e.g. Midterm Physics Assessment 2026">
              {(id) => <Input id={id} required placeholder="Midterm Assessment" value={f.name} onChange={set("name")} />}
            </Field>
          </div>

          <Field label="Class">
            {(id) => (
              <Select id={id} required value={f.class_id} onChange={set("class_id")}>
                <option value="">Select class...</option>
                {classes.data?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>

          <Field label="Subject">
            {(id) => (
              <Select id={id} required value={f.subject_id} onChange={set("subject_id")}>
                <option value="">Select subject...</option>
                {subjects.data?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>

          <Field label="Exam Type">
            {(id) => <Input id={id} required placeholder="Unit test / Semester" value={f.exam_type} onChange={set("exam_type")} />}
          </Field>

          <Field label="Exam Date">
            {(id) => <Input id={id} type="date" value={f.exam_date} onChange={set("exam_date")} />}
          </Field>

          <Field label="Duration (minutes)">
            {(id) => (
              <Input
                id={id}
                type="number"
                min={1}
                placeholder="e.g. 90"
                value={f.duration_minutes}
                onChange={set("duration_minutes")}
              />
            )}
          </Field>

          <Field label="Total Maximum Marks">
            {(id) => (
              <Input
                id={id}
                type="number"
                min={1}
                step="0.5"
                required
                placeholder="e.g. 50"
                value={f.total_marks}
                onChange={set("total_marks")}
              />
            )}
          </Field>

          <div className="sm:col-span-2">
            <Field label="Instructions (optional)" hint="Any general exam guidance or section instructions">
              {(id) => <Textarea id={id} rows={3} placeholder="Answer all questions in Section A..." value={f.instructions} onChange={set("instructions")} />}
            </Field>
          </div>
        </Card>

        <ErrorPanel error={error} />

        <div className="flex items-center justify-end gap-3">
          <Link to="/exams">
            <Button variant="ghost">Cancel</Button>
          </Link>
          <Button type="submit" variant="primary" busy={busy} className="shadow-xs">
            Create Exam &amp; Continue
          </Button>
        </div>
      </form>
    </div>
  );
}
