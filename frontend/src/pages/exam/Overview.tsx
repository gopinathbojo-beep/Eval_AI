import { Link } from "react-router-dom";
import { useApi } from "../../hooks/useApi";
import type { AuditRow } from "../../types";
import { date, label } from "../../utils/format";
import { Card, Stat } from "../../components/ui";
import { useExam } from "../ExamWorkspace";

const NEXT: Record<string, [string, string, string]> = {
  DRAFT: ["Upload the question paper", "question-paper", "The model reads each page and proposes the questions."],
  QUESTION_PAPER_UPLOADED: ["Wait for the paper to be read", "question-paper", "Or fix any failed pages."],
  QUESTIONS_EXTRACTED: ["Review and verify the questions", "questions", "Check each question against the page image."],
  QUESTIONS_VERIFIED: ["Upload the answer key", "answer-key", ""],
  ANSWER_KEY_UPLOADED: ["Review and verify the answer key", "answer-key", "Every question needs exactly one answer."],
  ANSWER_KEY_VERIFIED: ["Upload student answer sheets", "answer-sheets", ""],
  READY_FOR_EVALUATION: ["Review mapping and run evaluation", "evaluation", ""],
  EVALUATING: ["Evaluation is running", "evaluation", ""],
  REVIEW_REQUIRED: ["Review marks and finalize each student", "evaluation", ""],
  FINALIZED: ["All results are final", "results", ""],
};

export default function Overview() {
  const { exam } = useExam();
  const audit = useApi<AuditRow[]>(`/exams/${exam.id}/audit-logs`);
  const [title, to, hint] = NEXT[exam.status];
  return (
    <div className="space-y-6">
      <Card className="flex flex-wrap items-center justify-between gap-3 p-5">
        <div><p className="text-sm text-mute">Next step</p><p className="text-lg font-semibold">{title}</p>{hint && <p className="text-sm text-mute">{hint}</p>}</div>
        <Link to={to} className="rounded-md bg-pen px-4 py-2 text-sm font-medium text-surface">Go there</Link>
      </Card>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Questions" value={exam.question_count} />
        <Stat label="Verified questions" value={`${exam.verified_question_count}/${exam.question_count}`} />
        <Stat label="Answer sheets" value={exam.evaluation_count} />
        <Stat label="Finalized" value={`${exam.finalized_count}/${exam.evaluation_count}`} />
      </div>
      {exam.instructions && <Card className="p-4"><p className="mb-1 text-sm font-medium">Instructions</p><p className="doc-text text-sm">{exam.instructions}</p></Card>}
      <section>
        <h2 className="mb-2 font-semibold">Audit log</h2>
        {audit.data?.length ? (
          <Card className="max-h-80 overflow-auto"><table className="w-full text-sm"><thead className="sticky top-0 bg-surface text-left text-mute"><tr><th className="px-3 py-2 font-medium">When</th><th className="px-3 py-2 font-medium">Who</th><th className="px-3 py-2 font-medium">What</th><th className="px-3 py-2 font-medium">Change</th></tr></thead>
            <tbody className="divide-y divide-line">{audit.data.map((a) => (
              <tr key={a.id} className="align-top"><td className="whitespace-nowrap px-3 py-2 text-mute">{date(a.created_at)}</td><td className="px-3 py-2">{a.user ?? "–"}</td>
                <td className="px-3 py-2">{label(a.action)}</td>
                <td className="px-3 py-2 text-xs text-mute">{a.old_value != null && <span>{JSON.stringify(a.old_value).slice(0, 80)} → </span>}{a.new_value != null && JSON.stringify(a.new_value).slice(0, 80)}{a.reason && <em className="block">Reason: {a.reason}</em>}</td></tr>))}</tbody></table></Card>
        ) : <p className="text-sm text-mute">No changes recorded yet.</p>}
      </section>
    </div>
  );
}
