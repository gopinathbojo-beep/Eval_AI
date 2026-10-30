import { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { SearchableCombobox } from "./SearchableCombobox";

afterEach(cleanup);

it("keeps a subject selected when clicking another field without replaying the closed class selector", () => {
  function Form() {
    const [subject, setSubject] = useState("");
    return <>
      <SearchableCombobox id="class" value="10" options={[{ value: "10", label: "10-A" }]}
        onChange={() => setSubject("")} />
      <SearchableCombobox id="subject" value={subject} options={[{ value: "math", label: "Math" }]}
        onChange={setSubject} />
      <input aria-label="Exam date" />
      <output data-testid="selected-subject">{subject}</output>
    </>;
  }
  render(<Form />);
  fireEvent.focus(document.getElementById("subject")!);
  fireEvent.click(screen.getByRole("option", { name: "Math" }));
  expect(screen.getByTestId("selected-subject").textContent).toBe("math");
  fireEvent.mouseDown(screen.getByLabelText("Exam date"));
  fireEvent.focus(screen.getByLabelText("Exam date"));
  expect(screen.getByTestId("selected-subject").textContent).toBe("math");
  expect((document.getElementById("subject") as HTMLInputElement).value).toBe("Math");
});
