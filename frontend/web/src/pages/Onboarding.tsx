import { useState, type FormEvent } from "react";
import { Link, Navigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../context/Auth";
import { BrandLabel } from "../components/Brand";
import {
  Button,
  Card,
  ErrorPanel,
  Field,
  Input,
  Loading,
  Select,
} from "../components/ui";

export function WorkspaceProfile({ editing = false }: { editing?: boolean }) {
  const { teacher, refresh } = useAuth();
  const [role, setRole] = useState(
    teacher?.role === "PARENT" ? "PARENT" : "MANAGEMENT",
  );
  const [form, setForm] = useState<Record<string, string>>({
    name: teacher?.name ?? "",
    phone: "",
    school_name: "",
    address: "",
    city: "",
    state: "",
    postcode: "",
    principal_name: "",
    affiliation_number: "",
    child_name: "",
    child_class: "10",
    ...Object.fromEntries(
      Object.entries(teacher?.profile ?? {}).map(([k, v]) => [
        k,
        String(v ?? ""),
      ]),
    ),
  });
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await api("/auth/profile", {
        method: "PUT",
        json: {
          ...form,
          role,
          child_class: role === "PARENT" ? form.child_class : null,
        },
      });
      await refresh();
      setSaved(true);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  const field = (key: string, label: string, required = true) => (
    <Field key={key} label={label}>
      {(id) => (
        <Input
          id={id}
          value={form[key] ?? ""}
          required={required}
          maxLength={key === "address" ? 600 : key === "phone" ? 30 : 200}
          onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
        />
      )}
    </Field>
  );
  return (
    <Card className="p-6">
      <h1 className="font-display text-2xl font-semibold">
        {editing ? "Workspace profile" : "Complete your profile"}
      </h1>
      <p className="mt-2 text-sm text-mute">
        CBSE Classes 10 and 12. Your workspace is available as soon as you
        complete these details.
      </p>
      <form onSubmit={submit} className="mt-6 space-y-4">
        {teacher?.role === "UNASSIGNED" && (
          <Field label="Account type">
            {(id) => (
              <Select
                id={id}
                value={role}
                onChange={(e) => setRole(e.target.value)}
              >
                <option value="MANAGEMENT">School management</option>
                <option value="PARENT">Parent</option>
              </Select>
            )}
          </Field>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          {field(
            "name",
            role === "PARENT" ? "Parent name" : "Management contact name",
          )}
          {field("phone", "Contact number")}
        </div>
        {role === "MANAGEMENT" ? (
          <>
            {field("school_name", "School name")}
            {field("address", "School address")}
            <div className="grid gap-4 sm:grid-cols-2">
              {field("city", "City")}
              {field("state", "State")}
              {field("postcode", "Postcode")}
              {field("principal_name", "Principal name (optional)", false)}
              {field(
                "affiliation_number",
                "CBSE affiliation number (optional)",
                false,
              )}
            </div>
          </>
        ) : (
          <>
            {field("child_name", "Child's full name")}
            <Field label="Child's class">
              {(id) => (
                <Select
                  id={id}
                  value={form.child_class}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, child_class: e.target.value }))
                  }
                >
                  <option value="10">CBSE Class 10</option>
                  <option value="12">CBSE Class 12</option>
                </Select>
              )}
            </Field>
            {field("school_name", "Child's school (optional)", false)}
            <p className="text-xs text-mute">
              One child per parent account. Their evaluations stay private to
              your family.
            </p>
          </>
        )}
        <ErrorPanel error={error} />
        {saved && (
          <p role="status" className="text-sm text-pen">
            Profile saved.
          </p>
        )}
        <Button type="submit" variant="primary" busy={busy}>
          {editing ? "Save profile" : "Open my workspace"}
        </Button>
      </form>
    </Card>
  );
}

export default function Onboarding() {
  const { teacher, loading, logout } = useAuth();
  if (loading) return <Loading />;
  if (!teacher) return <Navigate to="/login" replace />;
  if (teacher.is_admin || teacher.profile_complete)
    return (
      <Navigate
        to={
          teacher.is_admin
            ? "/admin"
            : teacher.must_change_password
              ? "/account"
              : "/dashboard"
        }
        replace
      />
    );
  return (
    <main className="desk min-h-full p-6">
      <div className="mx-auto max-w-2xl space-y-6">
        <div className="flex justify-between">
          <BrandLabel onDark={false} />
          <Button onClick={logout}>Sign out</Button>
        </div>
        <WorkspaceProfile />
        <Link to="/account" className="text-sm underline">
          Account settings
        </Link>
      </div>
    </main>
  );
}
