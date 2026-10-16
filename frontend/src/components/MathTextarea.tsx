import { useRef, useState } from "react";
import { MathView } from "./MathView";

interface MathTextareaProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  rows?: number;
  placeholder?: string;
  className?: string;
  minHeight?: string;
}

interface MathShortcut {
  label: string;
  template: string;
  cursorOffset: number; // Offset from start of insertion
  title: string;
}

const SHORTCUTS: MathShortcut[] = [
  { label: "½ Fraction", template: "\\frac{a}{b}", cursorOffset: 6, title: "Insert fraction: \\frac{a}{b}" },
  { label: "xⁿ Power", template: "^{2}", cursorOffset: 2, title: "Insert exponent: ^{2}" },
  { label: "√ Root", template: "\\sqrt{x}", cursorOffset: 6, title: "Insert square root: \\sqrt{x}" },
  { label: "( ) Parens", template: "\\left(  \\right)", cursorOffset: 7, title: "Insert scaling parentheses: \\left( \\right)" },
  { label: "× Multiply", template: "\\times ", cursorOffset: 7, title: "Insert multiplication symbol: \\times" },
  { label: "÷ Divide", template: "\\div ", cursorOffset: 5, title: "Insert division symbol: \\div" },
  { label: "π Pi", template: "\\pi ", cursorOffset: 4, title: "Insert Pi symbol: \\pi" },
  { label: "± Plus/Minus", template: "\\pm ", cursorOffset: 4, title: "Insert plus/minus symbol: \\pm" },
];

export function MathTextarea({
  id,
  value,
  onChange,
  rows = 6,
  placeholder = "Write text and formulas here... Use \\( ... \\) for inline math or \\[ ... \\] for block formulas.",
  className = "",
  minHeight = "9rem",
}: MathTextareaProps) {
  const [tab, setTab] = useState<"edit" | "preview">("edit");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const insertTemplate = (shortcut: MathShortcut) => {
    const el = textareaRef.current;
    if (!el) {
      onChange(value ? `${value} ${shortcut.template}` : shortcut.template);
      return;
    }

    const start = el.selectionStart ?? value.length;
    const end = el.selectionEnd ?? value.length;
    const before = value.substring(0, start);
    const after = value.substring(end);

    // If text was selected, place it inside the template if applicable
    let insertion = shortcut.template;
    let newCursorPos = start + shortcut.cursorOffset;

    if (start !== end) {
      const selectedText = value.substring(start, end);
      if (shortcut.template.includes("{a}")) {
        insertion = shortcut.template.replace("{a}", `{${selectedText}}`);
        newCursorPos = start + insertion.indexOf("{b}") + 1;
      } else if (shortcut.template.includes("{x}")) {
        insertion = shortcut.template.replace("{x}", `{${selectedText}}`);
        newCursorPos = start + insertion.length;
      }
    }

    const newValue = before + insertion + after;
    onChange(newValue);

    // Re-focus and update cursor position
    setTimeout(() => {
      if (textareaRef.current) {
        textareaRef.current.focus();
        textareaRef.current.setSelectionRange(newCursorPos, newCursorPos);
      }
    }, 10);
  };

  return (
    <div className="space-y-1.5">
      {/* Top Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-1.5 text-xs">
        {/* Quick Math Shortcuts Toolbar (Visible in Edit mode) */}
        <div className="flex flex-wrap items-center gap-1">
          {tab === "edit" ? (
            <>
              <span className="text-[11px] font-medium text-mute mr-1">Insert:</span>
              {SHORTCUTS.map((s, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => insertTemplate(s)}
                  title={s.title}
                  className="rounded border border-line bg-surface px-1.5 py-0.5 text-[11px] font-medium text-ink transition hover:border-pen hover:bg-pen-soft/40 hover:text-pen"
                >
                  {s.label}
                </button>
              ))}
            </>
          ) : (
            <span className="text-[11px] text-mute italic">
              Showing rendered math equations as students and teachers see them.
            </span>
          )}
        </div>

        {/* Edit / Preview Tabs */}
        <div className="inline-flex rounded-md border border-line bg-sunken/40 p-0.5 text-xs">
          <button
            type="button"
            onClick={() => setTab("edit")}
            className={`rounded px-2.5 py-0.5 font-medium transition ${
              tab === "edit"
                ? "bg-surface text-pen font-semibold shadow-xs"
                : "text-mute hover:text-ink"
            }`}
          >
            ✏️ Edit
          </button>
          <button
            type="button"
            onClick={() => setTab("preview")}
            className={`rounded px-2.5 py-0.5 font-medium transition ${
              tab === "preview"
                ? "bg-surface text-pen font-semibold shadow-xs"
                : "text-mute hover:text-ink"
            }`}
          >
            👁️ Preview Math
          </button>
        </div>
      </div>

      {/* Editor or Preview View */}
      {tab === "edit" ? (
        <textarea
          ref={textareaRef}
          id={id}
          rows={rows}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          style={{ minHeight }}
          className={`doc-text w-full rounded-md border border-line bg-surface p-3 font-doc text-sm outline-none transition focus:border-pen focus:ring-1 focus:ring-pen ${className}`}
        />
      ) : (
        <div
          style={{ minHeight }}
          className="doc-text w-full rounded-md border border-line bg-sunken/30 p-3 font-doc text-sm overflow-x-auto"
        >
          {value.trim() ? (
            <MathView text={value} />
          ) : (
            <p className="text-xs text-mute italic">No text entered yet. Switch to Edit to type formulas.</p>
          )}
        </div>
      )}
    </div>
  );
}
