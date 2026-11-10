import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import UploadSheets from "./UploadSheets";
import { api } from "../../api/client";

let examStatus = "READY_FOR_EVALUATION";
const reload = vi.fn(async () => {});

vi.mock("../ExamWorkspace", () => ({
  useExam: () => ({ exam: { id: "e1", status: examStatus }, reload }),
}));

vi.mock("../../api/client", () => {
  class ApiError extends Error {
    issues = [];
    constructor(public status: number, public code: string, message: string) {
      super(message);
    }
  }
  return { ApiError, api: vi.fn(async () => ({})) };
});

const send = vi.mocked(api);
const file = (name: string) => new File(["x"], name);
const show = () => render(<MemoryRouter><UploadSheets /></MemoryRouter>);
const choose = (...files: File[]) =>
  fireEvent.change(screen.getByLabelText("Choose answer sheets"), { target: { files } });
const formOf = (call: number) => (send.mock.calls[call]![1] as { form: FormData }).form;

beforeEach(() => {
  examStatus = "READY_FOR_EVALUATION";
  send.mockReset();
  send.mockResolvedValue({});
});
afterEach(cleanup);

it("sends one sheet per PDF, with the typed roll or none", async () => {
  show();
  choose(file("a.pdf"), file("b.pdf"));
  fireEvent.change(screen.getByLabelText("Roll number for a.pdf"), { target: { value: "10c04" } });
  fireEvent.click(screen.getByRole("button", { name: /Upload 2 sheets/ }));

  await screen.findByText(/2 sent/);
  expect(send.mock.calls.map((c) => c[0])).toEqual(["/exams/e1/answer-sheets", "/exams/e1/answer-sheets"]);
  expect(formOf(0).get("roll_number")).toBe("10C04");
  expect(formOf(1).get("roll_number")).toBeNull();
  expect((formOf(1).get("file") as File).name).toBe("b.pdf");
  expect(reload).toHaveBeenCalled();
});

it("treats photos as the pages of one student, in page order", async () => {
  show();
  choose(file("p10.jpg"), file("p2.jpg"));
  choose(file("p3.jpg"));
  screen.getByText("3 photos of one student");
  fireEvent.click(screen.getByRole("button", { name: /Upload 1 sheet/ }));

  await screen.findByText(/1 sent/);
  expect(send.mock.calls[0]![0]).toBe("/exams/e1/answer-sheets/photos");
  expect(formOf(0).getAll("files").map((f) => (f as File).name)).toEqual(["p2.jpg", "p3.jpg", "p10.jpg"]);
});

it("keeps a failed sheet to send again, and does not resend the others", async () => {
  send.mockRejectedValueOnce(new Error("Roll 5 already has an answer sheet"));
  show();
  choose(file("a.pdf"), file("b.pdf"));
  fireEvent.click(screen.getByRole("button", { name: /Upload 2 sheets/ }));

  await screen.findByText("Roll 5 already has an answer sheet");
  await waitFor(() => expect(send).toHaveBeenCalledTimes(2));
  fireEvent.click(await screen.findByRole("button", { name: /Upload 1 sheet/ }));
  await screen.findByText(/2 sent/);
  expect(send).toHaveBeenCalledTimes(3);
  expect((formOf(2).get("file") as File).name).toBe("a.pdf");
});

it("stops the same roll number going on two sheets", () => {
  show();
  choose(file("a.pdf"), file("b.pdf"));
  fireEvent.change(screen.getByLabelText("Roll number for a.pdf"), { target: { value: "7" } });
  fireEvent.change(screen.getByLabelText("Roll number for b.pdf"), { target: { value: "7" } });
  fireEvent.click(screen.getByRole("button", { name: /Upload 2 sheets/ }));
  screen.getByText(/Roll number 7 is listed twice/);
  expect(send).not.toHaveBeenCalled();
});

it("skips file types it cannot read", () => {
  show();
  choose(file("a.pdf"), file("notes.txt"));
  screen.getByText(/1 file was skipped/);
  screen.getByText("a.pdf");
  expect(screen.queryByText("notes.txt")).toBeNull();
});

it("takes no sheets once the exam is finalized", () => {
  examStatus = "FINALIZED";
  show();
  screen.getByText(/no longer takes answer sheets/);
  expect(screen.queryByLabelText("Choose answer sheets")).toBeNull();
});

it("bulk upload sends PDF and Word files at once, no photos and no roll number to enter", async () => {
  send.mockResolvedValue({ uploaded: 2 });
  show();
  fireEvent.change(screen.getByLabelText("Bulk upload answer sheets"), {
    target: { files: [file("a.pdf"), file("b.jpg"), file("c.docx"), file("notes.txt")] },
  });
  await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
  expect(send.mock.calls[0]![0]).toBe("/exams/e1/answer-sheets/bulk");
  const form = formOf(0);
  expect((form.getAll("files") as File[]).map((f) => f.name)).toEqual(["a.pdf", "c.docx"]);
  expect(form.has("roll_number")).toBe(false);
  expect(screen.queryByPlaceholderText("Roll no. (optional)")).toBeNull(); // no roll boxes were shown
  await screen.findByText(/2 sheets uploaded.*2 files were skipped/);
  expect(reload).toHaveBeenCalled();
});
