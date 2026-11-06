import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AnswerSheets } from "./Sheets";

const exam = { id: "e1", name: "Model Exam", class_id: "c1", status: "REVIEW_REQUIRED" };
let examStatus = exam.status;
let sheets: unknown[] = [];

vi.mock("../ExamWorkspace", () => ({
  useExam: () => ({ exam: { ...exam, status: examStatus }, reload: async () => {} }),
}));

vi.mock("../../api/client", () => {
  class ApiError extends Error {}
  return {
    ApiError,
    downloadFile: vi.fn(),
    fetchBlobUrl: vi.fn(),
    api: vi.fn(async (path: string) => {
      if (path.endsWith("/answer-sheets")) return sheets;
      if (path.endsWith("/unassigned")) return [];
      if (path.endsWith("/review-summary")) return { processing: 0, ready: [], needs_review: [], finalized: 0, unassigned: 0 };
      if (path.endsWith("/question-summary")) {
        return { finalized_students: 1, questions: [{ no: "1", max: 5, average: 4, percentage: 80, full: 1, zero: 0 }] };
      }
      return [];
    }),
  };
});

const sheet = (id: string, roll: string, status: string, extra: object = {}) => ({
  id,
  status,
  run_status: "DONE",
  student: { id: `s${id}`, name: `Student ${roll}`, roll_number: roll },
  document: { id: `d${id}`, status: "READY", pages: [{}, {}], roll_check: null },
  detected_answers: 3,
  unresolved_answers: 0,
  total_marks: null,
  maximum_marks: null,
  percentage: null,
  ...extra,
});

const show = async () => {
  render(<MemoryRouter><AnswerSheets /></MemoryRouter>);
  await screen.findByText(/students finalized|No answer sheets uploaded/);
};

afterEach(() => {
  cleanup();
  examStatus = exam.status;
});

it("keeps every sheet, evaluation and result feature on one table", async () => {
  sheets = [
    sheet("1", "101", "FINALIZED", { total_marks: 64, maximum_marks: 80, percentage: 80 }),
    sheet("2", "102", "REVIEW_REQUIRED", {
      unresolved_answers: 1,
      document: { id: "d2", status: "READY", pages: [{}], roll_check: { status: "MISMATCH", typed: "102", written: "120" } },
    }),
  ];
  await show();

  expect(screen.getByText("1 of 2 students finalized")).toBeTruthy();
  expect(screen.getByRole("button", { name: /Re-map & evaluate all/ })).toBeTruthy();
  expect(screen.getByRole("button", { name: /Download All Student Reports/ })).toBeTruthy();
  expect(screen.getByRole("button", { name: /Download Exam Report/ })).toBeTruthy();
  expect((screen.getByRole("button", { name: /Finalize the Whole Exam/ }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByText("Question-wise analysis")).toBeTruthy();

  const final = within(screen.getByText("101").closest("tr")!);
  expect(final.getByText("64 / 80")).toBeTruthy();
  expect(final.getByText("80%")).toBeTruthy();
  expect(final.getByText("101").getAttribute("href")).toBe("/results/1");
  expect(final.getByRole("link", { name: /View Report/ }).getAttribute("href")).toBe("/results/1");
  expect(final.getByRole("link", { name: /Open Review/ }).getAttribute("href")).toBe("/evaluations/1");
  expect(final.getByRole("button", { name: /Sheet Report/ })).toBeTruthy();
  expect(final.getByRole("button", { name: /Delete/ })).toBeTruthy();
  expect(final.queryByRole("button", { name: /Re-map/ })).toBeNull();

  const open = within(screen.getByRole("link", { name: "102" }).closest("tr")!);
  expect(open.getByText("1 to map")).toBeTruthy();
  expect(open.getByRole("link", { name: "102" }).getAttribute("href")).toBe("/evaluations/2");
  expect(screen.getByRole("button", { name: "Keep 102" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Use 120" })).toBeTruthy();
  expect(open.getByRole("button", { name: /Re-map & evaluate/ })).toBeTruthy();
  expect(open.queryByRole("link", { name: /View Report/ })).toBeNull();
});

it("allows finalizing the exam only when every student is finalized", async () => {
  sheets = [sheet("1", "101", "FINALIZED", { total_marks: 64, maximum_marks: 80, percentage: 80 })];
  await show();
  expect((screen.getByRole("button", { name: /Finalize the Whole Exam/ }) as HTMLButtonElement).disabled).toBe(false);
});

it("leaves only the downloads and the student rows on a finalized exam", async () => {
  examStatus = "FINALIZED";
  sheets = [sheet("1", "101", "FINALIZED", { total_marks: 64, maximum_marks: 80, percentage: 80 })];
  await show();
  expect(screen.queryByRole("button", { name: /Finalize the Whole Exam/ })).toBeNull();
  expect(screen.queryByRole("button", { name: /Re-map & evaluate all/ })).toBeNull();
  expect(screen.queryByText(/can be uploaded once/)).toBeNull();
  expect(screen.getByRole("button", { name: /Download Exam Report/ })).toBeTruthy();
});

it("says so when no sheet has been uploaded", async () => {
  sheets = [];
  await show();
  expect(screen.getByText("No answer sheets uploaded")).toBeTruthy();
  expect(screen.queryByRole("button", { name: /Download Exam Report/ })).toBeNull();
});
