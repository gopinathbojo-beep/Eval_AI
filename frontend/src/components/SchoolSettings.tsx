import { useEffect, useState } from "react";
import { api, downloadFile, fetchBlobUrl } from "../api/client";
import { useApi } from "../hooks/useApi";
import type { ReportCardTerm, SchoolProfile, TemplateKind } from "../types";
import { TemplateEditor } from "./TemplateEditor";
import { Button, Card, ErrorPanel, Field, Input, Loading, Modal, Select, Textarea } from "./ui";

/** School name, address, principal and logo: printed on every report and report card. */
export function SchoolDetailsCard() {
  const { data, loading, error: loadError, reload } = useApi<SchoolProfile>("/school-profile");
  const [form, setForm] = useState({ name: "", address: "", principal_name: "" });
  const [logo, setLogo] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (data) setForm({ name: data.name, address: data.address, principal_name: data.principal_name });
  }, [data]);
  useEffect(() => {
    let url: string | null = null;
    if (data?.has_logo) fetchBlobUrl("/school-profile/logo").then((u) => setLogo((url = u))).catch(() => setLogo(null));
    else setLogo(null);
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [data]); // a fresh profile after every save/upload also refreshes the logo

  const run = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key);
    setError(null);
    setSaved(false);
    try {
      await fn();
      await reload();
      if (key === "save") setSaved(true);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  if (loadError) return <Card className="p-6"><ErrorPanel error={loadError} /></Card>;
  if (loading || !data) return <Card className="p-6"><Loading /></Card>;
  return (
    <Card className="p-6 shadow-soft space-y-4">
      <div className="border-b border-line pb-3">
        <h2 className="text-lg font-semibold text-ink">School Details</h2>
        <p className="text-xs text-mute">Printed at the top of reports and report cards.</p>
      </div>
      <div className="flex items-start gap-4">
        <div className="flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-line bg-sunken">
          {logo ? <img src={logo} alt="School logo" className="max-h-full max-w-full object-contain" /> : <span className="text-xs text-mute">No logo</span>}
        </div>
        <div className="space-y-2">
          <label className="inline-flex">
            <input type="file" accept="image/png,image/jpeg" className="sr-only"
              onChange={(e) => {
                const f = e.target.files?.[0];
                e.target.value = "";
                if (!f) return;
                const form = new FormData();
                form.append("file", f);
                run("logo", () => api("/school-profile/logo", { method: "POST", form }));
              }} />
            <span className="cursor-pointer rounded-lg bg-sunken px-3 py-1.5 text-xs font-medium text-ink hover:bg-hover">
              {busy === "logo" ? "Uploading…" : data.has_logo ? "Change logo" : "Upload logo"}
            </span>
          </label>
          {data.has_logo && (
            <Button small variant="ghost" className="text-mark hover:bg-mark-soft hover:text-mark" busy={busy === "dellogo"}
              onClick={() => run("dellogo", () => api("/school-profile/logo", { method: "DELETE" }))}>
              Remove
            </Button>
          )}
          <p className="text-xs text-mute">PNG or JPG, up to 3 MB.</p>
        </div>
      </div>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); run("save", () => api("/school-profile", { method: "PUT", json: form })); }}>
        <Field label="School name">
          {(id) => <Input id={id} value={form.name} maxLength={200} onChange={(e) => setForm({ ...form, name: e.target.value })} />}
        </Field>
        <Field label="Address">
          {(id) => <Textarea id={id} rows={2} value={form.address} maxLength={600} onChange={(e) => setForm({ ...form, address: e.target.value })} />}
        </Field>
        <Field label="Principal's name">
          {(id) => <Input id={id} value={form.principal_name} maxLength={200} onChange={(e) => setForm({ ...form, principal_name: e.target.value })} />}
        </Field>
        <ErrorPanel error={error} />
        <div className="flex items-center gap-3">
          <Button type="submit" variant="primary" busy={busy === "save"}>Save</Button>
          {saved && <span className="text-xs text-ok">Saved</span>}
        </div>
      </form>
    </Card>
  );
}

/** Opens the template editors for the exam report and the report card. */
export function ReportTemplatesCard() {
  const [editing, setEditing] = useState<TemplateKind | null>(null);
  return (
    <Card className="p-6 shadow-soft space-y-4">
      <div className="border-b border-line pb-3">
        <h2 className="text-lg font-semibold text-ink">Report Templates</h2>
        <p className="text-xs text-mute">Choose and edit how reports and report cards look.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => setEditing("report")}>Exam report template</Button>
        <Button onClick={() => setEditing("report_card")}>Report card template</Button>
      </div>
      {editing && <TemplateEditor kind={editing} onClose={() => setEditing(null)} />}
    </Card>
  );
}

/** Pick a term (academic year + exam type) and download report cards for one student or a whole class. */
export function ReportCardDialog({
  classId, studentId, title, onClose,
}: {
  classId: string; studentId?: string; title: string; onClose: () => void;
}) {
  const terms = useApi<ReportCardTerm[]>(`/classes/${classId}/report-card-terms`);
  const [sel, setSel] = useState("0");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const term = terms.data?.[Number(sel)];
  const download = async () => {
    if (!term) return;
    setBusy(true);
    setError(null);
    const q = `academic_year=${encodeURIComponent(term.academic_year)}&exam_type=${encodeURIComponent(term.exam_type)}`;
    try {
      await downloadFile(studentId ? `/students/${studentId}/report-card?${q}` : `/classes/${classId}/report-cards?${q}`, "report-card.pdf");
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title={title} onClose={onClose}>
      {terms.loading ? (
        <Loading />
      ) : !terms.data?.length ? (
        <p className="text-sm text-mute">No finalized results yet for this class. Report cards are made from finalized exams.</p>
      ) : (
        <div className="space-y-4">
          <Field label="Term">
            {(id) => (
              <Select id={id} value={sel} onChange={(e) => setSel(e.target.value)}>
                {terms.data!.map((t, i) => (
                  <option key={`${t.academic_year}-${t.exam_type}`} value={i}>{t.exam_type} · {t.academic_year}</option>
                ))}
              </Select>
            )}
          </Field>
          {term && <p className="text-xs text-mute">Subjects: {term.subjects.join(", ")}</p>}
          <ErrorPanel error={error} />
          <div className="flex justify-end gap-2 border-t border-line/60 pt-3">
            <Button variant="ghost" onClick={onClose}>Cancel</Button>
            <Button variant="primary" busy={busy} onClick={download}>Download PDF</Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
