import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["coverage", "node_modules", "dist", ".cache", "playwright-report", "test-results"] },
  js.configs.recommended,
  ...tseslint.configs.strict,
  {
    // Functions a reviewer can follow (docs/architecture-review.md). A function over these limits
    // today carries an `eslint-disable-next-line complexity` marker as recorded debt: remove the
    // marker when you split it, and never add one to get new code past these rules. JSX
    // conditionals count towards complexity, hence 18 rather than the 12 Ruff applies to Python.
    files: ["src/**/*.{ts,tsx}", "bundle/**/*.ts"],
    ignores: ["**/*.test.{ts,tsx}"],
    // A marker left on a function that now passes is an error, so the recorded debt only shrinks.
    linterOptions: { reportUnusedDisableDirectives: "error" },
    rules: {
      complexity: ["error", 18],
      "max-depth": ["error", 4],
    },
  },
);
