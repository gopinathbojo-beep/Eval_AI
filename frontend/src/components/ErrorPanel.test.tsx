import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ApiError } from "../api/client";
import { ErrorPanel } from "./ui";

afterEach(cleanup);

it("shows structured CBSE messages as well as legacy reasons", () => {
  render(<ErrorPanel error={new ApiError(409, "CBSE_NOT_READY", "Resolve validation issues.", [
    { question: "29", message: "Missing positive subpart allocation.", page: 5 },
    { question: null, message: "Section choices differ from the pattern." },
    { question: "34", reason: "Legacy question error." },
  ])} />);
  expect(screen.getByText("Q29")).toBeTruthy();
  expect(screen.getByText("Missing positive subpart allocation. (page 5)")).toBeTruthy();
  expect(screen.getByText("Section choices differ from the pattern.")).toBeTruthy();
  expect(screen.getByText("Legacy question error.")).toBeTruthy();
});
