import { useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { FilteredEmptyState, TablePagination, TableToolbar } from "../components/TableToolbar";
import {
  Button,
  Card,
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
  const { data, error, loading } = useApi<Exam[]>("/exams");

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
    <>
      <PageHeader
        title="Exams"
        actions={
          <Link to="/exams/new">
            <Button variant="primary">Create exam</Button>
          </Link>
        }
      />
      <ErrorPanel error={error} />
      {loading ? (
        <Loading />
      ) : !data?.length ? (
        <Empty title="No exams yet" hint="Create an exam, then upload its question paper." />
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
              message="No exams match your current search and filter combination."
              onClearFilters={table.clearFilters}
            />
          ) : (
            <Card className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-line text-left text-mute">
                  <tr>
                    {["Exam", "Class", "Subject", "Total marks", "Status"].map((h) => (
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
                        <Link className="font-medium text-pen hover:underline" to={`/exams/${e.id}`}>
                          {e.name}
                        </Link>
                        <div className="text-xs text-mute">
                          {e.academic_year ? `${e.academic_year} · ` : ""}
                          {e.exam_type}
                        </div>
                      </td>
                      <td className="px-4 py-2">{e.class_name}</td>
                      <td className="px-4 py-2">{e.subject_name}</td>
                      <td className="px-4 py-2">{e.total_marks}</td>
                      <td className="px-4 py-2">
                        <StatusBadge status={e.status} />
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
        </>
      )}
    </>
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
    <>
      <PageHeader title="Create exam" />
      {noRefs && (
        <div className="mb-4 rounded-lg border border-warn/40 bg-warn-soft p-3 text-sm">
          Add at least one <Link className="underline" to="/classes">class</Link> and one{" "}
          <Link className="underline" to="/subjects">subject</Link> first.
        </div>
      )}
      <form onSubmit={submit} className="max-w-3xl space-y-4">
        <Card className="grid gap-4 p-5 sm:grid-cols-2">
          <Field label="Exam name">
            {(id) => <Input id={id} required value={f.name} onChange={set("name")} />}
          </Field>
          <Field label="Class">
            {(id) => (
              <Select id={id} required value={f.class_id} onChange={set("class_id")}>
                <option value="">Choose</option>
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
                <option value="">Choose</option>
                {subjects.data?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Exam type">
            {(id) => <Input id={id} required value={f.exam_type} onChange={set("exam_type")} />}
          </Field>
          <Field label="Exam date">
            {(id) => <Input id={id} type="date" value={f.exam_date} onChange={set("exam_date")} />}
          </Field>
          <Field label="Duration (minutes)">
            {(id) => (
              <Input
                id={id}
                type="number"
                min={1}
                value={f.duration_minutes}
                onChange={set("duration_minutes")}
              />
            )}
          </Field>
          <Field label="Total marks">
            {(id) => (
              <Input
                id={id}
                type="number"
                min={1}
                step="0.5"
                required
                value={f.total_marks}
                onChange={set("total_marks")}
              />
            )}
          </Field>
          <div className="sm:col-span-2">
            <Field label="Instructions">
              {(id) => <Textarea id={id} rows={3} value={f.instructions} onChange={set("instructions")} />}
            </Field>
          </div>
        </Card>
        <ErrorPanel error={error} />
        <Button type="submit" variant="primary" busy={busy}>
          Create exam
        </Button>
      </form>
    </>
  );
}
