import { useMemo, useState, type FormEvent } from "react";
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
        <div className="flex justify-end gap-2">
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
    <>
      <PageHeader
        title="Classes"
        actions={
          <Button variant="primary" onClick={() => setOpen(true)}>
            Add
          </Button>
        }
      />
      <ErrorPanel error={error} />
      {loading ? (
        <Loading />
      ) : !data?.length ? (
        <Empty title="No classes yet" hint="Add a class such as 10-A before creating exams." />
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
            <Card className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-line text-left text-mute">
                  <tr>
                    <th className="px-4 py-2 font-medium">Class</th>
                    <th className="px-4 py-2 font-medium">Students</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {table.paginatedData.map((c) => (
                    <tr key={c.id} className="hover:bg-sunken">
                      <td className="px-4 py-2 font-medium">{c.name}</td>
                      <td className="px-4 py-2 text-mute">{c.student_count}</td>
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
    </>
  );
}

function ClassForm({ done, close }: { done: () => void; close: () => void }) {
  const [name, setName] = useState("");
  return (
    <SimpleForm
      title="Add class"
      onClose={close}
      onSubmit={async () => {
        await api("/classes", { method: "POST", json: { name } });
        done();
      }}
    >
      <Field label="Class name">
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

export function Subjects() {
  const { data, error, loading, reload } = useApi<Subject[]>("/subjects");
  const [open, setOpen] = useState(false);

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
    <>
      <PageHeader
        title="Subjects"
        actions={
          <Button variant="primary" onClick={() => setOpen(true)}>
            Add
          </Button>
        }
      />
      <ErrorPanel error={error} />
      {loading ? (
        <Loading />
      ) : !data?.length ? (
        <Empty title="No subjects yet" hint="Add the subjects you set exams for." />
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
            <Card className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-line text-left text-mute">
                  <tr>
                    <th className="px-4 py-2 font-medium">Subject</th>
                    <th className="px-4 py-2 font-medium">Code</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {table.paginatedData.map((s) => (
                    <tr key={s.id} className="hover:bg-sunken">
                      <td className="px-4 py-2 font-medium">{s.name}</td>
                      <td className="px-4 py-2 text-mute">{s.code ?? "–"}</td>
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
    </>
  );
}

function SubjectForm({ done, close }: { done: () => void; close: () => void }) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  return (
    <SimpleForm
      title="Add subject"
      onClose={close}
      onSubmit={async () => {
        await api("/subjects", { method: "POST", json: { name, code: code || null } });
        done();
      }}
    >
      <Field label="Subject name">
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
    <>
      <PageHeader
        title="Students"
        actions={
          <Button variant="primary" onClick={() => setOpen(true)}>
            Add
          </Button>
        }
      />
      <ErrorPanel error={error} />
      {loading ? (
        <Loading />
      ) : !data?.length ? (
        <Empty
          title="No students yet"
          hint="Students are also added automatically when you upload an answer sheet."
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
            <Card className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-line text-left text-mute">
                  <tr>
                    <th className="px-4 py-2 font-medium">Roll no.</th>
                    <th className="px-4 py-2 font-medium">Name</th>
                    <th className="px-4 py-2 font-medium">Class</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {table.paginatedData.map((s) => (
                    <tr key={s.id} className="hover:bg-sunken">
                      <td className="px-4 py-2 font-medium">{s.roll_number}</td>
                      <td className="px-4 py-2">{s.name}</td>
                      <td className="px-4 py-2 text-mute">{s.class_name ?? "–"}</td>
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
    </>
  );
}

function StudentForm({ done, close }: { done: () => void; close: () => void }) {
  const classes = useApi<ClassRow[]>("/classes");
  const [name, setName] = useState("");
  const [roll, setRoll] = useState("");
  const [cls, setCls] = useState("");
  return (
    <SimpleForm
      title="Add student"
      onClose={close}
      onSubmit={async () => {
        await api("/students", {
          method: "POST",
          json: { name, roll_number: roll, class_id: cls },
        });
        done();
      }}
    >
      <Field label="Name">
        {(id) => <Input id={id} required value={name} onChange={(e) => setName(e.target.value)} />}
      </Field>
      <Field label="Roll number">
        {(id) => <Input id={id} required value={roll} onChange={(e) => setRoll(e.target.value)} />}
      </Field>
      <Field label="Class">
        {(id) => (
          <Select id={id} required value={cls} onChange={(e) => setCls(e.target.value)}>
            <option value="">Choose a class</option>
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
    <>
      <PageHeader title="Settings" />
      <Card className="max-w-2xl p-5">
        <h2 className="font-semibold">AI service</h2>
        {loading || !data ? (
          <Loading />
        ) : (
          <div className="mt-3 space-y-2 text-sm">
            <p className="flex items-center gap-2">
              <StatusBadge status={data.available ? "READY" : "AI_ERROR"} /> {data.message}
            </p>
            <p className="text-mute">
              Model <code>{data.model}</code> at <code>{data.url}</code>
            </p>
            {data.detail && <p className="text-xs text-mute">{data.detail}</p>}
            <Button onClick={reload}>Check again</Button>
          </div>
        )}
      </Card>
    </>
  );
}
