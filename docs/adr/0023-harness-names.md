# ADR-0023: Names that mean the harness say "harness"

**Status:** Proposed
**Date:** 2026-10-21

## Context

ADR-0022 made the harness a package of its own (`dd_harness`) and the workbench one way in to it.
Several names still said "workbench" where they meant the harness: a configuration variable, the
A2A card that other systems read, an SDK class that agents import, the trace `service.name`, and
the core contract's identity. ADR-0022 left them alone because renaming them changes a
configuration variable, the agent card, stored traces and the generated schemas (#54). The app
and any other way in uses these names too, so "workbench" in them misleads the people who
operate or integrate a deployment.

The trace `service.name` and the core schema are fixed formats (`workbench/AGENTS.md`), so they
need an ADR.

## Decision

- **The names below change, with no aliases.** Every user of these names is in this repository,
  and the SDK, the harness and the app are alpha.

  | Before | After |
  |---|---|
  | `DD_WORKBENCH_URL`, `Settings.workbench_url`, `Conductor.workbench_url` | `DD_HARNESS_URL`, `Settings.harness_url`, `Conductor.harness_url` |
  | A2A card name "Data Director Workbench", description "Reference workbench for …" | "Data Director Harness", "The harness of the reference implementation of …" |
  | `dd_harness.transport.a2a.WorkbenchExecutor` | `ConductorExecutor` |
  | `dd_sdk.delegate.WorkbenchDelegate`, and "workbench" in `DelegationRefused` messages | `HarnessDelegate`, "harness" |
  | `dd_harness.testing.WORKBENCH_URL` (`http://workbench.test`) | `HARNESS_URL` (`http://harness.test`) |
  | `make_tracing`'s default `service.name` `data-director-workbench` | `data-director-harness`, the harness's distribution name |
  | Core schema id `https://w3id.org/data-director/schema/workbench`, name `data_director_workbench`, title "Data Director Workbench contract" | `https://w3id.org/data-director/schema/core`, `data_director_core`, "Data Director core contract" |

- **The contract version goes from 0.7.0 to 0.8.0.** The schema's id is the `$id` of every
  generated JSON Schema, so changing it changes the contract's identity, not only its prose.
- Docstrings, comments and schema descriptions in `sdk/` and `harness/` that call the harness
  "the workbench" say "the harness". "Workbench" stays where it means the workbench: the
  `workbench` CLI, its development configuration and the viewer.

## Dependencies introduced

None.

## Consequences

- An operator who set `DD_WORKBENCH_URL` must set `DD_HARNESS_URL` instead. The old variable is
  no longer read, and nothing warns about it.
- Under the caret rule (ADR-0019), an agent built against contract 0.7 is listed as
  incompatible until it is rebuilt against 0.8. Every agent in this repository takes the version
  from the SDK, so only agents outside it are affected.
- An agent that imported `WorkbenchDelegate` must import `HarnessDelegate`.
- Traces and envelopes stored before this change keep `service.name` `data-director-workbench`
  and `contract_version` 0.7.0. Nothing in this repository filters on `service.name`. A trace
  backend that does must match both values for runs on either side of the change.
- Accepted ADRs before this one keep the names they were written with (ADR-0012 names
  `DD_WORKBENCH_URL`).
- Do not add a name that says "workbench" to `sdk/` or `harness/` for something the harness does.

## Not yet decided

- TODO(#3): whether `https://w3id.org/data-director/schema/core` is registered with w3id, as for
  the previous id.
- TODO(#255): the prose in `workbench/docs/` (e.g. `contract.md`) and the requirements register behind
  `CONFORMANCE.md` still say "the workbench" in places where they mean the harness. That goes
  with ADR-0022's open question of whether the harness's documentation moves out of
  `workbench/docs/`.
