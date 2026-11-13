import js from "@eslint/js";
import boundaries from "eslint-plugin-boundaries";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "coverage", "playwright-report", "test-results", ".dependency-cruiser.cjs"] },
  js.configs.recommended,
  ...tseslint.configs.strict,
  jsxA11y.flatConfigs.strict,
  {
    // Layers of src/, described in docs/specs/app.md: the UI kit imports no
    // feature, and the domain folders import no component.
    files: ["src/**/*.{ts,tsx}"],
    plugins: { boundaries },
    settings: {
      "import/resolver": { typescript: { project: "./tsconfig.json" } },
      "boundaries/elements": [
        { type: "ui", pattern: "src/components/ui/**" },
        { type: "component", pattern: "src/components/**" },
        {
          type: "domain",
          pattern: "src/{run,manifest,conversation,flow,session,project,feedback,policy,model-account}/**",
        },
      ],
    },
    rules: {
      "boundaries/dependencies": [
        "error",
        {
          default: "allow",
          policies: [
            {
              from: { element: { type: "ui" } },
              disallow: { to: { element: { type: "component" } } },
              message: "The UI kit (components/ui) imports no feature component.",
            },
            {
              from: { element: { type: "domain" } },
              disallow: { to: { element: { types: ["component", "ui"] } } },
              message: "Domain folders import no component.",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Every button is the kit's, so that they look and behave alike (components/ui/Button.tsx).
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXOpeningElement[name.name='button']",
          message: "Use Button or ToggleButton from components/ui/Button.tsx.",
        },
      ],
    },
  },
);
