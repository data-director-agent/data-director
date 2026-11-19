import js from "@eslint/js";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: [".dependency-cruiser.cjs", "coverage", "node_modules"] },
  js.configs.recommended,
  ...tseslint.configs.strict,
  jsxA11y.flatConfigs.strict,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
    plugins: { "react-hooks": reactHooks },
    rules: reactHooks.configs.recommended.rules,
  },
  {
    // The headless entry point (src/index.ts and what it reaches) must not need React, so that a
    // host without React, such as the workbench's plain modules, can still read a card with it.
    files: ["src/{card,spec,schema,payload}/**/*.ts", "src/*.ts"],
    rules: {
      "no-restricted-imports": [
        "error",
        { patterns: [{ group: ["react", "react/*", "react-dom", "./react/*", "../react/*"], message: "The headless modules import no React; components belong in src/react." }] },
      ],
    },
  },
  {
    // Functions a reviewer can follow (docs/architecture-review.md). A function over these limits
    // today carries an `eslint-disable-next-line complexity` marker as recorded debt: remove the
    // marker when you split it, and never add one to get new code past these rules. JSX
    // conditionals count towards complexity, hence 18 rather than the 12 Ruff applies to Python.
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["**/*.test.{ts,tsx}"],
    // A marker left on a function that now passes is an error, so the recorded debt only shrinks.
    linterOptions: { reportUnusedDisableDirectives: "error" },
    rules: {
      complexity: ["error", 18],
      "max-depth": ["error", 4],
    },
  },
);
