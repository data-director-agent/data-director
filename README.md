# Data Director

[![CI](https://github.com/data-director-agent/data-director/actions/workflows/ci.yml/badge.svg)](https://github.com/data-director-agent/data-director/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/data-director-agent/data-director/graph/badge.svg)](https://codecov.io/gh/data-director-agent/data-director)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/data-director-agent/data-director)

The Data Director is an agentic AI tool for research data stewardship. It helps researchers to make their data [FAIR](https://www.go-fair.org/fair-principles/) (Findable, Accessible, Interoperable, and Reusable), select an appropriate data repository for archiving, draft metadata records, a README and data dictionaries, to create deposit-ready packages with an audit trail.

This is proposed _reference implementation_ for the [Data Director Agentic AI Blueprint](https://doi.org/10.15497/RDA00157) developed under the coordination of the [Research Data Alliance Data Director Working Group](https://www.rd-alliance.org/groups/data-director-agentic-ai-blueprint/activity/). The Blueprint followed an RDA community consultation, reported in [Global Community Priorities for Agentic AI in Research. Community Consultation Results](https://doi.org/10.15497/RDA00151).

## Overview

[![Towards a Data Director reference implementation — video](https://cdnapisec.kaltura.com/p/2103181/sp/210318100/thumbnail/entry_id/1_f0c1kkwg/width/640)](https://digitalmedia.sheffield.ac.uk/media/Towards+a+Data+Director+reference+implementation/1_f0c1kkwg)

[Towards a Data Director reference implementation](https://digitalmedia.sheffield.ac.uk/media/Towards+a+Data+Director+reference+implementation/1_f0c1kkwg) is a recorded introduction to this project. It is also posted on the [RDA working group page](https://www.rd-alliance.org/groups/data-director-agentic-ai-blueprint/posts/towards-a-data-director-reference-implementation/).

## Quick start

You need Python 3.14, [`uv`](https://docs.astral.sh/uv/), Node 22 or later (for the app's browser
shell) and a Bash shell (on Windows, use WSL). No account or API key is needed.

Clone the repository, then from its root, which is a uv workspace:

```sh
uv sync --all-packages --all-extras   # installs every package in the workspace
uv run pytest                         # network blocked; everything runs offline
```

Every invocation acts for a named person, so set who that is before running anything:

```sh
export DD_PRINCIPAL_ID=https://orcid.org/0000-0002-1825-0097   # your ORCID iD, or another IRI
export DD_PRINCIPAL_NAME="Josiah Carberry"                     # your name
```

There are two ways to run it. They are separate: the app does not start the agents, and the
agents do not start the app.

### Run the app

Build its shell once, then start the server. The `DD_PRINCIPAL_*` variables above must be set in
this terminal:

```sh
(cd app/web && npm ci && npm run build)
uv run data-director                  # opens http://127.0.0.1:7860
```

The app lists the agents named in `app/config/agents.yaml`, which it reaches over A2A. It starts
none of them, so the agent directory is empty ("No agents are registered with this deployment")
until they are running. Start them first, in a second terminal:

```sh
scripts/run-agents.sh                 # leave it running; Ctrl-C stops every agent
```

Then reload the page. Check which agents the app can reach with
`curl http://127.0.0.1:7860/api/agents`; an agent it could not reach is under `unavailable`, with
the reason.

`dd-orchestrator` stops at start-up with "no model key" unless it has one. This is expected and
the other agents keep running. The reference profile converses with `director.stub`, which needs
no key, so you can ignore it.

To use the orchestrator, give it a model key. The agents are separate from the workbench, but
`scripts/run-agents.sh` is a development convenience and looks for each agent's settings in
`workbench/agents/<name>.env`. That directory holds only settings files, no agent code. From the
repository root:

```sh
cp workbench/agents/env.example workbench/agents/orchestrator.env
```

Set `ANTHROPIC_API_KEY` in `workbench/agents/orchestrator.env`, then stop and restart
`scripts/run-agents.sh`. The file is ignored by git. See
[`app/README.md`](app/README.md#choosing-the-orchestrator). On a server the same settings live
in `/etc/data-director/agents/orchestrator.env` (see [`deploy/README.md`](deploy/README.md)).

If an agent will not start, or the agent directory stays empty, read the terminal running
`scripts/run-agents.sh`, which shows each agent's own start-up errors.

> **Known problem:** while any configured agent is not running (including `dd-orchestrator`
> without a key), `GET /api/agents` can fail with a 500 error ("asyncio.run() cannot be called
> from a running event loop"), and the page shows no agents. Until that is fixed, give
> `dd-orchestrator` a key, or remove it from `app/config/agents.yaml`.

To work on the shell with hot reload, leave `uv run data-director` running and start the Vite
development server in a second terminal. It proxies `/api` to the app (set `DD_APP_URL` if the app
is at another address):

```sh
cd app/web
npm ci                                # first time only
npm run dev                           # then open http://localhost:5173
```

### Develop and test agents

Start the agents in one terminal and use the workbench from a second terminal in `workbench/`:

```sh
scripts/run-agents.sh                 # first terminal; leave it running
```
```sh
cd workbench
uv run workbench serve                # then open http://127.0.0.1:8000/viewer/
```

To run the whole development stack in containers instead, you need only Docker with Compose.
Source is bind-mounted, so edits to Python and to the shell take effect without a rebuild:

```sh
cp docker/env.example .env            # then set DD_PRINCIPAL_ID and DD_PRINCIPAL_NAME
docker compose up --build             # app at http://127.0.0.1:7860, shell at :5173
docker compose --profile workbench up workbench   # viewer at http://127.0.0.1:8000/viewer/
docker compose --profile llm up       # adds the model-backed orchestrator
```

The first start installs the dependencies into a volume, which takes a few minutes. The agents are
reachable only inside the Compose network. Model keys go in `workbench/agents/<name>.env`, as when
running locally. If a host port is taken, set `DD_APP_HOST_PORT`, `DD_WEB_HOST_PORT` or
`DD_WORKBENCH_HOST_PORT` in `.env`. Containers run as uid 1000. This stack is for development only;
`deploy/` covers deployment.

### Settings in `workbench/.env`

`scripts/run-agents.sh` and the workbench read `workbench/.env` if it exists (copy
`workbench/env.example`). It is an ordinary dotenv file, so quote a value that contains a space:
`DD_PRINCIPAL_NAME="Josiah Carberry"`. An unquoted one gives
"Failed to parse environment file `workbench/.env`", and the file is not applied. Put a model key
only in that agent's own file, `workbench/agents/<name>.env` (for example `orchestrator.env`),
never in `workbench/.env`, which every agent reads.

[`docs/architecture.md`](docs/architecture.md) explains how the parts fit together. Each part of
the repository has its own README with the details:

| Directory | What it is |
|---|---|
| [`app/`](app/README.md) | The Data Director app (alpha): a browser shell drawn from each agent's manifest, and its configuration |
| [`harness/`](harness/README.md) | The governance every invocation goes through, and `dd-harness serve` for deployments |
| [`workbench/`](workbench/README.md) | The development test bed: the `workbench` CLI, the viewer, samples and profiles |
| [`agents/`](agents/README.md) | One package and one A2A service per agent, and how to write a new one from `hello/` |
| [`sdk/`](sdk/README.md) | What agents and the harness share: the contract, evidence, span helpers and the agent server |

## Contributing

This is a community-driven, open-source project. See:

- [Blueprint](docs/BLUEPRINT.md) — the Data Director Agentic AI Tool Blueprint (RDA, CC BY 4.0), reproduced here as Markdown
- [Project charter](https://github.com/data-director-agent/.github/blob/main/CHARTER.md) — the project's mission and scope
- [Governance](https://github.com/data-director-agent/.github/blob/main/GOVERNANCE.md) — how decisions are made and how the maintainer group grows
- [Contribution guide](CONTRIBUTING.md) — this repository's structure and tooling; the organisation-wide [contribution guide](https://github.com/data-director-agent/.github/blob/main/CONTRIBUTING.md) covers RFCs, sign-off and pull requests
- [Code of conduct](https://github.com/data-director-agent/.github/blob/main/CODE_OF_CONDUCT.md) — expected standards of behaviour
- [Software management plan](docs/SOFTWARE_MANAGEMENT_PLAN.md) — the software management plan
- [App](app/) — the Data Director itself (alpha): a browser shell drawn from each agent's manifest (ADR-0024)
- [Harness](harness/) — the governance every agent invocation goes through: the policy gate, input check, grounding linter, source check, run store and provenance
- [Workbench](workbench/) — development environment for building and testing sub-agents: the invocation contract (LinkML), a standards advisor over FAIRsharing, an abstaining stub, and a read-only viewer
- [Decision records](docs/adr/) — the architecture decisions that govern every package, with the requirements register and the generated [`CONFORMANCE.md`](CONFORMANCE.md)
