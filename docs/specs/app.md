# The app

## Intent and scope

The app (`app/`) is the Data Director that people use. The Blueprint's presentation layer is a
"web app providing a chat interface and feedback mechanism" over an application layer that
orchestrates requests and coordinates the agents
([§9.2, §9.3](../blueprint/09-reference-architecture.md#92-presentation-layer)). A person talks to
one Data Director; the specialist agents support it. So the app opens on a conversation with the
orchestrator, and every agent's own pages (what it does, a form to run it, its stored runs) sit
one step away.

The app is three things:

- a **browser shell** (`app/web`, React and TypeScript) that draws every agent from the manifest
  the harness holds, and later from a generic stream of AG-UI events, and names no agent;
- a **server** (`dd_app`, Starlette) that serves the built shell, runs every request through the
  harness's conductor under the app's own configuration (`app/config/`), and is the conductor's
  callback for an orchestrator's delegations;
- a **problem-report channel** that files what a person reports as a GitHub issue.

It is not the workbench, which is a test bed for engineers who write agents, and it must not
depend on it ([System and boundaries](system.md)). It does not decide policy, route messages,
or run agents. `app/README.md` describes what is built; `docs/ui/best-practices.md` is the design
input, whose evidence is weak, so its items are hypotheses to test, not findings.

## Invariants

1. **The shell names no agent.** No agent identifier, the orchestrator's included, appears in
   `app/web/src`. Adding an agent needs its package, an entry in `app/config/agents.yaml` and a
   profile entry, and no change to the shell. Enforced by review; the shell's tests run against
   `agents-several.json`, five agents of different grounding modes and payload shapes, so a
   shell that assumed one agent fails them.
2. **The shell holds no policy.** Whether an agent may run, which agent is the orchestrator, and
   (once built) whether an action needs review are decided by the harness and sent to the shell,
   which renders them. The server's `GET /api/agents` gives each manifest beside what the
   profile assigns it. A project's documents page (`/projects/{id}`) draws each version's state
   as the project log records it, and takes whether a decision needs a reason from the
   harness's rule in `GET /api/projects/{id}/documents`; the harness alone records a decision,
   and the server gives it the decider from the authenticator, never from the request
   ([Projects](projects.md), `app/tests/test_document_decisions.py`).
3. **The shell does not route.** It never classifies a message or sends it to a sub-agent.
   Each turn is one invocation of the orchestrator through the conductor, and each hand-off a
   child invocation under the conductor's grant
   ([Orchestration](orchestration.md)). A turn to any agent but the one the profile names as
   orchestrator is refused (`app/tests/test_app.py`,
   `test_a_turn_goes_only_to_the_orchestrator_the_profile_names`).
4. **The server builds a turn's history from the stored turns.** A request that supplies a
   history is refused, so the input hash covers what the agent was shown and a browser cannot put
   words in an earlier turn (`app/tests/test_app.py`).
5. **No fallback orchestrator.** When the profile names none, the named agent is unavailable, or
   its card does not declare `delegation` grounding, the home page says which and links to the
   agent directory. Neither the shell nor the server chooses another agent. The reference
   profile, not code, names the default (`app/web/src/components/conversation/ConversationHome.test.tsx`).
6. **Every delegated child is labelled `agent_id@agent_version`** and opens its run inside its
   own card in the conversation, at every width, drawn by the run view's components.
7. **What is undeclared is shown as undeclared.** A limit, reliability or data-handling
   statement an agent has not declared is shown as "Not declared"; a reliability nobody has
   evaluated is shown as unsubstantiated. The shell never fills one with a default.
8. **What is not built is drawn as not built.** A zone with no source yet says "Not built yet"
   and links to the issue that builds it, rather than showing invented data.
9. **The manifest carries no presentation.** It says what an agent does, never how to draw it;
   the shell works out presentation and keeps ownership of grounding, derivation badges and
   evidence links ([Agents](agents.md)). A later per-class renderer may lay out a payload but
   adds nothing to the manifest.
10. **Presentation comes from tokens.** Every colour, size and typeface is a custom property in
    `app/web/src/tokens/neutral.css`; no organisation's branding is built in, so a theme is a new
    token file. Stylelint rejects a literal colour outside the token file (`npm run lint`).
11. **The app runs no agent in its own process.** It reaches every agent over A2A through the
    conductor and imports no agent package and not the workbench
    (`app/tests/test_app_boundary.py`). Its agent list names every in-tree agent; one that is not
    running is shown as unavailable, never replaced by a local copy. Its tests serve agents in
    memory over A2A (`dd_harness.testing`), so they exercise the same wire.
12. **The app's A2A endpoint is no general way in.** It accepts only a delegation agent's
    callback under a live grant and refuses every other request
    (`test_the_app_takes_no_a2a_call_but_a_delegation_callback`).
13. **The shell's fixtures are what the server says.** The shell's tests draw from
    `app/web/fixtures/`, which `app/tests/test_app.py` regenerates from the real server and fails
    on drift.
14. **The app stops at start-up, with one line,** when a setting, a file or the built shell is
    missing or wrong. A stopped agent, the orchestrator included, does not stop it.
15. **A problem report never carries a person's work.** It holds what the person typed, the
    build, and the page's path. The run and conversation they came from are attached only if they
    tick a box, and then only as identifiers, agents, versions and outcomes read from the run
    store: never an input, a payload or evidence (`app/tests/test_feedback.py`).
16. **The server names the build in a report.** It adds the app version, harness version and
    commit to the issue itself; the page shows them but is not trusted for them.
17. **Problem reports are bounded.** Lengths are capped, unknown fields refused, and the number
    filed in a window limited (`app/src/dd_app/feedback.py`, `app/tests/test_feedback.py`).
    Without a token the feature is off, the page says so and links to GitHub, and the app still
    starts.
18. **Each conversation is started in a project of its own.** Where the app keeps projects,
    `POST /api/conversations` creates a project and starts the conversation in it, acting for the
    person signed in, and a conversation names its `project_id` and the inventory its project
    holds. The app gives the conductor the same project store, so a turn's runs belong to the
    project and a drafter's documents are kept in it ([Projects](projects.md),
    `app/tests/test_app.py`).
19. **An inventory is attached, never pasted into the message.** A turn may carry an `inventory`,
    the file `dd-inventory` writes, which the server adds to the conversation's project before the
    turn runs; with one, the message may be blank and the server supplies a sentence saying an
    inventory was attached. An inventory the project refuses, or one sent to a conversation in no
    project, refuses the turn and nothing runs or is recorded. The shell attaches one from a file
    chosen with a button, dropped on the message form, or pasted whole into the message box, and
    shows it as a chip with a link to the user guide's page on making one, never as its text. The
    transcript shows the chip on the turn where the project's inventory changed, read from the
    `project_inventory` the conductor gave that turn (`app/tests/test_app.py`,
    `app/web/src/components/conversation/ConversationHome.test.tsx`).

## Boundaries and contracts

- **Depends on** the harness (`dd_harness`) and the SDK only. Workspace-level dependency rules
  are in [System and boundaries](system.md).
- **Conversations and delegation** are specified in [Orchestration](orchestration.md); the app
  supplies the conductor's callback and the conversation API over it. Which agent is the
  orchestrator is a profile key ([Policy and identity](policy-and-identity.md)).
- **Signing in, whom a run acts for, and model credentials** are in
  [Policy and identity](policy-and-identity.md). The app never holds a model key: no agent runs in
  its process, so there is nothing in it to call a model.
- **Run events to the browser** are AG-UI ([Transport and tracing](transport.md)). Not built yet:
  a run is one request that answers when it has ended, so stages are read back, not watched, and
  a run cannot be cancelled. TODO(#68, #69).
- **Outcomes, evidence and the checks' reports** are rendered as the [Contract](contract.md) and
  [Evidence and grounding](grounding.md) define them. A drafted document in a run's result is
  shown as a document: rendered when its media type is `text/markdown`, tables included, and
  otherwise with its line breaks kept, with actions to copy the text and download it as a file.
  The project's documents page shows the stored text unrendered, since that is what a decision
  names.
- **The phases** come from the SDK's process flow, served by the app and joined in the shell to
  each manifest's `serves` ([Orchestration](orchestration.md)), so the shell keeps no copy of the
  flow.
- **Direct runs.** A person may run an agent from its Run page. That run goes through the
  conductor under the profile's permission for that agent like any other; there is no separate
  setting for direct runs.
- **Problem reports** go to one repository, named in the app's configuration, as an issue of type
  Bug, Feature or Task with the label `area: app`. The person needs no GitHub account.

## Rationale

- **A shell drawn from manifests.** The earlier app was built around one agent, so each new agent
  needed new page code. Drawing from the manifest makes the shell general, and the multi-agent
  fixture keeps it so.
- **Conversation first.** The Blueprint puts the chat interface first, and a person should not
  have to choose an agent before saying what they need.
- **The conversation at the centre of a workspace.** Around it: whom the work acts for and whose
  policy applies; the Blueprint's six phases; the project's documents and the orchestrator's
  declared limits; an activity log. Evidence belongs beside the claim it supports
  (`docs/ui/best-practices.md` §4), so a delegated run opens in its card. When proposals and a
  review gate exist they take the centre and the conversation docks beside them.
- **Policy in the profile.** Which agent a person talks to first is a policy choice. The profile
  is what a steward reviews and every run cites; a change to the orchestrator raises its version,
  so stored runs say which orchestrator the rules named.
- **An inventory in the project, not in the message.** Pasted into the message, an inventory of
  a few hundred files filled the transcript and was sent again in the history of every later
  turn, and an orchestrator could pass a changed copy to an agent. Kept by the project, it is
  given to each agent whole by the conductor, covered by the input hash, and shown to the
  researcher as one line (#443).
- **One path to every agent.** Two ways of reaching an agent are two behaviours to keep
  conformant. They did diverge: A2A carries numbers as doubles, so a payload over the wire gave
  `14.0` where the in-process path gave `14`, and the app's tests, using the in-process path,
  never saw it. One path also leaves one agent list for development and deployment.
- **The app files reports itself.** A report is little use without the build it was made on, and
  most researchers have no GitHub account. The token is narrow: a fine-grained token for one
  repository with Issues: write, which can do nothing a model key can.

## Rejected alternatives

- **Gradio, or a chat around a model of the app's own.** The page was built around one agent and
  its tools; the app now has no model of its own and converses with the orchestrator.
- **A UI schema or presentation hints from agents.** It would couple every agent to one shell's
  layout; the manifest declares derivations and the shell works out presentation.
- **Running an agent in the app's process.** See "One path to every agent". It also needed a
  special rule for model keys in the app's process and a second agent list for deployment.
- **The directory as the home page, with the conversation as one more page.** It makes a person
  choose an agent first.
- **The shell routing messages to sub-agents.** That puts a policy decision in the shell, and its
  hand-offs would not be recorded as delegations on any envelope.
- **A fallback orchestrator: one named in code, the first listed, or the only `delegation`
  agent.** A person would be talking to an agent they did not know had been chosen, and the
  choice would depend on what happens to be registered, not on anything a steward reads.
- **Naming the orchestrator in the app's own configuration** (agent list, environment variable).
  It is policy, which belongs in the profile.
- **Refusing to start unless the orchestrator is running.** One stopped service would stop the
  whole app, including the per-agent pages that still work.
- **The open run in a side column.** The evidence sat away from its turn, the column was empty
  until a run was opened, and on a narrow screen the run replaced the page.
- **The conversation as a strip beneath a working surface.** Until proposals exist nothing fills
  that surface, so the one working part would be the smallest thing on screen.
- **Marking the researcher's current phase from the conversation.** The shell would infer where a
  project stands, which no agent has said and no record holds.
- **A profile setting to switch off direct runs.** Nothing needs it, and the profile loader
  refuses a key nothing enforces.

## Non-functional requirements

- **Accessibility (C6).** The shell targets WCAG 2.2 AA, above the Blueprint's 2.1 baseline.
  Interactive widgets come from React Aria Components. A status is never shown by colour alone.
  CI runs ESLint with `jsx-a11y`, Vitest with axe, and Playwright (`app/web/e2e/shell.spec.ts`):
  axe in light and dark, keyboard-only journeys, and reflow at 320 CSS pixels (400% zoom) without
  horizontal scrolling. Automated checks find only some failures; the rest is human review
  ([Evaluation and conformance](evaluation.md)). Chat content needs particular care
  (`docs/ui/best-practices.md`).
- **Colour scheme.** Light by default whatever the system prefers; the person's choice of dark is
  remembered in that browser (`shell.spec.ts`).
- **Privacy.** No font or other asset is fetched from a third party; the typeface is self-hosted.
  A problem report is public, and the page says so and shows what will be sent beside the form.
- **Security.** The feedback token is a secret the app holds, read from the environment or a
  credential file; give it no scope beyond Issues on the one repository. Anyone who can reach the
  app can file a public issue as the project's bot. A delegation grant is a bearer token, so the
  app warns at start-up when it is not bound to a loopback address. TODO(#17): authenticate
  callers.

## Open questions

- TODO(#411): end-to-end journeys in a browser against the real server; the Playwright suite
  answers `/api` from fixtures.
- TODO(#244): whether the shell's tests feed `CONFORMANCE.md`; until then they carry no
  requirement marker and C6 rests on review.
- TODO(#68, #69, #159): streamed runs and replies over AG-UI, the activity log, live regions and
  cancellation.
- TODO(#72, #73): the review gate, and how the conversation docks once there is a working
  surface. A suspended child's card says it is waiting for review.
- TODO(#160): the project's documents and current phase in the workspace, and starting a
  conversation in an existing project.
- TODO(#67): no agent declares limits, reliability or data handling yet.
- TODO(#153): every signed-in person still sees every run and conversation.
- TODO(#188): the report limits are provisional and counted for the whole process, not per
  person.
- TODO(#254): integers in a payload arrive as floats over A2A.
