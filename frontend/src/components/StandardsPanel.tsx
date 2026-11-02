import { useState } from "react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import type { StandardProfile, ScoringNode } from "../types/standards";
import { Button, ErrorPanel, Input, Textarea } from "./ui";

type Evidence = {
  metadata: Record<string, string | number>;
  instructions: string[];
  issues: string[];
};
type Document = {
  id: string;
  kind: string;
  status: string;
  extraction: Evidence | null;
};
type Row = {
  id: string;
  display_number?: string;
  raw_question_number?: string;
  page_start?: number;
  structure?: { root: number; tree: ScoringNode | null; issues: string[] };
  rubric?: { cbse_tree?: ScoringNode; problems: string[] };
};
interface Validation {
  options: Record<string, string> | null;
  legacy: boolean;
  valid: boolean;
  profile: StandardProfile;
  can_edit: boolean;
  issues: {
    code: string;
    message: string;
    question?: string;
    page?: number;
    expected?: unknown;
    detected?: unknown;
  }[];
  documents: Document[];
  questions: Row[];
  keys: Row[];
  detected: { question_count: number; section_totals: Record<string, number> };
}

function NodeEditor({
  node,
  onChange,
}: {
  node: ScoringNode;
  onChange: (n: ScoringNode) => void;
}) {
  return (
    <div className="space-y-2 rounded border border-line bg-surface p-3">
      <div className="grid gap-2 sm:grid-cols-3">
        <label className="text-xs">
          Part / criterion label
          <Input
            value={node.label}
            onChange={(e) => onChange({ ...node, label: e.target.value })}
          />
        </label>
        <label className="text-xs">
          How marks count
          <select
            className="w-full rounded border border-line p-2"
            value={node.kind}
            onChange={(e) =>
              onChange({ ...node, kind: e.target.value as ScoringNode["kind"] })
            }
          >
            <option value="all">All parts count</option>
            <option value="choose">Choose best permitted parts</option>
            <option value="point">Marking point / whole answer</option>
            <option value="context">Unscored context</option>
          </select>
        </label>
        <label className="text-xs">
          Printed marks
          <Input
            type="number"
            min={0}
            step="any"
            value={node.marks ?? ""}
            onChange={(e) =>
              onChange({
                ...node,
                marks: e.target.value === "" ? null : Number(e.target.value),
              })
            }
          />
        </label>
        {node.kind === "choose" && (
          <label className="text-xs">
            Number to answer
            <Input
              type="number"
              min={1}
              value={node.limit ?? ""}
              onChange={(e) =>
                onChange({ ...node, limit: Number(e.target.value) })
              }
            />
          </label>
        )}
        {node.kind === "choose" && (
          <label className="text-xs">
            Type of choice
            <select
              className="w-full rounded border border-line p-2"
              value={node.choice_type || "question"}
              onChange={(e) =>
                onChange({
                  ...node,
                  choice_type: e.target.value as "question" | "method",
                })
              }
            >
              <option value="question">Question alternatives</option>
              <option value="method">Equivalent solution methods</option>
            </select>
          </label>
        )}
        <label className="text-xs">
          Version
          <select
            className="w-full rounded border border-line p-2"
            value={node.audience || ""}
            onChange={(e) =>
              onChange({ ...node, audience: e.target.value || null })
            }
          >
            <option value="">All versions</option>
            <option value="standard">Standard</option>
            <option value="accessible">Visually impaired</option>
            <option value="financial">Financial statements</option>
            <option value="computerised">Computerised accounting</option>
          </select>
        </label>
      </div>
      <label className="block text-xs">
        Answer type
        <select
          className="w-full rounded border border-line p-2"
          value={node.response_type || "open"}
          onChange={(e) =>
            onChange({
              ...node,
              response_type: e.target.value as "open" | "mcq",
            })
          }
        >
          <option value="open">Descriptive / working / rubric</option>
          <option value="mcq">MCQ (no partial marks)</option>
        </select>
      </label>
      <label className="block text-xs">
        Question part / marking instruction
        <Textarea
          rows={2}
          value={node.text}
          onChange={(e) => onChange({ ...node, text: e.target.value })}
        />
      </label>
      {(node.deductions || []).map((rule, index) => (
        <div
          key={rule.id}
          className="grid gap-2 rounded bg-sunken p-2 sm:grid-cols-3"
        >
          <label className="text-xs sm:col-span-2">
            Printed deduction rule
            <Input
              value={rule.text}
              onChange={(e) =>
                onChange({
                  ...node,
                  deductions: node.deductions!.map((r, i) =>
                    i === index ? { ...r, text: e.target.value } : r,
                  ),
                })
              }
            />
          </label>
          <label className="text-xs">
            Maximum deduction
            <Input
              type="number"
              min={0}
              step="any"
              value={rule.maximum}
              onChange={(e) =>
                onChange({
                  ...node,
                  deductions: node.deductions!.map((r, i) =>
                    i === index ? { ...r, maximum: Number(e.target.value) } : r,
                  ),
                })
              }
            />
          </label>
          <button
            type="button"
            className="text-xs text-mark"
            onClick={() =>
              onChange({
                ...node,
                deductions: node.deductions!.filter((_, i) => i !== index),
              })
            }
          >
            Remove deduction
          </button>
        </div>
      ))}
      <button
        type="button"
        className="text-xs font-semibold text-pen"
        onClick={() =>
          onChange({
            ...node,
            deductions: [
              ...(node.deductions || []),
              {
                id: `${node.id}.deduction.${crypto.randomUUID()}`,
                maximum: 1,
                text: "",
              },
            ],
          })
        }
      >
        + Add deduction specified by scheme
      </button>
      {node.children.map((child, index) => (
        <div key={child.id} className="ml-3 border-l-2 border-line pl-3">
          <NodeEditor
            node={child}
            onChange={(n) =>
              onChange({
                ...node,
                children: node.children.map((c, i) => (i === index ? n : c)),
              })
            }
          />
          <button
            type="button"
            className="text-xs text-mark"
            onClick={() =>
              onChange({
                ...node,
                children: node.children.filter((_, i) => i !== index),
              })
            }
          >
            Remove this part
          </button>
        </div>
      ))}
      <button
        type="button"
        className="text-xs font-semibold text-pen"
        onClick={() =>
          onChange({
            ...node,
            children: [
              ...node.children,
              {
                id: `${node.id}.${crypto.randomUUID()}`,
                kind: "point",
                label: "",
                text: "",
                marks: null,
                limit: null,
                audience: null,
                children: [],
              },
            ],
          })
        }
      >
        + Add scored part or criterion
      </button>
    </div>
  );
}

export function StandardsPanel({
  examId,
  phase,
  onChanged,
}: {
  examId: string;
  phase: "paper" | "scheme";
  onChanged: () => void;
}) {
  const { data, error, reload } = useApi<Validation>(
    `/exams/${examId}/standard-validation?phase=${phase}`,
    (d) =>
      d.documents?.some((x) =>
        ["UPLOADED", "RENDERING", "OCR_PROCESSING", "EXTRACTING"].includes(
          x.status,
        ),
      )
        ? 2500
        : null,
  );
  const [edit, setEdit] = useState<{
    options?: Record<string, string>;
    target: string;
    id: string;
    tree?: ScoringNode;
    evidence?: Evidence;
    root?: number;
    issues: string[];
  } | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setError] = useState<unknown>(null);
  if (error) return <ErrorPanel error={error} />;
  if (!data || data.legacy) return null;
  const save = async () => {
    if (!edit) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/exams/${examId}/standard-review`, {
        method: "POST",
        json: {
          target: edit.target,
          id: edit.id,
          options: edit.options,
          tree: edit.tree,
          root: edit.root,
          ...(edit.evidence ? edit.evidence : { issues: edit.issues }),
          reason,
        },
      });
      setEdit(null);
      setReason("");
      await reload();
      onChanged();
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section
      className="space-y-3 rounded-xl border border-line bg-surface p-5"
      aria-label="CBSE validation"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">CBSE validation</h2>
          <p className="text-xs text-mute">
            {data.profile.name} · {data.profile.code} · {data.profile.version}
          </p>
        </div>
        <Button variant="ghost" onClick={reload}>
          Check again
        </Button>
      </div>
      <p
        className={`text-sm font-semibold ${data.valid ? "text-ok" : "text-mark"}`}
      >
        {data.valid
          ? "Board pattern checks passed"
          : phase === "paper"
            ? "Review these findings before evaluation; accepted questions can continue to the answer key."
            : "Corrections required before continuing"}
      </p>
      <div className="flex flex-wrap gap-3 text-xs text-mute">
        <span>
          {data.detected.question_count}/{data.profile.question_count} whole
          questions
        </span>
        {data.profile.sections.map((s) => (
          <span key={s.key}>
            Section {s.key}: {data.detected.section_totals[s.key] || 0}/
            {s.marks} marks
          </span>
        ))}
      </div>
      {phase === "scheme" &&
        data.documents
          .filter((d) => d.kind === "answer-key" && d.extraction)
          .map((d) => (
            <details key={d.id} open>
              <summary className="text-sm font-semibold">
                Examiner instructions from the uploaded scheme
              </summary>
              <ul className="max-h-52 list-disc space-y-1 overflow-y-auto pl-5 text-xs">
                {d.extraction!.instructions.map((text, i) => (
                  <li key={i}>{text}</li>
                ))}
              </ul>
              {!d.extraction!.instructions.length && (
                <p className="text-xs text-mute">
                  No general instructions were extracted. Check the source
                  details before verifying.
                </p>
              )}
            </details>
          ))}
      {data.issues.length > 0 && (
        <ul
          className="max-h-64 space-y-2 overflow-y-auto text-sm"
          aria-label="Validation issues"
        >
          {data.issues.map((i, n) => (
            <li key={n} className="border-l-2 border-mark pl-3">
              {i.question && <b>Q{i.question}: </b>}
              {i.message}
              {i.page && (
                <span className="text-xs text-mute"> (page {i.page})</span>
              )}
              {i.expected != null && (
                <span className="block text-xs text-mute">
                  Expected: {JSON.stringify(i.expected)}
                  {i.detected != null
                    ? ` · Detected: ${JSON.stringify(i.detected)}`
                    : ""}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {data.can_edit && (
        <details>
          <summary className="cursor-pointer text-sm font-semibold text-pen">
            Review source details, parts and marking rules
          </summary>
          <p className="my-2 text-xs text-mute">
            Compare with the uploaded PDF. Corrections require a reason and
            fresh verification. A paper with a different board pattern must be
            replaced.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="ghost"
              onClick={() => {
                setReason("");
                setEdit({
                  target: "options",
                  id: examId,
                  options: { ...(data.options || {}) },
                  issues: [],
                });
              }}
            >
              Review paper version
            </Button>
            {data.documents
              .filter((d) => d.status === "READY")
              .map((d) => (
                <Button
                  key={d.id}
                  variant="ghost"
                  onClick={() => {
                    setError(null);
                    setReason("");
                    setEdit({
                      target: d.kind,
                      id: d.id,
                      evidence: structuredClone(
                        d.extraction || {
                          metadata: {},
                          instructions: [],
                          issues: [],
                        },
                      ),
                      issues: [],
                    });
                  }}
                >
                  Review {d.kind === "question-paper" ? "paper" : "scheme"}{" "}
                  details
                </Button>
              ))}
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {(phase === "paper" ? data.questions : data.keys).map((row) => (
              <Button
                key={row.id}
                variant="ghost"
                onClick={() => {
                  setError(null);
                  setReason("");
                  setEdit({
                    target: phase === "paper" ? "question" : "key",
                    id: row.id,
                    root: row.structure?.root,
                    tree: structuredClone(
                      row.structure?.tree ||
                        row.rubric?.cbse_tree || {
                          id: `q${row.display_number || row.raw_question_number}`,
                          kind: "all",
                          label:
                            row.display_number || row.raw_question_number || "",
                          text: "",
                          marks: null,
                          limit: null,
                          audience: null,
                          children: [],
                        },
                    ),
                    issues: row.structure?.issues || row.rubric?.problems || [],
                  });
                }}
              >
                Q{row.display_number || row.raw_question_number} parts
              </Button>
            ))}
          </div>
        </details>
      )}
      {edit && (
        <div className="space-y-3 border-t border-line pt-4">
          <h3 className="font-semibold">Correct source interpretation</h3>
          {edit.target === "question" && (
            <label className="block text-xs">
              Whole-question number
              <Input
                type="number"
                min={1}
                max={data.profile.question_count}
                value={edit.root ?? ""}
                onChange={(e) =>
                  setEdit({
                    ...edit,
                    root: e.target.value ? Number(e.target.value) : undefined,
                  })
                }
              />
            </label>
          )}
          {edit.options && (
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="text-xs">
                Paper version
                <select
                  className="w-full rounded border border-line p-2"
                  value={edit.options.accessibility || "standard"}
                  onChange={(e) =>
                    setEdit({
                      ...edit,
                      options: {
                        ...edit.options,
                        accessibility: e.target.value,
                      },
                    })
                  }
                >
                  <option value="standard">Standard</option>
                  <option value="accessible">Visually impaired</option>
                </select>
              </label>
              {data.profile.code === "055" && (
                <label className="text-xs">
                  Accountancy Part B
                  <select
                    className="w-full rounded border border-line p-2"
                    value={edit.options.accountancy_option || ""}
                    onChange={(e) =>
                      setEdit({
                        ...edit,
                        options: {
                          ...edit.options,
                          accountancy_option: e.target.value,
                        },
                      })
                    }
                  >
                    <option value="">Choose option...</option>
                    <option value="financial">Financial statements</option>
                    <option value="computerised">
                      Computerised accounting
                    </option>
                  </select>
                </label>
              )}
            </div>
          )}
          {edit.evidence && (
            <>
              <div className="grid gap-2 sm:grid-cols-3">
                {[
                  "class_level",
                  "subject_code",
                  "maximum_marks",
                  "duration_minutes",
                  "stated_question_count",
                  "printed_page_count",
                ].map((field) => (
                  <label key={field} className="text-xs">
                    {field.replace(/_/g, " ")}
                    <Input
                      value={edit.evidence!.metadata[field] ?? ""}
                      onChange={(e) => {
                        const value = e.target.value;
                        setEdit({
                          ...edit,
                          evidence: {
                            ...edit.evidence!,
                            metadata: {
                              ...edit.evidence!.metadata,
                              [field]:
                                field === "subject_code"
                                  ? value
                                  : value === ""
                                    ? ""
                                    : Number(value),
                            },
                          },
                        });
                      }}
                    />
                  </label>
                ))}
              </div>
              <label className="block text-xs">
                General instructions (one per line)
                <Textarea
                  rows={5}
                  value={edit.evidence.instructions.join("\n")}
                  onChange={(e) =>
                    setEdit({
                      ...edit,
                      evidence: {
                        ...edit.evidence!,
                        instructions: e.target.value.split("\n"),
                      },
                    })
                  }
                />
              </label>
            </>
          )}
          {edit.tree && (
            <NodeEditor
              node={edit.tree}
              onChange={(tree) => setEdit({ ...edit, tree })}
            />
          )}
          <label className="block text-xs">
            Unresolved extraction issues (remove only after checking the source)
            <Textarea
              value={(edit.evidence?.issues || edit.issues).join("\n")}
              onChange={(e) => {
                const issues = e.target.value.split("\n").filter(Boolean);
                setEdit(
                  edit.evidence
                    ? { ...edit, evidence: { ...edit.evidence, issues } }
                    : { ...edit, issues },
                );
              }}
            />
          </label>
          <label className="block text-xs">
            Reason for correction
            <Input
              required
              minLength={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          {!!actionError && <ErrorPanel error={actionError} />}
          <div className="flex gap-2">
            <Button disabled={busy || reason.trim().length < 3} onClick={save}>
              {busy ? "Saving..." : "Save source correction"}
            </Button>
            <Button variant="ghost" onClick={() => setEdit(null)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
