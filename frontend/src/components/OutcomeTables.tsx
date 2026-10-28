import type { OutcomeRow, Outcomes } from "../types";
import { fmt } from "../utils/format";
import { Card } from "./ui";

function Table({ title, first, rows, average }: { title: string; first: string; rows: OutcomeRow[]; average?: boolean }) {
  return (
    <Card className="overflow-x-auto shadow-soft">
      <div className="border-b border-line px-4 py-3">
        <h3 className="text-sm font-semibold text-ink">{title}</h3>
      </div>
      <table className="w-full text-left text-sm">
        <thead className="border-b border-line bg-surface text-xs font-semibold uppercase tracking-wider text-mute">
          <tr>
            <th className="px-4 py-2.5">{first}</th>
            <th className="px-4 py-2.5">Questions</th>
            <th className="px-4 py-2.5">{average ? "Class Average" : "Scored"}</th>
            <th className="px-4 py-2.5">Max</th>
            <th className="px-4 py-2.5 w-1/3">%</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((r) => (
            <tr key={r.key}>
              <td className="px-4 py-2.5 font-semibold text-ink">
                {r.key}
                {r.label !== r.key && <span className="ml-1.5 font-normal text-mute">{r.label}</span>}
              </td>
              <td className="px-4 py-2.5 font-mono text-mute">{r.questions}</td>
              <td className="px-4 py-2.5 font-mono font-semibold text-pen">{fmt(average ? r.average_scored : r.scored)}</td>
              <td className="px-4 py-2.5 font-mono text-mute">{fmt(r.max_marks)}</td>
              <td className="px-4 py-2.5">
                {r.percentage === null ? (
                  <span className="text-mute">–</span>
                ) : (
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-sunken">
                      <div className="h-full rounded-full bg-pen" style={{ width: `${Math.min(100, r.percentage)}%` }} />
                    </div>
                    <span className="w-12 text-right font-mono text-xs text-ink">{r.percentage}%</span>
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

/** Marks grouped by Bloom's K level. Hidden when no question is tagged. */
export function OutcomeTables({ outcomes, average }: { outcomes: Outcomes; average?: boolean }) {
  if (!outcomes.k_levels.some((r) => r.key !== "Untagged")) return null;
  return <Table title="Performance by Knowledge Level (Bloom's)" first="K Level" rows={outcomes.k_levels} average={average} />;
}
