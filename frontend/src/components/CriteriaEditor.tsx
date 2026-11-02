import { Button, Input } from "./ui";

export interface CriteriaEditorProps {
  label?: string;
  hint?: string;
  criteria: string[];
  onChange: (criteria: string[]) => void;
  marks?: number | string | null;
  className?: string;
  disabled?: boolean;
}

export function CriteriaEditor({
  label = "Criteria",
  hint,
  criteria,
  onChange,
  marks,
  className = "",
  disabled = false,
}: CriteriaEditorProps) {
  const numericMarks = typeof marks === "number" ? marks : Number(marks) || null;
  const targetCount = numericMarks ? Math.max(1, Math.round(numericMarks)) : 1;
  const displayCriteria = criteria && criteria.length > 0 ? criteria : [""];

  const handleUpdate = (index: number, value: string) => {
    const updated = [...displayCriteria];
    updated[index] = value;
    onChange(updated);
  };

  const handleAdd = () => {
    onChange([...displayCriteria, ""]);
  };

  const handleRemove = (index: number) => {
    const updated = displayCriteria.filter((_, i) => i !== index);
    onChange(updated.length > 0 ? updated : [""]);
  };

  const handleSyncWithMarks = () => {
    const adjusted = [...displayCriteria];
    while (adjusted.length < targetCount) {
      adjusted.push("");
    }
    if (adjusted.length > targetCount) {
      onChange(adjusted.slice(0, targetCount));
    } else {
      onChange(adjusted);
    }
  };

  return (
    <div className={`space-y-2.5 ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <label className="block text-sm font-medium">
            {label}
            <span className="ml-1 text-xs font-normal text-mute">(one input per mark)</span>
          </label>
          {hint && <p className="mt-0.5 text-xs text-mute">{hint}</p>}
        </div>
        <div className="flex items-center gap-2 text-xs text-mute">
          <span className="font-medium">
            {displayCriteria.length} {displayCriteria.length === 1 ? "mark field" : "mark fields"}
            {numericMarks != null ? ` · ${numericMarks} total mark${numericMarks === 1 ? "" : "s"}` : ""}
          </span>
          {numericMarks != null && displayCriteria.length !== targetCount && (
            <button
              type="button"
              disabled={disabled}
              onClick={handleSyncWithMarks}
              className="font-medium text-pen hover:underline disabled:opacity-50"
            >
              Align to {targetCount} {targetCount === 1 ? "mark" : "marks"}
            </button>
          )}
        </div>
      </div>

      <div className="space-y-2">
        {displayCriteria.map((crit, idx) => (
          <div key={idx} className="flex items-center gap-2">
            <span
              className="inline-flex shrink-0 items-center justify-center rounded bg-pen-soft px-2.5 py-1.5 text-xs font-semibold text-pen min-w-[4.5rem] select-none border border-pen/20 shadow-xs"
              title={`Mark ${idx + 1} criterion`}
            >
              Mark {idx + 1}
            </span>
            <div className="flex-1 min-w-0">
              <Input
                value={crit}
                disabled={disabled}
                placeholder={`Mark ${idx + 1} criterion (e.g. key point, required formula, correct step)...`}
                onChange={(e) => handleUpdate(idx, e.target.value)}
                className="w-full text-sm"
              />
            </div>
            <button
              type="button"
              disabled={disabled}
              onClick={() => handleRemove(idx)}
              title={`Remove Mark ${idx + 1} criterion`}
              aria-label={`Remove Mark ${idx + 1} criterion`}
              className="inline-flex shrink-0 items-center justify-center rounded p-1.5 text-mute hover:text-mark hover:bg-mark-soft disabled:opacity-40 transition-colors"
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between pt-0.5">
        <Button
          type="button"
          small
          variant="soft"
          disabled={disabled}
          onClick={handleAdd}
          className="text-xs font-medium"
        >
          + Add Criterion
        </Button>
      </div>
    </div>
  );
}
