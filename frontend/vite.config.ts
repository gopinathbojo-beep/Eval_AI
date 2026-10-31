import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": { target: process.env.EVAL_API_TARGET ?? "http://127.0.0.1:8000", changeOrigin: false } } },
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
