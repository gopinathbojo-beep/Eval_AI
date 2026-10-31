import { readFileSync } from "node:fs";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend on whichever API_BASE line is live in src/config/config.ts; the dev server forwards /api there.
const apiOrigin = () => {
  try {
    const src = readFileSync(new URL("./src/config/config.ts", import.meta.url), "utf8");
    const live = src.split(/\r?\n/).find((l) => /^\s*export const API_BASE\s*=/.test(l));
    const url = live?.match(/["'](https?:\/\/[^"']+)["']/)?.[1];
    return url ? new URL(url).origin : "http://127.0.0.1:8000";
  } catch {
    return "http://127.0.0.1:8000";
  }
};
const proxy = { "/api": { target: apiOrigin(), changeOrigin: true, secure: true } };

export default defineConfig({
  plugins: [react()],
  server: { port: 5175, proxy },
  preview: { proxy },
});
