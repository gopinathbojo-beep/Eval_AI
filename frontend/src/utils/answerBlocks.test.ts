import { describe, expect, it } from "vitest";
import type { StudentAnswer } from "../types";
import { groupAnswerBlocks } from "./answerBlocks";

describe("marks answer evidence", () => {
  it("retains every page in source order and excludes ignored and unmapped blocks", () => {
    const block = (id: string, position: number, question = "q", status = "MAPPED") =>
      ({ id, position, exam_question_id: question, status } as StudentAnswer);
    const input = [block("later", 3), block("first", 1), block("ignored", 2, "q", "IGNORED"), block("unmapped", 4, "")];
    expect(groupAnswerBlocks(input).get("q")?.map(a => a.id)).toEqual(["first", "later"]);
    expect(input[0].id).toBe("later");
  });
});
