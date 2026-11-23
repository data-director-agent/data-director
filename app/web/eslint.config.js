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

// Which feature folders (components/<feature>) may import which, and why (docs/architecture-review.md,
// #1060). A feature imports another only through an entry here; any other import between feature
// folders fails `npm run lint`. The list started as the imports of November 2026: an entry whose
// reason is marked TODO(#494) is debt to remove, not a pattern to copy. Remove an entry when its import goes.
const FEATURE_IMPORTS = [
  // The frame's page header is the top of every page, so that each page names itself the same way.
  ...["errors", "escalation", "feedback", "journey", "policy", "profile", "project", "session", "settings", "workspace"].map((from) => ({
    from,
    to: "frame",
    reason: "PageHeader is the top of every page.",
  })),
  ...["conversation", "project", "workspace"].map((from) => ({
    from,
    to: "escalation",
    reason: "A data steward is asked from the conversation, the project pane and every project page (docs/ui/steward-escalation-flows.md).",
  })),
  {
    from: "conversation",
    to: "workspace",
    reason: "The conversation home is laid out in the workspace, with its phase tracker and context panel.",
  },
  {
    from: "conversation",
    to: "inventory",
    reason: "The composer attaches an inventory and its chip opens it, using the inventory dialogs.",
  },
  {
    from: "conversation",
    to: "project",
    reason: "The home switches project (ProjectSwitcher); a document card says its facts (DocumentFacts).",
  },
  {
    from: "conversation",
    to: "run",
    reason: "A turn's run is drawn live (LiveRun); a delegated run shows its outcome, and a drafted document's text.",
  },
  {
    from: "conversation",
    to: "capabilities",
    reason: "Speaker says what powers an agent the same way as the agent directory (ModelDisclosure).",
  },
  {
    from: "workspace",
    to: "run",
    reason: "The activity log draws the events a run could not show as the run view does (UnrecognisedEvents).",
  },
  {
    from: "workspace",
    to: "inventory",
    reason: "The context panel adds and edits the project's inventory.",
  },
  {
    from: "workspace",
    to: "project",
    reason: "The context panel lists the project's documents with their facts (DocumentFacts).",
  },
  {
    from: "workspace",
    to: "conversation",
    reason: "TODO(#494): InventoryChip belongs to inventory; conversation and workspace import each other.",
  },
  {
    from: "project",
    to: "conversation",
    reason: "A project's page attaches a document through the check a message's attachment goes through (DocumentReviewDialog).",
  },
  {
    from: "project",
    to: "inventory",
    reason: "A project's page adds its inventory (AddInventory).",
  },
  {
    from: "project",
    to: "journey",
    reason: "A project card shows the project's journey at a glance (JourneyMini).",
  },
  {
    from: "journey",
    to: "project",
    reason: "The journey map is one of a project's pages, under its navigation (ProjectNav).",
  },
  {
    from: "project",
    to: "fairness",
    reason: "A project's FAIR feedback tab is the fairness panel (FairnessPanel).",
  },
  {
    from: "run",
    to: "fairness",
    reason: "A FAIR report in a run card is laid out as on the FAIR feedback tab (FairnessRenderer).",
  },
  {
    from: "workspace",
    to: "fairness",
    reason: "The context panel shows how FAIR the metadata record is (FairnessStanding).",
  },
  {
    from: "agent",
    to: "capabilities",
    reason: "An agent's page lists its capabilities (CapabilitiesPanel).",
  },
  {
    from: "capabilities",
    to: "agent",
    reason: "TODO(#494): the directory opens AgentDetail, so agent and capabilities import each other.",
  },
];

export default tseslint.config(
  { ignores: ["dist", "coverage", "playwright-report", "test-results", ".dependency-cruiser.cjs"] },
  js.configs.recommended,
  ...tseslint.configs.strict,
  jsxA11y.flatConfigs.strict,
  {
    // Layers of src/, described in docs/specs/app.md: the UI kit imports no
    // feature, the domain folders import no component, and a feature folder imports
    // another only through FEATURE_IMPORTS.
    files: ["src/**/*.{ts,tsx}"],
    plugins: { boundaries },
    settings: {
      "import/resolver": { typescript: { project: "./tsconfig.json" } },
      "boundaries/elements": [
        { type: "ui", pattern: "src/components/ui/**" },
        // Each folder of components/ is a feature, captured by name; files at its top
        // (NotBuilt.tsx) are shared by all of them.
        { type: "component", pattern: "src/components/*", capture: ["feature"] },
        { type: "component", pattern: "src/components/*" },
        {
          type: "domain",
          pattern: "src/{api,run,manifest,conversation,flow,session,project,feedback,policy,model-account,scan}/**",
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
            {
              from: { element: { type: "component" } },
              disallow: { to: { element: { type: "component", captured: { feature: "*" } } } },
              message:
                "Feature {{ from.element.captured.feature }} may not import feature " +
                "{{ to.element.captured.feature }}: add an entry with its reason to FEATURE_IMPORTS " +
                "in eslint.config.js, or move what both need to components/ui or a domain folder.",
            },
            {
              // A feature imports its own files.
              from: { element: { type: "component" } },
              allow: {
                to: { element: { type: "component", captured: { feature: "{{ from.element.captured.feature }}" } } },
              },
            },
            ...FEATURE_IMPORTS.map(({ from, to, reason }) => {
              if (!reason?.trim()) throw new Error(`FEATURE_IMPORTS: ${from} -> ${to} gives no reason.`);
              return {
                from: { element: { type: "component", captured: { feature: from } } },
                allow: { to: { element: { type: "component", captured: { feature: to } } } },
              };
            }),
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
