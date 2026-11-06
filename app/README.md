# Data Director app (alpha)

[![CI](https://github.com/data-director-agent/data-director/actions/workflows/ci.yml/badge.svg)](https://github.com/data-director-agent/data-director/actions/workflows/ci.yml) [![Coverage](https://codecov.io/gh/data-director-agent/data-director/graph/badge.svg?flag=app)](https://codecov.io/gh/data-director-agent/data-director?flags[0]=app)

**Alpha** (`0.2.0a1`). This is the Data Director that people use: a browser shell drawn from each
agent's manifest, over the harness ([The app](../docs/specs/app.md)). It is exploratory, and its shape will change.

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
`delegation` ([The app](../docs/specs/app.md)). Each reply and each delegated child is labelled `agent_id@agent_version`,
a child opens its run, and past conversations reopen. Without a permitted orchestrator the page
says so and links to the pages above, which are one step away (#131).

The conversation sits in the centre of a workspace ([The app](../docs/specs/app.md)):

- across the top, whom the work acts for and whose policy applies, then the project's dataset,
  phase, repository and governance flags, which are not built yet (#160);
- on the left, the six data management phases and their steps, from `GET /api/process-flow`, each step
  naming the agents here whose manifest `serves` the step ([Orchestration](../docs/specs/orchestration.md));
- on the right, the project's documents, which are not built yet (#160), and what the
  orchestrator is and what it has not declared;
- beneath, the activity log, which needs streamed runs (#68, #69).

Each run the orchestrator delegates is a card in the conversation; opening it shows the run's
stages, outcome and evidence inside the card. On a narrow screen the zones stack in that order.

The **Policy** page shows the deployment's institutional profile, the rules the policy gate holds
every run to: its reference and digest, the agent a conversation goes to, each agent it allows
with its action class, and which action classes need a data steward's approval
([The app](../docs/specs/app.md)).

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
  - `POST /api/conversations/{id}/turns` (`{agent_id, message_text, follows}`): sends one
    `Message` to the agent through the conductor and answers as `POST /api/runs` does. The server
    builds the message's history from the stored turns; a request that gives one is refused
    (docs/specs/app.md). `follows` is the `invocation_id` of the latest turn, or null for the first:
    a turn that does not follow the latest, or that arrives while another turn of the
    conversation is running, is refused with a 409 `turn-conflict` and nothing runs
    (docs/specs/orchestration.md), so a message sent again after a dropped connection is never run twice;
  - `GET /api/conversations` and `GET /api/conversations/{id}`: the stored conversations, most
    recently active first, and one conversation's turns, each with its delegated children, the
    stored inputs, version changes per agent and the history;
  - `GET /api/projects/{id}/documents`: a project's documents, each version with its text and
    state as the project log records it, and the harness's rule for when a decision needs a
    reason. The shell draws it at `/projects/{id}`;
  - `POST /api/projects/{id}/documents/{document_id}/decisions`
    (`{version, digest, decision, reason?, edited_text?}`): approves or rejects the latest
    version, or approves an edit of it, for the person signed in; a body that names a decider is
    refused. A decision on a version that is no longer the latest or undecided, or whose
    `digest` is not that of its text, is a 409 and is recorded as refused
    ([Projects](../docs/specs/projects.md));
  - `POST /a2a` and `GET /.well-known/agent-card.json`: the conductor's A2A endpoint, which
    takes a delegation agent's call back under its grant ([Orchestration](../docs/specs/orchestration.md)) and refuses every other
    request, so the app is no general A2A way in;
- the harness (`harness/`, `dd_harness`), whose conductor governs every run. The app runs no agent
  in its own process; it reaches each over A2A ([The app](../docs/specs/app.md)).

## Run it

From the repository root:

```bash
uv run scripts/dd.py setup        # once: whom runs act for, an optional model key; installs, builds
uv run scripts/dd.py start        # the agents, the app (:7860) and the Vite dev server (:5173)
```

`start` builds the shell again whenever `app/web` has changed since the last build, starts every
agent in `config/agents.yaml`, waits for each, and then starts the app and `npm run dev`, which
proxies `/api` to it. Ctrl-C stops them all. `uv run scripts/dd.py doctor` says what is wrong
when something is. The README at the repository root, "Quick start", has the steps by hand.

By hand, with Node 22 or later, from `app/web`:

```bash
npm ci && npm run build            # writes app/web/dist
```

Then from the repository root:

```bash
export DD_PRINCIPAL_ID=https://orcid.org/...  DD_PRINCIPAL_NAME="..."   # whom runs act for (or sign in, below)
uv run data-director               # opens http://127.0.0.1:7860
```

The agents are separate services. Start them with `scripts/run-agents.sh` from the
repository root before the app; one that is not running is listed as unavailable, and is found
when it starts. The orchestrator runs the agents it delegates to through the
app's own A2A endpoint, under a grant the conductor issues for that run.

To run it on a server that keeps itself up to date with `main`, see `deploy/README.md`.

`DD_APP_HOST` and `DD_APP_PORT` change the address. The agents call the app back on
`http://DD_APP_HOST:DD_APP_PORT`; set `DD_HARNESS_URL` if they reach it at another address. To work on the shell, run the server as
above and `npm run dev` in `app/web`, which proxies `/api` to it (set `DD_APP_URL` if it is
elsewhere).

## Configuration

The app supplies its own configuration to the harness ([System and boundaries](../docs/specs/system.md)). Its reference set is in
`config/`:

| File | What it is | Override |
|---|---|---|
| `config/profile.yaml.example` | The institutional profile. It enables every in-tree agent. Copy it to `config/profile.yaml` (not committed) to edit it locally; the app prefers that copy. | `DD_PROFILE` |
| `config/agents.yaml` | Agents reached over A2A: every in-tree agent. | `DD_AGENTS_CONFIG` |
| `config/sources.yaml` | The pinned FAIRsharing snapshot the source check uses. | `DD_SOURCES_CONFIG` |
| `config/examples/` | Example inputs, copied from the workbench's samples. TODO(#108): agents should declare their own. | — |
| `runs/` (not committed) | Where each run is stored. | `DD_RUNS_DIR` |
| `projects/` (not committed) | Each project's log, with its documents and the decisions on them. | `DD_PROJECTS_DIR` |

`scripts/dd.py` writes the profile the app runs under, `config/local/profile.yaml`, from the
example and `config/local/deployment.yaml`, and names it with `DD_PROFILE`. It does this again
on each `start`, so the profile follows the example. To choose the orchestrator or leave an
agent out, edit `deployment.yaml`.

Without `DD_PROFILE`, the app uses `config/profile.yaml` in place of the example when that file
exists. It is not committed:

```bash
cp app/config/profile.yaml.example app/config/profile.yaml
```

Edit the copy (raise `version` when you change it). Delete it to return to the example.

This copy is the fallback. `scripts/dd.py apply` generates a profile from `deployment.yaml`
(`config/local/profile.yaml`) and names it in `DD_PROFILE`, which takes precedence; the
orchestrator and the agents that run are better changed there
([the command](../docs/guide/operations/commands.md)).

The copy does not follow the example: an agent added to the example later is not enabled in it,
and the app refuses that agent as not enabled. `scripts/dd.py start` and `doctor` name any agent
the example enables that the copy omits; add it to the copy, or delete the copy.

The app stops at start-up, with one line, if a setting is unset or wrong, a file is missing or
malformed, or the shell has not been built.

### Who a run acts for: signing in

With `DD_OIDC_ISSUER` set, people sign in with ORCID, and each run acts for the person who
started it, recorded as `authenticated` with the issuer that vouched ([Policy and identity](../docs/specs/policy-and-identity.md)):

| Variable | What it is |
|---|---|
| `DD_OIDC_ISSUER` | `https://orcid.org`, or `https://sandbox.orcid.org` for development. |
| `DD_OIDC_CLIENT_ID` | The ORCID public API client's ID (`APP-…`). |
| `DD_OIDC_CLIENT_SECRET` or `_FILE` | Its secret, or a file that holds it. |
| `DD_APP_PUBLIC_URL` | Where people reach the app. The client's redirect URI is this followed by `/api/sign-in/callback`. Defaults to `http://DD_APP_HOST:DD_APP_PORT`. |
| `DD_SESSION_IDLE_S`, `DD_SESSION_LIFETIME_S` | A session ends after this long unused (8 hours) or this long at most (7 days). |

To try it locally, register a client through ORCID's
[sandbox registration page](https://info.orcid.org/register-a-client-application-sandbox-member-api/)
with the redirect URI `http://127.0.0.1:7860/api/sign-in/callback`. Sign in with a sandbox account:
create one at `https://sandbox.orcid.org/register`, using a `@mailinator.com` address, since the
sandbox only sends email there, and verify it before editing records. Sandbox data is not backed up
and may be deleted (#178). Open the app at `http://127.0.0.1:7860`, not `localhost`, so the sign-in
cookie returns with the callback; the [operations guide](../docs/guide/operations/configuration.md#trying-sign-in-against-the-orcid-sandbox)
has the full set-up and what its failures mean. A test needs neither: `dd_harness.testing.FakeIdentityProvider` stands in
for ORCID.

- The app serves the sign-in routes and runs the harness's authorisation-code flow
  (`dd_harness.signin`), which asks for the `openid` scope alone and verifies the ID token with
  `verify_id_token`. It keeps the principal in a server-side session (`dd_harness.sessions`) and no
  token. The browser holds an
  opaque `HttpOnly`, `Secure`, `SameSite=Lax` cookie. Browsers treat `127.0.0.1` as secure, so
  this works over plain HTTP locally; a deployment needs HTTPS (#155).
- Every `/api` route that runs or reads anything answers `401` with an `unauthenticated` problem
  when there is no session, and the shell then shows its sign-in page. `/api/about`,
  `/api/session` and the sign-in routes are open, as is `/server-status`, which answers a monitor's
  `GET /server-status?auto` (collectd's apache plugin) with the app's uptime in `Key: value` lines.
- Sessions are held in memory, so restarting the app signs everyone out.
- Signing out ends the session here. ORCID offers no sign-out for the app, so the person may still
  be signed in at ORCID, and the signed-out page says so.
- TODO(#153): every signed-in person still sees every run and conversation.

Without `DD_OIDC_ISSUER` the app is a development server. `DD_PRINCIPAL_ID` and
`DD_PRINCIPAL_NAME` are then required, every run acts for this operator, not for the person
using the page ([Policy and identity](../docs/specs/policy-and-identity.md)), and the banner says on every page that nobody is signed in. Setting
both a provider and an operator principal stops start-up.

### Version and problem reports

`GET /api/about` names the build: the app and harness versions, and the commit (`DD_REVISION`,
else a `REVISION` file at the root of a deployed release, else `git` in a checkout), and what
the deployment runs: the profile (`id`, `version`, `digest`, `orchestrator`) and the names of the
configured agents it cannot reach (`unavailable`, `incompatible`). It needs no session, so an
operator can check a server without signing in. The
footer of every page shows it, and the
"Report a problem" page, linked from the banner, shows it too and files a GitHub issue through
`POST /api/feedback` ([The app](../docs/specs/app.md)). It is on only if the app holds a credential for
GitHub, and then only one of these: a **GitHub App** (`DD_FEEDBACK_GITHUB_APP_ID` and
`DD_FEEDBACK_GITHUB_APP_PRIVATE_KEY_FILE`, the PEM key's path, relative to `$CREDENTIALS_DIRECTORY`
under systemd; `DD_FEEDBACK_GITHUB_APP_INSTALLATION_ID` is optional), or a fine-grained
**token** (`DD_FEEDBACK_GITHUB_TOKEN`, or `_FILE`). The App is preferred, since it belongs to the
organisation and its tokens expire by themselves; [Problem reports](../deploy/README.md#problem-reports)
says how to create it. `DD_FEEDBACK_REPO` names the repository. A report carries what the person typed, the
build, the page, and, if they agree, the identifiers of the run and conversation, never their
inputs or results.

A delegation grant is a bearer token: whoever holds it may run agents for the operator while
the run that issued it lasts. Until callers are authenticated (#17), keep the app's port, like
the agents' ports, on the host or a private network ([Agents](../docs/specs/agents.md)). The app warns at start-up if
`DD_APP_HOST` is not a loopback address.

### Choosing the orchestrator

The home page converses with the agent the profile names under `orchestrator` ([The app](../docs/specs/app.md)),
and the app refuses a conversation turn to any other. The example profile names the
rule-based `orchestrator.stub`, which needs no model key: its replies are templates, and it routes
by its `routing.yaml`.

The model-backed `orchestrator.model` (`agents/orchestrator-model/`) decides which agents to ask
from what each one declares, and writes its replies with a model. To use it:

1. Give it a model key: `uv run scripts/dd.py secret set orchestrator-model anthropic-api-key`,
   or `sudo data-director secret set …` on a server.
2. Set `orchestrator: model` in `deployment.yaml`: `config/local/` in development,
   `/etc/data-director/` on a server.
3. Apply it. `dd.py start` does this in development; on a server, run `sudo data-director apply`.

`apply` writes the profile the app runs under, with `orchestrator: orchestrator.model` and a raised
`version` ([Configuration](../docs/guide/operations/configuration.md)). In development,
`uv run scripts/dd.py setup` does steps 1 and 2 when you give it a key.

When the named agent is not running, does not delegate, or is not permitted, the home page says
so and links to the agent directory; it does not fall back to another agent.

## Layout and styles

Every page is the same frame (`web/src/components/frame/Frame.tsx`): a banner holding the name,
the main navigation, who is signed in and the dark mode switch, identical on every page so that
nothing in it moves, and one `main`. Each page opens with a `PageHeader` (its `h1` and what the reader needs
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
- **Values.** Every colour, size, weight, shadow and font is a token from
  `web/src/tokens/neutral.css` ([The app](../docs/specs/app.md)). Stylelint (`web/.stylelintrc.json`, part of
  `npm run lint`) rejects a literal colour outside the token file. The typeface, Inter, is
  self-hosted from `@fontsource-variable/inter`; no font is fetched from a third party.
- **Imports.** `npm run lint` also checks the import graph: dependency-cruiser
  (`web/.dependency-cruiser.cjs`) rejects cycles, and eslint-plugin-boundaries
  (`web/eslint.config.js`) keeps `components/ui` free of feature components and the domain
  folders free of components ([The app](../docs/specs/app.md)).
- **Icons.** Icons are [Lucide](https://lucide.dev) (`lucide-react`, ISC licence), bundled with
  the app and imported one by one. A button takes one through its `icon` prop. The icon is
  decoration and hidden from screen readers, so the label alone says what the button does.
- **Controls.** Buttons come from the shell's kit, `web/src/components/ui/Button.tsx`: React
  Aria's `Button` and `ToggleButton` in four variants (`primary` for the one action a view exists
  for, `secondary` by default, `quiet` beside the content it acts on, `danger` to remove what the
  reader entered) and two sizes. An action under way takes `isPending`, which keeps the focus.
  ESLint rejects a bare `<button>`. Text fields, text areas and selects share the buttons' height,
  radius and focus ring (`styles/base.css`).

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
- A person can approve, edit then approve, or reject a project's documents at `/projects/{id}`,
  but no run adds a document to a project yet (#394), nothing links to that page, and anyone
  signed in can decide (#389). Risk tiers and batching for review are #72 and #73.
- The form checks only required fields and numbers; the conductor's input check decides.
- The conversation is with the rule-based `orchestrator.stub` unless the profile names the
  model-backed orchestrator, which needs a key (see "Choosing the orchestrator"). Replies are not
  streamed (#159). The agent directory is its own page, `/agents`, reached
  from the navigation and from a delegated child's card (`/agents?agent=<id>` selects an agent).
- No agent declares its limits, reliability or data handling yet. That needs the oversight
  extension, TODO(#67).

This package substantiates no Blueprint requirement, and its tests carry no requirement marker.
