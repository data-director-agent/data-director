# harness

Rules for working on `dd_harness`: the conductor, policy gate, input check, grounding linter,
source check, run store and provenance, the A2A way in and the test kit `dd_harness.testing`
([System and boundaries](../docs/specs/system.md), [`README.md`](README.md)). The repository-wide
rules in the root [`AGENTS.md`](../AGENTS.md) apply as well.

Governance code belongs here, and it is used by every way in (the app, the workbench, an A2A
client). If you are writing governance, a test double or a storage backend in another package,
stop and put it here.

## Load-bearing things

- **The harness stands on its own ([System and boundaries](../docs/specs/system.md)).** `src/`
  imports `dd_sdk` and third-party libraries only, never `workbench`, `dd_app`, an agent or
  `inspect_ai`; `tests/test_harness_boundary.py` enforces it. The harness has no configuration of
  its own: each path comes from a `DD_*` variable or the caller's default (the workbench's
  development defaults are in `workbench.config`, the app's in `app/config/`). If you find
  yourself computing a default from a harness module's `__file__`, stop.
- **The harness imports no agent.** Agents are services reached through `RemoteAgent`
  (`dd_harness.remote`), and a registry file lists their URLs. Tests may import agent packages to
  serve them in memory (`dd_harness.testing.in_process`), and `src/` must not.
- **An agent's spans come back over the wire.** `RemoteAgent.call` returns them in
  `Received.spans`, beside the `AgentResult`, never inside it; the conductor imports them into
  its trace before linting. G0 rejects a span outside the `invoke_agent` tree or one carrying a
  conductor attribute. Do not filter imported spans by trace id; that would hide such spans from
  G0.
- **Only the conductor fills identifiers, timestamps, telemetry, grounding mode and input hash.**
- **Only the authentication boundary names the human ([Policy and identity](../docs/specs/policy-and-identity.md)).**
  A transport asks its `Authenticator` and passes `acting_for` to `Conductor.invoke`. The
  conductor holds no default, and a delegated child acts for the grant's principal. The stub
  (`OperatorAssertion`) records `assurance: asserted`; do not describe that as authenticated. If
  you find yourself reading `acting_for` from a request body, sending it to an agent, or giving
  the conductor a default, stop. Tests act for `dd_harness.testing.TEST_PRINCIPAL`.
- **Only the conductor sets lineage.** `parent_invocation_id` and `delegations` come from a
  delegation grant the conductor issued; `invoke` refuses a request that carries
  `parent_invocation_id`. An orchestrator delegates through `ctx.delegate`, never by calling an
  agent directly ([Orchestration](../docs/specs/orchestration.md)).
- **The linter applies the agent's declared mode.** `retrieval`: G1–G4. `input_only`: R1–R3.
  `none`: R1–R3 + N1. `delegation`: R1, D1–D3, G4 ([Orchestration](../docs/specs/orchestration.md)).
  G0 and E1 apply in every mode. A violation downgrades `succeeded` to `failed`. Do not weaken a
  rule to make a test pass; do not add a mode without changing the grounding spec.
- **The linter checks consistency, not retrieval ([Evidence and grounding](../docs/specs/grounding.md)).**
  An agent's `retrieval` spans are its own declarations. `dd_harness.sources` re-hashes cited
  records against the pinned copies in a sources file. An unresolved item is never counted as
  verified, and a source file is never read without its `sha256` pin. Do not describe
  `grounding: passed` as proof that an agent retrieved anything.
- **The doubles' schema is generated.** Edit `src/dd_harness/schema/doubles.yaml` and run
  `uv run dd-gen-schema harness/src/dd_harness/schema/doubles.yaml`.
- **Shared test doubles live in `dd_harness.testing`**, not in another package's tests, so that
  every way in and every agent can test against a conductor.
