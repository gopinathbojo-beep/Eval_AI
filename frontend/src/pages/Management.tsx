import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../context/Auth";
import { useApi } from "../hooks/useApi";
import {
  Button,
  Card,
  ErrorPanel,
  Field,
  Input,
  Loading,
  Modal,
  PageHeader,
  Select,
} from "../components/ui";
import type { Teacher, ClassRow, Subject } from "../types";
import { WorkspaceProfile } from "./Onboarding";

type Pair = { class_id: string; subject_id: string };
type SchoolTeacher = Teacher & { is_active: boolean; assignments: Pair[] };

function TeacherEditor({
  row,
  done,
  close,
  classes,
  subjects,
}: {
  row: SchoolTeacher | null;
  done: () => void;
  close: () => void;
  classes: ClassRow[];
  subjects: Subject[];
}) {
  const [name, setName] = useState(row?.name ?? "");
  const [email, setEmail] = useState(row?.email ?? "");
  const [phone, setPhone] = useState(row?.profile?.phone ?? "");
  const [password, setPassword] = useState("");
  const [active, setActive] = useState(row?.is_active ?? true);
  const [pairs, setPairs] = useState<Pair[]>(row?.assignments ?? []);
  const [cid, setCid] = useState(classes[0]?.id ?? "");
  const [sid, setSid] = useState(subjects[0]?.id ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api(
        row ? `/management/teachers/${row.id}` : "/management/teachers",
        {
          method: row ? "PATCH" : "POST",
          json: {
            name,
            email,
            phone,
            is_active: active,
            assignments: pairs,
            ...(password ? { password } : {}),
          },
        },
      );
      done();
      close();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title={row ? "Edit teacher" : "Create teacher login"}
      onClose={close}
    >
      <form onSubmit={submit} className="space-y-4">
        <Field label="Teacher name">
          {(id) => (
            <Input
              id={id}
              required
              maxLength={200}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          )}
        </Field>
        <Field label="Email">
          {(id) => (
            <Input
              id={id}
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          )}
        </Field>
        <Field label="Phone (optional)">
          {(id) => (
            <Input
              id={id}
              maxLength={30}
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />
          )}
        </Field>
        <Field
          label={
            row ? "Reset temporary password (optional)" : "Temporary password"
          }
        >
          {(id) => (
            <Input
              id={id}
              type="password"
              autoComplete="new-password"
              required={!row}
              minLength={10}
              maxLength={72}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
        </Field>
        <p className="text-xs text-mute">
          Share credentials securely. The teacher must change this password at
          first login.
        </p>
        {row && (
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={active}
              onChange={(e) => setActive(e.target.checked)}
            />
            Account enabled
          </label>
        )}
        <fieldset className="space-y-3 rounded border border-line p-3">
          <legend className="px-1 text-sm font-semibold">
            Class and subject assignments
          </legend>
          <div className="grid gap-2 sm:grid-cols-2">
            <Select
              aria-label="Assignment class"
              value={cid}
              onChange={(e) => setCid(e.target.value)}
            >
              {classes.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
            <Select
              aria-label="Assignment subject"
              value={sid}
              onChange={(e) => setSid(e.target.value)}
            >
              {subjects.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </Select>
          </div>
          <Button
            type="button"
            disabled={!cid || !sid}
            onClick={() =>
              setPairs((p) =>
                p.some((a) => a.class_id === cid && a.subject_id === sid)
                  ? p
                  : [...p, { class_id: cid, subject_id: sid }],
              )
            }
          >
            Add assignment
          </Button>
          {pairs.map((p, i) => (
            <div
              key={`${p.class_id}:${p.subject_id}`}
              className="flex items-center justify-between gap-2 text-sm"
            >
              <span>
                {classes.find((c) => c.id === p.class_id)?.name} ·{" "}
                {subjects.find((s) => s.id === p.subject_id)?.name}
              </span>
              <Button
                type="button"
                small
                onClick={() => setPairs((a) => a.filter((_, j) => i !== j))}
              >
                Remove
              </Button>
            </div>
          ))}
          {!classes.length || !subjects.length ? (
            <p className="text-xs text-mute">
              Create classes and subjects before assigning teachers.
            </p>
          ) : null}
        </fieldset>
        <ErrorPanel error={error} />
        <div className="flex justify-end gap-2">
          <Button type="button" onClick={close}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" busy={busy}>
            Save teacher
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export default function Management() {
  const { teacher } = useAuth();
  const {
    data: rows,
    error,
    loading,
    reload,
  } = useApi<SchoolTeacher[]>(
    teacher?.role === "MANAGEMENT" ? "/management/teachers" : null,
  );
  const { data: classes } = useApi<ClassRow[]>("/classes");
  const { data: subjects } = useApi<Subject[]>("/subjects");
  const [editing, setEditing] = useState<SchoolTeacher | null | undefined>(
    undefined,
  );
  const [q, setQ] = useState("");
  const [tab, setTab] = useState("teachers");
  if (teacher?.role !== "MANAGEMENT")
    return <Navigate to="/dashboard" replace />;
  return (
    <div className="space-y-6">
      <PageHeader
        title="School management"
        sub="Manage your school's team and shared CBSE Class 10 and 12 workspace."
      />
      <div className="flex gap-2">
        <Button
          variant={tab === "teachers" ? "primary" : "soft"}
          onClick={() => setTab("teachers")}
        >
          Teachers
        </Button>
        <Button
          variant={tab === "profile" ? "primary" : "soft"}
          onClick={() => setTab("profile")}
        >
          School profile
        </Button>
      </div>
      {tab === "profile" ? (
        <WorkspaceProfile editing />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            {[
              ["Teachers", rows?.length ?? 0],
              ["Enabled", rows?.filter((t) => t.is_active).length ?? 0],
              [
                "Assignments",
                rows?.reduce((n, t) => n + t.assignments.length, 0) ?? 0,
              ],
            ].map(([k, v]) => (
              <Card key={k} className="p-5">
                <p className="text-xs uppercase tracking-wide text-mute">{k}</p>
                <p className="mt-2 text-3xl font-semibold">{v}</p>
              </Card>
            ))}
          </div>
          <Card className="overflow-hidden">
            <div className="flex flex-wrap justify-between gap-3 border-b border-line p-4">
              <Input
                aria-label="Search teachers"
                placeholder="Search name or email"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                className="max-w-sm"
              />
              <Button variant="primary" onClick={() => setEditing(null)}>
                Add teacher
              </Button>
            </div>
            <ErrorPanel error={error} />
            {loading ? (
              <Loading />
            ) : (
              <div className="divide-y divide-line">
                {rows
                  ?.filter((t) =>
                    `${t.name} ${t.email}`
                      .toLowerCase()
                      .includes(q.toLowerCase()),
                  )
                  .map((t) => (
                    <div
                      key={t.id}
                      className="flex flex-wrap items-center justify-between gap-3 p-5"
                    >
                      <div>
                        <p className="font-semibold">
                          {t.name}{" "}
                          <span className="ml-2 text-xs font-normal text-mute">
                            {t.is_active ? "Enabled" : "Disabled"}
                          </span>
                        </p>
                        <p className="text-sm text-mute">{t.email}</p>
                        <p className="mt-2 text-xs text-mute">
                          {t.assignments
                            .map(
                              (a) =>
                                `${classes?.find((c) => c.id === a.class_id)?.name ?? "Class"} · ${subjects?.find((s) => s.id === a.subject_id)?.name ?? "Subject"}`,
                            )
                            .join(" / ") || "No assignments yet"}
                        </p>
                      </div>
                      <Button onClick={() => setEditing(t)}>
                        Edit teacher
                      </Button>
                    </div>
                  ))}
                {!rows?.length && (
                  <p className="p-8 text-center text-mute">
                    Create classes and subjects, then add your first teacher.
                  </p>
                )}
              </div>
            )}
          </Card>
        </>
      )}
      {editing !== undefined && (
        <TeacherEditor
          row={editing}
          close={() => setEditing(undefined)}
          done={reload}
          classes={classes ?? []}
          subjects={subjects ?? []}
        />
      )}
    </div>
  );
}
