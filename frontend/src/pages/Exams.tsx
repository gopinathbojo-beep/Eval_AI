import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import {
  FilteredEmptyState,
  TablePagination,
  TableToolbar,
} from "../components/TableToolbar";
import {
  LinkButton,
  Button,
  Card,
  Confirm,
  Empty,
  ErrorPanel,
  Field,
  Input,
  Loading,
  Modal,
  PageCanvas,
  PageHeader,
  Select,
  StatusBadge,
} from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useTableState } from "../hooks/useTableState";
import type { CatalogSubject, Exam, ReportDetailKey } from "../types";
import { UploadZone } from "../components/DocPanel";
import PaperGenerator, { type GenerateBody } from "../components/PaperGenerator";

/** What the exam's printed reports say. Only the wording on the reports changes: marks and grading are untouched. */
function EditReportDetails({ exam, onClose, onSaved }: { exam: Exam; onClose: () => void; onSaved: () => Promise<void> | void }) {
  const fields: { key: ReportDetailKey; label: string; current: string; max: number; hint?: string }[] = [
    { key: "name", label: "Examination", current: exam.name, max: 200 },
    { key: "class_name", label: "Class", current: exam.class_name, max: 100 },
    { key: "subject", label: "Subject", current: exam.subject_name, max: 200 },
    { key: "exam_type", label: "Exam type", current: exam.exam_type, max: 50 },
    { key: "academic_year", label: "Academic year", current: exam.academic_year, max: 20 },
    { key: "exam_date", label: "Exam date", current: exam.exam_date ?? "", max: 20, hint: "e.g. 05 Nov 2026" },
  ];
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(fields.map((f) => [f.key, exam.report_details?.[f.key] ?? f.current])));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      // a value equal to the exam's own is not stored, so the report keeps following the exam
      const json = Object.fromEntries(fields.map((f) => {
        const v = (values[f.key] ?? "").trim();
        return [f.key, v === f.current ? null : v || null];
      }));
      await api(`/exams/${exam.id}/report-details`, { method: "PUT", json });
      await onSaved();
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };

  return (
    <Modal title={`Edit report details: ${exam.name}`} onClose={onClose}>
      <form onSubmit={save} className="space-y-4">
        <p className="text-xs text-mute">
          These appear on this exam's student reports and exam report. Marks and grading do not change. Leave a box
          empty to use the exam's own value. Student name, roll number and registration number belong to each student.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          {fields.map((f) => (
            <Field key={f.key} label={f.label} hint={f.hint}>
              {(id) => <Input id={id} maxLength={f.max} placeholder={f.current} value={values[f.key] ?? ""}
                              onChange={(e) => setValues({ ...values, [f.key]: e.target.value })} />}
            </Field>
          ))}
        </div>
        <ErrorPanel error={error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" busy={busy}>Save</Button>
        </div>
      </form>
    </Modal>
  );
}

export function ExamsList() {
  const { data, error, loading, reload } = useApi<Exam[]>("/exams");
  const [deletingExam, setDeletingExam] = useState<Exam | null>(null);
  const [editingExam, setEditingExam] = useState<Exam | null>(null);

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


  const table = useTableState<Exam>({
    data,
    searchFilter: (e, q) => e.name.toLowerCase().includes(q),
    filters: {
      class: (e, val) => (e.class_name || "") === val,
      subject: (e, val) => (e.subject_name || "") === val,
    },
    sortFns: {
      recent: (a, b) =>
        new Date(b.created_at || b.exam_date || 0).getTime() -
        new Date(a.created_at || a.exam_date || 0).getTime(),
      name: (a, b) => a.name.localeCompare(b.name),
      date: (a, b) =>
        new Date(b.exam_date || b.created_at || 0).getTime() -
        new Date(a.exam_date || a.created_at || 0).getTime(),
      marks: (a, b) => (a.total_marks ?? 0) - (b.total_marks ?? 0),
    },
    defaultSort: "recent",
    defaultOrder: "asc",
    initialPageSize: 10,
  });

  const sortOptions = [
    { value: "recent", label: "Most Recent First" },
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
  ];

  return (
    <div className="w-full">
      <div className="glass-canvas p-5 sm:p-7 lg:p-8 space-y-6 stagger">
        
        {/* Header & Create Exam Button */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="aurora-text text-2xl sm:text-[2rem] font-bold tracking-tight">
              Exams Management
            </h1>
            <p className="mt-1.5 text-sm sm:text-base font-medium text-blue-800/80">
              Create exams and track their progress.
            </p>
          </div>
          <div>
            <Link
              to="/exams/new"
              className="inline-flex items-center gap-2 rounded-xl aurora-fill hover:-translate-y-0.5 hover:shadow-lg active:translate-y-0 active:scale-[0.98] px-6 py-3 text-sm font-semibold text-white shadow-md shadow-indigo-500/25 transition-all cursor-pointer"
            >
              <span>Create New Exam</span>
            </Link>
          </div>
        </div>

        <ErrorPanel error={error} />

        {loading ? (
          <Loading />
        ) : !data?.length ? (
          <Empty
            title="No exams created yet"
            hint="Create an exam to get started."
            action={
              <LinkButton to="/exams/new" variant="primary">
                Create Exam
              </LinkButton>
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
              <div className="overflow-hidden rounded-2xl border border-white bg-white/90 shadow-[0_10px_30px_-20px_rgba(30,64,175,0.35)]">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="border-b border-blue-100/70 bg-blue-50/40 text-xs font-extrabold uppercase tracking-wider text-blue-800">
                      <tr>
                        <th className="px-6 py-4">Exam Details</th>
                        <th className="px-6 py-4">Class</th>
                        <th className="px-6 py-4">Subject</th>
                        <th className="px-6 py-4">Total Marks</th>
                        <th className="px-6 py-4">Status</th>
                        <th className="px-6 py-4 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="stagger divide-y divide-blue-50">
                      {table.paginatedData.map((e) => (
                        <tr key={e.id} className="transition-colors duration-150 hover:bg-blue-50/50">
                          <td className="px-6 py-4">
                            <Link
                              className="block text-base font-bold text-emerald-700 transition-colors hover:text-emerald-600 hover:underline underline-offset-2"
                              to={`/exams/${e.id}`}
                            >
                              {e.name}
                            </Link>
                            <div className="mt-0.5 text-xs font-medium text-slate-500">
                              {e.academic_year ? `${e.academic_year} · ` : ""}
                              {e.exam_type || "School exam"}
                            </div>
                          </td>
                          <td className="px-6 py-4 font-medium text-slate-700">
                            {e.class_name}
                          </td>
                          <td className="px-6 py-4 font-medium text-slate-700">
                            {e.subject_name}
                          </td>
                          <td className="px-6 py-4 font-semibold text-slate-800 tabular-nums">
                            {e.total_marks ?? "–"}
                          </td>
                          <td className="px-6 py-4">
                            <StatusBadge status={e.status} withDot />
                          </td>
                          <td className="px-6 py-4 text-right whitespace-nowrap">
                            <div className="flex items-center justify-end gap-2">
                              <Link
                                to={`/exams/${e.id}`}
                                className="group inline-flex items-center gap-1 rounded-full border border-blue-100 bg-blue-50 px-4 py-1.5 text-sm font-semibold text-blue-700 shadow-xs transition-all hover:bg-blue-100 hover:shadow"
                              >
                                <span>Open</span>
                                <svg
                                  className="h-3 w-3 group-hover:translate-x-0.5 transition-transform"
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2.5}
                                    d="M9 5l7 7-7 7"
                                  />
                                </svg>
                              </Link>
                              <button
                                type="button"
                                className="rounded-lg p-1.5 text-slate-400 hover:bg-blue-50 hover:text-blue-700 transition-colors cursor-pointer"
                                onClick={() => setEditingExam(e)}
                                title={`Edit report details of ${e.name}`}
                                aria-label={`Edit report details of ${e.name}`}
                              >
                                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                                  />
                                </svg>
                              </button>
                              <button
                                type="button"
                                className="rounded-lg p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600 transition-colors cursor-pointer"
                                onClick={() => setDeletingExam(e)}
                                title={`Delete exam ${e.name}`}
                              >
                                <svg
                                  className="h-4 w-4"
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                                  />
                                </svg>
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <TablePagination
                  currentPage={table.page}
                  totalPages={table.totalPages}
                  pageSize={table.pageSize}
                  totalFilteredCount={table.filteredCount}
                  itemLabel="exams"
                  onPageChange={table.setPage}
                  onPageSizeChange={table.setPageSize}
                />
              </div>
            )}
          </>
        )}
      </div>

      {editingExam && (
        <EditReportDetails
          exam={editingExam}
          onClose={() => setEditingExam(null)}
          onSaved={async () => {
            await reload();
            setEditingExam(null);
          }}
        />
      )}

      {deletingExam && (
        <Confirm
          title={`Delete exam “${deletingExam.name}”?`}
              danger
              confirmLabel="Delete Exam"
              body={
                <div className="space-y-2 text-sm text-ink">
                  <p>
                    Are you sure you want to permanently delete exam{" "}
                    <b>{deletingExam.name}</b>?
                  </p>
                  <p className="text-xs text-mute">
                    All extracted questions, answer keys, uploaded answer
                    sheets, and student evaluation results will be permanently
                    removed. This action cannot be reversed.
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
    </div>
  );
}

/** One form: name, class, section and subject, plus the question paper and answer key side by side. Both files are
 * read in parallel as soon as the exam is created; the school then reviews them and finalizes. */
export function ExamNew() {
  const nav = useNavigate();
  const [grade, setGrade] = useState<"10" | "12">("10");
  const catalog = useApi<Record<string, CatalogSubject[]>>(`/subjects/catalog?grade=${grade}`);
  const subjects = catalog.data?.[grade] ?? [];
  const [name, setName] = useState("");
  const [section, setSection] = useState("");
  const [subjectKey, setSubjectKey] = useState("");
  const [paper, setPaper] = useState<File | null>(null);
  const [key, setKey] = useState<File | null>(null);
  const [source, setSource] = useState<"upload" | "generate">("upload");
  const [genBody, setGenBody] = useState<GenerateBody | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => setSubjectKey(""), [grade]);
  const subjectOptions = subjects.find((s) => s.key === subjectKey)?.options ?? [];
  const [standardOptions, setStandardOptions] = useState<Record<string, string>>({});
  // a new subject starts on each option's first choice (shown, so the school can change it)
  useEffect(() => setStandardOptions(Object.fromEntries(subjectOptions.map((o) => [o.key, o.choices[0]?.value ?? ""]))),
            [subjectKey, subjects.length]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (source === "upload" && (!paper || !key)) return setError(new Error("Add both the question paper and the answer key."));
    if (source === "generate" && !genBody) return setError(new Error("Choose the paper options first."));
    setBusy(true);
    setError(null);
    try {
      const exam = await api<Exam>("/exams/simple", {
        method: "POST",
        json: { name: name.trim(), grade, section: section.trim(), subject_key: subjectKey,
                standard_options: Object.keys(standardOptions).length ? standardOptions : null },
      });
      if (source === "generate") {
        // the paper and key are written from the textbooks, then read and reviewed like uploaded files
        await api(`/exams/${exam.id}/generate-paper`, { method: "POST", json: genBody });
        nav(`/exams/${exam.id}`, { replace: true });
        return;
      }
      const upload = (path: string, file: File) => {
        const form = new FormData();
        form.append("file", file);
        return api(`/exams/${exam.id}/${path}`, { method: "POST", form });
      };
      await upload("question-paper", paper!);  // the paper first: the key is read alongside it, then built on it
      await upload("answer-key", key!);
      nav(`/exams/${exam.id}`, { replace: true });
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };

  return (
    <PageCanvas className="max-w-3xl mx-auto">
      <PageHeader title="Create exam" sub="Upload your question paper and answer key, or let the AI write them from the NCERT textbooks." />
      <form onSubmit={submit}>
        <Card className="space-y-5 p-6">
          <Field label="Exam name" required>
            {(id) => <Input id={id} required maxLength={200} placeholder="Term 1 examination" value={name}
                            onChange={(e) => setName(e.target.value)} />}
          </Field>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Class" required>
              {(id) => (
                <Select id={id} value={grade} onChange={(e) => setGrade(e.target.value as "10" | "12")}>
                  <option value="10">Class 10</option>
                  <option value="12">Class 12</option>
                </Select>
              )}
            </Field>
            <Field label="Section" hint="e.g. A">
              {(id) => <Input id={id} maxLength={20} placeholder="A" value={section}
                              onChange={(e) => setSection(e.target.value.toUpperCase())} />}
            </Field>
          </div>
          <Field label="Subject" required>
            {(id) => (
              <Select id={id} required value={subjectKey} onChange={(e) => setSubjectKey(e.target.value)}
                      disabled={catalog.loading}>
                <option value="">{catalog.loading ? "Loading subjects..." : "Choose a subject"}</option>
                {subjects.map((s) => <option key={s.key} value={s.key}>{s.name}</option>)}
              </Select>
            )}
          </Field>
          {subjectOptions.map((o) => (
            <Field key={o.key} label={o.label} required hint="Which branch students answer">
              {(id) => (
                <Select id={id} value={standardOptions[o.key] ?? ""}
                        onChange={(e) => setStandardOptions({ ...standardOptions, [o.key]: e.target.value })}>
                  {o.choices.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                </Select>
              )}
            </Field>
          ))}
          <div className="space-y-2">
            <p className="text-[13px] font-semibold text-ink">Question paper and answer key</p>
            <div className="inline-flex rounded-full border border-slate-200 bg-slate-50 p-1" role="radiogroup">
              {([["upload", "Upload my own"], ["generate", "Generate with AI"]] as const).map(([v, text]) => (
                <button key={v} type="button" role="radio" aria-checked={source === v} disabled={busy}
                        onClick={() => setSource(v)}
                        className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${source === v ? "bg-white text-blue-700 shadow-xs" : "text-slate-600 hover:text-ink"}`}>
                  {text}
                </button>
              ))}
            </div>
          </div>
          {source === "generate" ? (
            subjectKey ? (
              <div className="rounded-xl border border-blue-100 bg-blue-50/30 p-4">
                <p className="mb-4 text-xs text-mute">
                  Written from the NCERT textbook and CBSE sample papers. The questions and answer key go straight into the exam, ready for answer sheets.
                </p>
                <PaperGenerator key={subjectKey} grade={grade} subjectKey={subjectKey} onChange={setGenBody} disabled={busy} />
              </div>
            ) : (
              <p className="text-sm text-mute">Choose the subject first.</p>
            )
          ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            <UploadZone compact title="Question paper" accept=".pdf,.png,.jpg,.jpeg,.docx" chosen={paper?.name}
                        hint="PDF, image or Word" disabled={busy} onFile={async (f) => setPaper(f)} />
            <UploadZone compact title="Answer key" accept=".pdf,.png,.jpg,.jpeg,.docx" chosen={key?.name}
                        hint="PDF, image or Word" disabled={busy} onFile={async (f) => setKey(f)} />
          </div>
          )}
          <ErrorPanel error={error} />
        </Card>
        <div className="mt-5 flex justify-end gap-2">
          <LinkButton to="/exams" variant="secondary">Cancel</LinkButton>
          <Button type="submit" variant="primary" busy={busy} disabled={!name.trim() || !subjectKey || (source === "upload" ? !paper || !key : !genBody)}>
            {source === "generate" ? "Create exam and generate paper" : "Create exam"}
          </Button>
        </div>
      </form>
    </PageCanvas>
  );
}
