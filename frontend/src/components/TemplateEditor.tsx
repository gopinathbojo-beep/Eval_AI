import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, postBlobUrl } from "../api/client";
import type { ReportTemplate, TemplateConfig, TemplateKind, Toggle } from "../types";
import { Button, ErrorPanel, Field, Input, Loading, Modal, Select, Textarea } from "./ui";

const NAMES: Record<string, string> = {
  header: "School header", title: "Title", student_details: "Student details", summary: "Summary box",
  marks_table: "Question-wise marks", subjects_table: "Subject-wise marks", outcomes: "Bloom's level summary",
  note: "Note", remarks: "Remarks", signatures: "Signatures", grade_scale: "Grading scale",
  qno: "Question no.", k_level: "K level", max: "Max marks", obtained: "Obtained", feedback: "Feedback",
  subject: "Subject", percent: "Percentage", grade: "Grade", percentage: "Percentage", total: "Total", rank: "Class rank",
};
const TABS = ["Layout", "Labels", "Style", "Text"] as const;

/** Show/hide and reorder a list of parts (sections, columns or summary items). */
function ToggleList({ items, onChange }: { items: Toggle[]; onChange: (v: Toggle[]) => void }) {
  const move = (i: number, d: number) => {
    const next = [...items];
    [next[i], next[i + d]] = [next[i + d], next[i]];
    onChange(next);
  };
  return (
    <ul className="divide-y divide-line rounded-lg border border-line">
      {items.map((t, i) => (
        <li key={t.id} className="flex items-center gap-2 px-3 py-1.5 text-sm">
          <input
            type="checkbox"
            className="h-4 w-4 accent-pen"
            checked={t.visible}
            onChange={() => onChange(items.map((x) => (x.id === t.id ? { ...x, visible: !x.visible } : x)))}
            aria-label={`Show ${NAMES[t.id] ?? t.id}`}
          />
          <span className={`flex-1 ${t.visible ? "text-ink" : "text-mute line-through"}`}>{NAMES[t.id] ?? t.id}</span>
          <button type="button" className="px-1.5 text-mute hover:text-brown disabled:opacity-30" disabled={i === 0}
            onClick={() => move(i, -1)} aria-label="Move up">▲</button>
          <button type="button" className="px-1.5 text-mute hover:text-brown disabled:opacity-30" disabled={i === items.length - 1}
            onClick={() => move(i, 1)} aria-label="Move down">▼</button>
        </li>
      ))}
    </ul>
  );
}

export function TemplateEditor({ kind, onClose }: { kind: TemplateKind; onClose: () => void }) {
  const [templates, setTemplates] = useState<ReportTemplate[]>([]);
  const [activeId, setActiveId] = useState("");
  const [selId, setSelId] = useState("");
  const [draft, setDraft] = useState<TemplateConfig | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]>("Layout");
  const [preview, setPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [saveAs, setSaveAs] = useState<string | null>(null);
  const prevUrl = useRef<string | null>(null);

  const load = async (select?: string) => {
    const r = await api<{ templates: ReportTemplate[]; active_id: string }>(`/report-templates?kind=${kind}`);
    setTemplates(r.templates);
    setActiveId(r.active_id);
    const id = select ?? r.active_id;
    const t = r.templates.find((x) => x.id === id) ?? r.templates[0];
    setSelId(t.id);
    setDraft(structuredClone(t.config));
  };
  useEffect(() => {
    load().catch(setError);
  }, [kind]);

  const selected = templates.find((t) => t.id === selId);
  const defaults = templates[0]?.config; // Classic: the reference wording for every label
  const dirty = useMemo(() => !!selected && !!draft && JSON.stringify(selected.config) !== JSON.stringify(draft), [selected, draft]);

  // live preview: re-render the draft shortly after the last change
  useEffect(() => {
    if (!draft) return;
    const ctl = new AbortController();
    const h = setTimeout(async () => {
      try {
        const url = await postBlobUrl("/report-templates/preview", { kind, config: draft }, ctl.signal);
        if (prevUrl.current) URL.revokeObjectURL(prevUrl.current);
        prevUrl.current = url;
        setPreview(url);
      } catch (e) {
        if ((e as Error).name !== "AbortError") setError(e);
      }
    }, 500);
    return () => {
      clearTimeout(h);
      ctl.abort();
    };
  }, [draft, kind]);
  useEffect(() => () => { if (prevUrl.current) URL.revokeObjectURL(prevUrl.current); }, []);

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };
  const set = (patch: Partial<TemplateConfig>) => draft && setDraft({ ...draft, ...patch });
  const pick = (id: string) => {
    const t = templates.find((x) => x.id === id);
    if (!t) return;
    setSelId(id);
    setDraft(structuredClone(t.config));
  };
  const saveNew = (name: string) =>
    run("saveas", async () => {
      const t = await api<ReportTemplate>("/report-templates", { method: "POST", json: { kind, name, config: draft } });
      setSaveAs(null);
      await load(t.id);
    });

  const title = kind === "report" ? "Exam Report Template" : "Report Card Template";
  // stable identity: Modal re-focuses itself whenever onClose changes, which would steal focus while typing
  const closeSaveAs = useCallback(() => setSaveAs(null), []);

  return (
    <Modal title={title} onClose={onClose} wide="xl">
      {!draft || !defaults ? (
        <Loading />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
          {/* editor */}
          <div className="space-y-3 min-w-0">
            <div className="flex flex-wrap items-end gap-2">
              <div className="min-w-0 flex-1">
                <Field label="Template">
                  {(id) => (
                    <Select id={id} value={selId} onChange={(e) => pick(e.target.value)}>
                      {templates.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name}{t.preset ? " (built-in)" : ""}{t.id === activeId ? " — in use" : ""}
                        </option>
                      ))}
                    </Select>
                  )}
                </Field>
              </div>
              <Button
                small
                variant="primary"
                disabled={selId === activeId || dirty}
                title={dirty ? "Save your changes first" : undefined}
                busy={busy === "use"}
                onClick={() => run("use", async () => {
                  await api("/report-templates/activate", { method: "POST", json: { kind, id: selId } });
                  setActiveId(selId);
                })}
              >
                {selId === activeId ? "In use" : "Use this"}
              </Button>
            </div>

            <div className="flex flex-wrap gap-1.5">
              {selected && !selected.preset && (
                <Button small variant="primary" disabled={!dirty} busy={busy === "save"}
                  onClick={() => run("save", async () => {
                    await api(`/report-templates/${selId}`, { method: "PUT", json: { config: draft } });
                    await load(selId);
                  })}>
                  Save
                </Button>
              )}
              <Button small onClick={() => setSaveAs(selected?.preset ? `My ${selected.name}` : `${selected?.name} copy`)}>
                Save as new
              </Button>
              {dirty && <Button small variant="ghost" onClick={() => selected && setDraft(structuredClone(selected.config))}>Undo changes</Button>}
              {selected && !selected.preset && (
                <Button small variant="ghost" className="text-mark hover:bg-mark-soft hover:text-mark" busy={busy === "del"}
                  onClick={() => run("del", async () => {
                    await api(`/report-templates/${selId}`, { method: "DELETE" });
                    await load();
                  })}>
                  Delete
                </Button>
              )}
            </div>
            {selected?.preset && dirty && (
              <p className="text-xs text-mute">Built-in templates can't be changed. Use "Save as new" to keep your edits.</p>
            )}
            <ErrorPanel error={error} />

            <div className="flex gap-1 border-b border-line">
              {TABS.map((t) => (
                <button key={t} type="button" onClick={() => setTab(t)}
                  className={`border-b-2 px-3 py-1.5 text-xs font-semibold ${tab === t ? "border-pen text-pen" : "border-transparent text-mute hover:text-brown"}`}>
                  {t}
                </button>
              ))}
            </div>

            <div className="max-h-[52vh] space-y-4 overflow-y-auto pr-1">
              {tab === "Layout" && (
                <>
                  <div className="space-y-1.5">
                    <p className="text-xs font-semibold text-mute">Sections (tick to show, arrows to reorder)</p>
                    <ToggleList items={draft.sections} onChange={(sections) => set({ sections })} />
                  </div>
                  <div className="space-y-1.5">
                    <p className="text-xs font-semibold text-mute">Table columns</p>
                    <ToggleList items={draft.columns} onChange={(columns) => set({ columns })} />
                  </div>
                  <div className="space-y-1.5">
                    <p className="text-xs font-semibold text-mute">Summary box</p>
                    <ToggleList items={draft.summary} onChange={(summary) => set({ summary })} />
                  </div>
                </>
              )}

              {tab === "Labels" && (
                <div className="grid gap-2 sm:grid-cols-2">
                  {Object.keys(defaults.labels).map((k) => (
                    <Field key={k} label={defaults.labels[k]}>
                      {(id) => (
                        <Input id={id} value={draft.labels[k] ?? ""} placeholder={defaults.labels[k]}
                          onChange={(e) => set({ labels: { ...draft.labels, [k]: e.target.value } })} />
                      )}
                    </Field>
                  ))}
                </div>
              )}

              {tab === "Style" && (
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Accent colour">
                    {(id) => (
                      <div className="flex items-center gap-2">
                        <input id={id} type="color" className="h-9 w-12 cursor-pointer rounded border border-line"
                          value={draft.style.accent} onChange={(e) => set({ style: { ...draft.style, accent: e.target.value } })} />
                        <span className="font-mono text-xs text-mute">{draft.style.accent}</span>
                      </div>
                    )}
                  </Field>
                  <Field label="Font">
                    {(id) => (
                      <Select id={id} value={draft.style.font} onChange={(e) => set({ style: { ...draft.style, font: e.target.value } })}>
                        <option value="default">Default (Segoe / Arial)</option>
                        <option value="helvetica">Helvetica</option>
                        <option value="times">Times (serif)</option>
                      </Select>
                    )}
                  </Field>
                  <Field label={`Text size: ${draft.style.font_size}`}>
                    {(id) => (
                      <input id={id} type="range" min={7} max={12} step={0.5} className="w-full" value={draft.style.font_size}
                        onChange={(e) => set({ style: { ...draft.style, font_size: Number(e.target.value) } })} />
                    )}
                  </Field>
                  <Field label={`Logo size: ${draft.style.logo_size}`}>
                    {(id) => (
                      <input id={id} type="range" min={30} max={160} step={2} className="w-full" value={draft.style.logo_size}
                        onChange={(e) => set({ style: { ...draft.style, logo_size: Number(e.target.value) } })} />
                    )}
                  </Field>
                  <Field label="Logo position">
                    {(id) => (
                      <Select id={id} value={draft.style.logo_position} onChange={(e) => set({ style: { ...draft.style, logo_position: e.target.value } })}>
                        <option value="left">Left of school name</option>
                        <option value="center">Above school name</option>
                        <option value="none">Hide logo</option>
                      </Select>
                    )}
                  </Field>
                  <Field label="Table lines">
                    {(id) => (
                      <Select id={id} value={draft.style.borders} onChange={(e) => set({ style: { ...draft.style, borders: e.target.value } })}>
                        <option value="grid">Full grid</option>
                        <option value="lines">Row lines only</option>
                        <option value="none">No lines</option>
                      </Select>
                    )}
                  </Field>
                  <Field label="Paper">
                    {(id) => (
                      <Select id={id} value={draft.style.paper} onChange={(e) => set({ style: { ...draft.style, paper: e.target.value } })}>
                        <option value="A4">A4</option>
                        <option value="Letter">Letter</option>
                      </Select>
                    )}
                  </Field>
                  <label className="flex items-center gap-2 self-end pb-2 text-sm text-ink">
                    <input type="checkbox" className="h-4 w-4" checked={draft.style.zebra}
                      onChange={(e) => set({ style: { ...draft.style, zebra: e.target.checked } })} />
                    Shade alternate rows
                  </label>
                </div>
              )}

              {tab === "Text" && (
                <div className="space-y-3">
                  <Field label="Signature lines (one per line, up to 4)">
                    {(id) => (
                      <Textarea id={id} rows={4} value={draft.signers.join("\n")}
                        onChange={(e) => set({ signers: e.target.value.split("\n").slice(0, 4) })} />
                    )}
                  </Field>
                  <Field label="Note (shown in the Note section)">
                    {(id) => (
                      <Textarea id={id} rows={3} value={draft.text.note} placeholder="e.g. Parent-teacher meeting on 12 Oct."
                        onChange={(e) => set({ text: { ...draft.text, note: e.target.value } })} />
                    )}
                  </Field>
                  <Field label="Footer (left blank: school name and document)">
                    {(id) => (
                      <Input id={id} value={draft.text.footer}
                        onChange={(e) => set({ text: { ...draft.text, footer: e.target.value } })} />
                    )}
                  </Field>
                </div>
              )}
            </div>
          </div>

          {/* live preview with sample data */}
          <div className="min-w-0 space-y-1.5">
            <p className="text-xs text-mute">Preview with sample data</p>
            {preview ? (
              <iframe title="Template preview" src={`${preview}#toolbar=0&navpanes=0`} className="h-[70vh] w-full rounded-lg border border-line bg-white" />
            ) : (
              <div className="flex h-[70vh] items-center justify-center rounded-lg border border-line bg-sunken/50"><Loading /></div>
            )}
          </div>
        </div>
      )}

      {saveAs !== null && (
        <Modal title="Save as new template" onClose={closeSaveAs}>
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (saveAs.trim()) saveNew(saveAs.trim()); }}>
            <Field label="Name">
              {(id) => <Input id={id} autoFocus maxLength={100} value={saveAs} onChange={(e) => setSaveAs(e.target.value)} />}
            </Field>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={() => setSaveAs(null)}>Cancel</Button>
              <Button type="submit" variant="primary" busy={busy === "saveas"} disabled={!saveAs.trim()}>Save</Button>
            </div>
          </form>
        </Modal>
      )}
    </Modal>
  );
}
