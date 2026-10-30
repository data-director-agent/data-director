# Data Director harness

[![CI](https://github.com/data-director-agent/data-director/actions/workflows/ci.yml/badge.svg)](https://github.com/data-director-agent/data-director/actions/workflows/ci.yml) [![Coverage](https://codecov.io/gh/data-director-agent/data-director/graph/badge.svg?flag=harness)](https://codecov.io/gh/data-director-agent/data-director?flags[0]=harness)

The harness governs every invocation of a Data Director agent. It applies the institutional
profile, checks the input, calls the agent over A2A, lints the agent's account of its run, checks
cited records against pinned source copies, validates the envelope, and records the run with its
trace and a Process Run Crate. The workbench describes each step in
[`docs/conductor.md`](docs/conductor.md).

The harness is a library with one way in of its own, the A2A endpoint (`dd_harness.transport.a2a`),
which `dd-harness serve` serves. Other ways in are built on it. The [workbench](../workbench/) is
one of them, used for developing and testing agents
([ADR-0022](../docs/adr/0022-harness-is-its-own-package.md)).

| Module | What it does |
|---|---|
| `conductor.py` | Runs the steps above. Every way in calls `Conductor.invoke`. |
| `policy.py` | The policy gate over an institutional profile (ADR-0003, ADR-0017). |
| `grounding.py` | The grounding linter (ADR-0008, ADR-0012). |
| `sources.py` | The source check against pinned copies (ADR-0016). |
| `store.py`, `provenance.py`, `conversations.py` | The JSONL run store, Process Run Crates, and conversations derived from the store. |
| `projects.py` | The project record: an append-only log per project that holds its file inventory ([`docs/projects.md`](docs/projects.md), ADR-0034). |
| `registry.py`, `remote.py` | The agent registry and the A2A client for agents (ADR-0010, ADR-0011). |
| `identity.py` | The authentication boundary that names whom an invocation acts for (ADR-0018). |
| `settings.py` | Settings from the environment, and the factory that builds a conductor. |
| `transport/a2a.py` | The A2A JSON-RPC endpoint that serves the conductor to other systems. |
| `server.py` | `dd-harness serve`: the A2A endpoint and the agent card in one process, for deployments. `dd-harness project`: create a project, add an inventory, list its events. |

## Configuration belongs to the deployment

The harness ships no profile, agent list or source list, and has no default run directory. Each
comes from a `DD_*` variable or from a default the caller passes to `Settings.from_env`:

| Variable | What it names |
|---|---|
| `DD_PROFILE` | The institutional profile applied to every invocation. |
| `DD_AGENTS_CONFIG` | The YAML list of agent base URLs. |
| `DD_SOURCES_CONFIG` | The pinned source copies the source check resolves evidence against. |
| `DD_RUNS_DIR` | Where runs are written. |
| `DD_PROJECTS_DIR` | Where project records are kept. Only `dd-harness project` needs it so far. |
| `DD_PRINCIPAL_ID`, `DD_PRINCIPAL_NAME`, `DD_PRINCIPAL_KIND` | Whom every invocation acts for on a server that signs no one in, and for callers with no request (the CLI, the evaluation). Recorded as `asserted`. |
| `DD_OIDC_ISSUER`, `DD_OIDC_CLIENT_ID` | The OpenID Connect provider (for example `https://orcid.org`) and the client ID its ID tokens are issued to. Set, every HTTP caller must send one of its ID tokens, and is recorded as `authenticated` (ADR-0029). It cannot be set beside `DD_PRINCIPAL_ID`. |

A way in supplies a set by passing its files to `Settings.from_env` as defaults, then calls
`build_conductor(settings)`. A variable wins over the default, so a deployment replaces one file
without touching the others. Two sets are in the repository:

- `app/config/` is the Data Director app's reference set (`profile.yaml.example`, `agents.yaml`,
  `sources.yaml`), supplied by `dd_app.config`, with runs in `app/runs/`.
- `workbench/` holds the workbench's development set, supplied by `workbench.config`.

`build_conductor(settings, agents=[...])` also registers agent objects that the caller runs in
its own process, beside the agents the agent list names. The profile still decides which may run.
The app does not use it (ADR-0027).

Not yet decided (#57):

- TODO(#225): one file (e.g. `harness.yaml`) naming the other three and the run directory.
- TODO(#225): how `sources.yaml` pins a source copy stored outside the repository.
- TODO(#225): how a steward edits and reviews the profile in a deployment (ADR-0017, #41).

## Serving the harness

`dd-harness serve` runs the conductor as a server of its own (#55). It serves the A2A endpoint at
`/a2a` and the agent card at `/.well-known/agent-card.json`, and nothing else: no viewer, AG-UI,
run index, test kit or Inspect AI. Other systems call it, such as an app, another Data Director
instance, or a delegation agent calling back under its grant (ADR-0012).

```sh
pip install 'data-director-harness[serve]'   # uvicorn is an extra; in this workspace, uv sync installs it
export DD_PROFILE=... DD_AGENTS_CONFIG=... DD_SOURCES_CONFIG=... DD_RUNS_DIR=...
export DD_PRINCIPAL_ID=... DD_PRINCIPAL_NAME=...
dd-harness serve --host 127.0.0.1 --port 8000
```

- Every setting comes from the environment. There are no defaults and no `.env` file: an unset
  path or principal, or a missing or malformed file, stops start-up with a one-line message.
- `DD_HARNESS_URL` is the address other systems reach the server by. The agent card advertises
  it, and delegation agents call back on it. Set it when the server binds all interfaces, or sits
  behind a proxy or a container network. Unset, it is `http://<host>:<port>`.
- With `DD_OIDC_ISSUER` and `DD_OIDC_CLIENT_ID` set, a caller sends
  `Authorization: Bearer <ID token>` with an ID token from that issuer. The server verifies it on
  every request against the issuer's published keys (fetched through its discovery document and
  cached), and each invocation acts for the person the token names. A caller without a good token
  is refused with the problem type `…/problems/unauthenticated`, in the A2A task. A delegation
  callback needs no token: its grant names whom it acts for (ADR-0012, ADR-0018).
  - TODO(#17): answer such a caller with HTTP `401` and `WWW-Authenticate: Bearer` (ADR-0029), and
    decide whether an ID token is the right credential for a program at all (#17).
- Without a provider, callers are not authenticated (ADR-0018, #17, #43). Every invocation acts
  for the configured principal, whoever sent it. **Do not expose such a server beyond a trusted
  network.**
  It prints a warning when bound to anything other than a loopback address.
- `workbench serve` builds its conductor the same way (`dd_harness.server.serving`) and adds
  AG-UI, the run and conversation index and the viewer to the same A2A routes.

Not yet decided:

- TODO(#170): whether the run and conversation read endpoints (`/runs`, `/conversations`) belong to
  the harness server or only to the workbench.
- TODO(#17, #43): authentication of callers and of agents.

## Test kit

`dd_harness.testing` is the harness's test kit, for the harness's own tests, for agent packages
and for any way in to the harness. `in_process(agent)` serves an agent in memory over A2A,
`make_conductor(runs_dir, *agents)` builds a conductor over agents served that way (with its own
delegation callback, also in memory), and `ScriptedAgent` is a double whose behaviour each test
sets. The doubles' classes are declared in `src/dd_harness/schema/doubles.yaml`, and the test
profiles `PERMISSIVE` and `RESTRICTIVE` are in `src/dd_harness/testing/profiles/`. Tests act for
`TEST_PRINCIPAL`. Nothing in the kit needs the workbench.

## Rules

- The harness imports `dd_sdk` and third-party libraries only. It never imports the workbench,
  the app, an agent package or the evaluation framework. `tests/test_harness_boundary.py`
  enforces this.
- The rules in [`../workbench/AGENTS.md`](../workbench/AGENTS.md) ("Load-bearing things") apply
  here unchanged.
