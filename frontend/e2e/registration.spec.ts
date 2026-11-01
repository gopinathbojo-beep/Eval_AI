import { expect, test } from "@playwright/test";

async function answer(page: import("@playwright/test").Page, value: string) {
  await page.locator("input").fill(value);
  await page.getByRole("button", { name: "Send", exact: true }).click();
}

test("mobile landing and registration support edits, password validation and server errors", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(
    page.getByRole("link", { name: "Login", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Register", exact: true }).click();
  await page.getByRole("button", { name: /^Parent/ }).click();
  await answer(page, "Original name");
  await page
    .getByRole("button", { name: "Edit Full name", exact: true })
    .click();
  await expect(page.locator("input")).toHaveValue("Original name");
  await answer(page, "Updated name");
  await answer(page, "new-parent@example.com");
  await answer(page, "short");
  await expect(
    page.getByRole("alert").getByText("Use at least 10 characters", { exact: false }),
  ).toBeVisible();
  await answer(page, "my-private-password");
  await expect(
    page.getByText("my-private-password", { exact: true }),
  ).toHaveCount(0);
  await answer(page, "different-password");
  await expect(
    page.getByText("That doesn’t match", { exact: false }),
  ).toBeVisible();
  await answer(page, "my-private-password");
  await page.route("**/api/auth/register", (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({
        code: "EMAIL_EXISTS",
        message: "An account with this email already exists. Sign in instead.",
      }),
    }),
  );
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByText("An account with this email already exists.", {
      exact: false,
    }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: test.info().outputPath("mobile-registration.png"),
    fullPage: true,
  });
});

test("school registers without approval and provisions a teacher", async ({
  page,
  browser,
}) => {
  await page.goto("/register");
  await page.getByRole("button", { name: /^School management/ }).click();
  await page.screenshot({
    path: test.info().outputPath("registration-chat.png"),
    fullPage: true,
  });
  await answer(page, "School Manager");
  await answer(page, "school-browser@example.com");
  await answer(page, "school-password-123");
  await answer(page, "school-password-123");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(page).toHaveURL(/\/onboarding$/);
  await answer(page, "School Manager");
  await answer(page, "9876543210");
  await answer(page, "New CBSE School");
  await answer(page, "School Road");
  await answer(page, "Chennai");
  await answer(page, "Tamil Nadu");
  await answer(page, "600001");
  await page.getByRole("button", { name: "Skip for now" }).click();
  await page.getByRole("button", { name: "Skip for now" }).click();
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
  await page.getByRole("button", { name: /^Parent/ }).click();
  await answer(page, "Parent User");
  await answer(page, "parent-browser@example.com");
  await answer(page, "parent-password-123");
  await answer(page, "parent-password-123");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(page).toHaveURL(/\/onboarding$/);
  await answer(page, "Parent User");
  await answer(page, "9876543210");
  await answer(page, "Child One");
  await page.getByRole("button", { name: "Class 12", exact: true }).click();
  await page.getByRole("button", { name: "Skip for now" }).click();
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
