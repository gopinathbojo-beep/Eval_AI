import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../context/Auth";
import { useApi } from "../hooks/useApi";
import {
  Button,
  Card,
  Confirm,
  ErrorPanel,
  Field,
  Input,
  Loading,
  Modal,
  PageHeader,
  Select,
} from "../components/ui";
import type { Teacher } from "../types";

type Metrics = {
  exams: number;
  uploads: number;
  ai_runs: number;
  ai_completed: number;
  ai_failed: number;
  ai_requests: number;
};
type User = Teacher &
  Metrics & {
    is_active: boolean;
    workspace_name: string | null;
    workspace_active: boolean;
    last_login_at: string | null;
  };
type Workspace = Metrics & {
  id: string;
  name: string;
  kind: string;
  owner_id: string;
  is_active: boolean;
};
type Event = {
  id: string;
  action: string;
  teacher_name: string;
  workspace_id: string | null;
  created_at: string;
};
const roles: Record<string, string> = {
  ADMIN: "Platform admin",
  MANAGEMENT: "School management",
  TEACHER: "Teacher",
  PARENT: "Parent",
  UNASSIGNED: "Profile incomplete",
};

function UserEditor({
  user,
  close,
  done,
}: {
  user: User;
  close: () => void;
  done: () => void;
}) {
  const [name, setName] = useState(user.name);
  const [email, setEmail] = useState(user.email);
  const [password, setPassword] = useState("");
  const [active, setActive] = useState(user.is_active);
  const [profile, setProfile] = useState<Record<string, string>>(
    Object.fromEntries(
      Object.entries(user.profile ?? {}).map(([k, v]) => [k, String(v ?? "")]),
    ),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const fields =
    user.role === "MANAGEMENT"
      ? [
          "phone",
          "school_name",
          "address",
          "city",
          "state",
          "postcode",
          "principal_name",
          "affiliation_number",
        ]
      : user.role === "PARENT"
        ? ["phone", "child_name", "child_class", "school_name"]
        : ["phone"];
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api(`/admin/users/${user.id}`, {
        method: "PATCH",
        json: {
          name,
          email,
          is_active: active,
          phone: profile.phone,
          ...(password ? { password } : {}),
        },
      });
      if (user.workspace_id && ["MANAGEMENT", "PARENT"].includes(user.role))
        await api(`/admin/users/${user.id}/profile`, {
          method: "PUT",
          json: {
            ...profile,
            name,
            role: user.role,
            child_class: user.role === "PARENT" ? profile.child_class : null,
          },
        });
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
      title={`Edit ${roles[user.role]?.toLowerCase() ?? "account"}`}
      onClose={close}
    >
      <form onSubmit={submit} className="space-y-4">
        <Field label="Full name">
          {(id) => (
            <Input
              id={id}
              required
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
              disabled={user.is_admin || user.email_verified}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          )}
        </Field>
        {fields.map((key) => (
          <Field key={key} label={key.replace(/_/g, " ")}>
            {(id) =>
              key === "child_class" ? (
                <Select
                  id={id}
                  value={profile[key] ?? "10"}
                  onChange={(e) =>
                    setProfile((p) => ({ ...p, [key]: e.target.value }))
                  }
                >
                  <option value="10">CBSE Class 10</option>
                  <option value="12">CBSE Class 12</option>
                </Select>
              ) : (
                <Input
                  id={id}
                  value={profile[key] ?? ""}
                  onChange={(e) =>
                    setProfile((p) => ({ ...p, [key]: e.target.value }))
                  }
                />
              )
            }
          </Field>
        ))}
        <Field label="New password (optional)">
          {(id) => (
            <Input
              id={id}
              type="password"
              autoComplete="new-password"
              minLength={10}
              maxLength={72}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
        </Field>
        <label className="flex gap-2 text-sm">
          <input
            type="checkbox"
            checked={active}
            disabled={user.is_admin}
            onChange={(e) => setActive(e.target.checked)}
          />
          Account enabled
        </label>
        <ErrorPanel error={error} />
        <div className="flex justify-end gap-2">
          <Button type="button" onClick={close}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" busy={busy}>
            Save changes
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export default function Admin() {
  const { teacher } = useAuth();
  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<User | null>(null);
  const [editing, setEditing] = useState<User | null>(null);
  const [toggle, setToggle] = useState<Workspace | null>(null);
  const [error, setError] = useState<unknown>(null);
  const dates = `${start ? `&start=${start}` : ""}${end ? `&end=${end}` : ""}`;
  const { data: summary, reload: reloadSummary } = useApi<
    Metrics & {
      schools: number;
      parents: number;
      teachers: number;
      users: number;
    }
  >(teacher?.is_admin ? `/admin/summary?${dates}` : null);
  const {
    data: users,
    loading,
    reload,
  } = useApi<{ total: number; users: User[] }>(
    teacher?.is_admin
      ? `/admin/users?q=${encodeURIComponent(q)}&role=${role}&offset=${offset}${dates}`
      : null,
  );
  const { data: workspaces, reload: reloadWorkspaces } = useApi<Workspace[]>(
    teacher?.is_admin ? `/admin/workspaces?${dates}` : null,
  );
  const { data: activity } = useApi<{ total: number; events: Event[] }>(
    teacher?.is_admin
      ? `/admin/activity?limit=50${selected ? `&user_id=${selected.id}` : ""}${dates}`
      : null,
  );
  const refresh = () => {
    void reload();
    void reloadSummary();
    void reloadWorkspaces();
  };
  if (!teacher?.is_admin) return <Navigate to="/dashboard" replace />;
  return (
    <div className="space-y-6">
      <PageHeader
        title="Platform administration"
        sub="Manage schools, families and user access. Track evaluation activity across Eval AI."
      />
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Usage from">
          {(id) => (
            <Input
              id={id}
              type="date"
              value={start}
              onChange={(e) => {
                setStart(e.target.value);
                setSelected(null);
              }}
            />
          )}
        </Field>
        <Field label="Through">
          {(id) => (
            <Input
              id={id}
              type="date"
              value={end}
              min={start}
              onChange={(e) => {
                setEnd(e.target.value);
                setSelected(null);
              }}
            />
          )}
        </Field>
        <Button
          onClick={() => {
            setStart("");
            setEnd("");
            setSelected(null);
          }}
        >
          All time
        </Button>
      </div>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[
          ["Schools", summary?.schools],
          ["Parents", summary?.parents],
          ["Teachers", summary?.teachers],
          ["AI evaluations", summary?.ai_runs],
        ].map(([label, n]) => (
          <Card key={label} className="p-5">
            <p className="text-xs uppercase tracking-wide text-mute">{label}</p>
            <p className="mt-2 text-3xl font-semibold">{n ?? 0}</p>
          </Card>
        ))}
      </div>
      <ErrorPanel error={error} />
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b border-line p-4">
          <h2 className="mr-auto font-semibold">User directory</h2>
          <Input
            aria-label="Search users"
            placeholder="Name, email or school"
            className="max-w-xs"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setOffset(0);
            }}
          />
          <Select
            aria-label="Filter by role"
            className="max-w-xs"
            value={role}
            onChange={(e) => {
              setRole(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All roles</option>
            {Object.entries(roles).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </Select>
        </div>
        {loading ? (
          <Loading />
        ) : (
          <div>
            <div className="divide-y divide-line md:hidden">
              {users?.users.map((u) => (
                <div key={u.id} className="space-y-3 p-4">
                  <div>
                    <p className="font-semibold">{u.name}</p>
                    <p className="break-all text-xs text-mute">{u.email}</p>
                  </div>
                  <p className="text-sm">
                    {roles[u.role]} · {u.workspace_name ?? "Platform"}
                  </p>
                  <p className="text-xs text-mute">
                    {u.is_active && u.workspace_active ? "Enabled" : "Disabled"}{" "}
                    · {u.ai_runs} runs · {u.uploads} uploads
                  </p>
                  <div className="flex gap-2">
                    <Button small onClick={() => setSelected(u)}>
                      Usage
                    </Button>
                    <Button small onClick={() => setEditing(u)}>
                      Edit
                    </Button>
                  </div>
                </div>
              ))}
            </div>
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-left text-sm">
                <thead className="bg-hover text-xs text-mute">
                  <tr>
                    {[
                      "Account",
                      "Role / workspace",
                      "Access",
                      "AI usage",
                      "Actions",
                    ].map((h) => (
                      <th key={h} className="px-5 py-3">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {users?.users.map((u) => (
                    <tr key={u.id}>
                      <td className="px-5 py-4">
                        <p className="font-semibold">{u.name}</p>
                        <p className="text-xs text-mute">{u.email}</p>
                      </td>
                      <td className="px-5 py-4">
                        {roles[u.role]}
                        <p className="text-xs text-mute">
                          {u.workspace_name ?? "No workspace"}
                        </p>
                      </td>
                      <td className="px-5 py-4">
                        <span className="rounded border border-line px-2 py-1 text-xs">
                          {!u.is_active || !u.workspace_active
                            ? "Disabled"
                            : !u.profile_complete && !u.is_admin
                              ? "Profile incomplete"
                              : "Enabled"}
                        </span>
                      </td>
                      <td className="px-5 py-4">
                        {u.ai_runs} runs
                        <p className="text-xs text-mute">
                          {u.ai_requests} requests · {u.uploads} uploads
                        </p>
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex gap-2">
                          <Button small onClick={() => setSelected(u)}>
                            Usage
                          </Button>
                          <Button small onClick={() => setEditing(u)}>
                            Edit
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!users?.users.length && (
                <p className="p-8 text-center text-mute">
                  No matching accounts.
                </p>
              )}
            </div>
          </div>
        )}
        <div className="flex items-center justify-between border-t border-line p-4 text-xs text-mute">
          <span>{users?.total ?? 0} accounts</span>
          <div className="flex gap-2">
            <Button
              small
              disabled={!offset}
              onClick={() => setOffset((n) => Math.max(0, n - 50))}
            >
              Previous
            </Button>
            <Button
              small
              disabled={offset + 50 >= (users?.total ?? 0)}
              onClick={() => setOffset((n) => n + 50)}
            >
              Next
            </Button>
          </div>
        </div>
      </Card>
      <Card className="p-5">
        <h2 className="font-semibold">Schools and families</h2>
        <p className="mt-1 text-xs text-mute">
          Disabling a workspace immediately blocks all its members. Re-enabling
          does not restore old sessions.
        </p>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {workspaces?.map((w) => (
            <div
              key={w.id}
              className="flex flex-wrap justify-between gap-3 rounded border border-line p-4"
            >
              <div>
                <p className="font-semibold">{w.name}</p>
                <p className="text-xs text-mute">
                  {w.kind === "SCHOOL" ? "School" : "Family"} · {w.ai_runs} runs
                  · {w.uploads} uploads · {w.exams} exams
                </p>
              </div>
              <Button small onClick={() => setToggle(w)}>
                {w.is_active ? "Disable workspace" : "Enable workspace"}
              </Button>
            </div>
          ))}
          {!workspaces?.length && (
            <p className="text-sm text-mute">
              Workspaces appear when schools and parents complete registration.
            </p>
          )}
        </div>
      </Card>
      <Card className="p-5">
        <div className="flex justify-between gap-2">
          <h2 className="font-semibold">
            {selected
              ? `${selected.name}: activity and usage`
              : "Recent platform activity"}
          </h2>
          {selected && (
            <Button small onClick={() => setSelected(null)}>
              All users
            </Button>
          )}
        </div>
        {selected && (
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              ["Evaluation runs", selected.ai_runs],
              ["Completed", selected.ai_completed],
              ["Failed", selected.ai_failed],
              ["AI requests", selected.ai_requests],
            ].map(([k, v]) => (
              <div key={k} className="rounded bg-hover p-3">
                <p className="text-xs text-mute">{k}</p>
                <p className="text-xl font-semibold">{v}</p>
              </div>
            ))}
          </div>
        )}
        <div className="mt-4 divide-y divide-line">
          {activity?.events.map((e) => (
            <div
              key={e.id}
              className="flex flex-wrap justify-between gap-2 py-3 text-sm"
            >
              <div>
                <p>{e.action.replace(/_/g, " ")}</p>
                <p className="text-xs text-mute">
                  {e.teacher_name} ·{" "}
                  {workspaces?.find((w) => w.id === e.workspace_id)?.name ??
                    "Platform"}
                </p>
              </div>
              <time className="text-xs text-mute">
                {new Date(e.created_at).toLocaleString()}
              </time>
            </div>
          ))}
          {!activity?.events.length && (
            <p className="text-sm text-mute">No activity in this date range.</p>
          )}
        </div>
      </Card>
      {editing && (
        <UserEditor
          user={editing}
          close={() => setEditing(null)}
          done={refresh}
        />
      )}
      {toggle && (
        <Confirm
          title={toggle.is_active ? "Disable workspace?" : "Enable workspace?"}
          body={`${toggle.name}: this affects every member's access.`}
          confirmLabel={
            toggle.is_active ? "Disable workspace" : "Enable workspace"
          }
          onClose={() => setToggle(null)}
          onConfirm={async () => {
            try {
              await api(`/admin/workspaces/${toggle.id}`, {
                method: "PATCH",
                json: { is_active: !toggle.is_active },
              });
              setToggle(null);
              refresh();
            } catch (e) {
              setError(e);
              setToggle(null);
            }
          }}
        />
      )}
    </div>
  );
}
