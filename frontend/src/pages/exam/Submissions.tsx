import { useState } from "react";
import { ExamStudents, AnswerSheets } from "./Sheets";
import { useExam } from "../ExamWorkspace";
import { useApi } from "../../hooks/useApi";
import type { Evaluation, Student } from "../../types";

interface SubmissionsProps {
  defaultSubTab?: "sheets" | "roster";
}

export default function Submissions({ defaultSubTab = "sheets" }: SubmissionsProps) {
  const { exam } = useExam();
  const [activeTab, setActiveTab] = useState<"sheets" | "roster">(defaultSubTab);

  const students = useApi<Student[]>(`/students?class_id=${exam.class_id}`);
  const sheets = useApi<Evaluation[]>(`/exams/${exam.id}/answer-sheets`);

  const totalStudents = students.data?.length ?? 0;
  const totalSheets = sheets.data?.length ?? 0;

  return (
    <div className="space-y-5">
      {/* Sub-navigation & Metrics Bar */}
      <div className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-2 sm:flex-row sm:items-center sm:justify-between shadow-xs">
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            aria-pressed={activeTab === "sheets"}
            onClick={() => setActiveTab("sheets")}
            className={`flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-semibold transition-all ${
              activeTab === "sheets"
                ? "bg-pen text-white shadow-xs"
                : "text-ink/80 hover:bg-hover hover:text-brown"
            }`}
          >
            <span>Student Answer Sheets</span>
            <span
              className={`rounded-full px-2 py-px text-[10px] font-bold ${
                activeTab === "sheets"
                  ? "bg-white/20 text-white"
                  : "bg-line/60 text-mute"
              }`}
            >
              {totalSheets}
            </span>
          </button>

          <button
            type="button"
            aria-pressed={activeTab === "roster"}
            onClick={() => setActiveTab("roster")}
            className={`flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-semibold transition-all ${
              activeTab === "roster"
                ? "bg-pen text-white shadow-xs"
                : "text-ink/80 hover:bg-hover hover:text-brown"
            }`}
          >
            <span>Class Students</span>
            <span
              className={`rounded-full px-2 py-px text-[10px] font-bold ${
                activeTab === "roster"
                  ? "bg-white/20 text-white"
                  : "bg-line/60 text-mute"
              }`}
            >
              {totalStudents}
            </span>
          </button>
        </div>

        <div className="flex items-center gap-3 px-2 text-xs text-mute">
          <span>Enrolled: <strong className="text-ink">{totalStudents}</strong></span>
          <span>•</span>
          <span>Submitted: <strong className="text-ok">{totalSheets}</strong></span>
          {totalStudents > totalSheets && (
            <>
              <span>•</span>
              <span>Pending: <strong className="text-warn">{totalStudents - totalSheets}</strong></span>
            </>
          )}
        </div>
      </div>

      {/* Render active subtab */}
      <div>
        {activeTab === "sheets" ? <AnswerSheets /> : <ExamStudents />}
      </div>
    </div>
  );
}
