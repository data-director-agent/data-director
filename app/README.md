# Data Director app (alpha)

[![CI](https://github.com/data-director-agent/data-director/actions/workflows/ci.yml/badge.svg)](https://github.com/data-director-agent/data-director/actions/workflows/ci.yml) [![Coverage](https://codecov.io/gh/data-director-agent/data-director/graph/badge.svg?flag=app)](https://codecov.io/gh/data-director-agent/data-director?flags[0]=app)

**Alpha** (`0.2.0a1`). This is the Data Director that people use: a browser shell drawn from each
agent's manifest, over the harness (ADR-0024). It is exploratory, and its shape will change.

The shell names no agent. It shows every agent the harness has registered, each with three tabs:

- **Run**: a form drawn from the agent's input class (or JSON), with example inputs. A run goes
  through the conductor; the page then shows the conductor's stages, the outcome (succeeded,
  abstained, referred or failed, each with what it means and what to do next), the result laid
  out from its schema with derivation badges, and the evidence each result rests on with the
  grounding and source checks' reports.
- **About**: what it takes and returns, how it grounds its results, how each field is produced,
  and whether this deployment's policy profile permits it. A limit or a reliability an agent has
  not declared is shown as "Not declared", never filled in.
- **History**: its stored runs, each of which reopens in the same view.

The app opens on a conversation with the orchestrator, the agent whose grounding mode is
`delegation` (ADR-0024). Each reply and each delegated child is labelled `agent_id@agent_version`,
a child opens its run, and past conversations reopen. Without a permitted orchestrator the page
says so and links to the pages above, which are one step away (#131).

The conversation sits in the centre of a workspace (ADR-0024 §18):

- across the top, whom the work acts for and whose policy applies, then the project's dataset,
  phase, repository and governance flags, which are not built yet (#160);
- on the left, the Blueprint's six phases and their steps, from `GET /api/process-flow`, each step
  naming the agents here whose manifest `serves` its requirements (ADR-0028);
- on the right, the delegated run the researcher opened, with its stages, outcome and evidence,
  or, with none open, what the orchestrator is and what it has not declared;
- beneath, the activity log, which needs streamed runs (#68, #69).

On a narrow screen the zones stack in that order, and an open run is its own view.

What is not built yet is drawn in place, marked "Not built yet", with a link to the issue that
builds it, rather than filled with invented data (#75). `docs/ui/best-practices.md` is the design
input.

It is built from:

- `app/web`: React and TypeScript, built with [Vite](https://vite.dev/), with widgets from
  [React Aria Components](https://react-spectrum.adobe.com/react-aria/) and neutral design tokens
  (`app/web/src/tokens/neutral.css`);
- `dd_app`: a [Starlette](https://www.starlette.io/) server, which also serves the built shell:
  - `GET /api/agents`: each agent's manifest beside what the profile assigns it;
  - `POST /api/runs` (`{agent_id, input}`): runs the agent through the conductor and answers when
    it has ended, with the envelope and the checks' reports. A request refused before it runs is
    a 400 with Problem Details;
  - `GET /api/runs` and `GET /api/runs/{id}`: the run store, newest first;
  - `GET /api/examples`: the example inputs in `config/examples/`;
  - `GET /api/process-flow`: the Blueprint's entry points and phases (`dd_sdk.process_flow`);
  - `POST /api/conversations`: starts a conversation and gives its `conversation_id`;
  - `POST /api/conversations/{id}/turns` (`{agent_id, message_text}`): sends one `Message` to
    the agent through the conductor and answers as `POST /api/runs` does. The server builds the
    message's history from the stored turns; a request that gives one is refused (ADR-0024 §17);
  - `GET /api/conversations` and `GET /api/conversations/{id}`: the stored conversations, most
    recently active first, and one conversation's turns, each with its delegated children, the
    stored inputs, version changes per agent and the history;
  - `POST /a2a` and `GET /.well-known/agent-card.json`: the conductor's A2A endpoint, which
    takes a delegation agent's call back under its grant (ADR-0012) and refuses every other
    request, so the app is no general A2A way in;
- the harness (`harness/`, `dd_harness`), whose conductor governs every run. The app runs no agent
  in its own process; it reaches each over A2A (ADR-0027).

## Run it

Node 22 or later, once, from `app/web`:

```bash
npm ci && npm run build            # writes app/web/dist
```

Then from the repository root:

```bash
export DD_PRINCIPAL_ID=https://orcid.org/...  DD_PRINCIPAL_NAME="..."   # whom runs act for
uv run data-director               # opens http://127.0.0.1:7860
```

The agents are separate services. Start them with `scripts/run-agents.sh` from the
repository root before the app, which reads their cards once at start-up; one that is not
running is listed as unavailable. The orchestrator runs the agents it delegates to through the
app's own A2A endpoint, under a grant the conductor issues for that run.

To run it on a server that keeps itself up to date with `main`, see `deploy/README.md`.

`DD_APP_HOST` and `DD_APP_PORT` change the address. The agents call the app back on
`http://DD_APP_HOST:DD_APP_PORT`; set `DD_HARNESS_URL` if they reach it at another address. To work on the shell, run the server as
above and `npm run dev` in `app/web`, which proxies `/api` to it (set `DD_APP_URL` if it is
elsewhere).

## Configuration

The app supplies its own configuration to the harness (ADR-0022). Its reference set is in
`config/`:

| File | What it is | Override |
|---|---|---|
| `config/profile.yaml` | The institutional profile. It enables every in-tree agent. | `DD_PROFILE` |
| `config/agents.yaml` | Agents reached over A2A: every in-tree agent. | `DD_AGENTS_CONFIG` |
| `config/sources.yaml` | The pinned FAIRsharing snapshot the source check uses. | `DD_SOURCES_CONFIG` |
| `config/examples/` | Example inputs the Run tab offers, copied from the workbench's samples. TODO: agents should declare their own (#108). | — |
| `runs/` (not committed) | Where each run is stored. | `DD_RUNS_DIR` |

`DD_PRINCIPAL_ID` and `DD_PRINCIPAL_NAME` are required. Until there is authentication (#17),
every run acts for this operator, not for the person using the page (ADR-0018), and the page
says so. The app stops at start-up, with one line, if either is unset, a file is missing or
malformed, or the shell has not been built.

### Version and problem reports

`GET /api/about` names the build: the app and harness versions, and the commit (`DD_REVISION`,
else a `REVISION` file at the root of a deployed release, else `git` in a checkout). The
"Report a problem" page, linked from the banner, shows it and files a GitHub issue through
`POST /api/feedback` (ADR-0030). It is on only if `DD_FEEDBACK_GITHUB_TOKEN` (or `_FILE`) is
set; `DD_FEEDBACK_REPO` names the repository. A report carries what the person typed, the
build, the page, and, if they agree, the identifiers of the run and conversation, never their
inputs or results.

A delegation grant is a bearer token: whoever holds it may run agents for the operator while
the run that issued it lasts. Until callers are authenticated (#17), keep the app's port, like
the agents' ports, on the host or a private network (ADR-0011). The app warns at start-up if
`DD_APP_HOST` is not a loopback address.

### Choosing the orchestrator

The home page converses with the agent the profile names under `orchestrator` (ADR-0024 §10),
and the app refuses a conversation turn to any other. The reference profile names the
rule-based `director.stub`, which needs no model key: its replies are templates, and it routes
by its `routing.yaml`.

The model-backed `orchestrator.model` (`agents/orchestrator/`) decides which agents to ask
from what each one declares, and writes its replies with a model. To use it, give it a model key
(`workbench/agents/orchestrator.env` in development, `deploy/README.md` on a server), and in the
profile the app runs under set

```yaml
version: 5                         # one more than before
orchestrator: orchestrator.model
```

When the named agent is not running, does not delegate, or is not permitted, the home page says
so and links to the agent directory; it does not fall back to another agent.

## Layout and styles

Every page is the same frame (`web/src/components/frame/Frame.tsx`): a banner holding the name,
the main navigation and the dark mode switch, identical on every page so that nothing in it
moves, and one `main`. Each page opens with a `PageHeader` (its `h1` and what the reader needs
before the content). What a page acts for is said in the page, not in the banner.

Styles are plain CSS in cascade layers, declared once in `web/src/styles/index.css`:
`reset`, `base` (element defaults), `layout` (page grids), `components` and `utilities`. Order of
layers, not selector specificity, decides which rule wins.

- **Where a rule goes.** Page layout and each page's grid are in `styles/layout.css`; patterns
  used by several components (statuses, callouts, fields, data tables) in `styles/patterns.css`;
  anything else beside its component (`RunForm.tsx` imports `RunForm.css`), wrapped in
  `@layer components`. A component does not set its own outer margins or grid placement.
- **Names.** Classes are kebab-case and start with their component's name (`app-nav-link`,
  `stage-name`).
- **State.** Selected, current and hovered come from ARIA and React Aria attributes
  (`[aria-current="page"]`, `[data-selected]`), not modifier classes. A selected item is marked by
  colour and a bar, never by a change of weight, so selecting it does not shift its neighbours.
- **Values.** Every colour, size and font is a token from `web/src/tokens/neutral.css`
  (ADR-0024 §5). Stylelint (`web/.stylelintrc.json`, part of `npm run lint`) rejects a literal
  colour outside the token file.

## Tests

```bash
uv run pytest app/tests            # the server; keeps app/web/fixtures current
cd app/web
npm run lint && npm run typecheck && npm test      # ESLint (with jsx-a11y), Stylelint, tsc, Vitest + axe
npx playwright install chromium && npm run e2e      # axe light and dark, keyboard, 400% reflow
```

The shell's tests draw manifests from `app/web/fixtures/`. `app/tests/test_app.py` builds them
from the real server and fails if they drift; `DD_WRITE_FIXTURES=1 uv run pytest app/tests`
rewrites them. `agents-several.json` holds five agents of different grounding modes and payload
shapes, under a profile that does not list the standards advisor, so the shell is tested on more than one agent.

## What it does not do

- A run is one request that answers when the run has ended, so the stages are read back
  afterwards rather than watched, and a run cannot be cancelled. Streaming runs over AG-UI
  replaces it (#68, #69).
- There is no human review of proposed changes (#72, #73). The standards advisor only advises, so it proposes none.
- The form checks only required fields and numbers; the conductor's input check decides.
- The conversation is with the rule-based `director.stub` unless the profile names the
  model-backed orchestrator, which needs a key (see "Choosing the orchestrator"). Replies are not
  streamed (#159). The agent directory is its own page, `/agents`, reached
  from the navigation and from a delegated child's card (`/agents?agent=<id>` selects an agent).
- No agent declares its limits, reliability or data handling yet. That needs the oversight
  extension (ADR-0025, TODO).

This package substantiates no Blueprint requirement, and its tests carry no requirement marker.
