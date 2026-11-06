import { useEffect, useState } from "react";
import { useExam } from "../ExamWorkspace";
import Overview from "./Overview";
import QuestionPaper from "./QuestionPaper";
import Questions from "./Questions";
import AnswerKey from "./AnswerKey";
import ExamPaperGenerator from "../../components/ExamPaperGenerator";
import ReplaceFileBar from "../../components/ReplaceFileBar";

// a generated paper can replace the exam's paper and key until answer sheets arrive
const GEN_OPEN = ["DRAFT", "QUESTION_PAPER_UPLOADED", "QUESTIONS_EXTRACTED", "QUESTIONS_VERIFIED", "ANSWER_KEY_UPLOADED",
                  "ANSWER_KEY_VERIFIED", "READY_FOR_EVALUATION"];

interface ContentAndKeyProps {
  defaultSubTab?: "overview" | "paper" | "questions" | "key";
}

export default function ContentAndKey({ defaultSubTab }: ContentAndKeyProps) {
  const { exam, reload, inSetup, uploading, setUploading } = useExam();
  const generating = ["QUEUED", "GENERATING"].includes(exam.generation?.status ?? "");

  // Determine initial subtab based on prop or exam progress
  const getInitialTab = (): "overview" | "paper" | "questions" | "key" => {
    if (defaultSubTab) return defaultSubTab;
    if (exam.status === "DRAFT") return "paper";
    if (exam.status === "QUESTIONS_VERIFIED" || exam.status === "ANSWER_KEY_UPLOADED") return "key";
    return "questions";
  };

  const [activeSubTab, setActiveSubTab] = useState<"overview" | "paper" | "questions" | "key">(getInitialTab);

  useEffect(() => {
    if (defaultSubTab) {
      setActiveSubTab(defaultSubTab);
    }
  }, [defaultSubTab]);

  // review both side by side in time: questions and key are read in parallel and finalized together
  const subTabs = [
    {
      id: "questions" as const,
      label: "Questions",
      badge: exam.question_count > 0 ? `${exam.question_count}` : null,
      badgeTone: "ok",
    },
    {
      id: "key" as const,
      label: "Answer key",
      badge: null,
      badgeTone: "ok",
    },
    {
      id: "paper" as const,
      label: "Files",
      badge: generating ? "Generating" : exam.question_paper && exam.answer_key_document ? null : "Missing",
      badgeTone: "warn",
    },
  ];

  return (
    <div className="space-y-5">
      {/* Sub-Navigation Pill Bar */}
      <div className="inline-flex flex-wrap items-center gap-1 rounded-lg bg-sunken p-1">
        {subTabs.map((t) => {
          const isActive = activeSubTab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              aria-pressed={isActive}
              onClick={() => setActiveSubTab(t.id)}
              className={`flex items-center gap-2 rounded-lg px-3.5 py-2 text-xs font-semibold transition-all ${
                isActive
                  ? "bg-surface text-ink shadow-sm"
                  : "text-mute hover:text-ink"
              }`}
            >
              <span>{t.label}</span>
              {t.badge && (
                <span
                  className={`rounded-full px-1.5 py-px text-[10px] font-bold ${
                    isActive
                      ? "bg-pen-soft text-pen"
                      : t.badgeTone === "ok"
                      ? "bg-ok-soft text-ok border border-ok/30"
                      : "bg-warn-soft text-warn border border-warn/30"
                  }`}
                >
                  {t.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Render Active Sub-section */}
      <div>
        {activeSubTab === "overview" && <Overview onSelectSubTab={(tab) => setActiveSubTab(tab)} />}
        {activeSubTab === "paper" && <QuestionPaper onReviewQuestions={() => setActiveSubTab("questions")} onOpenAnswerKey={() => setActiveSubTab("key")} />}
        {activeSubTab === "questions" && (
          <div className="space-y-5">
            {/* AI generation lives with the questions it produces: progress here, then the questions below */}
            {inSetup && <ReplaceFileBar exam={exam} kind="question-paper" uploading={uploading}
                                        setUploading={setUploading} onReload={reload} />}
            <ExamPaperGenerator examId={exam.id} examStatus={exam.status} onAttached={reload}
              hasPaper={!!exam.question_paper}
              locked={!GEN_OPEN.includes(exam.status) || (exam.evaluation_count ?? 0) > 0} />
            {/* remount when a generated paper lands so the list reloads */}
            {!generating && <Questions key={`${exam.status}-${exam.question_count}-${exam.generation?.status ?? ""}`} />}
          </div>
        )}
        {activeSubTab === "key" && (
          <div className="space-y-5">
            {inSetup && <ReplaceFileBar exam={exam} kind="answer-key" uploading={uploading}
                                        setUploading={setUploading} onReload={reload} />}
            <AnswerKey />
          </div>
        )}
      </div>
    </div>
  );
}
