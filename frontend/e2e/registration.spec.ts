import { expect, test, type Page } from "@playwright/test";

/** Answer the current chat question with the text input. */
async function answer(page: Page, value: string) {
  const question = page.locator("#chat-question");
  const asked = (await question.count()) ? await question.innerText() : "";
  await page.getByLabel("Registration conversation").locator("form input").last().fill(value);
  await page.getByRole("button", { name: "Send", exact: true }).click();
  // the next question (or a validation message) must be on screen before the next answer is typed
  await expect
    .poll(async () => (await page.getByRole("alert").count()) > 0 ||
      !(await question.count()) || (await question.innerText()) !== asked)
    .toBe(true);
}

const unique = (prefix: string) => `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;

/** Account chat (original questions), then the original profile chat in onboarding. */
async function account(page: Page, name: string, email: string) {
  await answer(page, name);
  await answer(page, email);
  await answer(page, "School-password-123");
  await answer(page, "School-password-123");
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page).toHaveURL(/\/onboarding$/);
}

test("mobile landing: Login first, Register here, original questions, edits, validation and server errors", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Login", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Register here" }).click();
  await expect(page).toHaveURL(/\/register$/);
  await page.getByRole("link", { name: /^Parent/ }).click();
  await expect(page).toHaveURL(/\/register\/parent$/);

  await answer(page, "Original name");
  await page.getByRole("button", { name: "Edit Full name", exact: true }).click();
  await expect(page.getByLabel("Registration conversation").locator("form input").last()).toHaveValue("Original name");
  await answer(page, "R2D2");  // digits are not a name
  await expect(page.getByRole("alert").getByText("can contain only letters", { exact: false })).toBeVisible();
  await answer(page, "Updated Name");
  await answer(page, "not-an-email");
  await expect(page.getByRole("alert").getByText("Enter a valid email address", { exact: false })).toBeVisible();
  await answer(page, unique("parent"));
  await answer(page, "short");
  await expect(page.getByRole("alert").getByText("at least 8 characters", { exact: false })).toBeVisible();
  await answer(page, "My-Private-password1");
  await expect(page.getByText("My-Private-password1", { exact: true })).toHaveCount(0);
  await answer(page, "Different-password1");
  await expect(page.getByText("That doesn’t match", { exact: false })).toBeVisible();
  await answer(page, "My-Private-password1");
  await page.route("**/api/auth/register", (route) =>
    route.fulfill({ status: 409, contentType: "application/json",
      body: JSON.stringify({ code: "EMAIL_EXISTS", message: "An account with this email already exists. Sign in instead." }) }));
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page.getByText("An account with this email already exists. Edit the email", { exact: false })).toBeVisible();
  await expect(page.getByText("Updated Name", { exact: true })).toBeVisible();   // answers are kept
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("school registers with the original questions and gets the school tabs", async ({ page }) => {
  await page.goto("/register");
  await page.getByRole("link", { name: /^School Management/ }).click();
  await account(page, "School Manager", unique("school"));
  await page.getByRole("button", { name: "Skip", exact: true }).click();   // CBSE affiliation number (optional)
  await answer(page, "New CBSE School");                                     // school name, searched in CBSE records
  const manual = page.getByRole("button", { name: /None of these/ });
  if (await manual.isVisible().catch(() => false)) await manual.click();
  // the address is one card: all five fields, then Submit Address
  await expect(page.getByText("School address details", { exact: true })).toBeVisible();
  await page.getByLabel("Building / Campus Name").fill("Green Valley Campus");
  await page.getByLabel("Locality / Area").fill("Anna Nagar");
  await page.getByLabel("City").fill("Chennai");
  await page.getByLabel("State").fill("Tamil Nadu");
  await page.getByLabel("PIN Code").fill("60001");
  await page.getByRole("button", { name: "Submit Address" }).click();
  await expect(page.getByRole("alert").getByText("6-digit PIN code", { exact: false })).toBeVisible();
  await page.getByLabel("PIN Code").fill("600001");
  await page.getByRole("button", { name: "Submit Address" }).click();
  await expect(page.getByText("Green Valley Campus, Anna Nagar, Chennai, Tamil Nadu - 600001", { exact: false })).toBeVisible();
  await answer(page, "Dr. Lakshmi Rao");            // principal: mandatory
  await answer(page, "12345");
  await expect(page.getByRole("alert").getByText("10-digit phone number", { exact: false })).toBeVisible();
  await answer(page, "044 2345 6789");
  await page.getByRole("button", { name: "Open my workspace" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  for (const tab of ["Dashboard", "Exams"])
    await expect(page.getByRole("link", { name: tab, exact: true }).first()).toBeVisible();
  const me = await (await page.request.get("/api/auth/me")).json();
  expect(me.role).toBe("MANAGEMENT");
  expect(me.profile.principal_name).toBe("Dr. Lakshmi Rao");
  expect(me.profile.address).toBe("Green Valley Campus, Anna Nagar, Chennai, Tamil Nadu - 600001");
  expect(me.profile.locality).toBe("Anna Nagar");
  await page.goto("/management");   // teachers were retired
  await expect(page).toHaveURL(/\/dashboard$/);
});

test("parent registers with the original questions and reaches the family dashboard", async ({ page }) => {
  await page.goto("/register/parent");
  await account(page, "Meena Raman", unique("parent"));
  await answer(page, "Meena Raman");
  await answer(page, "9876543210");
  await answer(page, "Arun Raman");
  await page.getByRole("button", { name: "Class 12" }).click();
  await page.getByRole("button", { name: "Skip", exact: true }).click();   // child's school (optional)
  await page.getByRole("button", { name: "Open my workspace" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  const me = await (await page.request.get("/api/auth/me")).json();
  expect(me.role).toBe("PARENT");
  expect(me.profile.child_name).toBe("Arun Raman");
  await expect(page.getByRole("navigation", { name: "Navigation" }).getByRole("link", { name: "My child & profile" })).toBeVisible();
});
