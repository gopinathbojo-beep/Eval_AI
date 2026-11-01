import { expect, test } from "@playwright/test";

test("management selects exact board variant and subject persists after leaving the field", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Email address").fill("browser@example.test");
  await page.getByLabel("Password", { exact: true }).fill("test-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  const cls = await page.request.post("/api/classes", {
    headers: { "X-Requested-With": "EvalAI" },
    data: { name: "10-C" },
  });
  expect(cls.ok()).toBeTruthy();
  await page.goto("/exams/new");
  await page.getByLabel("Exam Name").fill("Board Mathematics");
  await page.getByRole("combobox", { name: /^Class/ }).click();
  await page.getByRole("option", { name: /10-C/ }).click();
  await page.getByRole("combobox", { name: /^Subject/ }).click();
  await page.getByRole("option", { name: /Mathematics Standard/ }).click();
  await expect(page.getByLabel("Duration (minutes)")).toHaveValue("180");
  await expect(page.getByLabel("Total Maximum Marks")).toHaveValue("80");
  await expect(page.getByLabel("Total Maximum Marks")).toHaveAttribute(
    "readonly",
    "",
  );
  await page.getByLabel("Exam Date").fill("2026-12-10");
  await expect(page.getByRole("combobox", { name: /^Subject/ })).toHaveValue(
    "Mathematics Standard",
  );
  await page.getByRole("button", { name: "Create Exam & Continue" }).click();
  await expect(page).toHaveURL(/\/exams\/[0-9a-f-]{36}$/);
  const id = page.url().split("/").pop();
  const response = await page.request.get(`/api/exams/${id}`);
  expect(response.ok()).toBeTruthy();
  expect((await response.json()).standard_profile_id).toBe("cbse-10-041");
  await page
    .getByRole("button", { name: "Questions", exact: false })
    .first()
    .click();
  await expect(
    page.getByRole("region", { name: "CBSE validation" }),
  ).toBeVisible();
  await expect(
    page.getByText("Review these findings before evaluation; accepted questions can continue to the answer key."),
  ).toBeVisible();
  await expect(
    page.getByText("Whole questions are missing from the extracted paper."),
  ).toBeVisible();
  await page.screenshot({
    path: test.info().outputPath("cbse-validation.png"),
    fullPage: true,
  });
});
