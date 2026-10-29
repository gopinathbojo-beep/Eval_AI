import type { Rubric, RubricPoint } from "../types";
import { Badge } from "./ui";
import type { Tone } from "../utils/format";

/** How each marking point is checked when grading (see the backend formatter's rubric builder). */
const KIND: Record<RubricPoint["kind"], { label: string; tone: Tone; hint: string }> = {
  number: { label: "Value", tone: "pen", hint: "The student's final value must match" },
  unit: { label: "Unit", tone: "pen", hint: "The SI unit must match (any listed form)" },
  equation: { label: "Equation", tone: "pen", hint: "Same reactants and products, in any order" },
  exact: { label: "Exact", tone: "pen", hint: "This word or answer exactly" },
  meaning: { label: "Meaning", tone: "mute", hint: "Same idea, in the student's own words" },
  criterion: { label: "Band", tone: "mute", hint: "Judged on the whole answer (format, content, expression)" },
};

const marks = (m: number | null) => (m == null ? "–" : Number.isInteger(m) ? String(m) : m.toFixed(1).replace(/\.0$/, ""));

export function RubricView({ rubric, status, questionMarks }: { rubric: Rubric; status: string; questionMarks?: number | null }) {
  const adds = questionMarks == null || Math.abs(rubric.total - questionMarks) < 1e-9;
  return (
    <div className="mt-2.5 space-y-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[11px] text-mute font-semibold uppercase tracking-wider">Marking rubric</span>
        <Badge tone={adds ? "ok" : "mark"}>{marks(rubric.total)} marks</Badge>
        {status === "CONFIRMED" && <Badge tone="ok">Confirmed</Badge>}
      </div>
      <ul className="space-y-1">
        {rubric.points.map((p) => {
          const k = KIND[p.kind] ?? KIND.meaning;
          return (
            <li key={p.id} className="flex flex-wrap items-start gap-1.5 rounded bg-sunken px-2 py-1 text-xs text-ink border border-line/60">
              <span className="font-semibold text-pen text-[11px] whitespace-nowrap">{marks(p.marks)} mk</span>
              {p.part && <span className="text-[11px] font-semibold text-mute">({p.part})</span>}
              <span title={k.hint}><Badge tone={k.tone}>{k.label}</Badge></span>
              <span className="min-w-0 flex-1">{p.text}</span>
              {p.expected.length > 0 && (
                <span className="text-[11px] text-mute">
                  expects <span className="font-semibold text-ink">{p.expected.join(" / ")}</span>
                </span>
              )}
            </li>
          );
        })}
      </ul>
      {rubric.deductions.map((d, i) => (
        <p key={`d${i}`} className="text-[11px] text-mute">Deduction: {d}</p>
      ))}
      {rubric.notes.map((n, i) => (
        <p key={`n${i}`} className="text-[11px] text-mute">Note: {n}</p>
      ))}
      {rubric.problems.map((p, i) => (
        <p key={`p${i}`} className="text-xs font-semibold text-mark">Rubric problem: {p}</p>
      ))}
    </div>
  );
}
