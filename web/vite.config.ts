import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The Flask backend serves the API; proxy /api through this origin so the UI needs no CORS.
const API_URL = process.env.API_URL ?? "http://127.0.0.1:5050";
const proxy = { "/api": { target: API_URL, changeOrigin: true } };

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL(".", import.meta.url)) } },
  build: {
    // The app used to ship as a single ~1 MB index.js, which tripped the
    // "chunks larger than 500 kB" warning and forced every visitor to download
    // PostHog, the whole UI kit and the data layer before the first paint.
    // Split third-party code into its own long-lived, individually cacheable
    // chunks so the entry stays small and a dependency bump only invalidates
    // one vendor chunk instead of the entire bundle.
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            // Analytics is the single largest dependency and is never needed
            // for first paint, so it gets its own chunk.
            {
              name: "posthog",
              test: /node_modules[\\/]posthog-js[\\/]/,
              priority: 40,
              includeDependenciesRecursively: false,
            },
            {
              name: "react",
              test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/,
              priority: 35,
              includeDependenciesRecursively: false,
            },
            {
              name: "query",
              test: /node_modules[\\/]@tanstack[\\/]/,
              priority: 30,
              includeDependenciesRecursively: false,
            },
            {
              name: "base-ui",
              test: /node_modules[\\/]@base-ui-components[\\/]/,
              priority: 25,
              includeDependenciesRecursively: false,
            },
            // Catch-all so no third-party module is ever inlined twice.
            {
              name: "vendor",
              test: /node_modules[\\/]/,
              priority: 10,
              includeDependenciesRecursively: false,
            },
          ],
        },
      },
    },
  },
  test: { include: ["lib/**/*.test.ts"], environment: "node" },
  server: { host: "127.0.0.1", port: 3000, strictPort: true, proxy },
  preview: { host: "127.0.0.1", port: 3000, strictPort: true, proxy },
});
