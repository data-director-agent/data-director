import js from "@eslint/js";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["coverage", "node_modules"] },
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
);
