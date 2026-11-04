import { useEffect, useMemo, useState } from "react";
import { useApi } from "../hooks/useApi";
import { Field, Input, Select, Textarea } from "./ui";

export interface GenPattern { id: string; name: string; total_marks: number; duration_minutes: number; questions: number }
export interface GenSubject { key: string; name: string; patterns: GenPattern[]; chapters: number }
export interface GenChapter { id: string; book: string | null; chapter: string; title: string; pages: number }

export interface GenerateBody {
  grade?: "10" | "12";
  subject_key?: string;
  pattern: "board" | "custom";
  profile_id?: string | null;
  mix?: Record<string, number> | null;
  duration_minutes: number;
  choices: boolean;
  source_ids: string[];
  difficulty: "easy" | "balanced" | "hard";
  topics: string;
  notes: string;
  title?: string;
}

const MARKS = [1, 2, 3, 4, 5];
const DEFAULT_MIX: Record<string, number> = { "1": 10, "2": 5, "3": 4, "4": 0, "5": 2 };

/** The generation options: pattern, chapters, difficulty, focus. The class and subject are chosen here unless the
 *  caller fixes them (an exam's own subject). Reports every change through onChange; null = not ready to submit. */
export default function PaperGenerator({
  grade: fixedGrade,
  subjectKey: fixedSubject,
  onChange,
  disabled,
}: {
  grade?: "10" | "12";
  subjectKey?: string;
  onChange: (body: GenerateBody | null) => void;
  disabled?: boolean;
}) {
  const subjects = useApi<Record<string, GenSubject[]>>("/generation/subjects");
  const [gradeSel, setGradeSel] = useState<"10" | "12">("10");
  const [subjectSel, setSubjectSel] = useState("");
  const grade = fixedGrade ?? gradeSel;
  const subjectKey = fixedSubject ?? subjectSel;
  const subject = subjects.data?.[grade]?.find((s) => s.key === subjectKey);
  const chapters = useApi<GenChapter[]>(subjectKey ? `/generation/chapters?subject=${encodeURIComponent(subjectKey)}` : null);

  const [pattern, setPattern] = useState<string>("custom");
  const [mix, setMix] = useState<Record<string, number>>(DEFAULT_MIX);
  const [duration, setDuration] = useState(90);
  const [choices, setChoices] = useState(true);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [difficulty, setDifficulty] = useState<GenerateBody["difficulty"]>("balanced");
  const [topics, setTopics] = useState("");
  const [notes, setNotes] = useState("");

  // a subject with a CBSE board pattern starts on the full board paper
  useEffect(() => setPattern(subject?.patterns[0]?.id ?? "custom"), [subject?.key]);
  useEffect(() => setPicked(new Set()), [subjectKey]);

  const customTotal = useMemo(() => MARKS.reduce((t, m) => t + m * (mix[String(m)] || 0), 0), [mix]);
  const customCount = useMemo(() => MARKS.reduce((t, m) => t + (mix[String(m)] || 0), 0), [mix]);
  const board = subject?.patterns.find((p) => p.id === pattern);

  const body: GenerateBody | null = useMemo(() => {
    if (!subject || !subject.chapters) return null;
    if (!board && (customCount < 1 || customCount > 60)) return null;
    return {
      ...(fixedGrade ? {} : { grade, subject_key: subjectKey }),
      pattern: board ? "board" : "custom",
      profile_id: board?.id ?? null,
      mix: board ? null : Object.fromEntries(Object.entries(mix).filter(([, n]) => n > 0)),
      duration_minutes: board ? board.duration_minutes : duration,
      choices,
      source_ids: [...picked],
      difficulty,
      topics,
      notes,
    };
  }, [subject, board, mix, duration, choices, picked, difficulty, topics, notes, grade, subjectKey, fixedGrade, customCount]);

  useEffect(() => onChange(body), [body]);

  const byBook = useMemo(() => {
    const groups: Record<string, GenChapter[]> = {};
    for (const c of chapters.data ?? []) (groups[c.book || "Textbook"] ??= []).push(c);
    return groups;
  }, [chapters.data]);

  const toggle = (id: string) => setPicked((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleBook = (ids: string[]) => setPicked((s) => {
    const n = new Set(s);
    const all = ids.every((i) => n.has(i));
    ids.forEach((i) => (all ? n.delete(i) : n.add(i)));
    return n;
  });

  return (
    <fieldset disabled={disabled} className="space-y-5">
      {!fixedSubject && (
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Class" required>
            {(id) => (
              <Select id={id} value={gradeSel} onChange={(e) => { setGradeSel(e.target.value as "10" | "12"); setSubjectSel(""); }}>
                <option value="10">Class 10</option>
                <option value="12">Class 12</option>
              </Select>
            )}
          </Field>
          <Field label="Subject" required>
            {(id) => (
              <Select id={id} value={subjectSel} onChange={(e) => setSubjectSel(e.target.value)} disabled={subjects.loading}>
                <option value="">{subjects.loading ? "Loading subjects..." : "Choose a subject"}</option>
                {(subjects.data?.[grade] ?? []).map((s) => (
                  <option key={s.key} value={s.key} disabled={!s.chapters}>
                    {s.name}{s.chapters ? "" : " (textbook not loaded)"}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </div>
      )}

      {subjectKey && subject && !subject.chapters && (
        <p className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          No NCERT textbook for this subject is loaded in the reference library yet, so a paper cannot be generated.
        </p>
      )}

      {subject && subject.chapters > 0 && (
        <>
          <Field label="Paper pattern" required>
            {(id) => (
              <Select id={id} value={pattern} onChange={(e) => setPattern(e.target.value)}>
                {subject.patterns.map((p) => (
                  <option key={p.id} value={p.id}>
                    CBSE board pattern: {p.name} ({p.total_marks} marks, {p.questions} questions)
                  </option>
                ))}
                <option value="custom">Custom (unit test, chapter test...)</option>
              </Select>
            )}
          </Field>

          {!board && (
            <div className="rounded-xl border border-slate-200 p-4 space-y-3">
              <p className="text-[13px] font-semibold text-ink">Number of questions per mark value</p>
              <div className="grid grid-cols-3 gap-3 sm:grid-cols-5">
                {MARKS.map((m) => (
                  <label key={m} className="text-xs text-mute space-y-1">
                    <span>{m} mark{m > 1 ? "s" : ""}</span>
                    <Input type="number" min={0} max={40} value={mix[String(m)] ?? 0}
                           onChange={(e) => setMix({ ...mix, [String(m)]: Math.max(0, Math.min(40, Number(e.target.value) || 0)) })} />
                  </label>
                ))}
              </div>
              <div className="flex flex-wrap items-end gap-4">
                <label className="text-xs text-mute space-y-1">
                  <span>Duration (minutes)</span>
                  <Input type="number" min={15} max={240} value={duration}
                         onChange={(e) => setDuration(Math.max(15, Math.min(240, Number(e.target.value) || 60)))} />
                </label>
                <p className="text-sm text-ink pb-2">
                  {customCount} questions, <b>{customTotal} marks</b>
                  {customCount > 60 && <span className="text-rose-600"> (at most 60 questions)</span>}
                </p>
              </div>
            </div>
          )}

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-[13px] font-semibold text-ink">Chapters</p>
              <p className="text-xs text-mute">{picked.size ? `${picked.size} chosen` : "None chosen = the whole syllabus"}</p>
            </div>
            <div className="max-h-64 overflow-y-auto rounded-xl border border-slate-200 p-3 space-y-3">
              {chapters.loading && <p className="text-xs text-mute">Loading chapters...</p>}
              {Object.entries(byBook).map(([book, list]) => (
                <div key={book} className="space-y-1">
                  {Object.keys(byBook).length > 1 && (
                    <button type="button" className="text-xs font-semibold text-blue-700 hover:underline"
                            onClick={() => toggleBook(list.map((c) => c.id))}>
                      {book}
                    </button>
                  )}
                  {list.map((c) => (
                    <label key={c.id} className="flex items-start gap-2 text-sm text-ink cursor-pointer">
                      <input type="checkbox" className="mt-1" checked={picked.has(c.id)} onChange={() => toggle(c.id)} />
                      <span>{c.chapter}</span>
                    </label>
                  ))}
                </div>
              ))}
            </div>
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Difficulty">
              {(id) => (
                <Select id={id} value={difficulty} onChange={(e) => setDifficulty(e.target.value as GenerateBody["difficulty"])}>
                  <option value="easy">Easy</option>
                  <option value="balanced">Balanced (board level)</option>
                  <option value="hard">Challenging</option>
                </Select>
              )}
            </Field>
            <label className="flex items-center gap-2 text-sm text-ink pt-7">
              <input type="checkbox" checked={choices} onChange={(e) => setChoices(e.target.checked)} />
              Internal choices (OR questions)
            </label>
          </div>
          <Field label="Focus topics" hint="Optional">
            {(id) => <Input id={id} maxLength={500} placeholder="e.g. neutralisation, pH scale" value={topics}
                            onChange={(e) => setTopics(e.target.value)} />}
          </Field>
          <Field label="Instructions for the AI" hint="Optional">
            {(id) => <Textarea id={id} rows={2} maxLength={800} placeholder="e.g. include two numerical problems; more competency-based questions"
                               value={notes} onChange={(e) => setNotes(e.target.value)} />}
          </Field>
        </>
      )}
    </fieldset>
  );
}
