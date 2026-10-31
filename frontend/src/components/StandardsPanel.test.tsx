import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { StandardsPanel } from "./StandardsPanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows source issues and saves reviewed allocations only with a reason", async () => {
  const data = {
    legacy: false,
    valid: false,
    profile: {
      name: "Computer Applications",
      code: "165",
      version: "2026-27.1",
      question_count: 26,
      sections: [{ key: "A", marks: 12 }],
    },
    can_edit: true,
    issues: [
      {
        code: "QUESTION_TOTAL",
        message: "Choice-aware marks disagree",
        page: 2,
      },
    ],
    documents: [],
    detected: { question_count: 26, section_totals: { A: 12 } },
    keys: [],
    questions: [
      {
        id: "q",
        display_number: "1",
        structure: {
          root: 1,
          issues: [],
          tree: {
            id: "q1",
            kind: "point",
            label: "1",
            text: "Expected source",
            marks: 1,
            limit: null,
            audience: null,
            children: [],
          },
        },
      },
    ],
  };
  const fetcher = vi
    .fn()
    .mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify(data))),
    );
  vi.stubGlobal("fetch", fetcher);
  const changed = vi.fn();
  render(<StandardsPanel examId="exam" phase="paper" onChanged={changed} />);
  expect(await screen.findByText("Choice-aware marks disagree")).toBeTruthy();
  fireEvent.click(
    screen.getByText("Review source details, parts and marking rules"),
  );
  fireEvent.click(screen.getByRole("button", { name: "Q1 parts" }));
  expect(
    (
      screen.getByRole("button", {
        name: "Save source correction",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  fireEvent.change(screen.getByLabelText("Reason for correction"), {
    target: { value: "Checked against page 2" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Save source correction" }),
  );
  await waitFor(() => expect(changed).toHaveBeenCalledOnce());
  const post = fetcher.mock.calls.find((call) => call[1]?.method === "POST");
  expect(JSON.parse(post![1].body)).toMatchObject({
    target: "question",
    id: "q",
    root: 1,
    reason: "Checked against page 2",
  });
});
