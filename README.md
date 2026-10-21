# Data Director

A proposed reference implementation for the [Data Director Agentic AI Blueprint](https://doi.org/10.15497/RDA00157) developed under the coordination of the [Research Data Alliance Data Director Working Group](https://www.rd-alliance.org/groups/data-director-agentic-ai-blueprint/activity/).

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

To run the Data Director app, build its shell once and start the server:

```sh
(cd app/web && npm ci && npm run build)
uv run data-director                  # opens http://127.0.0.1:7860
```

To develop and test agents instead, start the agents in one terminal and use the workbench from a
second terminal in `workbench/`:

```sh
scripts/run-agents.sh                 # first terminal; leave it running
```
```sh
cd workbench
uv run workbench agents               # what is registered, what each accepts
uv run workbench invoke --agent hello.world --input samples/hello.salutation.json
uv run workbench serve                # then open http://127.0.0.1:8000/viewer/
```

Each part of the repository has its own README with the details:

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
- [Workbench](workbench/) — development environment for building and testing sub-agents: the invocation contract (LinkML), an R3 agent over FAIRsharing, an abstaining stub, and a read-only viewer
- [Decision records](docs/adr/) — the architecture decisions that govern every package, with the requirements register and the generated [`CONFORMANCE.md`](CONFORMANCE.md)
