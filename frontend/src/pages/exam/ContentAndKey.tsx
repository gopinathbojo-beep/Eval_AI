import { useEffect, useState } from "react";
import { useExam } from "../ExamWorkspace";
import Overview from "./Overview";
import QuestionPaper from "./QuestionPaper";
import Questions from "./Questions";
import AnswerKey from "./AnswerKey";

interface ContentAndKeyProps {
  defaultSubTab?: "overview" | "paper" | "questions" | "key";
}

export default function ContentAndKey({ defaultSubTab }: ContentAndKeyProps) {
  const { exam } = useExam();

  // Determine initial subtab based on prop or exam progress
  const getInitialTab = (): "overview" | "paper" | "questions" | "key" => {
    if (defaultSubTab) return defaultSubTab;
    if (exam.status === "DRAFT") return "paper";
    if (exam.status === "QUESTION_PAPER_UPLOADED" || exam.status === "QUESTIONS_EXTRACTED") return "questions";
    if (exam.status === "QUESTIONS_VERIFIED" || exam.status === "ANSWER_KEY_UPLOADED") return "key";
    return "overview";
  };

  const [activeSubTab, setActiveSubTab] = useState<"overview" | "paper" | "questions" | "key">(getInitialTab);

  useEffect(() => {
    if (defaultSubTab) {
      setActiveSubTab(defaultSubTab);
    }
  }, [defaultSubTab]);

  const subTabs = [
    {
      id: "overview" as const,
      label: "Overview",
      badge: null,
    },
    {
      id: "paper" as const,
      label: "Paper & Key",
      badge: exam.question_paper && exam.answer_key_document ? "Uploaded" : exam.question_paper || exam.answer_key_document ? "1 of 2" : "Missing",
      badgeTone: exam.question_paper && exam.answer_key_document ? "ok" : "warn",
    },
    {
      id: "questions" as const,
      label: "Questions",
      badge: exam.question_count > 0 ? `${exam.verified_question_count}/${exam.question_count}` : null,
      badgeTone: exam.verified_question_count === exam.question_count && exam.question_count > 0 ? "ok" : "pen",
    },
    {
      id: "key" as const,
      label: "Answer Key",
      badge: exam.status !== "DRAFT" && exam.status !== "QUESTION_PAPER_UPLOADED" && exam.status !== "QUESTIONS_EXTRACTED" ? "Configured" : null,
      badgeTone: "ok",
    },
  ];

  return (
    <div className="space-y-5">
      {/* Sub-Navigation Pill Bar */}
      <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-line bg-surface p-1.5 shadow-xs">
        {subTabs.map((t) => {
          const isActive = activeSubTab === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setActiveSubTab(t.id)}
              className={`flex items-center gap-2 rounded-lg px-3.5 py-2 text-xs font-semibold transition-all ${
                isActive
                  ? "bg-pen text-white shadow-xs"
                  : "text-ink/80 hover:bg-hover hover:text-brown"
              }`}
            >
              <span>{t.label}</span>
              {t.badge && (
                <span
                  className={`rounded-full px-1.5 py-0.2 text-[10px] font-bold ${
                    isActive
                      ? "bg-white/20 text-white"
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
        {activeSubTab === "questions" && <Questions />}
        {activeSubTab === "key" && <AnswerKey />}
      </div>
    </div>
  );
}
