# Data Director harness

The harness governs every invocation of a Data Director agent. It applies the institutional
profile, checks the input, calls the agent over A2A, lints the agent's account of its run, checks
cited records against pinned source copies, validates the envelope, and records the run with its
trace and a Process Run Crate. The workbench describes each step in
[`docs/conductor.md`](docs/conductor.md).

The harness is a library with one way in of its own, the A2A endpoint (`dd_harness.transport.a2a`).
Other ways in are built on it. The [workbench](../workbench/) is one of them, used for developing
and testing agents ([ADR-0022](../docs/adr/0022-harness-is-its-own-package.md)).

| Module | What it does |
|---|---|
| `conductor.py` | Runs the steps above. Every way in calls `Conductor.invoke`. |
| `policy.py` | The policy gate over an institutional profile (ADR-0003, ADR-0017). |
| `grounding.py` | The grounding linter (ADR-0008, ADR-0012). |
| `sources.py` | The source check against pinned copies (ADR-0016). |
| `store.py`, `provenance.py`, `conversations.py` | The JSONL run store, Process Run Crates, and conversations derived from the store. |
| `registry.py`, `remote.py` | The agent registry and the A2A client for agents (ADR-0010, ADR-0011). |
| `identity.py` | The authentication boundary that names whom an invocation acts for (ADR-0018). |
| `settings.py` | Settings from the environment, and the factory that builds a conductor. |
| `transport/a2a.py` | The A2A JSON-RPC endpoint that serves the conductor to other systems. |

## Configuration belongs to the deployment

The harness ships no profile, agent list or source list, and has no default run directory. Each
comes from a `DD_*` variable or from a default the caller passes to `Settings.from_env`:

| Variable | What it names |
|---|---|
| `DD_PROFILE` | The institutional profile applied to every invocation. |
| `DD_AGENTS_CONFIG` | The YAML list of agent base URLs. |
| `DD_SOURCES_CONFIG` | The pinned source copies the source check resolves evidence against. |
| `DD_RUNS_DIR` | Where runs are written. |
| `DD_PRINCIPAL_ID`, `DD_PRINCIPAL_NAME`, `DD_PRINCIPAL_KIND` | Whom every invocation acts for, until there is authentication. |

A way in supplies a set by passing its files to `Settings.from_env` as defaults, then calls
`build_conductor(settings)`. A variable wins over the default, so a deployment replaces one file
without touching the others. Two sets are in the repository:

- `app/config/` is the Data Director app's reference set (`profile.yaml`, `agents.yaml`,
  `sources.yaml`), supplied by `dd_app.config`, with runs in `app/runs/`.
- `workbench/` holds the workbench's development set, supplied by `workbench.config`.

`build_conductor(settings, agents=[...])` also registers agent objects that the caller runs in
its own process, beside the agents the agent list names. The app runs R3 this way. The profile
still decides which may run.

Not yet decided (#57):

- TODO: one file (e.g. `harness.yaml`) naming the other three and the run directory.
- TODO: how `sources.yaml` pins a source copy stored outside the repository.
- TODO: how a steward edits and reviews the profile in a deployment (ADR-0017, #41).

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
