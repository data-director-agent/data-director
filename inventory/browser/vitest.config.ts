import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,
    include: ["tests/**/*.test.ts"],
    // The package is small and pure, so its floors sit near full coverage.
    coverage: {
      provider: "v8",
      include: ["src/**/*.ts"],
      reporter: ["text", ["lcov", { projectRoot: "../.." }]],
      thresholds: { statements: 95, branches: 90, functions: 95, lines: 95 },
    },
  },
});
