import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";

const caddy = readFileSync(new URL("../../deploy/Caddyfile", import.meta.url), "utf8");
const csp = caddy.match(/Content-Security-Policy "([^"]+)"/)![1];

test.beforeEach(async ({ page }) => {
  // Exercise the compiled application with the same script policy as the HTTPS ingress.
  await page.route("**/*", async (route) => {
    if (route.request().resourceType() !== "document") return route.continue();
    const response = await route.fetch();
    await route.fulfill({ response, headers: { ...response.headers(), "Content-Security-Policy": csp } });
  });
});

test("deep routes, cookie sign-in, reload and logout", async ({ page, context }) => {
  await page.goto("/students");
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Email").fill("browser@example.test");
  await page.getByLabel("Password", { exact: true }).fill("test-password-123");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/students$/);
  await expect(page.getByRole("main")).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("adem_token"))).toBeNull();
  const session = (await context.cookies()).find((cookie) => cookie.name === "eval_session");
  expect(session?.httpOnly).toBe(true);
  await page.reload();
  await expect(page).toHaveURL(/\/students$/);
  await expect(page.getByRole("main")).toBeVisible();
  const blocked = await page.request.post("/api/classes", { data: { name: "Forged" } });
  expect(blocked.status()).toBe(403);
  await page.getByRole("button", { name: "Account: Browser Test" }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
  await page.reload();
  await expect(page).toHaveURL(/\/login$/);
});

test("wrong credentials stay on the login page with a useful error", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("browser@example.test");
  await page.getByLabel("Password", { exact: true }).fill("wrong-password");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByText("Email or password is incorrect.")).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});
