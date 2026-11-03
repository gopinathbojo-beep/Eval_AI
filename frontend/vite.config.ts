import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { existsSync, readFileSync } from "node:fs";

// HTTPS only when scripts/make-cert.sh has made a certificate: phones on the Wi-Fi need it for the in-app camera.
const cert = { key: new URL("./certs/key.pem", import.meta.url), cert: new URL("./certs/cert.pem", import.meta.url) };
const https = existsSync(cert.key) && existsSync(cert.cert)
  ? { key: readFileSync(cert.key), cert: readFileSync(cert.cert) }
  : undefined;

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, host: true, https, proxy: { "/api": { target: process.env.EVAL_API_TARGET ?? "http://127.0.0.1:8000", changeOrigin: false } } },
  preview: { proxy: { "/api": { target: process.env.EVAL_API_TARGET ?? "http://127.0.0.1:8000", changeOrigin: false } } },
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            { name: "math", test: /node_modules[\\/]katex/ },
            { name: "react", test: /node_modules[\\/](react|react-dom|react-router|react-router-dom|scheduler)[\\/]/ },
          ],
        },
      },
    },
  },
});
