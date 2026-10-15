import { useState } from "react";
import { api } from "../api/client";
import { Button, Field, Input, Modal, Select, Textarea } from "./ui";

interface SaveToVerifiedCollectionProps {
  onClose: () => void;
  onSuccess?: () => void;
  initialData: {
    document_type: "question_paper" | "answer_key" | "student_answer";
    subject: string;
    source_document: string;
    page_number?: number;
    question_number?: string | null;
    normalized_number?: string | null;
    original_ocr: string;
    corrected_text: string;
    approved_marks?: number | null;
    criteria?: string[];
  };
}

export function SaveToVerifiedCollectionModal({ onClose, onSuccess, initialData }: SaveToVerifiedCollectionProps) {
  const [subject, setSubject] = useState(initialData.subject || "General");
  const [docType] = useState(initialData.document_type);
  const [sourceDoc] = useState(initialData.source_document || "Examination Document");
  const [qNum, setQNum] = useState(initialData.question_number || "");
  const [originalOcr] = useState(initialData.original_ocr || "");
  const [correctedText, setCorrectedText] = useState(initialData.corrected_text || "");
  const [errorCategory, setErrorCategory] = useState("word_typo");
  const [structureType, setStructureType] = useState("descriptive");
  const [approvedMarks, setApprovedMarks] = useState(
    initialData.approved_marks != null ? String(initialData.approved_marks) : ""
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const save = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api("/reference-collection", {
        method: "POST",
        json: {
          document_type: docType,
          subject,
          source_document: sourceDoc,
          page_number: initialData.page_number || 1,
          question_number: qNum || null,
          normalized_number: initialData.normalized_number || qNum || null,
          original_ocr: originalOcr,
          corrected_text: correctedText,
          error_category: errorCategory,
          structure_type: structureType,
          approved_marks: approvedMarks ? parseFloat(approvedMarks) : null,
          criteria: initialData.criteria || [],
          verification_status: "APPROVED",
        },
      });
      if (onSuccess) onSuccess();
      onClose();
    } catch (e: any) {
      setErr(e?.message || "Failed to save reference example");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Save to Verified Local Reference Collection"
      wide
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" busy={busy} onClick={save}>
            Approve & Save Reference
          </Button>
        </>
      }
    >
      <div className="space-y-4 text-sm">
        <p className="text-xs text-mute">
          Approved corrections expand the local reference collection. They teach the system recurring layout patterns,
          formula conventions, and error types without invalidating application business rules.
        </p>

        {err && <div className="p-2.5 rounded bg-mark/10 text-mark text-xs">{err}</div>}

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Field label="Subject">
            {(id) => (
              <Input id={id} value={subject} onChange={(e) => setSubject(e.target.value)} />
            )}
          </Field>
          <Field label="Question Number">
            {(id) => (
              <Input id={id} value={qNum} onChange={(e) => setQNum(e.target.value)} />
            )}
          </Field>
          <Field label="Approved Marks">
            {(id) => (
              <Input
                id={id}
                type="number"
                step="0.5"
                value={approvedMarks}
                onChange={(e) => setApprovedMarks(e.target.value)}
              />
            )}
          </Field>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Primary Error Category">
            {(id) => (
              <Select id={id} value={errorCategory} onChange={(e) => setErrorCategory(e.target.value)}>
                <option value="mathematical_symbols">Mathematical Symbols / Powers / Fractions</option>
                <option value="chemical_formula">Chemical Formula / Reaction Arrow</option>
                <option value="table_formatting">Table Formatting / Alignment</option>
                <option value="numbering">Question Numbering / Subquestions</option>
                <option value="word_typo">Word Typo / Misread</option>
                <option value="missing_content">Missing Words or Lines</option>
                <option value="none">None (Clean Ground Truth)</option>
              </Select>
            )}
          </Field>

          <Field label="Structure Type">
            {(id) => (
              <Select id={id} value={structureType} onChange={(e) => setStructureType(e.target.value)}>
                <option value="descriptive">Descriptive Question / Answer</option>
                <option value="formula">Mathematical Formula / Derivation</option>
                <option value="equation">Chemical Equation</option>
                <option value="table">Table / Tabular Grid</option>
                <option value="subquestion">Multi-part Subquestion</option>
                <option value="notice_box">Formatted Notice / Letter Box</option>
                <option value="mcq">Multiple Choice (MCQ)</option>
              </Select>
            )}
          </Field>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Field label="Original Transcription (Preserved)">
            {(id) => (
              <Textarea
                id={id}
                rows={6}
                readOnly
                className="bg-sunken text-xs font-doc text-mute cursor-not-allowed"
                value={originalOcr}
              />
            )}
          </Field>

          <Field label="Teacher-Corrected Text">
            {(id) => (
              <Textarea
                id={id}
                rows={6}
                className="text-xs font-doc bg-surface"
                value={correctedText}
                onChange={(e) => setCorrectedText(e.target.value)}
              />
            )}
          </Field>
        </div>
      </div>
    </Modal>
  );
}
