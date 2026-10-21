# ADR-0024: The app is a React shell drawn from each agent's manifest

**Status:** Proposed
**Date:** 2026-10-21

Amended by [ADR-0028](0028-conversation-is-the-front-door.md) (the app's home page).

## Context

The alpha app (`app/`) was a Gradio chat around one language model whose one tool called R3.
Its page was built around that agent: a new agent meant new tool code and new page code. The UI
best-practice synthesis (`docs/ui/best-practices.md`, §9) asks for a structured surface for the
work rather than chat alone: capabilities and limits declared upfront, a plan and activity log,
review gated by risk, evidence on every suggestion, and abstain and refer as real screens. That
document marks its own evidence as weak, so its items are design hypotheses to test, not
findings.

Three earlier decisions constrain the answer. ADR-0016: the manifest says what an agent does,
never how to draw it. ADR-0017: the deployment's profile, not the agent, decides what may run.
ADR-0001: AG-UI carries run events to a browser.

## Decision

1. **The app is a shell, not an agent's page.** `app/web` is a React and TypeScript application
   built with Vite. It names no agent. It draws each agent from the manifest the harness already
   holds (the `agent-spec/v0` extension on the agent's card) and, from later increments, from a
   generic stream of AG-UI events. Adding an agent needs its package, one line in the agent
   list and a profile entry, and no change to the shell.
2. **Gradio and pydantic-ai are removed.** `dd_app` becomes a Starlette server: `GET /api/agents`
   returns the registry's listing beside what the profile assigns each agent (its action class,
   and whether that class needs approval), and every other path serves the built shell from
   `app/web/dist`. The app stops at start-up, with one line, if the shell is not built. The
   language-model chat is not replaced in this decision; it returns as an orchestrator under
   `delegation` grounding (ADR-0012, #21).
3. **What an agent has not declared is shown as not declared.** The shell never fills a missing
   limit, reliability or data-handling statement with a default. A reliability nobody has
   evaluated is shown as unsubstantiated.
4. **The shell renders decisions; it does not make them.** Whether an agent may run, and later
   whether an action needs review, is decided by the harness and sent to the shell. The shell
   holds no policy.
5. **Presentation comes from tokens.** Colours, spacing and type are CSS custom properties in a
   theme file (`app/web/src/tokens/neutral.css`). Components use no literal value, so another
   theme (for example an institution's) is a new token file. No organisation's branding is
   built in.
6. **Accessibility is tested from the first increment.** WCAG 2.2 AA: axe in component and
   browser tests, light and dark; keyboard-only journeys; reflow at 320 CSS pixels (400% zoom)
   without horizontal scrolling. A status is never shown by colour alone. Interactive widgets
   come from React Aria Components.
7. **Fixtures are what the server says.** The shell's tests draw manifests from
   `app/web/fixtures/*.json`, which `app/tests/test_app.py` regenerates from the real server and
   checks for drift.
8. **ADR-0016 still holds.** A later per-class renderer in the shell may lay out a payload, but
   the shell keeps ownership of grounding, derivation badges and evidence links, and nothing
   about presentation is added to the manifest.

## Dependencies introduced

| Dependency | Tier | Fallback if this dependency is abandoned |
|---|---|---|
| `react`, `react-dom` | Runtime path | Preact with `preact/compat` runs the same components. |
| `react-aria-components` | Runtime path | The listbox is the only widget so far (`components/capabilities/AgentDirectory.tsx`); the WAI-ARIA listbox pattern by hand, or Radix primitives. |
| `starlette` | Runtime path | Already installed with `a2a-sdk[http-server]`; one route and a static mount in `dd_app/app.py` move to any ASGI framework. |
| `uvicorn` | Runtime path | Any ASGI server. |
| `vite`, `@vitejs/plugin-react`, `typescript` | Evaluation/CI path (build) | Any bundler that compiles TSX; the output is static files. |
| `vitest`, `@testing-library/*`, `jsdom`, `jest-axe` | Evaluation/CI path | — |
| `@playwright/test`, `@axe-core/playwright` (MPL-2.0, unmodified) | Evaluation/CI path | — |
| `eslint`, `typescript-eslint`, `eslint-plugin-jsx-a11y`, `eslint-plugin-react-hooks` | Evaluation/CI path | — |
| `gradio`, `pydantic-ai-slim` | Removed | — |

Every dependency's licence is compatible with the repository's MIT licence.

## Consequences

- The repository now has a Node toolchain (Node 22 or later, npm, `app/web/package-lock.json`).
  A contributor who only works on Python is unaffected unless they run the app, which needs
  `npm ci && npm run build` once.
- The app's entry point is a conversation with the orchestrator (ADR-0028), not free-text
  questions to a model of its own. The per-agent directory stays, one step away.
- The JavaScript tests carry no requirement marker and do not feed `CONFORMANCE.md`. TODO:
  decide whether to bridge them (for example from Playwright's JSON report) or leave C6 to
  review.
- A future contributor must not name an agent in `app/web/src`, put a policy decision in the
  shell, or add a presentation hint to the manifest without revisiting this decision.
