# Data Director

[![CI](https://github.com/data-director-agent/data-director/actions/workflows/ci.yml/badge.svg)](https://github.com/data-director-agent/data-director/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/data-director-agent/data-director/graph/badge.svg)](https://codecov.io/gh/data-director-agent/data-director)
[![Ask DeepWiki](https://img.shields.io/badge/Ask-DeepWiki-blue)](https://deepwiki.com/data-director-agent/data-director)

The Data Director is an agentic AI tool for research data stewardship. It helps researchers to make their data [FAIR](https://www.go-fair.org/fair-principles/) (Findable, Accessible, Interoperable, and Reusable), select an appropriate data repository for archiving, draft metadata records, a README and data dictionaries, to create deposit-ready packages with an audit trail.

This is proposed _reference implementation_ for the [Data Director Agentic AI Blueprint](https://doi.org/10.15497/RDA00157) developed under the coordination of the [Research Data Alliance Data Director Working Group](https://www.rd-alliance.org/groups/data-director-agentic-ai-blueprint/activity/). The Blueprint followed an RDA community consultation, reported in [Global Community Priorities for Agentic AI in Research. Community Consultation Results](https://doi.org/10.15497/RDA00151).

## Overview

[![Towards a Data Director reference implementation — video](https://cdnapisec.kaltura.com/p/2103181/sp/210318100/thumbnail/entry_id/1_f0c1kkwg/width/640)](https://digitalmedia.sheffield.ac.uk/media/Towards+a+Data+Director+reference+implementation/1_f0c1kkwg)

[Towards a Data Director reference implementation](https://digitalmedia.sheffield.ac.uk/media/Towards+a+Data+Director+reference+implementation/1_f0c1kkwg) is a recorded introduction to this project. It is also posted on the [RDA working group page](https://www.rd-alliance.org/groups/data-director-agentic-ai-blueprint/posts/towards-a-data-director-reference-implementation/).

## Quick start

You need [`uv`](https://docs.astral.sh/uv/getting-started/installation/), which brings Python
3.14 with it, Node 22 or later (for the app's browser shell) and a Bash shell (on Windows, use
WSL). No account or API key is needed.

Clone the repository, then from its root:

```sh
uv run scripts/dev.py setup           # asks a few questions, then installs and builds everything
uv run scripts/dev.py start           # the agents, the app and the shell; Ctrl-C stops them all
```

`setup` asks for your name and ORCID iD, because every run acts for a named person, and,
optionally, for an Anthropic API key. Without a key, the app converses with `director.stub`, a
rule-based agent, and everything else works. `setup` writes each answer to the file it belongs in,
so you never edit a settings file by hand: your name in `.env` at the root, and the key only in
the files of the agents that use it (`workbench/agents/<name>.env`), never in a file every agent
reads (ADR-0026). Run `setup` again at any time to change an answer; Enter keeps the value shown.

`start` opens nothing itself: open <http://localhost:5173>, which reloads as you edit the shell,
or <http://127.0.0.1:7860>, the app serving its built shell (`start --no-web` starts only that).
Each line of output is labelled with the service it came from. An agent that needs a model key
and has none is skipped, and says so.

If something does not work, run

```sh
uv run scripts/dev.py doctor          # checks the toolchain, the settings and the ports
```

which changes nothing and names each problem it finds, such as a missing tool, a settings file
uv cannot read, a key in the wrong file, a port already in use, or an agent the app cannot reach.

To run the tests:

```sh
uv run pytest                         # network blocked; everything runs offline
```

### By hand

`scripts/dev.py` runs these steps for you. The app does not start the agents, and the agents do
not start the app, so each needs its own terminal. Every invocation acts for a named person, so in
each terminal set who that is:

```sh
export DD_PRINCIPAL_ID=https://orcid.org/0000-0002-1825-0097   # your ORCID iD, or another IRI
export DD_PRINCIPAL_NAME="Josiah Carberry"                     # your name
```

Then install everything, build the shell, start the agents and start the app:

```sh
uv sync --all-packages --all-extras   # installs every package in the workspace
(cd app/web && npm ci && npm run build)
scripts/run-agents.sh                 # first terminal; leave it running
uv run data-director                  # second terminal; opens http://127.0.0.1:7860
```

The app lists the agents named in `app/config/agents.yaml`, which it reaches over A2A. Check
which it can reach with `curl http://127.0.0.1:7860/api/agents`; an agent it could not reach is
under `unavailable`, with the reason. For hot reload, run `npm run dev` in `app/web` as well and
open <http://localhost:5173>; it proxies `/api` to the app (set `DD_APP_URL` if the app is at
another address).

To give the orchestrator a model key by hand, copy `workbench/agents/env.example` to
`workbench/agents/orchestrator.env`, set `ANTHROPIC_API_KEY` in it, and name `orchestrator.model`
in your profile (see [`app/README.md`](app/README.md#choosing-the-orchestrator)). The file is
ignored by git. On a server the same settings live in `/etc/data-director/agents/orchestrator.env`
(see [`deploy/README.md`](deploy/README.md)).

### Develop and test agents

Start the agents in one terminal and use the workbench from a second terminal in `workbench/`:

```sh
scripts/run-agents.sh                 # first terminal; the same as `scripts/dev.py start --agents-only`
```
```sh
cd workbench
uv run workbench serve                # then open http://127.0.0.1:8000/viewer/
```

To run the whole development stack in containers instead, you need only Docker with Compose.
Source is bind-mounted, so edits to Python and to the shell take effect without a rebuild:

```sh
uv run scripts/dev.py setup --no-install   # or: cp docker/env.example .env, then edit it
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

`scripts/dev.py start` (and so `scripts/run-agents.sh`) and the workbench read `workbench/.env` if
it exists (copy `workbench/env.example`); for `dev.py`, the root `.env` that `setup` writes wins
over it. It is an ordinary dotenv file, so quote a value that contains a space:
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

- [Blueprint](docs/blueprint/README.md) — the Data Director Agentic AI Tool Blueprint v1.0 (RDA, CC BY 4.0, [doi:10.15497/RDA00157](https://doi.org/10.15497/RDA00157)), reproduced here as Markdown
- [Project charter](https://github.com/data-director-agent/.github/blob/main/CHARTER.md) — the project's mission and scope
- [Governance](https://github.com/data-director-agent/.github/blob/main/GOVERNANCE.md) — how decisions are made and how the maintainer group grows
- [Releasing](RELEASING.md) — versioning policy and how a release is made
- [Contribution guide](CONTRIBUTING.md) — this repository's structure and tooling; the organisation-wide [contribution guide](https://github.com/data-director-agent/.github/blob/main/CONTRIBUTING.md) covers RFCs, sign-off and pull requests
- [Code of conduct](https://github.com/data-director-agent/.github/blob/main/CODE_OF_CONDUCT.md) — expected standards of behaviour
- [Software management plan](docs/SOFTWARE_MANAGEMENT_PLAN.md) — the software management plan
- [App](app/) — the Data Director itself (alpha): a browser shell drawn from each agent's manifest (ADR-0024)
- [Harness](harness/) — the governance every agent invocation goes through: the policy gate, input check, grounding linter, source check, run store and provenance
- [Workbench](workbench/) — development environment for building and testing sub-agents: the invocation contract (LinkML), a standards advisor over FAIRsharing, an abstaining stub, and a read-only viewer
- [Decision records](docs/adr/) — the architecture decisions that govern every package, with the requirements register and the generated [`CONFORMANCE.md`](CONFORMANCE.md)
