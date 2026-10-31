import { useEffect, useId, useMemo, useRef, useState, type ComponentType } from "react";
import { useNavigate } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import type { Evaluation, Exam } from "../types";
import { IconEvaluation, IconExam, IconPlus, IconSearch } from "./Icons";

export interface PaletteLink {
  to: string;
  label: string;
  icon: ComponentType<{ size?: number; className?: string }>;
}

interface Entry {
  to: string;
  label: string;
  hint?: string;
  group: string;
  icon: PaletteLink["icon"];
}

const MAX_PER_GROUP = 6;

/** Ctrl/⌘ K jump-to: pages, exams and answer scripts. Exams and scripts load only while the palette is open. */
export function CommandPalette({ open, onClose, pages }: { open: boolean; onClose: () => void; pages: PaletteLink[] }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listId = useId();
  const { data: exams } = useApi<Exam[]>(open ? "/exams" : null);
  const { data: scripts } = useApi<Evaluation[]>(open ? "/evaluations" : null);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActive(0);
    inputRef.current?.focus();
  }, [open]);

  const entries = useMemo<Entry[]>(() => {
    const q = query.trim().toLowerCase();
    const hit = (...xs: (string | null | undefined)[]) => !q || xs.some((x) => x?.toLowerCase().includes(q));
    const pageEntries: Entry[] = [
      { to: "/exams/new", label: "Create exam", group: "Actions", icon: IconPlus },
      ...pages.map((p) => ({ ...p, group: "Pages" })),
    ].filter((e) => hit(e.label));
    const examEntries: Entry[] = (exams ?? [])
      .filter((e) => hit(e.name, e.class_name, e.subject_name))
      .slice(0, MAX_PER_GROUP)
      .map((e) => ({
        to: `/exams/${e.id}`,
        label: e.name,
        hint: [e.class_name, e.subject_name].filter(Boolean).join(" · "),
        group: "Exams",
        icon: IconExam,
      }));
    // Scripts only once the teacher types, otherwise the list is dominated by them
    const scriptEntries: Entry[] = q
      ? (scripts ?? [])
          .filter((s) => hit(s.student.name, s.student.roll_number, s.exam_name))
          .slice(0, MAX_PER_GROUP)
          .map((s) => ({
            to: `/evaluations/${s.id}`,
            label: s.student.name,
            hint: s.exam_name ?? undefined,
            group: "Answer scripts",
            icon: IconEvaluation,
          }))
      : [];
    return [...pageEntries, ...examEntries, ...scriptEntries];
  }, [query, pages, exams, scripts]);

  useEffect(() => setActive(0), [query]);
  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  if (!open) return null;

  const go = (e: Entry | undefined) => {
    if (!e) return;
    onClose();
    navigate(e.to);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const n = entries.length;
      if (n) setActive((i) => (i + (e.key === "ArrowDown" ? 1 : n - 1)) % n);
    } else if (e.key === "Enter") {
      e.preventDefault();
      go(entries[active]);
    } else if (e.key === "Escape") {
      e.stopPropagation();
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center px-4 pt-[12vh]" onKeyDown={onKeyDown}>
      <div className="absolute inset-0 animate-fadeIn bg-cover/55 backdrop-blur-[3px]" onClick={onClose} aria-hidden />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search"
        className="relative w-full max-w-xl animate-rise overflow-hidden rounded-lg border border-line bg-surface shadow-pop"
      >
        <div className="flex items-center gap-3 border-b border-line px-4">
          <IconSearch size={18} className="shrink-0 text-mute" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search exams, students, pages…"
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={entries[active] ? `${listId}-${active}` : undefined}
            className="h-12 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-mute"
          />
          <kbd className="rounded border border-line bg-sunken px-1.5 py-0.5 text-[10px] font-medium text-mute">Esc</kbd>
        </div>
        <ul ref={listRef} id={listId} role="listbox" className="max-h-[50vh] overflow-y-auto p-1.5">
          {entries.length === 0 && <li className="px-3 py-6 text-center text-sm text-mute">No matches for “{query}”</li>}
          {entries.map((e, i) => {
            const Icon = e.icon;
            const header = i === 0 || entries[i - 1]!.group !== e.group;
            return (
              <li key={`${e.group}-${e.to}`} role="presentation">
                {header && (
                  <p className="px-2.5 pb-1 pt-2.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-mute">{e.group}</p>
                )}
                <div
                  id={`${listId}-${i}`}
                  data-index={i}
                  role="option"
                  aria-selected={i === active}
                  onMouseMove={() => setActive(i)}
                  onClick={() => go(e)}
                  className={`flex cursor-pointer items-center gap-3 rounded-md px-2.5 py-2 text-sm ${
                    i === active ? "bg-hover text-brown" : "text-ink"
                  }`}
                >
                  <Icon size={16} className="shrink-0 text-mute" />
                  <span className="truncate">{e.label}</span>
                  {e.hint && <span className="ml-auto truncate pl-3 text-xs text-mute">{e.hint}</span>}
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
