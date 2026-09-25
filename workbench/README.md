# Data Director Workbench

A test bed for building and testing Data Director sub-agents. It calls each agent, checks that the
agent kept to a shared contract, and records every run so that a person can inspect what the agent
did and why.

## Background

The [Data Director Agentic AI Blueprint](https://doi.org/10.15497/RDA00157), adopted by the
Research Data Alliance (RDA), describes an assistant made of sub-agents that help researchers
manage their data. This repository is a proposed reference implementation of it; the Blueprint is
reproduced in [`../docs/BLUEPRINT.md`](../docs/BLUEPRINT.md) and its requirements are cited by ID
(`R3`, `P14`, …).

The workbench is not the reference implementation itself, and it contains no agent code. Each
agent states what input it reads, what output it returns, and what that output is based on.
Agents are separate services in [`../agents/`](../agents/). The workbench calls each one over
A2A, the [Agent2Agent protocol](https://a2a-protocol.org/), then checks that it kept to those
statements ([ADR-0011](docs/adr/0011-remote-agents.md)).
[`docs/architecture.md`](docs/architecture.md) explains how the pieces fit together.

## Who it is for

Software engineers and testers who write Data Director sub-agents, and anyone reviewing whether
those agents meet the Blueprint. Using it requires familiarity with the command line and Python
tooling; no knowledge of language models is needed, since the demonstration agents use none.

## Installation

Requirements:

- Python 3.14.
- [`uv`](https://docs.astral.sh/uv/), which installs the dependencies listed in
  [`pyproject.toml`](pyproject.toml).
- A Bash shell to run [`../scripts/run-agents.sh`](../scripts/run-agents.sh). On Windows, use
  WSL.

No account or API key is needed. Clone the repository, then from the repository root, which is a
uv workspace:

```sh
uv sync --all-packages --all-extras
uv run pytest                                          # network blocked; everything offline
```

The tests serve every agent in memory, so they need no agent running.

## Usage

### Quick start

To call agents from the command line, start them first and leave them running. Then, in a second
terminal in `workbench/`, name the person the invocations act for (see
[Who an invocation acts for](#who-an-invocation-acts-for)) and run the commands:

```sh
../scripts/run-agents.sh                               # in the first terminal

export DD_PRINCIPAL_ID=https://orcid.org/0000-0002-1825-0097   # your ORCID iD, or another IRI
export DD_PRINCIPAL_NAME="Josiah Carberry"                     # your name
uv run workbench agents                                # what is registered, what each accepts
uv run workbench invoke --agent quality.reviewer --input samples/orda-record.metadata.json
uv run workbench invoke --agent fact.checker     --input samples/claim.json
uv run workbench invoke --agent hello.world      --input samples/hello.salutation.json
uv run workbench invoke --agent quality.reviewer --input samples/claim.json   # failed: input-not-accepted
uv run workbench invoke --agent stub.abstain     --input samples/claim.json   # abstained
uv run workbench serve                                 # then open http://127.0.0.1:8000/viewer/
```

### The viewer

The viewer has two pages, reached by the tabs under its header.

- **Inspect** runs one agent over a sample and shows the run.
- **Chat** (`http://127.0.0.1:8000/viewer/chat.html`) holds a conversation with the orchestrator,
  `director.stub`, which hands each message to other agents and shows their replies inside its
  own ([ADR-0012](docs/adr/0012-conversation-and-orchestration.md)).

Only `serve` can run the orchestrator: `invoke` does not grant the permission it needs to call
other agents, so `samples/director.message.json` has to go through the viewer or the conversation
API.

### Inputs and outputs

An input is a JSON document whose `schema_class` names its input class; the samples and what each
exercises are listed in [`samples/README.md`](samples/README.md). The request and response formats
are described in [`docs/contract.md`](docs/contract.md).

`invoke` prints the agent's response and the result of the grounding check, which confirms that
everything the response relies on can be traced to something the agent actually read during the
run ([`docs/grounding.md`](docs/grounding.md)). It also writes a folder, `runs/<invocation_id>/`,
holding the request, the response, the trace of the run and a provenance record (a
[Process Run Crate](https://www.researchobject.org/workflow-run-crate/profiles/process_run_crate/)).
To re-run the grounding check on a finished run, use
`workbench lint <spans.jsonl> <envelope.json>`.

Every response has one of five outcomes: `succeeded`, `abstained`, `referred`, `failed` or
`suspended`; see [`docs/contract.md`](docs/contract.md).

## Configuration

The defaults run entirely offline, and nothing needs configuring to run the tests. To invoke an
agent, from the command line or through `serve`, the workbench must be told who the invocation
acts for; it will not start `invoke` or `serve` without that. The workbench is configured in
three places.

### Who an invocation acts for

The Blueprint (§5.4) requires that no agent operates anonymously: every invocation is made on
behalf of a named human, and the response and the provenance record say who. A request cannot
name that person. Until the workbench has authentication, the operator of the deployment names
one person in its configuration, and every invocation is recorded as acting for them, marked
`assurance: asserted` to show that nobody's identity was checked. On a shared `workbench serve`,
every caller is therefore recorded as the operator.

Set both of these before running `invoke` or `serve`:

| Variable | Meaning |
|---|---|
| `DD_PRINCIPAL_ID` | An absolute IRI for the person, such as `https://orcid.org/0000-0002-1825-0097`. Use an ORCID iD where the person has one. |
| `DD_PRINCIPAL_NAME` | The person's name, as it should appear in the record. |
| `DD_PRINCIPAL_KIND` | Optional. `person` (the default), or `accountable_role` when the principal is a role rather than an individual. |

`--acting-for-id` and `--acting-for-name` on `invoke` or `serve` take the place of the first two
for one command. If either is missing, the command stops with
`DD_PRINCIPAL_ID and DD_PRINCIPAL_NAME unset`; if the identifier is not an IRI, it stops with
`the configured principal is malformed`.

### Environment variables

The workbench reads these from the environment when it starts. For local development, copy
[`env.example`](env.example) to `workbench/.env`: the `workbench` command loads it at start-up,
from whichever directory it is run. A variable already set in the environment takes precedence
over the file. `scripts/run-agents.sh` passes the same file to the agents.

| Variable | Default | Meaning |
|---|---|---|
| `DD_PRINCIPAL_ID`, `DD_PRINCIPAL_NAME` | none; required | Who every invocation acts for; see [above](#who-an-invocation-acts-for). |
| `DD_PRINCIPAL_KIND` | `person` | `person` or `accountable_role`. |
| `DD_RUNS_DIR` | `runs` | Where each run's folder is written. |
| `DD_WRITE_CRATE` | `1` | `0` stops the provenance record (Process Run Crate) being written. |
| `DD_PROFILE` | `profiles/default.yaml` | The institutional profile applied to every invocation. A request cannot name one (ADR-0017). |
| `DD_AGENTS_CONFIG` | `agents.yaml` | The agent registry file. |
| `DD_WORKBENCH_URL` | the host and port of `serve` | The address the orchestrator uses to call the workbench back. Set it when agents reach the workbench by another name, such as a container network or a proxy. |

Relative defaults are resolved against `workbench/`. Each agent is a separate process and reads
its own variables, such as the R3 retrieval backend or a model API key, where it runs;
[`env.example`](env.example) lists them.

### Agent registry

[`agents.yaml`](agents.yaml) lists the base URL of each agent, with an optional `timeout_s`. The
ports match those started by `../scripts/run-agents.sh`. An agent that cannot be reached is listed
as unavailable and the rest still run; see [`docs/registry.md`](docs/registry.md).

### Institutional profiles

A profile says which agents may run, which action class each is assigned, and which classes need
a person's approval. The deployment chooses one profile for every invocation; a request cannot
name one. The default is [`profiles/default.yaml`](profiles/default.yaml). Set `DD_PROFILE`, or
pass `--profile <path>` to `invoke` or `serve`, to use another. The format is described in
[`profiles/README.md`](profiles/README.md).

### Command-line options

`uv run workbench <command> --help` lists every option. The ones most often changed are:

- `serve --host 127.0.0.1 --port 8000`: the address the viewer and APIs are served on.
- `invoke|serve --acting-for-id <IRI> --acting-for-name <name>`: who the invocations act for,
  in place of `DD_PRINCIPAL_ID` and `DD_PRINCIPAL_NAME`.
- `invoke --input-type <class>`: the input class, when the document has no `schema_class` and the
  agent accepts several.
- `invoke --requirement <ID>`: the Blueprint requirement being exercised; repeatable.

## Troubleshooting

- **`invoke` or `serve` will not start: `DD_PRINCIPAL_ID and DD_PRINCIPAL_NAME unset`.** Name
  the person the invocations act for; see
  [Who an invocation acts for](#who-an-invocation-acts-for).
- **`the configured principal is malformed`.** `DD_PRINCIPAL_ID` must be an absolute IRI, such
  as `https://orcid.org/…`, and `DD_PRINCIPAL_KIND` must be `person` or `accountable_role`.
- **An agent is listed as unavailable.** Its service is not running or is on another port. Start
  it with `../scripts/run-agents.sh`, and check its URL in `agents.yaml`.
- **`failed: input-not-accepted`.** The agent does not read that input class. `workbench agents`
  shows what each accepts.
- **`failed: agent-not-permitted`.** The profile in use does not list the agent under `agents`.
- **`failed: action-class-mismatch`.** The agent declares a different action class from the one
  the profile assigns it, usually because the agent changed. The steward updates the profile.
- **The workbench will not start: `has keys nothing enforces`.** The profile uses a key outside
  its vocabulary; see [`profiles/README.md`](profiles/README.md).
- **`director.stub` cannot reach other agents from `invoke`.** `invoke` issues no delegation
  grant, so the orchestrator has no way to call them. Use `workbench serve`; see
  [The viewer](#the-viewer).

## Agents

`workbench agents` lists what is registered. The agents themselves, and how to add one, are
described in [`../agents/README.md`](../agents/README.md).

## Project layout

| Path | Contents |
|---|---|
| `src/workbench/` | The harness: the conductor, policy gate, input check, grounding linter, run store, provenance and the `workbench` CLI. |
| `viewer/` | The browser UI served by `workbench serve`. |
| `agents.yaml` | The agent registry. |
| `profiles/` | Institutional profiles. |
| `samples/` | Example inputs. |
| `tests/` | The test suite. |
| `scripts/` | Maintenance scripts, including the conformance report generator. |
| `docs/` | Design documentation and decision records. |
| `CONFORMANCE.md` | Generated report of which requirements the tests and reviews demonstrate. |

## Further reading

- [Architecture](docs/architecture.md): the components, the order they run in, and where the
  code lives.
- [The conductor](docs/conductor.md): the function that runs an agent and applies every check.
- [The agent registry](docs/registry.md): how the workbench finds its agents, and what happens
  when one cannot be reached.
- [The contract](docs/contract.md): the request an agent receives and the response it returns.
- [Grounding](docs/grounding.md): the rules that tie an agent's output to its sources.
- [The conformance report](docs/conformance.md): how requirements are assessed by test and by
  human review, and how to record a review.
- [Glossary](docs/glossary.md): the terms used in this directory.
- [`CONFORMANCE.md`](CONFORMANCE.md): which requirements the tests and the recorded reviews
  demonstrate. It is generated. A requirement with nothing behind it is marked
  *unsubstantiated*.
- [`docs/adr/`](docs/adr/): the Architectural Decision Records (ADRs), one record per design
  decision.

## Contributing, contact and licence

See the [contribution guide](../CONTRIBUTING.md) and the links in the
[repository README](../README.md). The maintainer is Joe Heffer, University of Sheffield
(<j.heffer@sheffield.ac.uk>). The workbench is released under the [MIT Licence](../LICENSE); to
cite it, use [`CITATION.cff`](../CITATION.cff).
