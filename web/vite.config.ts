import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The Flask backend serves the API; proxy /api through this origin so the UI needs no CORS.
const API_URL = process.env.API_URL ?? "http://127.0.0.1:5050";
const proxy = { "/api": { target: API_URL, changeOrigin: true } };

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL(".", import.meta.url)) } },
  test: { include: ["lib/**/*.test.ts"], environment: "node" },
  server: { host: "127.0.0.1", port: 3000, strictPort: true, proxy },
  preview: { host: "127.0.0.1", port: 3000, strictPort: true, proxy },
});
