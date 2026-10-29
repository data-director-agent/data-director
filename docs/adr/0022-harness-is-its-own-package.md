# ADR-0022: The harness is a package of its own, and the workbench is one way in to it

**Status:** Proposed; amended by [ADR-0027](0027-no-agent-in-the-apps-process.md)
**Date:** 2026-10-21

## Context

The harness is the code that governs an invocation: the conductor, the policy gate, the input
check, the grounding linter, the source check, the run store and the provenance record. Until
now it was packaged inside `workbench/`, beside the CLI, the viewer, the test kit and the
evaluation code.

The workbench is a development tool for people who write sub-agents. The Data Director app
(`app/`) is what researchers use, and it must not depend on the workbench. So the app could not
reach the harness at all. It called the standards advisor's retrieval code in-process, and it had to warn that
nothing it said was checked or recorded. "Every front end calls the conductor" held for the
development test bed and not for the product.

The harness modules did not import the workbench-side modules, so they could be separated
without redesign (issue #47). One thing did tie the harness to the workbench tree: its default
configuration. `policy.py` and `settings.py` computed the profile, `agents.yaml`,
`sources.yaml`, the run directory and the settings file from their own location in `workbench/`.

## Decision

- **The harness is the workspace package `harness/`** (distribution `data-director-harness`,
  import `dd_harness`). It holds the modules below and depends only on `sdk/` and third-party
  libraries.

  | Harness (`harness/`, deployable) | Workbench (`workbench/`, development only) |
  |---|---|
  | `conductor.py`, `policy.py`, `grounding.py`, `sources.py`, `store.py`, `provenance.py`, `identity.py`, `registry.py`, `remote.py`, `conversations.py`, `settings.py` | `cli.py`, `config.py`, `transport/agui.py`, `transport/app.py`, `viewer/` |
  | `transport/a2a.py`, the way in for other systems | `evaluation.py` (Inspect AI) |
  | `testing/` (the test kit and its profiles) and `schema/doubles.yaml` | |
  | | `profiles/`, `agents.yaml`, `sources.yaml`, `samples/`, the conformance report |

- **The harness imports no way in to it, and no agent.** Nothing under `harness/src/` imports
  `workbench`, `dd_app`, a `dd_agent_*` package or `inspect_ai`.
  `harness/tests/test_harness_boundary.py` enforces this. The workbench, the app and an A2A
  server are ways in. Each one builds a conductor and calls `Conductor.invoke`.
- **Configuration belongs to the deployment, not to the harness.** This extends ADR-0017 (the
  profile is the deployment's) to everything else a deployment supplies:
  - The harness ships no profile, agent list or source list, and has no default run directory.
  - `Settings.from_env` takes each path from its `DD_*` variable (`DD_PROFILE`,
    `DD_AGENTS_CONFIG`, `DD_SOURCES_CONFIG`, `DD_RUNS_DIR`). If the variable is unset, it uses a
    default passed by the caller. If there is neither, it raises `SettingsError`, and start-up
    stops.
  - `load_env_file` takes the file it reads as an argument.
  - The workbench supplies its development set from `workbench.config`. The paths are the same
    as before this decision.
- **Where a deployment's configuration lives (#57).** Each way in brings its own set and passes
  it to `Settings.from_env` as defaults. The workbench's development set stays in `workbench/`.
  The app's reference set is `app/config/` (`profile.yaml.example`, `agents.yaml`, `sources.yaml`), and
  its runs go to `app/runs/`. A `DD_*` variable still wins over each file, so a deployment can
  replace any of them without changing the repository.
- **The app reaches the standards advisor through the conductor (#60, option 1).** The app's one tool builds a
  `DatasetProfile` and calls `Conductor.invoke("standards.advisor", ...)` for the operator's
  principal (`OperatorAssertion`, ADR-0018). The standards advisor does not delegate, so the app runs it in its own
  process: `build_conductor(settings, agents=[...])` registers agent objects beside those its
  agent list names. Each standards advisor run is gated, checked and stored. The app's own model turn and its
  final answer are not.
- **The CLI stays with the workbench.** The harness is a library with one way in of its own,
  the A2A endpoint. `workbench serve` adds AG-UI and the viewer on top of it.

## Dependencies introduced

| Dependency | Tier | Fallback if this dependency is abandoned |
|---|---|---|
| None | n/a | The harness's existing runtime dependencies (`a2a-sdk`, `httpx`, `opentelemetry-sdk`, `rocrate`, `pyyaml`, `python-dotenv`) move with the modules that import them. Their tiers are unchanged (ADR-0006). |

## Consequences

- A deployment can install the SDK and the harness without the viewer, Inspect AI or the test
  kit.
- The app can call the conductor without depending on the workbench, so its runs can be checked,
  recorded and attributed (`acting_for`, ADR-0018) like those from any other way in.
- The workbench holds neither agent code nor governance code. It is a test bed for sub-agent
  authors.
- Code that called `Settings.from_env()`, `build_conductor()` or `load_env_file()` with no
  arguments, relying on the workbench's files, must now name them. Inside the workbench, that is
  `workbench.config.settings_from_env()`.
- Accepted ADRs before this one name modules at `workbench/src/workbench/`. Those paths record
  the layout when each ADR was written. The modules are now under `harness/src/dd_harness/`
  with the same file names.
- Do not add a workbench, app, agent or evaluation import to `harness/src/`. Do not compute a
  configuration default from a harness module's location.

## Not yet decided

- The app's own model turn and answer are governed by making the app a front end to an
  orchestrator under `delegation` grounding (ADR-0012, ADR-0024 §15, #21).
- Names that still said "workbench" where they meant the harness are renamed by ADR-0023 (#54).
- **The harness has a server of its own (#55).** `dd-harness serve` (`dd_harness.server`) serves
  the A2A routes and the agent card, and nothing else, for deployments that need no viewer. Its
  settings come from the environment with no defaults. `uvicorn` is the optional extra
  `data-director-harness[serve]`, so the app, which embeds the conductor, does not install it.
  `workbench serve` builds its conductor with the same `serving` function and adds its own
  routes. TODO(#170): whether `/runs` and `/conversations` belong to the harness server; until callers
  are authenticated (#17, #43), it must not be exposed beyond a trusted network.
- **The test kit belongs to the harness (#56).** The scripted doubles, `in_process`,
  `make_conductor`, `TEST_PRINCIPAL` and the two test profiles are `dd_harness.testing`, in the
  deployable package beside the code they exercise, as `dd_agent_standards.testing` is for R3. The
  doubles' classes are `dd_harness/schema/doubles.yaml`, because `ClassSchema.of` looks for a
  class's schema in its top-level package. `make_conductor` serves the delegation callback with
  `dd_harness.transport.a2a.a2a_routes` alone, so a test conductor needs nothing from the
  workbench. Harness tests are in `harness/tests/`; the workbench keeps the tests of its CLI and
  its development configuration, and `workbench.testing` re-exports the kit.
- The harness's documentation has moved out of `workbench/docs/` (#58). `conductor.md`,
  `grounding.md` and `registry.md` are in `harness/docs/`. The ADRs, the contract, the glossary,
  the requirements register and the review record govern every package, so they are in the
  repository-level `docs/`, with `CONFORMANCE.md` at the root and its generator in `scripts/`.
- TODO(#225): whether configuration may also come from one file (e.g. a `harness.yaml` naming the
  profile, agent list, source list and run directory), rather than four variables (#57).
- TODO(#225): how `sources.yaml` pins a source copy stored outside the repository. Today its paths
  are relative to the file, and its copies are the committed snapshots under `agents/` (#57).
- TODO(#225): how a steward edits and reviews the profile in a deployment (ADR-0017, #41, #57).
