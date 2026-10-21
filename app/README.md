# Data Director app (alpha)

**Alpha** (`0.2.0a1`). This is the Data Director that people use: a browser shell drawn from each
agent's manifest, over the harness (ADR-0024). It is exploratory, and its shape will change.

The shell names no agent. It shows every agent the harness has registered: what it takes and
returns, how it grounds its results, how each field is produced, and whether this deployment's
policy profile permits it. A limit or a reliability an agent has not declared is shown as "Not
declared", never filled in. Later increments add runs, progress, evidence, abstain and refer
screens, and a review gate (`docs/ui/best-practices.md` is the design input).

It is built from:

- `app/web`: React and TypeScript, built with [Vite](https://vite.dev/), with widgets from
  [React Aria Components](https://react-spectrum.adobe.com/react-aria/) and neutral design tokens
  (`app/web/src/tokens/neutral.css`);
- `dd_app`: a [Starlette](https://www.starlette.io/) server with `GET /api/agents`, which also
  serves the built shell;
- the harness (`harness/`, `dd_harness`), whose conductor governs every run. R3
  (`r3.standards-advisor`) runs in the app's process.

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

`DD_APP_HOST` and `DD_APP_PORT` change the address. To work on the shell, run the server as
above and `npm run dev` in `app/web`, which proxies `/api` to it (set `DD_APP_URL` if it is
elsewhere).

## Configuration

The app supplies its own configuration to the harness (ADR-0022). Its reference set is in
`config/`:

| File | What it is | Override |
|---|---|---|
| `config/profile.yaml` | The institutional profile. It enables R3 only. | `DD_PROFILE` |
| `config/agents.yaml` | Agents reached over A2A. Empty: R3 runs in the app's process. | `DD_AGENTS_CONFIG` |
| `config/sources.yaml` | The pinned FAIRsharing snapshot the source check uses. | `DD_SOURCES_CONFIG` |
| `runs/` (not committed) | Where each run is stored. | `DD_RUNS_DIR` |

`DD_PRINCIPAL_ID` and `DD_PRINCIPAL_NAME` are required. Until there is authentication (#17),
every run acts for this operator, not for the person using the page (ADR-0018), and the page
says so. The app stops at start-up, with one line, if either is unset, a file is missing or
malformed, or the shell has not been built.

## Tests

```bash
uv run pytest app/tests            # the server; keeps app/web/fixtures current
cd app/web
npm run lint && npm run typecheck && npm test      # ESLint (with jsx-a11y), tsc, Vitest + axe
npx playwright install chromium && npm run e2e      # axe light and dark, keyboard, 400% reflow
```

The shell's tests draw manifests from `app/web/fixtures/`. `app/tests/test_app.py` builds them
from the real server and fails if they drift; `DD_WRITE_FIXTURES=1 uv run pytest app/tests`
rewrites them. `agents-several.json` holds five agents of different grounding modes and payload
shapes, under a profile that does not list R3, so the shell is tested on more than one agent.

## What it does not do

- It does not run agents yet. Runs, progress, evidence and review come in the next increments.
- There is no language-model chat. The Gradio chat this replaced is gone (ADR-0024); chat for
  intent returns as an orchestrator under `delegation` grounding (ADR-0012, #21).
- No agent declares its limits, reliability or data handling yet. That needs the oversight
  extension (ADR-0025, TODO).

This package substantiates no Blueprint requirement, and its tests carry no requirement marker.
