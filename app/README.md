# Data Director app (alpha)

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
| `config/examples/` | Example inputs the Run tab offers, copied from the workbench's samples. TODO: agents should declare their own (#108). | — |
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

- A run is one request that answers when the run has ended, so the stages are read back
  afterwards rather than watched, and a run cannot be cancelled. Streaming runs over AG-UI
  replaces it (#68, #69).
- There is no human review of proposed changes (#72, #73). R3 only advises, so it proposes none.
- The form checks only required fields and numbers; the conductor's input check decides.
- There is no language-model chat. The Gradio chat this replaced is gone (ADR-0024); chat for
  intent returns as an orchestrator under `delegation` grounding (ADR-0012, #21).
- No agent declares its limits, reliability or data handling yet. That needs the oversight
  extension (ADR-0025, TODO).

This package substantiates no Blueprint requirement, and its tests carry no requirement marker.
