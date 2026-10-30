import { expect, test } from "@playwright/test";

test("admin can filter accounts and inspect activity without approval actions", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Email address").fill("seyamesh91@gmail.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("owner-test-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
  await expect(
    page.getByRole("heading", { name: "Platform administration" }),
  ).toBeVisible();
  await page.screenshot({
    path: test.info().outputPath("admin-desktop.png"),
    fullPage: true,
  });
  await page.getByLabel("Search users").fill("browser@example.test");
  await expect(
    page.getByRole("table").getByText("browser@example.test", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Usage", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Browser Test: activity and usage" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Approve teacher", exact: true }),
  ).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("heading", { name: "Platform administration" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: test.info().outputPath("admin-mobile.png"),
    fullPage: true,
  });
});
