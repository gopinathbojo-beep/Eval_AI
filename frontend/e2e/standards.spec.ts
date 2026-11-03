import { expect, test } from "@playwright/test";

test("create exam: class, typed section and joined subject in one form", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email address").fill("browser@example.test");
  await page.getByLabel("Password", { exact: true }).fill("Test-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.goto("/exams/new");
  await page.getByLabel("Exam name").fill("Board Mathematics");
  await page.getByLabel("Class").selectOption("10");
  await page.getByLabel("Section").fill("c");
  await expect(page.getByLabel("Section")).toHaveValue("C");
  // textbook subjects: Hindi Course A and B are one "Hindi"; Tamil is built in
  const subjects = await page.getByLabel("Subject").locator("option").allTextContents();
  expect(subjects).toEqual(expect.arrayContaining(["Hindi", "Mathematics", "Tamil"]));
  expect(subjects).not.toContain("Hindi Course A");
  await page.getByLabel("Subject").selectOption({ label: "Mathematics" });
  // both files are required before the exam can be created
  await expect(page.getByRole("button", { name: "Create exam" })).toBeDisabled();
  const created = await page.request.post("/api/exams/simple", {
    headers: { "X-Requested-With": "EvalAI" },
    data: { name: "Board Mathematics", grade: "10", section: "C", subject_key: "10-mathematics" },
  });
  expect(created.ok()).toBeTruthy();
  expect((await created.json()).standard_profile_id).toBe("cbse-10-041");
});
