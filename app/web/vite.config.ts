import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The app's Python server (`uv run data-director`) serves /api; `npm run dev` proxies to it.
const API = process.env.DD_APP_URL ?? "http://127.0.0.1:7860";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": API } },
  build: {
    outDir: "dist",
    sourcemap: true,
    // In one chunk the bundle passed Vite's 500 kB warning (#212). Lazy loading would not
    // help: React, React Aria and the Markdown renderer are all needed by the first page. So
    // the vendors go in their own chunks instead, each well under the limit, which a browser
    // keeps cached across releases that change only the app's own code. The first group a
    // module matches wins, so `vendor` collects whatever the two before it leave.
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            { name: "react", test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/ },
            {
              name: "react-aria",
              test: /node_modules[\\/](react-aria|react-stately|@react-aria|@react-stately|@react-types|@internationalized|@swc)/,
            },
            { name: "vendor", test: /node_modules[\\/]/ },
          ],
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
