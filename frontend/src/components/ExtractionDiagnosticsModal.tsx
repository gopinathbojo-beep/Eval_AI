import { useState, useEffect } from "react";
import { api } from "../api/client";
import { Badge, Button, Card, Loading, Modal } from "./ui";

interface DiagnosticsData {
  status: string;
  model: string;
  diagnostics: {
    sample_size: number;
    overall_cer: number;
    overall_wer: number;
    overall_accuracy_pct: number;
    question_number_accuracy_pct: number;
    marks_accuracy_pct: number;
    by_subject: Record<string, { samples: number; cer: number; wer: number; accuracy_pct: number }>;
    by_error_category: Record<string, number>;
  };
  hardware_constraint_note: string;
}

interface ReferenceExample {
  id: string;
  subject: string;
  document_type: string;
  source_document: string;
  page_number: number;
  question_number: string | null;
  original_ocr: string;
  corrected_text: string;
  error_category: string;
  structure_type: string;
  approved_marks: number | null;
  cer: number;
  wer: number;
  accuracy_pct: number;
}

export function ExtractionDiagnosticsModal({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<DiagnosticsData | null>(null);
  const [examples, setExamples] = useState<ReferenceExample[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterSubject, setFilterSubject] = useState<string>("ALL");
  const [selectedEx, setSelectedEx] = useState<ReferenceExample | null>(null);

  useEffect(() => {
    Promise.all([
      api<DiagnosticsData>("/reference-collection/diagnostics"),
      api<{ examples: ReferenceExample[] }>("/reference-collection"),
    ])
      .then(([diag, exRes]) => {
        setData(diag);
        setExamples(exRes.examples || []);
      })
      .catch((e) => console.error(e))
      .finally(() => setLoading(false));
  }, []);

  return (
    <Modal title="OCR & Extraction Diagnostics (Verified Reference Benchmarks)" wide onClose={onClose}
      footer={<Button variant="primary" onClick={onClose}>Close</Button>}>
      {loading ? (
        <Loading />
      ) : !data ? (
        <p className="text-sm text-mute">Diagnostics could not be loaded.</p>
      ) : (
        <div className="space-y-5 text-sm">
          {/* Hardware & Model Note */}
          <div className="rounded-lg border border-accent/30 bg-accent/10 p-3.5 text-xs text-ink/90 leading-relaxed">
            <div className="flex items-center gap-2 mb-1.5 font-semibold text-pen text-[13px]">
              <span>Mandatory Model: {data.model}</span>
              <Badge tone="pen">Ollama Integration</Badge>
            </div>
            <p>{data.hardware_constraint_note}</p>
          </div>

          {/* Key Accuracy Metrics Cards */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            <Card className="p-3 text-center bg-surface">
              <span className="block text-xs text-mute font-medium">Text Accuracy</span>
              <span className="text-2xl font-bold text-ok">{data.diagnostics.overall_accuracy_pct}%</span>
              <span className="block text-[11px] text-mute mt-0.5">(1 - CER)</span>
            </Card>
            <Card className="p-3 text-center bg-surface">
              <span className="block text-xs text-mute font-medium">Char Error Rate (CER)</span>
              <span className="text-2xl font-bold text-pen">{data.diagnostics.overall_cer}</span>
              <span className="block text-[11px] text-mute mt-0.5">Levenshtein / len</span>
            </Card>
            <Card className="p-3 text-center bg-surface">
              <span className="block text-xs text-mute font-medium">Word Error Rate (WER)</span>
              <span className="text-2xl font-bold text-pen">{data.diagnostics.overall_wer}</span>
              <span className="block text-[11px] text-mute mt-0.5">Word edit dist</span>
            </Card>
            <Card className="p-3 text-center bg-surface">
              <span className="block text-xs text-mute font-medium">Q-Number Accuracy</span>
              <span className="text-2xl font-bold text-ok">{data.diagnostics.question_number_accuracy_pct}%</span>
              <span className="block text-[11px] text-mute mt-0.5">Normalized label match</span>
            </Card>
            <Card className="p-3 text-center bg-surface">
              <span className="block text-xs text-mute font-medium">Marks Accuracy</span>
              <span className="text-2xl font-bold text-ok">{data.diagnostics.marks_accuracy_pct}%</span>
              <span className="block text-[11px] text-mute mt-0.5">Scheme match</span>
            </Card>
          </div>

          {/* Breakdown by Subject */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-mute mb-2">Subject-Level Breakdown (Sample Size: {data.diagnostics.sample_size} verified items)</h4>
            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
              {Object.entries(data.diagnostics.by_subject).map(([subj, stats]) => (
                <div key={subj} className="rounded-lg border border-line bg-surface p-3">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="font-semibold text-ink">{subj}</span>
                    <Badge tone="mute">{stats.samples} items</Badge>
                  </div>
                  <div className="space-y-1 text-xs">
                    <div className="flex justify-between">
                      <span className="text-mute">Accuracy:</span>
                      <span className="font-medium text-ok">{stats.accuracy_pct}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-mute">CER:</span>
                      <span className="font-medium">{stats.cer}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-mute">WER:</span>
                      <span className="font-medium">{stats.wer}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Error Category Tally */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-mute mb-2">Error Categories Identified in Teacher Review</h4>
            <div className="flex flex-wrap gap-2">
              {Object.entries(data.diagnostics.by_error_category).map(([cat, cnt]) => (
                <Badge key={cat} tone={cat === "none" ? "ok" : "pen"}>
                  {cat.replace(/_/g, " ")}: <b>{cnt}</b>
                </Badge>
              ))}
            </div>
          </div>

          {/* Reference Collection Inspection & Compare */}
          <div className="pt-2 border-t border-line">
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-mute">Verified Reference Exemplars ({examples.length})</h4>
              <div className="flex gap-1.5">
                {["ALL", "Chemistry", "English", "Mathematics"].map((s) => (
                  <button
                    key={s}
                    className={`px-2 py-0.5 rounded text-xs transition ${filterSubject === s ? "bg-pen text-white font-medium" : "bg-sunken text-mute hover:text-ink"}`}
                    onClick={() => setFilterSubject(s)}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>

            <div className="max-h-60 overflow-y-auto space-y-2 pr-1">
              {examples
                .filter((ex) => filterSubject === "ALL" || ex.subject.toLowerCase() === filterSubject.toLowerCase())
                .map((ex) => (
                  <div
                    key={ex.id}
                    className={`p-2.5 rounded-lg border text-xs cursor-pointer transition ${selectedEx?.id === ex.id ? "border-pen bg-pen/5" : "border-line bg-surface hover:bg-sunken/40"}`}
                    onClick={() => setSelectedEx(selectedEx?.id === ex.id ? null : ex)}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold text-ink">
                        {ex.subject} · {ex.question_number || `P${ex.page_number}`} ({ex.structure_type})
                      </span>
                      <div className="flex items-center gap-1.5">
                        <Badge tone={ex.error_category === "none" ? "ok" : "warn"}>{ex.error_category.replace(/_/g, " ")}</Badge>
                        <Badge tone="mute">Acc: {ex.accuracy_pct}%</Badge>
                      </div>
                    </div>

                    {selectedEx?.id === ex.id && (
                      <div className="mt-3 pt-2.5 border-t border-line grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                        <div className="rounded bg-sunken p-2.5">
                          <span className="block font-semibold text-mute mb-1">Original Model OCR:</span>
                          <pre className="whitespace-pre-wrap font-doc text-ink text-[11px] leading-relaxed max-h-40 overflow-y-auto">{ex.original_ocr || "(empty)"}</pre>
                        </div>
                        <div className="rounded bg-ok-soft/30 p-2.5 border border-ok/30">
                          <span className="block font-semibold text-ok mb-1">Teacher-Verified Ground Truth:</span>
                          <pre className="whitespace-pre-wrap font-doc text-ink text-[11px] leading-relaxed max-h-40 overflow-y-auto">{ex.corrected_text}</pre>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}
