# workbench

The Data Director Workbench: a harness (conductor, policy gate, input check, OpenTelemetry trace,
per-mode grounding linter, JSONL store, Process Run Crate), a registry of agents reached over A2A,
a read-only shell, and a generated `CONFORMANCE.md`. The workbench contains no agent code. Agents
are separate packages and services under `../agents/`, and what both sides share (the contract,
evidence, span helpers, the A2A agent server) is `../sdk/` (ADR-0011). `docs/MVP_PLAN.md`
is the plan; `docs/adr/` records the decisions; `docs/architecture.md` is the overview.

Two rules from the plan govern everything here:

1. **Formats are decided; components sit behind interfaces.** The LinkML schema, the owned
   `dd.*` trace attributes, the registered evidence canonicalisations and the outcome vocabulary
   are fixed. Changing any of them is an ADR. Agents, retrieval backends, explainers and
   transports are swappable.
2. **Adopt the plumbing; own the governance.** Bespoke code is limited to: the outcome vocabulary
   and reason codes, the policy gate, the input check, the grounding linter, evidence hashing,
   each agent's own decision logic, and the traceability rule in the conformance report.
   Everything else is a maintained library behind a thin module (ADR-0006).

## Working on the code

Python 3.14, `uv`. The repository root is a uv workspace (`sdk/`, `workbench/`, `agents/*`).
Tooling config (pytest, ruff, mypy) is in the root `pyproject.toml`; run these from the root.

```bash
uv sync --all-packages --all-extras             # after adding a workspace member
uv run pytest                                   # network blocked; no credentials needed
uv run ruff check . && uv run ruff format .
uv run mypy
uv run python sdk/scripts/gen_schema.py         # after editing the LinkML schema
scripts/run-agents.sh                           # every agent on the port agents.yaml expects
uv run pytest --json-report --json-report-file=workbench/.report.json && uv run python workbench/scripts/conformance_report.py
```

## Load-bearing things

- **`sdk/src/dd_sdk/schema/generated/` is generated.** Edit `data_director.yaml` beside it,
  regenerate, and keep `dd_sdk/contract/models.py` in step; `sdk/tests/test_contract.py` checks
  both.
- **The workbench imports no agent.** Agents are services reached through `RemoteAgent`
  (`remote.py`); `agents.yaml` lists their URLs. Tests may import agent packages to serve them in
  memory (`testing.in_process`), and `src/` must not. If you find yourself importing
  `dd_agent_*` from `src/workbench/`, stop.
- **Adding an agent touches nothing central.** A package under `../agents/` with `AgentSpec` +
  `run` + `build` + `main`, one line in `agents.yaml`, a sample, a uischema fragment, marked
  tests, a profile entry. Recipe: `../agents/README.md`; `../agents/hello/` is the worked example
  to copy. If you find yourself editing the conductor, linter, CLI, transport or shell to add an
  agent, stop.
- **An agent's spans come back over the wire.** `RemoteAgent` returns them in
  `AgentResult.spans`; the conductor imports them into its trace before linting. G0 rejects a
  span outside the `invoke_agent` tree or one carrying a conductor attribute. Do not filter
  imported spans by trace id; that would hide such spans from G0.
- **Only the conductor fills identifiers, timestamps, telemetry, grounding mode and input hash.**
  An agent returns an `AgentResult` (outcome, payload, evidence). If you find yourself setting
  `invocation_id` or `grounding_mode` in an agent, stop.
- **Only the conductor sets lineage.** `parent_invocation_id` and `delegations` come from a
  delegation grant the conductor issued; `invoke` refuses a request that carries
  `parent_invocation_id`. An orchestrator delegates through `ctx.delegate`, never by calling an
  agent directly (ADR-0012).
- **An input or payload class carries `schema_class`; a payload class mixes in `Grounded`.**
  `grounded_on` is the only place identity is asserted. A payload without it fails the linter
  (G0) by design. Do not add a payload class without the mixin.
- **The linter applies the agent's declared mode.** `retrieval`: G1–G4. `input_only`: R1–R3.
  `none`: R1–R3 + N1. `delegation`: R1, D1–D3, G4 (ADR-0012). A violation downgrades
  `succeeded` to `failed`. Do not weaken a rule to make a test pass; do not add a mode without an
  ADR.
- **A content problem is an outcome, not an exception.** Empty search → `abstained`; registry down
  → `abstained(registry_unavailable)`; policy refusal → `failed` with Problem Details or
  `referred`; wrong input class → `failed(input-not-accepted)`. Exceptions are for programmer and
  configuration errors (`ContractViolation`, `PolicyError`, `UnknownAgent`, `RegistryError`).
- **A canonicalisation is registered, never invented.** `dd_sdk.evidence.CANONICALISATIONS`; a new
  projection is a new name, and an existing name's bytes never change.
- **A rule with missing inputs returns `None`, never `0.0`** (`agents/r3/src/dd_agent_r3/rank.py`).
- **Every test that substantiates a requirement carries `@pytest.mark.requirement("<ID>")`**, and
  the ID must be in `docs/requirements.yaml`. Do not mark a test with an ID it does not actually
  exercise; a demonstration agent does not substantiate a Blueprint `R` it does not meet.
- **R3 states each identity twice.** A `Recommendation` names its record in `resource` for
  the reader and in `grounded_on` for the linter, which reads only `grounded_on`. Both are built
  from the same retrieved record, and R3's own tests check that they agree.
- **`agents/r3/data/fairsharing/snapshot.jsonl` is CC BY-SA 4.0** (see its LICENCE.md). Rebuild
  with `agents/r3/scripts/build_snapshot.py`; do not hand-edit records.
- **Cassettes must not contain credentials.** The root `conftest.py` filters the auth headers and
  the sign-in password; check a new cassette before committing it.
- **Test module basenames are unique across the workspace.** Test directories are not packages;
  shared doubles live in `workbench.testing` and `dd_agent_r3.testing`.

British English, declarative prose, `TODO` rather than a plausible guess (root `CLAUDE.md`).
