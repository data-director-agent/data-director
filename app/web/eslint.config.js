import js from "@eslint/js";
import boundaries from "eslint-plugin-boundaries";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

// Every button is the kit's, so that they look and behave alike (components/ui/Button.tsx).
const BUTTON = {
  selector: "JSXOpeningElement[name.name='button']",
  message: "Use Button or ToggleButton from components/ui/Button.tsx.",
};

// Live regions are the frame's two, spoken through the announcer (components/ui/Announcer.tsx,
// #948), so run progress is said once and errors go to the assertive region.
const LIVE_REGION = {
  selector: "JSXAttribute[name.name='aria-live']",
  message: "Announce through useAnnounce (components/ui/Announcer.tsx) instead of an aria-live region.",
};

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
          pattern: "src/{run,manifest,conversation,flow,session,project,feedback,policy,model-account,scan}/**",
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
      "no-restricted-syntax": ["error", BUTTON, LIVE_REGION],
    },
  },
  {
    // The announcer owns the live regions for run progress. AddInventory says an upload's result
    // in its own region, which is not run progress; TODO(#1025): move it to the announcer.
    files: ["src/components/ui/Announcer.tsx", "src/components/inventory/AddInventory.tsx"],
    rules: { "no-restricted-syntax": ["error", BUTTON] },
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
