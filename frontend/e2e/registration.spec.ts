import { expect, test } from "@playwright/test";

test("school registers without approval and provisions a teacher", async ({
  page,
  browser,
}) => {
  await page.goto("/register");
  await page.getByLabel("Full name", { exact: true }).fill("School Manager");
  await page.getByLabel("Email address").fill("school-browser@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("school-password-123");
  await page
    .getByLabel("Confirm password", { exact: true })
    .fill("school-password-123");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(page).toHaveURL(/\/onboarding$/);
  await page
    .getByLabel("Contact name", { exact: false })
    .fill("School Manager");
  await page.getByLabel("Contact number").fill("9876543210");
  await page.getByLabel("School name", { exact: true }).fill("New CBSE School");
  await page.getByLabel("School address").fill("School Road");
  await page.getByLabel("City", { exact: true }).fill("Chennai");
  await page.getByLabel("State", { exact: true }).fill("Tamil Nadu");
  await page.getByLabel("Postcode").fill("600001");
  await page.getByRole("button", { name: "Open my workspace" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  const c = await page.request.post("/api/classes", {
    headers: { "X-Requested-With": "EvalAI" },
    data: { std: "10", section: "A" },
  });
  expect(c.status()).toBe(201);
  const s = await page.request.post("/api/subjects", {
    headers: { "X-Requested-With": "EvalAI" },
    data: { name: "English" },
  });
  expect(s.status()).toBe(201);
  await page.goto("/management");
  await page.getByRole("button", { name: "Add teacher", exact: true }).click();
  await page.getByLabel("Teacher name", { exact: true }).fill("School Teacher");
  await page
    .getByLabel("Email", { exact: true })
    .fill("school-teacher@example.com");
  await page
    .getByLabel("Temporary password", { exact: true })
    .fill("temporary-password-123");
  await page
    .getByRole("button", { name: "Add assignment", exact: true })
    .click();
  await page.getByRole("button", { name: "Save teacher", exact: true }).click();
  await expect(
    page.getByText("school-teacher@example.com", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: test.info().outputPath("school-management.png"),
    fullPage: true,
  });
  const context = await browser.newContext();
  const teacher = await context.newPage();
  await teacher.goto("/login");
  await teacher.getByLabel("Email address").fill("school-teacher@example.com");
  await teacher
    .getByLabel("Password", { exact: true })
    .fill("temporary-password-123");
  await teacher.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(teacher).toHaveURL(/\/account$/);
  await teacher
    .getByLabel("Current password", { exact: false })
    .fill("temporary-password-123");
  await teacher
    .getByLabel("New password", { exact: true })
    .fill("updated-password-123");
  await teacher
    .getByLabel("Confirm new password", { exact: true })
    .fill("updated-password-123");
  await teacher.getByRole("button", { name: "Update password" }).click();
  await expect(
    teacher.getByText("Password updated.", { exact: false }),
  ).toBeVisible();
  await teacher
    .getByRole("link", { name: "Open workspace", exact: true })
    .click();
  await expect(teacher).toHaveURL(/\/dashboard$/);
  await teacher.goto("/students");
  await expect(
    teacher.getByRole("heading", { name: "Assigned students" }),
  ).toBeVisible();
  await expect(
    teacher.getByRole("button", { name: "Add Student" }),
  ).toHaveCount(0);
  await context.close();
});

test("parent registers with one child and edits the private family profile", async ({
  page,
}) => {
  await page.goto("/register");
  await page.getByLabel("I am registering as").selectOption("PARENT");
  await page.getByLabel("Full name", { exact: true }).fill("Parent User");
  await page.getByLabel("Email address").fill("parent-browser@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("parent-password-123");
  await page
    .getByLabel("Confirm password", { exact: true })
    .fill("parent-password-123");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(page).toHaveURL(/\/onboarding$/);
  await page.getByLabel("Contact number").fill("9876543210");
  await page.getByLabel("Child's full name", { exact: true }).fill("Child One");
  await page.getByLabel("Child's class", { exact: true }).selectOption("12");
  await page.getByRole("button", { name: "Open my workspace" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(
    page.getByRole("link", { name: "School management", exact: true }),
  ).toHaveCount(0);
  await page.goto("/family");
  await page
    .getByLabel("Child's full name", { exact: true })
    .fill("Child Updated");
  await page.getByRole("button", { name: "Save profile", exact: true }).click();
  await expect(page.getByText("Profile saved.", { exact: true })).toBeVisible();
  await page.screenshot({
    path: test.info().outputPath("parent-profile.png"),
    fullPage: true,
  });
  const students = await page.request.get("/api/students");
  expect((await students.json()).map((s: { name: string }) => s.name)).toEqual([
    "Child Updated",
  ]);
});
