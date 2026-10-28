# ADR-0027: The app runs no agent in its own process

**Status:** Proposed
**Date:** 2026-10-22

Amends [ADR-0022](0022-harness-is-its-own-package.md) (the app ran the standards advisor in its
own process, #60) and [ADR-0026](0026-model-credentials.md) §2 (an agent in another component's
process may not call a model). Restores [ADR-0011](0011-remote-agents.md) §9 for the app.

## Context

ADR-0011 made every agent a separate service that the harness calls over A2A. Its §9 kept
in-process agents for tests only, and it rejected a second way of reaching an agent because there
would then be two sets of behaviour to keep conformant.

The app broke that rule. When it was first routed through the conductor (#60, #63), it had no
agent services to reach, so it imported `dd_agent_standards` and registered the standards
advisor in its own process. A deployment that listed `standards` was reached over A2A instead. The
app kept the in-process path after it gained `hello`, `quality` and `director` over A2A, and three
consequences followed:

- ADR-0026 needed a special rule for an agent running in the app's process, which the app
  enforced at start-up.
- The deployment needed a second agent list (`deploy/agents.yaml`) for when the advisor calls a
  model, and an operator had to change the app's settings to switch between the two.
- The two paths behaved differently. A2A carries a data part as a protobuf `Struct`, whose numbers
  are all doubles, so a payload that crosses the wire gives `14.0` where the in-process path gave
  `14`. The app's tests used the in-process path, so this was never tested.

## Decision

1. **The app reaches every agent over A2A through the conductor.** It imports no agent package
   at run time; a test (`app/tests/test_app_boundary.py`) enforces this.
2. **The app's reference agent list names every in-tree agent**, the standards advisor included
   (`name: standards`, port 8105). An agent that is not running is shown as unavailable, as any
   other is. The app does not substitute a copy of its own.
3. **Tests serve agents in memory over A2A** (`dd_harness.testing.in_process`), as ADR-0011 §9
   says, so they exercise the wire the app uses.

`build_conductor(settings, agents=[...])` stays in the harness for other ways in to it; the app
does not use it.

## Dependencies introduced

None. The app drops its dependency on `data-director-agent-standards`.

## Consequences

- ADR-0026 §1 still holds, and §2 has nothing left to govern: no agent runs in the app's process,
  so the app never holds a model key. Giving the standards advisor a model is a change to its
  own settings and key only.
- One agent list serves development and deployment, and `deploy/agents.yaml` is removed. The
  deployment always runs `data-director-agent@standards` and the app waits for port 8105.
- The app lists no available agent until the agent services are running
  (`scripts/run-agents.sh` in development).
- Integers in an agent's payload arrive as floats over A2A. That was already true of every agent
  except the in-process advisor. TODO(#254): decide whether the SDK restores them, and whether that
  needs an ADR.
- A future contributor must not register an agent object in the app's process. A new agent is a
  new entry in `app/config/agents.yaml`.
