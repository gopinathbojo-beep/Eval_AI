import { useState } from "react";
import type { Rubric, RubricPoint } from "../types";
import type { ScoringNode } from "../types/standards";
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

/** One row of the marking-scheme tree: its marks, label and text, then its parts (OR options say so). */
function CriteriaNode({ node, depth }: { node: ScoringNode; depth: number }) {
  const choice = node.kind === "choose";
  const vi = node.audience === "accessible";
  return (
    <li className={depth ? "border-l border-line/70 pl-2.5" : ""}>
      <div className="flex flex-wrap items-start gap-1.5 py-0.5">
        {node.marks != null && node.kind !== "context" && (
          <span className="whitespace-nowrap text-[11px] font-semibold text-pen">{marks(node.marks)} mk</span>
        )}
        {node.label && <span className="text-[11px] font-semibold text-ink">{node.label}</span>}
        {choice && <Badge tone="pen">{`Any ${node.limit ?? 1} of ${node.children.length}`}</Badge>}
        {vi && <Badge tone="mute">Visually impaired</Badge>}
        {node.text && <span className="min-w-0 flex-1 text-ink/90">{node.text}</span>}
      </div>
      {(node.deductions ?? []).map((d) => (
        <p key={d.id} className="text-[11px] text-mute">Deduction (up to {marks(d.maximum)}): {d.text}</p>
      ))}
      {node.children.length > 0 && (
        <ul className="ml-1 space-y-0.5">
          {node.children.map((child, i) => [
            choice && i > 0 && (
              <li key={`${child.id}-or`} className="py-0.5 text-[10px] font-bold uppercase tracking-wider text-mute">or</li>
            ),
            <CriteriaNode key={child.id} node={child} depth={depth + 1} />,
          ])}
        </ul>
      )}
    </li>
  );
}

export function RubricView({ rubric, status, questionMarks, criteria = [] }: {
  rubric: Rubric; status: string; questionMarks?: number | null; criteria?: string[];
}) {
  const [open, setOpen] = useState(false);
  if (rubric.cbse_tree) return <div className="mt-3 rounded border border-line p-3 text-xs">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span><strong>Uploaded marking scheme</strong> · {questionMarks} marks</span>
      <button
        type="button"
        className="inline-flex items-center gap-1 rounded-full border border-line bg-surface px-2.5 py-1 text-[11px] font-semibold text-pen hover:bg-hover"
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}
        aria-expanded={open}
      >
        {open ? "Hide mark criteria" : "View mark criteria"}
      </button>
    </div>
    <p className="mt-1 text-mute">{status==="CONFIRMED"?"Reviewed and confirmed.":"Review the answer, marks and question mapping before verification."}</p>
    {open && (
      <div className="mt-2 space-y-2 border-t border-dashed border-line pt-2" onClick={(e) => e.stopPropagation()}>
        <ul><CriteriaNode node={rubric.cbse_tree} depth={0} /></ul>
        {criteria.length > 0 && (
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-mute">Marking instructions</p>
            <ul className="mt-0.5 list-disc space-y-0.5 pl-4">{criteria.map((c, i) => <li key={i}>{c}</li>)}</ul>
          </div>
        )}
        {rubric.problems.map((p, i) => (
          <p key={`p${i}`} className="font-semibold text-mark">Note: {p}</p>
        ))}
      </div>
    )}
  </div>;
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
