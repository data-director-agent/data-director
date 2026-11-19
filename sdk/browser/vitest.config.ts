import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      reporter: ["text", ["lcov", { projectRoot: "../.." }]],
      thresholds: { statements: 90, branches: 80, functions: 90, lines: 90 },
    },
  },
});
