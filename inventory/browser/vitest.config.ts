import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,
    include: ["tests/**/*.test.ts"],
    // The package is small and pure, so its floors sit near full coverage.
    coverage: {
      provider: "v8",
      // The bundle's build and parity check, and the scanner's worker, need uv, the network,
      // Pyodide or a browser, and CI runs them in their own job (`npm run parity`, `npm run e2e`);
      // their pure parts are measured here.
      include: ["src/**/*.ts", "bundle/resolve.ts", "bundle/compare.ts", "bundle/manifest.ts"],
      exclude: ["src/scanner/worker.ts"],
      reporter: ["text", ["lcov", { projectRoot: "../.." }]],
      thresholds: { statements: 95, branches: 90, functions: 95, lines: 95 },
    },
  },
});
