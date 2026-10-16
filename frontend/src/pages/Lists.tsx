import { useMemo, useState, type FormEvent } from "react";
import { api, downloadFile } from "../api/client";
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
  Modal,
  PageHeader,
  Select,
  StatusBadge,
} from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useTableState } from "../hooks/useTableState";
import type { ClassRow, Student, Subject } from "../types";

function SimpleForm({
  title,
  onClose,
  onSubmit,
  children,
}: {
  title: string;
  onClose: () => void;
  onSubmit: () => Promise<void>;
  children: React.ReactNode;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const go = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await onSubmit();
      onClose();
    } catch (x) {
      setErr(x);
      setBusy(false);
    }
  };
  return (
    <Modal title={title} onClose={onClose}>
      <form onSubmit={go} className="space-y-4">
        {children}
        <ErrorPanel error={err} />
        <div className="flex justify-end gap-2 border-t border-line/60 pt-3">
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" busy={busy}>
            Save
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function Classes() {
  const { data, error, loading, reload } = useApi<ClassRow[]>("/classes");
  const [open, setOpen] = useState(false);
  const [editingClass, setEditingClass] = useState<ClassRow | null>(null);
  const [deletingClass, setDeletingClass] = useState<ClassRow | null>(null);
  const [downloading, setDownloading] = useState(false);

  const handleDownloadMarksheet = async () => {
    try {
      setDownloading(true);
      await downloadFile("/reports/marksheet", "EvalAI_Student_Marksheet.xlsx");
    } catch (err: any) {
      alert(err.message || "Failed to download marksheet.");
    } finally {
      setDownloading(false);
    }
  };

  const table = useTableState<ClassRow>({
    data,
    searchFilter: (c, q) => c.name.toLowerCase().includes(q),
    sortFns: {
      name: (a, b) => a.name.localeCompare(b.name),
      student_count: (a, b) => (a.student_count ?? 0) - (b.student_count ?? 0),
    },
    defaultSort: "name",
    defaultOrder: "asc",
    initialPageSize: 10,
  });

  const sortOptions = [
    { value: "name", label: "Class name" },
    { value: "student_count", label: "Student count" },
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Classes Roster"
        sub="Manage class cohorts, student enrollment, and export complete marksheets."
        actions={
          <div className="flex items-center gap-2">
            <Button variant="soft" busy={downloading} onClick={handleDownloadMarksheet}>
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span>Export Marksheet (.xlsx)</span>
            </Button>
            <Button variant="primary" onClick={() => setOpen(true)} className="shadow-xs">
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              <span>Add Class</span>
            </Button>
          </div>
        }
      />
      <ErrorPanel error={error} />
      {loading ? (
        <Loading />
      ) : !data?.length ? (
        <Empty
          title="No classes added yet"
          hint="Create a class (such as 10-A or Grade 12-Science) before setting up exams."
          action={<Button variant="primary" onClick={() => setOpen(true)}>Add Class</Button>}
        />
      ) : (
        <>
          <TableToolbar
            searchPlaceholder="Search by class name..."
            searchValue={table.search}
            onSearchChange={table.setSearch}
            sortOptions={sortOptions}
            sortValue={table.sortBy}
            onSortChange={table.setSortBy}
            sortOrder={table.sortOrder}
            onSortOrderToggle={table.toggleSortOrder}
            isFiltered={table.isFiltered}
            onClearFilters={table.clearFilters}
            totalCount={table.totalCount}
            filteredCount={table.filteredCount}
            itemLabel="classes"
          />

          {table.filteredCount === 0 ? (
            <FilteredEmptyState
              title="No matching classes found"
              message="No classes match your current search query."
              onClearFilters={table.clearFilters}
            />
          ) : (
            <Card className="overflow-x-auto shadow-soft">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-line bg-surface text-xs font-semibold uppercase tracking-wider text-mute">
                  <tr>
                    <th className="px-4 py-3">Class Cohort</th>
                    <th className="px-4 py-3">Enrolled Students</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line text-sm">
                  {table.paginatedData.map((c) => (
                    <tr key={c.id} className="hover:bg-sunken/40">
                      <td className="px-4 py-3 font-semibold text-ink">{c.name}</td>
                      <td className="px-4 py-3 font-mono text-mute">{c.student_count ?? 0} students</td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <div className="flex items-center justify-end gap-1.5">
                          <Button
                            small
                            variant="soft"
                            onClick={() => setEditingClass(c)}
                          >
                            Edit
                          </Button>
                          <Button
                            small
                            variant="ghost"
                            className="text-mark hover:bg-mark-soft hover:text-mark"
                            onClick={() => setDeletingClass(c)}
                          >
                            Delete
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
                itemLabel="classes"
                onPageChange={table.setPage}
                onPageSizeChange={table.setPageSize}
              />
            </Card>
          )}
        </>
      )}
      {open && <ClassForm done={reload} close={() => setOpen(false)} />}
      {editingClass && (
        <EditClassForm
          cls={editingClass}
          done={reload}
          close={() => setEditingClass(null)}
        />
      )}
      {deletingClass && (
        <Confirm
          title={`Delete class "${deletingClass.name}"?`}
          danger
          confirmLabel="Delete Class"
          body={
            <div className="space-y-2 text-sm text-ink">
              <p>
                Are you sure you want to delete class <b>{deletingClass.name}</b>?
              </p>
              <p className="text-xs text-mute">
                This will also remove any exams and enrolled students associated with this class.
              </p>
            </div>
          }
          onConfirm={async () => {
            await api(`/classes/${deletingClass.id}`, { method: "DELETE" });
            await reload();
            setDeletingClass(null);
          }}
          onClose={() => setDeletingClass(null)}
        />
      )}
    </div>
  );
}

function ClassForm({ done, close }: { done: () => void; close: () => void }) {
  const [name, setName] = useState("");
  return (
    <SimpleForm
      title="Add New Class"
      onClose={close}
      onSubmit={async () => {
        await api("/classes", { method: "POST", json: { name } });
        done();
      }}
    >
      <Field label="Class Name" hint="e.g. 10-A, 11-B, or Grade 12-Science">
        {(id) => (
          <Input
            id={id}
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="10-A"
          />
        )}
      </Field>
    </SimpleForm>
  );
}

function EditClassForm({ cls, done, close }: { cls: ClassRow; done: () => void; close: () => void }) {
  const [name, setName] = useState(cls.name);
  return (
    <SimpleForm
      title={`Edit Class (${cls.name})`}
      onClose={close}
      onSubmit={async () => {
        await api(`/classes/${cls.id}`, { method: "PATCH", json: { name } });
        done();
      }}
    >
      <Field label="Class Name">
        {(id) => (
          <Input
            id={id}
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        )}
      </Field>
    </SimpleForm>
  );
}

export function Subjects() {
  const { data, error, loading, reload } = useApi<Subject[]>("/subjects");
  const [open, setOpen] = useState(false);
  const [editingSubject, setEditingSubject] = useState<Subject | null>(null);
  const [deletingSubject, setDeletingSubject] = useState<Subject | null>(null);

  const table = useTableState<Subject>({
    data,
    searchFilter: (s, q) =>
      s.name.toLowerCase().includes(q) || (s.code || "").toLowerCase().includes(q),
    sortFns: {
      name: (a, b) => a.name.localeCompare(b.name),
      code: (a, b) => (a.code || "").localeCompare(b.code || ""),
    },
    defaultSort: "name",
    defaultOrder: "asc",
    initialPageSize: 10,
  });

  const sortOptions = [
    { value: "name", label: "Subject name" },
    { value: "code", label: "Subject code" },
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Subjects Directory"
        sub="Manage curriculum subjects and subject codes for question papers and evaluation."
        actions={
          <Button variant="primary" onClick={() => setOpen(true)} className="shadow-xs">
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            <span>Add Subject</span>
          </Button>
        }
      />
      <ErrorPanel error={error} />
      {loading ? (
        <Loading />
      ) : !data?.length ? (
        <Empty
          title="No subjects added yet"
          hint="Add the subjects you conduct examinations for (e.g. Physics, Chemistry, Mathematics)."
          action={<Button variant="primary" onClick={() => setOpen(true)}>Add Subject</Button>}
        />
      ) : (
        <>
          <TableToolbar
            searchPlaceholder="Search by subject name or code..."
            searchValue={table.search}
            onSearchChange={table.setSearch}
            sortOptions={sortOptions}
            sortValue={table.sortBy}
            onSortChange={table.setSortBy}
            sortOrder={table.sortOrder}
            onSortOrderToggle={table.toggleSortOrder}
            isFiltered={table.isFiltered}
            onClearFilters={table.clearFilters}
            totalCount={table.totalCount}
            filteredCount={table.filteredCount}
            itemLabel="subjects"
          />

          {table.filteredCount === 0 ? (
            <FilteredEmptyState
              title="No matching subjects found"
              message="No subjects match your current search query."
              onClearFilters={table.clearFilters}
            />
          ) : (
            <Card className="overflow-x-auto shadow-soft">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-line bg-surface text-xs font-semibold uppercase tracking-wider text-mute">
                  <tr>
                    <th className="px-4 py-3">Subject Name</th>
                    <th className="px-4 py-3">Subject Code</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line text-sm">
                  {table.paginatedData.map((s) => (
                    <tr key={s.id} className="hover:bg-sunken/40">
                      <td className="px-4 py-3 font-semibold text-ink">{s.name}</td>
                      <td className="px-4 py-3 font-mono text-mute">{s.code ?? "–"}</td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <div className="flex items-center justify-end gap-1.5">
                          <Button
                            small
                            variant="soft"
                            onClick={() => setEditingSubject(s)}
                          >
                            Edit
                          </Button>
                          <Button
                            small
                            variant="ghost"
                            className="text-mark hover:bg-mark-soft hover:text-mark"
                            onClick={() => setDeletingSubject(s)}
                          >
                            Delete
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
                itemLabel="subjects"
                onPageChange={table.setPage}
                onPageSizeChange={table.setPageSize}
              />
            </Card>
          )}
        </>
      )}
      {open && <SubjectForm done={reload} close={() => setOpen(false)} />}
      {editingSubject && (
        <EditSubjectForm
          subject={editingSubject}
          done={reload}
          close={() => setEditingSubject(null)}
        />
      )}
      {deletingSubject && (
        <Confirm
          title={`Delete subject "${deletingSubject.name}"?`}
          danger
          confirmLabel="Delete Subject"
          body={
            <div className="space-y-2 text-sm text-ink">
              <p>
                Are you sure you want to delete subject <b>{deletingSubject.name}</b>?
              </p>
              <p className="text-xs text-mute">
                This will also remove any examinations associated with this subject.
              </p>
            </div>
          }
          onConfirm={async () => {
            await api(`/subjects/${deletingSubject.id}`, { method: "DELETE" });
            await reload();
            setDeletingSubject(null);
          }}
          onClose={() => setDeletingSubject(null)}
        />
      )}
    </div>
  );
}

function SubjectForm({ done, close }: { done: () => void; close: () => void }) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  return (
    <SimpleForm
      title="Add New Subject"
      onClose={close}
      onSubmit={async () => {
        await api("/subjects", { method: "POST", json: { name, code: code || null } });
        done();
      }}
    >
      <Field label="Subject Name">
        {(id) => <Input id={id} required placeholder="e.g. Physics" value={name} onChange={(e) => setName(e.target.value)} />}
      </Field>
      <Field label="Subject Code (optional)">
        {(id) => <Input id={id} placeholder="e.g. PHY101" value={code} onChange={(e) => setCode(e.target.value)} />}
      </Field>
    </SimpleForm>
  );
}

function EditSubjectForm({ subject, done, close }: { subject: Subject; done: () => void; close: () => void }) {
  const [name, setName] = useState(subject.name);
  const [code, setCode] = useState(subject.code || "");
  return (
    <SimpleForm
      title={`Edit Subject (${subject.name})`}
      onClose={close}
      onSubmit={async () => {
        await api(`/subjects/${subject.id}`, { method: "PATCH", json: { name, code: code || null } });
        done();
      }}
    >
      <Field label="Subject Name">
        {(id) => <Input id={id} required value={name} onChange={(e) => setName(e.target.value)} />}
      </Field>
      <Field label="Code (optional)">
        {(id) => <Input id={id} value={code} onChange={(e) => setCode(e.target.value)} />}
      </Field>
    </SimpleForm>
  );
}

export function Students() {
  const { data, error, loading, reload } = useApi<Student[]>("/students");
  const [open, setOpen] = useState(false);
  const [editingStudent, setEditingStudent] = useState<Student | null>(null);
  const [deletingStudent, setDeletingStudent] = useState<Student | null>(null);

  const classOptions = useMemo(() => {
    if (!data) return [];
    const map = new Map<string, string>();
    for (const s of data) {
      if (s.class_name) map.set(s.class_name, s.class_name);
    }
    return Array.from(map.entries())
      .map(([value, label]) => ({ value, label }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [data]);

  const table = useTableState<Student>({
    data,
    searchFilter: (s, q) =>
      s.name.toLowerCase().includes(q) || s.roll_number.toLowerCase().includes(q),
    filters: {
      class: (s, val) => (s.class_name || s.class_id) === val,
    },
    sortFns: {
      name: (a, b) => a.name.localeCompare(b.name),
      roll: (a, b) =>
        a.roll_number.localeCompare(b.roll_number, undefined, { numeric: true, sensitivity: "base" }),
      class: (a, b) => (a.class_name || "").localeCompare(b.class_name || ""),
    },
    defaultSort: "roll",
    defaultOrder: "asc",
    initialPageSize: 10,
  });

  const sortOptions = [
    { value: "roll", label: "Roll number" },
    { value: "name", label: "Student name" },
    { value: "class", label: "Class" },
  ];

  const filterConfigs = [
    {
      key: "class",
      label: "All Classes",
      options: classOptions,
      value: table.activeFilters.class || "",
      onChange: (val: string) => table.setFilter("class", val),
    },
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Student Roster"
        sub="Enroll and manage student records and roll numbers across all classes."
        actions={
          <Button variant="primary" onClick={() => setOpen(true)} className="shadow-xs">
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            <span>Add Student</span>
          </Button>
        }
      />
      <ErrorPanel error={error} />
      {loading ? (
        <Loading />
      ) : !data?.length ? (
        <Empty
          title="No students enrolled yet"
          hint="Add students manually, or upload their answer sheets during examinations to enroll them automatically."
          action={<Button variant="primary" onClick={() => setOpen(true)}>Add Student</Button>}
        />
      ) : (
        <>
          <TableToolbar
            searchPlaceholder="Search by student name or roll number..."
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
            itemLabel="students"
          />

          {table.filteredCount === 0 ? (
            <FilteredEmptyState
              title="No matching students found"
              message="No students match your current search and filter combination."
              onClearFilters={table.clearFilters}
            />
          ) : (
            <Card className="overflow-x-auto shadow-soft">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-line bg-surface text-xs font-semibold uppercase tracking-wider text-mute">
                  <tr>
                    <th className="px-4 py-3">Roll No.</th>
                    <th className="px-4 py-3">Student Name</th>
                    <th className="px-4 py-3">Class</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line text-sm">
                  {table.paginatedData.map((s) => (
                    <tr key={s.id} className="hover:bg-sunken/40">
                      <td className="px-4 py-3 font-mono font-medium text-ink">{s.roll_number}</td>
                      <td className="px-4 py-3 font-semibold text-ink">{s.name}</td>
                      <td className="px-4 py-3 font-medium text-mute">{s.class_name ?? "–"}</td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <div className="flex items-center justify-end gap-1.5">
                          <Button
                            small
                            variant="soft"
                            onClick={() => setEditingStudent(s)}
                          >
                            Edit
                          </Button>
                          <Button
                            small
                            variant="ghost"
                            className="text-mark hover:bg-mark-soft hover:text-mark"
                            onClick={() => setDeletingStudent(s)}
                          >
                            Delete
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
                itemLabel="students"
                onPageChange={table.setPage}
                onPageSizeChange={table.setPageSize}
              />
            </Card>
          )}
        </>
      )}
      {open && <StudentForm done={reload} close={() => setOpen(false)} />}
      {editingStudent && (
        <EditStudentForm
          student={editingStudent}
          done={reload}
          close={() => setEditingStudent(null)}
        />
      )}
      {deletingStudent && (
        <Confirm
          title={`Delete student "${deletingStudent.name}"?`}
          danger
          confirmLabel="Delete Student"
          body={
            <div className="space-y-2 text-sm text-ink">
              <p>
                Are you sure you want to delete student <b>{deletingStudent.name}</b> (Roll: {deletingStudent.roll_number})?
              </p>
              <p className="text-xs text-mute">
                This will also remove any evaluations associated with this student.
              </p>
            </div>
          }
          onConfirm={async () => {
            await api(`/students/${deletingStudent.id}`, { method: "DELETE" });
            await reload();
            setDeletingStudent(null);
          }}
          onClose={() => setDeletingStudent(null)}
        />
      )}
    </div>
  );
}

function StudentForm({ done, close }: { done: () => void; close: () => void }) {
  const classes = useApi<ClassRow[]>("/classes");
  const [name, setName] = useState("");
  const [roll, setRoll] = useState("");
  const [cls, setCls] = useState("");
  return (
    <SimpleForm
      title="Add New Student"
      onClose={close}
      onSubmit={async () => {
        await api("/students", {
          method: "POST",
          json: { name, roll_number: roll, class_id: cls },
        });
        done();
      }}
    >
      <Field label="Student Full Name">
        {(id) => <Input id={id} required placeholder="e.g. Priya Patel" value={name} onChange={(e) => setName(e.target.value)} />}
      </Field>
      <Field label="Roll Number">
        {(id) => <Input id={id} required placeholder="e.g. 101" value={roll} onChange={(e) => setRoll(e.target.value)} />}
      </Field>
      <Field label="Class">
        {(id) => (
          <Select id={id} required value={cls} onChange={(e) => setCls(e.target.value)}>
            <option value="">Choose a class...</option>
            {classes.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        )}
      </Field>
    </SimpleForm>
  );
}

function EditStudentForm({ student, done, close }: { student: Student; done: () => void; close: () => void }) {
  const classes = useApi<ClassRow[]>("/classes");
  const [name, setName] = useState(student.name);
  const [roll, setRoll] = useState(student.roll_number);
  const [cls, setCls] = useState(student.class_id);
  return (
    <SimpleForm
      title={`Edit Student (${student.name})`}
      onClose={close}
      onSubmit={async () => {
        await api(`/students/${student.id}`, {
          method: "PATCH",
          json: { name, roll_number: roll, class_id: cls },
        });
        done();
      }}
    >
      <Field label="Student Full Name">
        {(id) => <Input id={id} required value={name} onChange={(e) => setName(e.target.value)} />}
      </Field>
      <Field label="Roll Number">
        {(id) => <Input id={id} required value={roll} onChange={(e) => setRoll(e.target.value)} />}
      </Field>
      <Field label="Class">
        {(id) => (
          <Select id={id} required value={cls} onChange={(e) => setCls(e.target.value)}>
            {classes.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        )}
      </Field>
    </SimpleForm>
  );
}

export function SettingsPage() {
  const { data, loading, reload } = useApi<{
    available: boolean;
    model: string;
    url: string;
    message: string;
    detail?: string;
  }>("/system/ai-status");

  return (
    <div className="space-y-4 max-w-2xl">
      <PageHeader
        title="System Settings"
        sub="Monitor local Ollama AI model connectivity and application status."
      />
      <Card className="p-6 shadow-soft space-y-4">
        <div className="flex items-center justify-between border-b border-line pb-3">
          <h2 className="text-base font-semibold text-ink">Local AI Service Health</h2>
          {data && <StatusBadge status={data.available ? "READY" : "AI_ERROR"} />}
        </div>
        {loading || !data ? (
          <Loading />
        ) : (
          <div className="space-y-3 text-sm">
            <p className="flex items-center gap-2 font-medium text-ink">
              <span>{data.message}</span>
            </p>
            <div className="rounded-lg bg-sunken p-3 font-mono text-xs text-mute space-y-1 border border-line/60">
              <p>Model: <span className="text-ink font-semibold">{data.model}</span></p>
              <p>Endpoint URL: <span className="text-ink">{data.url}</span></p>
            </div>
            {data.detail && (
              <div className="rounded-lg bg-warn-soft/50 p-3 text-xs text-warn border border-warn/30">
                {data.detail}
              </div>
            )}
            <div className="pt-2">
              <Button onClick={reload} variant="soft">
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                <span>Check Service Status Again</span>
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
