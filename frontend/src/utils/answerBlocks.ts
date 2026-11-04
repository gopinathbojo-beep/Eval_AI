import type { StudentAnswer } from "../types";

export function groupAnswerBlocks(answers: StudentAnswer[]): Map<string, StudentAnswer[]> {
  const grouped = new Map<string, StudentAnswer[]>();
  for (const answer of [...answers].sort((a, b) => (a.position ?? 0) - (b.position ?? 0))) {
    if (!answer.exam_question_id || answer.status === "IGNORED") continue;
    const blocks = grouped.get(answer.exam_question_id) ?? [];
    blocks.push(answer);
    grouped.set(answer.exam_question_id, blocks);
  }
  return grouped;
}
