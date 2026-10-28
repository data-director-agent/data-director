# ADR-0024: The app is a React shell drawn from each agent's manifest, opening on the orchestrator conversation

**Status:** Proposed
**Date:** 2026-10-21

Amends [ADR-0017](0017-policy-is-the-deployments.md) (a new profile key, `orchestrator`).

## Context

The alpha app (`app/`) was a Gradio chat around one language model whose one tool called R3.
Its page was built around that agent: a new agent meant new tool code and new page code. The UI
best-practice synthesis (`docs/ui/best-practices.md`, §1, §9) asks for chat for intent and a
structured surface for the work: capabilities and limits declared upfront, a plan and activity
log, review gated by risk, evidence on every suggestion, and abstain and refer as real screens.
That document marks its own evidence as weak, so its items are design hypotheses to test, not
findings.

A directory of agents, each with Run, About and History pages, is close to the workbench's
Inspect page, a test bed for the engineers who write agents. The Blueprint describes something
else. Its presentation layer is a "web app providing a chat interface and feedback mechanism"
(§9.2, Table 5), over an application layer that orchestrates user requests and coordinates the
agents (§9.3, Table 6, "AI Model Orchestration"). A person talks to one Data Director; the
specialist agents support it.

Earlier decisions constrain the answer. ADR-0016: the manifest says what an agent does, never
how to draw it. ADR-0017: the deployment's profile, not the agent, decides what may run.
ADR-0001: AG-UI carries run events to a browser. ADR-0012 §5, §12: an orchestrator delegates
only through the conductor, under a grant; it is found by grounding mode, never by name; and
every delegated child is labelled `agent_id@agent_version`.

## Decision

### The shell

1. **The app is a shell, not an agent's page.** `app/web` is a React and TypeScript application
   built with Vite. It names no agent. It draws each agent from the manifest the harness already
   holds (the `agent-spec/v0` extension on the agent's card) and, from later increments, from a
   generic stream of AG-UI events. Adding an agent needs its package, one line in the agent
   list and a profile entry, and no change to the shell.
2. **Gradio and pydantic-ai are removed.** `dd_app` becomes a Starlette server: `GET /api/agents`
   returns the registry's listing beside what the profile assigns each agent (its action class,
   and whether that class needs approval), and every other path serves the built shell from
   `app/web/dist`. The app stops at start-up, with one line, if the shell is not built. The
   language-model chat is replaced by the conversation with the orchestrator (9–16), not by a
   model of the app's own.
3. **What an agent has not declared is shown as not declared.** The shell never fills a missing
   limit, reliability or data-handling statement with a default. A reliability nobody has
   evaluated is shown as unsubstantiated.
4. **The shell renders decisions; it does not make them.** Whether an agent may run, and later
   whether an action needs review, is decided by the harness and sent to the shell. The shell
   holds no policy.
5. **Presentation comes from tokens.** Colours, spacing and type are CSS custom properties in a
   theme file (`app/web/src/tokens/neutral.css`). Components use no literal value, so another
   theme (for example an institution's) is a new token file. No organisation's branding is
   built in. The scheme is light by default, whatever the system prefers; a switch in the
   banner applies the dark scheme and remembers the choice in that browser.
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

### The front door

9. **The app opens on a conversation with the orchestrator.** The orchestrator is an agent
   whose grounding mode is `delegation`. The shell is told which agent it is by the harness and
   never names it.
10. **The profile names the orchestrator.** A new optional profile key, `orchestrator`, holds one
    `agent_id`. When the app starts, that agent must also be listed under `agents`; otherwise the
    profile is refused, with one line, like any other malformed profile. A change to the key
    raises the profile's `version`, so stored runs say which orchestrator the rules named.
11. **The default is written in the reference profile, not in code.** The app's reference profile
    (`app/config/profile.example.yaml`) names the orchestrator released in this repository, at present
    `director.stub`. A deployment that wants another names it in its own profile. Neither the
    harness nor the shell holds a fallback agent identifier.
12. **Without a usable orchestrator there is no conversation.** The grounding mode is on the
    agent's card, which can be read only while its service is running, so it is checked when the
    agent is reached, not at start-up. When the profile has no `orchestrator` key, when the named
    agent is not available, or when its card does not declare `delegation` grounding, the home
    page says which and links to the agent directory. The app does not fall back to another agent
    or pick one itself in any of these cases.
13. **The per-agent pages remain.** Run, About and History stay, one step away from the
    conversation, so a person can see what each agent does and inspect its runs. A person may
    still run an agent directly from its Run page. That run goes through the conductor under the
    profile's permission for that agent, like any other; the profile has no separate setting for
    direct runs.
14. **Every delegated child is named and linked.** The conversation shows each child as
    `agent_id@agent_version` and links it to its own run. The selected run is the `run` query parameter, so Back and reload keep
    it. It shows beside the transcript, drawn by the run view's own components; on a narrow screen
    it is its own view, reached from the card. A suspended child's card says it is waiting for
    review. TODO: the review gate itself waits for #72 and #73.
15. **A turn is a governed invocation.** Each message is one invocation of the orchestrator
    through the conductor (ADR-0012 §1), and each hand-off is a child invocation under the grant
    the conductor issues (ADR-0012 §5). The app must issue that grant (#129).
16. **What the conversation is not.** It does not bypass the conductor, and the shell does not
    route, classify or forward a person's message to a sub-agent itself. Routing is the
    orchestrator's, and every hand-off is stored.
17. **The server holds the conversation's history.** The app's server mints each
    `conversation_id` and builds each turn's `Message.history` from the turns already stored
    (`dd_harness.conversations`). A turn gives only the agent and the message text; a request
    that gives a history is refused. The input hash then covers what the agent was really shown,
    and a browser cannot put words in an earlier turn (#130). This settles, for the app,
    ADR-0012's open question of checking a caller's history against the store.

### The workspace

18. **The conversation is the centre of a workspace.** Around it: a status bar (whom the work
    acts for, the policy, and the project's dataset, phase, repository and governance flags); the
    Blueprint's six phases on the left; the open delegated run, its evidence and the
    orchestrator's declared limits on the right; and an activity log beneath. The phases are
    served from `dd_sdk.process_flow` (`GET /api/process-flow`) and joined in the shell to each
    manifest entry's `serves` (ADR-0028), so the shell keeps no copy of the flow and names no
    agent. A zone with no source yet is drawn as not built and linked to its issue (#75). When
    proposals and the review gate exist (#71-#73) they take the centre and the conversation docks
    beside them. TODO: decide how the dock behaves once there is a working surface.

Rejected:

- **The conversation as a strip beneath a working surface, as in the target design.** Nothing
  can fill that surface until proposals exist (#71), so the one part that works would be the
  smallest thing on screen.
- **Marking the researcher's current phase from the conversation.** The shell would be
  inferring where a project stands, which no agent has said and no record holds (#160).
- **Keeping the directory as the home page, with the conversation as one more page.** The
  Blueprint puts the chat interface first, and a person should not have to choose an agent before
  saying what they need.
- **The shell routing messages to sub-agents.** That would put routing, a policy decision, in the
  shell, and its hand-offs would not be recorded as delegations on any envelope.
- **Falling back to a named or first-listed agent in code.** A person would be talking to an
  agent they did not know had been chosen for them, and a steward reading the profile could not
  see the choice.
- **Choosing the only `delegation` agent when the profile names none.** For the same reason: the
  choice would depend on which agents happen to be registered, not on anything a steward reads.
- **Choosing the orchestrator in the app's own configuration (`agents.yaml`, an environment
  variable).** Which agent a person talks to first is a policy choice, and ADR-0017 puts policy
  in the profile, which a steward reviews and every run cites.
- **Refusing to start unless the orchestrator is running.** One stopped service would stop the
  whole app, including the per-agent pages that still work.
- **Letting the profile switch off direct runs.** Nothing yet needs it, and a key nothing
  enforces would be refused by the loader. A deployment that wants it can propose it later.

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
- The app's entry point is a conversation with the orchestrator, not free-text questions to a
  model of its own. The home page and navigation change (#131, #132), and the directory becomes
  its own page.
- The home page needs the app to issue delegation grants (#129) and a conversation API over the
  conductor (#130) before it works.
- The profile loader refuses keys nothing enforces, so `orchestrator` was added to the loader,
  the profile vocabulary (`workbench/profiles/README.md`) and the reference profile with the
  second orchestrator (#21), when the shell could no longer take the only `delegation` agent it
  was shown. The app enforces it: a conversation turn to any other agent is refused. The
  workbench's profiles may leave it out.
- The model-backed orchestrator, `orchestrator.model` (#21), is released, but the reference
  profile still names the rule-based `director.stub`, so that the app runs with no model key. A
  deployment with a key names `orchestrator.model` in its own profile, in an ordinary profile
  change with a new `version` (`app/README.md`).
- The JavaScript tests carry no requirement marker and do not feed `CONFORMANCE.md`. TODO:
  decide whether to bridge them (for example from Playwright's JSON report) or leave C6 to
  review.
- A future contributor must not name an agent (the orchestrator included) in `app/web/src`, put
  a policy decision in the shell, route messages in the shell, call a sub-agent from the
  conversation outside the conductor, or add a presentation hint to the manifest without
  revisiting this decision.
