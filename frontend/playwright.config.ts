import { defineConfig, devices } from "@playwright/test";
import { resolve } from "node:path";

const backend = resolve(import.meta.dirname, "../backend");
const python = process.env.PYTHON_EXECUTABLE ?? resolve(backend, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  use: { baseURL: "http://127.0.0.1:4174", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    { command: `"${python}" -m scripts.e2e_server`, cwd: backend, url: "http://127.0.0.1:18000/api/ready", reuseExistingServer: false },
    { command: "npm run preview -- --host 127.0.0.1 --port 4174 --strictPort", url: "http://127.0.0.1:4174", reuseExistingServer: false,
      env: { EVAL_API_TARGET: "http://127.0.0.1:18000" } },
  ],
});
