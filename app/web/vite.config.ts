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
    // A test that drives a whole run and then checks it with axe takes about three seconds, and
    // coverage instrumentation adds two thirds again, which is past Vitest's default of five.
    testTimeout: 15_000,
    // Measured only with --coverage, as CI runs it, so that `npm test` stays quick. The text
    // file is the job summary (fully covered files left out, as the Python report does); lcov
    // goes to Codecov under the `web` flag (codecov.yml), its paths from the repository root.
    // The floors sit a few points under the measured figures (87, 76, 89 and 90% when set), so
    // ordinary variation does not fail a run; Codecov holds the figures from falling.
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/test/**"],
      reporter: [
        "text",
        ["text", { file: "coverage.txt", skipFull: true }],
        ["lcov", { projectRoot: "../.." }],
      ],
      thresholds: { statements: 82, branches: 71, functions: 84, lines: 85 },
    },
  },
});
