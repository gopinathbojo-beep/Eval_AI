import { useToast } from "../components/Toast";
import { useMemo, useState, type FormEvent } from "react";
import { api, downloadFile } from "../api/client";
import {
  FilteredEmptyState,
  TablePagination,
  TableToolbar,
} from "../components/TableToolbar";
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
} from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useTableState } from "../hooks/useTableState";
import type { ClassRow, ImportSummary, Student, Subject } from "../types";
import {
  ReportCardDialog,
  ReportTemplatesCard,
  SchoolDetailsCard,
} from "../components/SchoolSettings";
import { useAuth } from "../context/Auth";
import { Navigate } from "react-router-dom";

function AssignedDirectory({
  kind,
}: {
  kind: "classes" | "students" | "subjects";
}) {
  const { data, error, loading } = useApi<
    Array<{
      id: string;
      name: string;
      roll_number?: string;
      class_name?: string;
    }>
  >(`/${kind}`);
  return (
    <div className="space-y-5">
      <PageHeader
        title={`Assigned ${kind}`}
        sub="Your school management maintains these shared records."
      />
      <ErrorPanel error={error} />
      {loading ? (
        <Loading />
      ) : (
        <Card className="divide-y divide-line">
          {data?.map((r) => (
            <div key={r.id} className="p-4">
              <p className="font-semibold">{r.name}</p>
              <p className="text-sm text-mute">
                {[r.roll_number, r.class_name].filter(Boolean).join(" · ")}
              </p>
            </div>
          ))}
          {!data?.length && (
            <p className="p-6 text-mute">
              No records assigned yet. Contact school management.
            </p>
          )}
        </Card>
      )}
    </div>
  );
}

export function Classes() {
  const { teacher } = useAuth();
  return teacher?.role === "TEACHER" ? (
    <AssignedDirectory kind="classes" />
  ) : teacher?.role === "PARENT" ? (
    <Navigate to="/family" replace />
  ) : (
    <EditableClasses />
  );
}
export function Subjects() {
  const { teacher } = useAuth();
  return teacher?.role === "TEACHER" ? (
    <AssignedDirectory kind="subjects" />
  ) : (
    <EditableSubjects />
  );
}
export function Students() {
  const { teacher } = useAuth();
  return teacher?.role === "TEACHER" ? (
    <AssignedDirectory kind="students" />
  ) : teacher?.role === "PARENT" ? (
    <Navigate to="/family" replace />
  ) : (
    <EditableStudents />
  );
}

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

function EditableClasses() {
  const { data, error, loading, reload } = useApi<ClassRow[]>("/classes");
  const [open, setOpen] = useState(false);
  const [editingClass, setEditingClass] = useState<ClassRow | null>(null);
  const [deletingClass, setDeletingClass] = useState<ClassRow | null>(null);
  const [cardsFor, setCardsFor] = useState<ClassRow | null>(null);
  const toast = useToast();
  const [downloading, setDownloading] = useState(false);

  const handleDownloadMarksheet = async () => {
    try {
      setDownloading(true);
      await downloadFile("/reports/marksheet", "EvalAI_Student_Marksheet.xlsx");
      toast("Marksheet downloaded.");
    } catch (err: any) {
      toast(err.message || "Failed to download marksheet.", "mark");
    } finally {
      setDownloading(false);
    }
  };

  const table = useTableState<ClassRow>({
    data,
    searchFilter: (c, q) => c.name.toLowerCase().includes(q),
    sortFns: {
      name: (a, b) =>
        a.name.localeCompare(b.name, undefined, {
          numeric: true,
          sensitivity: "base",
        }),
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
        sub="Your classes and marksheets."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="soft"
              busy={downloading}
              onClick={handleDownloadMarksheet}
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
                  strokeWidth={1.75}
                  d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
              </svg>
              <span>Export Marksheet (.xlsx)</span>
            </Button>
            <Button
              variant="primary"
              onClick={() => setOpen(true)}
              className="shadow-xs"
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
                  d="M12 4v16m8-8H4"
                />
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
          hint="Add a class (Std 10, Sec A) before creating exams."
          action={
            <Button variant="primary" onClick={() => setOpen(true)}>
              Add Class
            </Button>
          }
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
                    <th className="px-4 py-3">Std</th>
                    <th className="px-4 py-3">Sec</th>
                    <th className="px-4 py-3">Enrolled Students</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line text-sm">
                  {table.paginatedData.map((c) => (
                    <tr key={c.id} className="hover:bg-hover">
                      <td className="px-4 py-3 font-semibold text-ink">
                        {c.std}
                      </td>
                      <td className="px-4 py-3 font-semibold text-ink">
                        {c.section || "–"}
                      </td>
                      <td className="px-4 py-3 font-mono text-mute">
                        {c.student_count ?? 0} students
                      </td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <div className="flex items-center justify-end gap-1.5">
                          <Button
                            small
                            variant="soft"
                            onClick={() => setCardsFor(c)}
                          >
                            Report cards
                          </Button>
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
      {cardsFor && (
        <ReportCardDialog
          classId={cardsFor.id}
          title={`Report cards · ${cardsFor.name}`}
          onClose={() => setCardsFor(null)}
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
                Are you sure you want to delete class{" "}
                <b>{deletingClass.name}</b>?
              </p>
              <p className="text-xs text-mute">
                This will also remove any exams and enrolled students associated
                with this class.
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

/** Std and Sec make up the class name the rest of the app shows: Std 10 + Sec A -> 10-A. */
function StdSecFields({
  std,
  sec,
  setStd,
  setSec,
}: {
  std: string;
  sec: string;
  setStd: (v: string) => void;
  setSec: (v: string) => void;
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Field label="Std" hint="e.g. 10, 11 or Grade 12">
        {(id) => (
          <Select
            id={id}
            required
            value={std}
            onChange={(e) => setStd(e.target.value)}
          >
            <option value="">Choose class</option>
            <option value="10">CBSE Class 10</option>
            <option value="12">CBSE Class 12</option>
          </Select>
        )}
      </Field>
      <Field label="Sec (optional)" hint="e.g. A, B or Science">
        {(id) => (
          <Input
            id={id}
            value={sec}
            onChange={(e) => setSec(e.target.value)}
            placeholder="A"
          />
        )}
      </Field>
    </div>
  );
}

function ClassForm({ done, close }: { done: () => void; close: () => void }) {
  const [std, setStd] = useState("");
  const [sec, setSec] = useState("");
  return (
    <SimpleForm
      title="Add New Class"
      onClose={close}
      onSubmit={async () => {
        await api("/classes", { method: "POST", json: { std, section: sec } });
        done();
      }}
    >
      <StdSecFields std={std} sec={sec} setStd={setStd} setSec={setSec} />
    </SimpleForm>
  );
}

function EditClassForm({
  cls,
  done,
  close,
}: {
  cls: ClassRow;
  done: () => void;
  close: () => void;
}) {
  const [std, setStd] = useState(cls.std);
  const [sec, setSec] = useState(cls.section ?? "");
  return (
    <SimpleForm
      title={`Edit Class (${cls.name})`}
      onClose={close}
      onSubmit={async () => {
        await api(`/classes/${cls.id}`, {
          method: "PATCH",
          json: { std, section: sec },
        });
        done();
      }}
    >
      <StdSecFields std={std} sec={sec} setStd={setStd} setSec={setSec} />
    </SimpleForm>
  );
}

function EditableSubjects() {
  const { data, error, loading, reload } = useApi<Subject[]>("/subjects");
  const [open, setOpen] = useState(false);
  const [editingSubject, setEditingSubject] = useState<Subject | null>(null);
  const [deletingSubject, setDeletingSubject] = useState<Subject | null>(null);

  const table = useTableState<Subject>({
    data,
    searchFilter: (s, q) =>
      s.name.toLowerCase().includes(q) ||
      (s.code || "").toLowerCase().includes(q),
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
        sub="Subjects you set exams for."
        actions={
          <Button
            variant="primary"
            onClick={() => setOpen(true)}
            className="shadow-xs"
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
                d="M12 4v16m8-8H4"
              />
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
          hint="Add a subject, e.g. Physics."
          action={
            <Button variant="primary" onClick={() => setOpen(true)}>
              Add Subject
            </Button>
          }
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
                    <tr key={s.id} className="hover:bg-hover">
                      <td className="px-4 py-3 font-semibold text-ink">
                        {s.name}
                      </td>
                      <td className="px-4 py-3 font-mono text-mute">
                        {s.code ?? "–"}
                      </td>
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
                Are you sure you want to delete subject{" "}
                <b>{deletingSubject.name}</b>?
              </p>
              <p className="text-xs text-mute">
                This will also remove any examinations associated with this
                subject.
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
        await api("/subjects", {
          method: "POST",
          json: { name, code: code || null },
        });
        done();
      }}
    >
      <Field label="Subject Name">
        {(id) => (
          <Input
            id={id}
            required
            placeholder="e.g. Physics"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        )}
      </Field>
      <Field label="Subject Code (optional)">
        {(id) => (
          <Input
            id={id}
            placeholder="e.g. PHY101"
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        )}
      </Field>
    </SimpleForm>
  );
}

function EditSubjectForm({
  subject,
  done,
  close,
}: {
  subject: Subject;
  done: () => void;
  close: () => void;
}) {
  const [name, setName] = useState(subject.name);
  const [code, setCode] = useState(subject.code || "");
  return (
    <SimpleForm
      title={`Edit Subject (${subject.name})`}
      onClose={close}
      onSubmit={async () => {
        await api(`/subjects/${subject.id}`, {
          method: "PATCH",
          json: { name, code: code || null },
        });
        done();
      }}
    >
      <Field label="Subject Name">
        {(id) => (
          <Input
            id={id}
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        )}
      </Field>
      <Field label="Code (optional)">
        {(id) => (
          <Input
            id={id}
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        )}
      </Field>
    </SimpleForm>
  );
}

function EditableStudents() {
  const { data, error, loading, reload } = useApi<Student[]>("/students");
  const [open, setOpen] = useState(false);
  const [editingStudent, setEditingStudent] = useState<Student | null>(null);
  const [deletingStudent, setDeletingStudent] = useState<Student | null>(null);
  const [cardFor, setCardFor] = useState<Student | null>(null);
  const [importing, setImporting] = useState(false);
  const [exporting, setExporting] = useState<"xlsx" | "pdf" | null>(null);
  const [exportErr, setExportErr] = useState<unknown>(null);

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
      s.name.toLowerCase().includes(q) ||
      s.roll_number.toLowerCase().includes(q) ||
      (s.registration_number || "").toLowerCase().includes(q),

    filters: {
      class: (s, val) => (s.class_name || s.class_id) === val,
    },

    sortFns: {
      name: (a, b) => a.name.localeCompare(b.name),

      roll: (a, b) =>
        a.roll_number.localeCompare(b.roll_number, undefined, {
          numeric: true,
          sensitivity: "base",
        }),

      class: (a, b) =>
        (a.class_name || "").localeCompare(b.class_name || "", undefined, {
          numeric: true,
          sensitivity: "base",
        }),
    },

    defaultSort: "class",
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

  const exportAs = async (format: "xlsx" | "pdf") => {
    // export follows the class filter when one is chosen
    const classId = data?.find(
      (s) => s.class_name === table.activeFilters.class,
    )?.class_id;
    setExporting(format);
    setExportErr(null);
    try {
      await downloadFile(
        `/students/export?format=${format}${classId ? `&class_id=${classId}` : ""}`,
        `students.${format}`,
      );
    } catch (e) {
      setExportErr(e);
    } finally {
      setExporting(null);
    }
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title="Students"
        sub="Answer sheets are matched to students by registration or roll number."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="soft"
              onClick={() => setImporting(true)}
              title="Import students from an Excel sheet"
            >
              <span>Import Excel</span>
            </Button>
            <Button
              variant="soft"
              busy={exporting === "xlsx"}
              disabled={!data?.length}
              onClick={() => exportAs("xlsx")}
            >
              <span>Export Excel</span>
            </Button>
            <Button
              variant="soft"
              busy={exporting === "pdf"}
              disabled={!data?.length}
              onClick={() => exportAs("pdf")}
            >
              <span>Export PDF</span>
            </Button>
            <Button
              variant="primary"
              onClick={() => setOpen(true)}
              className="shadow-xs"
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
                  d="M12 4v16m8-8H4"
                />
              </svg>
              <span>Add Student</span>
            </Button>
          </div>
        }
      />
      <ErrorPanel error={error || exportErr} />
      {loading ? (
        <Loading />
      ) : !data?.length ? (
        <Empty
          title="No students enrolled yet"
          hint="Add students one by one or import an Excel sheet."
          action={
            <div className="flex gap-2">
              <Button variant="soft" onClick={() => setImporting(true)}>
                Import Excel
              </Button>
              <Button variant="primary" onClick={() => setOpen(true)}>
                Add Student
              </Button>
            </div>
          }
        />
      ) : (
        <>
          <TableToolbar
            searchPlaceholder="Search by name, roll number or registration number..."
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
                    <th className="px-4 py-3">Reg. No.</th>
                    <th className="px-4 py-3">Std</th>
                    <th className="px-4 py-3">Sec</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line text-sm">
                  {table.paginatedData.map((s) => (
                    <tr key={s.id} className="hover:bg-hover">
                      <td className="px-4 py-3 font-mono font-medium text-ink">
                        {s.roll_number}
                      </td>
                      <td className="px-4 py-3 font-semibold text-ink">
                        {s.name}
                      </td>
                      <td className="px-4 py-3 font-mono text-ink">
                        {s.registration_number || "–"}
                      </td>
                      <td className="px-4 py-3 font-medium text-mute">
                        {s.class_std ?? s.class_name ?? "–"}
                      </td>
                      <td className="px-4 py-3 font-medium text-mute">
                        {s.section || "–"}
                      </td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <div className="flex items-center justify-end gap-1.5">
                          <Button
                            small
                            variant="soft"
                            onClick={() => setCardFor(s)}
                          >
                            Report card
                          </Button>
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
      {importing && (
        <ImportStudents done={reload} close={() => setImporting(false)} />
      )}
      {cardFor && (
        <ReportCardDialog
          classId={cardFor.class_id}
          studentId={cardFor.id}
          title={`Report card · ${cardFor.name}`}
          onClose={() => setCardFor(null)}
        />
      )}
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
                Are you sure you want to delete student{" "}
                <b>{deletingStudent.name}</b> (Roll:{" "}
                {deletingStudent.roll_number})?
              </p>
              <p className="text-xs text-mute">
                This will also remove any evaluations associated with this
                student.
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

/** Pick a student's class as Std, then Sec; a class with no section is the "–" choice. */
function ClassPicker({
  classes,
  value,
  onChange,
}: {
  classes: ClassRow[];
  value: string;
  onChange: (id: string) => void;
}) {
  const [std, setStd] = useState(
    classes.find((c) => c.id === value)?.std ?? "",
  );
  const byStd = (x: string) => classes.filter((c) => c.std === x);
  const stds = [...new Set(classes.map((c) => c.std))].sort((a, b) =>
    a.localeCompare(b, undefined, { numeric: true }),
  );
  const secs = byStd(std).sort((a, b) =>
    (a.section ?? "").localeCompare(b.section ?? "", undefined, {
      numeric: true,
    }),
  );
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Field label="Std">
        {(id) => (
          <Select
            id={id}
            required
            value={std}
            onChange={(e) => {
              setStd(e.target.value);
              const only = byStd(e.target.value);
              onChange(only.length === 1 ? only[0].id : "");
            }}
          >
            <option value="">Choose std...</option>
            {stds.map((x) => (
              <option key={x} value={x}>
                {x}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label="Sec">
        {(id) => (
          <Select
            id={id}
            required
            disabled={!std}
            value={value}
            onChange={(e) => onChange(e.target.value)}
          >
            <option value="">Choose sec...</option>
            {secs.map((c) => (
              <option key={c.id} value={c.id}>
                {c.section ?? "–"}
              </option>
            ))}
          </Select>
        )}
      </Field>
    </div>
  );
}

function StudentForm({ done, close }: { done: () => void; close: () => void }) {
  const classes = useApi<ClassRow[]>("/classes");
  const [name, setName] = useState("");
  const [roll, setRoll] = useState("");
  const [cls, setCls] = useState("");
  const [reg, setReg] = useState("");
  return (
    <SimpleForm
      title="Add New Student"
      onClose={close}
      onSubmit={async () => {
        const section =
          classes.data?.find((c) => c.id === cls)?.section ?? null;
        await api("/students", {
          method: "POST",
          json: {
            name,
            roll_number: roll,
            class_id: cls,
            registration_number: reg || null,
            section,
          },
        });
        done();
      }}
    >
      <Field label="Student Full Name">
        {(id) => (
          <Input
            id={id}
            required
            placeholder="e.g. Priya Patel"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        )}
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Roll Number">
          {(id) => (
            <Input
              id={id}
              required
              placeholder="e.g. 101"
              value={roll}
              onChange={(e) => setRoll(e.target.value)}
            />
          )}
        </Field>
        <Field label="Registration Number">
          {(id) => (
            <Input
              id={id}
              placeholder="e.g. 2026BIO0142"
              value={reg}
              onChange={(e) => setReg(e.target.value)}
            />
          )}
        </Field>
      </div>
      {classes.data && (
        <ClassPicker classes={classes.data} value={cls} onChange={setCls} />
      )}
    </SimpleForm>
  );
}

function EditStudentForm({
  student,
  done,
  close,
}: {
  student: Student;
  done: () => void;
  close: () => void;
}) {
  const classes = useApi<ClassRow[]>("/classes");
  const [name, setName] = useState(student.name);
  const [roll, setRoll] = useState(student.roll_number);
  const [cls, setCls] = useState(student.class_id);
  const [reg, setReg] = useState(student.registration_number || "");
  return (
    <SimpleForm
      title={`Edit Student (${student.name})`}
      onClose={close}
      onSubmit={async () => {
        // a class without a section keeps whatever section the student already had
        const section =
          classes.data?.find((c) => c.id === cls)?.section ??
          student.section ??
          null;
        await api(`/students/${student.id}`, {
          method: "PATCH",
          json: {
            name,
            roll_number: roll,
            class_id: cls,
            registration_number: reg || null,
            section,
          },
        });
        done();
      }}
    >
      <Field label="Student Full Name">
        {(id) => (
          <Input
            id={id}
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        )}
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Roll Number">
          {(id) => (
            <Input
              id={id}
              required
              value={roll}
              onChange={(e) => setRoll(e.target.value)}
            />
          )}
        </Field>
        <Field label="Registration Number">
          {(id) => (
            <Input
              id={id}
              value={reg}
              onChange={(e) => setReg(e.target.value)}
            />
          )}
        </Field>
      </div>
      {classes.data && (
        <ClassPicker classes={classes.data} value={cls} onChange={setCls} />
      )}
    </SimpleForm>
  );
}

function ImportStudents({
  done,
  close,
}: {
  done: () => void;
  close: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [result, setResult] = useState<
    | (ImportSummary & {
        rows?: Array<{
          row: number;
          name: string;
          roll_number: string;
          class_name: string;
          action: string;
        }>;
      })
    | null
  >(null);
  const [committed, setCommitted] = useState(false);

  const go = async (e: FormEvent, confirmed = false) => {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setErr(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("confirm", confirmed ? "true" : "false");
      const response = await api<ImportSummary & { committed: boolean }>(
        "/students/import",
        { method: "POST", form },
      );
      setResult(response);
      setCommitted(response.committed);
      if (response.committed) done();
    } catch (x) {
      setErr(x);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Import Students from Excel" onClose={close}>
      {result ? (
        <div className="space-y-4 text-sm">
          <p className="text-ink">
            {committed ? "Imported: " : "Preview: "}
            <b>{result.created}</b> additions, <b>{result.updated}</b> updates
            {result.errors.length > 0 && (
              <>
                , <b className="text-mark">{result.errors.length}</b> row(s)
                skipped
              </>
            )}
            .
          </p>
          {result.errors.length > 0 && (
            <ul className="max-h-60 space-y-1 overflow-auto rounded-lg border border-line bg-sunken/50 p-3 text-xs">
              {result.errors.map((x) => (
                <li key={x.row}>
                  <span className="font-mono font-semibold">Row {x.row}:</span>{" "}
                  {x.reason}
                </li>
              ))}
            </ul>
          )}
          {!committed && (
            <p className="text-xs text-mute">
              No records have been saved. Correct all errors before confirming.
            </p>
          )}
          {!!result.rows?.length && (
            <div className="max-h-60 overflow-auto rounded border border-line">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr>
                    {["Action", "Name", "Roll", "Class"].map((h) => (
                      <th key={h} className="p-2">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((r) => (
                    <tr key={r.row}>
                      <td className="p-2">{r.action}</td>
                      <td className="p-2">{r.name}</td>
                      <td className="p-2">{r.roll_number}</td>
                      <td className="p-2">{r.class_name}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="flex justify-end border-t border-line/60 pt-3">
            <Button onClick={() => setResult(null)}>Choose another file</Button>
            {!committed && !result.errors.length && (
              <Button
                variant="primary"
                busy={busy}
                onClick={(e) => void go(e, true)}
              >
                Confirm import
              </Button>
            )}
            <Button onClick={close}>{committed ? "Done" : "Cancel"}</Button>
          </div>
        </div>
      ) : (
        <form onSubmit={go} className="space-y-4">
          <Button
            type="button"
            onClick={() =>
              downloadFile(
                "/students/import-template",
                "student-import-template.xlsx",
              )
            }
          >
            Download Excel template
          </Button>
          <div className="rounded-lg border border-line bg-sunken/50 p-3 text-xs text-mute space-y-1">
            <p>
              The first sheet needs a header row with these columns (any order):
            </p>
            <p className="font-mono text-ink">
              Name · Roll Number · Registration Number · Std · Sec
            </p>
            <p>
              <b className="text-ink">Name, Roll Number and Std are required</b>
              : answer sheets are matched to students by the roll or
              registration number written on them. Each Std + Sec becomes its
              own class (Std 10, Sec A → 10-A) and is created if it doesn't
              exist. Existing students are updated (matched by registration
              number, or Std + Sec + roll number). Tip: export your current list
              to get a ready template.
            </p>
          </div>
          <Field label="Excel file (.xlsx)">
            {(id) => (
              <Input
                id={id}
                type="file"
                required
                accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            )}
          </Field>
          <ErrorPanel error={err} />
          <div className="flex justify-end gap-2 border-t border-line/60 pt-3">
            <Button type="button" variant="ghost" onClick={close}>
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              busy={busy}
              disabled={!file}
            >
              Preview import
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}

export function SettingsPage() {
  const { teacher } = useAuth();
  if (teacher?.role !== "MANAGEMENT") return <Navigate to="/account" replace />;
  return (
    <div className="space-y-4 max-w-2xl">
      <PageHeader title="Settings" sub="School details and report templates." />
      <SchoolDetailsCard />
      <ReportTemplatesCard />
    </div>
  );
}
