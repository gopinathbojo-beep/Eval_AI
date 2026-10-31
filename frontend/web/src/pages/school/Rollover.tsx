import { useState } from "react";
import { api } from "../../api/client";
import { useApi } from "../../hooks/useApi";
import { Button, Card, Empty, ErrorPanel, Field, Input, Loading, PageHeader, Select } from "../../components/ui";

interface Plan { classes: { id: string; name: string; students: number }[] }
interface Move { from: string; to: string | null; created?: boolean; copied: number; skipped: number; graduated?: number }
interface Result { academic_year: string; dry_run: boolean; moves: Move[] }
type Choice = { action: "copy" | "graduate" | "skip"; to: string };

/** Year rollover: for each class, carry its students into next year's class or mark them as leaving. Last year's
 * classes, marks and report cards are not touched. Preview first, then run. */
export default function Rollover() {
  const { data, error, loading, reload } = useApi<Plan>("/school/rollover");
  const [year, setYear] = useState(() => { const y = new Date().getFullYear(); return `${y}-${String(y + 1).slice(2)}`; });
  const [choice, setChoice] = useState<Record<string, Choice>>({});
  const [result, setResult] = useState<Result | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (loading && !data) return <Loading />;
  if (error) return <ErrorPanel error={error} />;
  if (!data) return null;

  const of = (id: string, name: string): Choice => choice[id] ?? { action: name.startsWith("12") ? "graduate" : "copy", to: "" };
  const moves = data.classes.map((c) => ({ c, ch: of(c.id, c.name) })).filter(({ ch }) => ch.action !== "skip")
    .map(({ c, ch }) => ({ from_class_id: c.id, graduate: ch.action === "graduate", to_class_name: ch.to }));

  const run = async (dry_run: boolean) => {
    setBusy(true); setErr(null);
    try {
      setResult(await api<Result>("/school/rollover", { method: "POST", json: { academic_year: year, moves, dry_run } }));
      if (!dry_run) await reload();
    } catch (e) { setErr(e); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title="Year rollover" sub="Start the new academic year. Students are copied into next year's classes; last year's classes and results stay as they are." />
      {!data.classes.length ? <Empty title="No classes yet" /> : (
        <Card>
          <div className="mb-4 max-w-xs">
            <Field label="New academic year" required>{(id) => <Input id={id} value={year} onChange={(e) => setYear(e.target.value)} />}</Field>
          </div>
          <div className="space-y-3">
            {data.classes.map((c) => {
              const ch = of(c.id, c.name);
              const set = (p: Partial<Choice>) => { setChoice({ ...choice, [c.id]: { ...ch, ...p } }); setResult(null); };
              return (
                <div key={c.id} className="grid items-center gap-2 border-b border-dashed border-line pb-3 sm:grid-cols-[1fr_12rem_1fr]">
                  <p><span className="font-semibold">{c.name}</span> <span className="text-sm text-mute">· {c.students} students</span></p>
                  <Select aria-label={`What happens to ${c.name}`} value={ch.action} onChange={(e) => set({ action: e.target.value as Choice["action"] })}>
                    <option value="copy">Move to class</option><option value="graduate">Leaving (graduate)</option><option value="skip">Leave as is</option>
                  </Select>
                  {ch.action === "copy"
                    ? <Input aria-label={`Next year's class for ${c.name}`} placeholder="e.g. 10-A 2026" value={ch.to} onChange={(e) => set({ to: e.target.value })} />
                    : <span />}
                </div>
              );
            })}
          </div>
          <ErrorPanel error={err} />
          <div className="mt-4 flex flex-wrap gap-2">
            <Button busy={busy} disabled={!moves.length} onClick={() => run(true)}>Preview</Button>
            <Button variant="primary" busy={busy} disabled={!result?.dry_run} onClick={() => run(false)}>Run rollover</Button>
          </div>
        </Card>
      )}
      {result && (
        <Card className="mt-6">
          <h2 className="mb-2 font-display text-lg font-semibold">{result.dry_run ? "Preview" : `Done: ${result.academic_year}`}</h2>
          <ul className="space-y-1 text-sm">
            {result.moves.map((m, i) => (
              <li key={i}>{m.to === null ? `${m.from}: ${m.graduated} student(s) leaving`
                : `${m.from} → ${m.to}${m.created ? " (new class)" : ""}: ${m.copied} copied${m.skipped ? `, ${m.skipped} already there` : ""}`}</li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}
