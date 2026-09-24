# workbench

The Data Director Workbench: the invocation contract, a harness (conductor, policy gate, input
check, OpenTelemetry trace, per-mode grounding linter, evidence hashes, JSONL store, Process Run
Crate), an agent registry with four usable agents (one of them the `hello.world` template) and
one awaiting port (R3), a read-only shell, and a generated `CONFORMANCE.md`. `docs/MVP_PLAN.md`
is the plan; `docs/adr/` records the decisions.

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

Python 3.14, `uv`. All of it lives in this directory; nothing goes at the repository root.

```bash
uv sync --all-extras                            # also after adding an agent entry point
uv run pytest                                   # network blocked; no credentials needed
uv run ruff check . && uv run ruff format .
uv run mypy
uv run python scripts/gen_schema.py             # after editing schema/data_director.yaml
uv run pytest --json-report --json-report-file=.report.json && uv run python scripts/conformance_report.py
```

## Load-bearing things

- **`schema/generated/` is generated.** Edit `schema/data_director.yaml`, regenerate, and keep
  `contract/models.py` in step; `tests/test_contract.py` checks both.
- **Adding an agent touches nothing central.** A package with `AgentSpec` + `run` + `build`, one
  entry-point line in `pyproject.toml`, a sample, a uischema fragment, marked tests, a profile
  entry. Recipe: `src/workbench/agents/README.md`; `agents/hello/` is the worked example to
  copy. If you find yourself editing the conductor, linter, CLI, transport or shell to add an
  agent, stop.
- **Only the conductor fills identifiers, timestamps, telemetry, grounding mode and input hash.**
  An agent returns an `AgentResult` (outcome, payload, evidence). If you find yourself setting
  `invocation_id` or `grounding_mode` in an agent, stop.
- **An input or payload class carries `schema_class`; a payload class mixes in `Grounded`.**
  `grounded_on` is the only place identity is asserted. A payload without it fails the linter
  (G0) by design. Do not add a payload class without the mixin.
- **The linter applies the agent's declared mode.** `retrieval`: G1–G4. `input_only`: R1–R3.
  `none`: R1–R3 + N1. A violation downgrades `succeeded` to `failed`. Do not weaken a rule to make
  a test pass; do not add a mode without an ADR.
- **A content problem is an outcome, not an exception.** Empty search → `abstained`; registry down
  → `abstained(registry_unavailable)`; policy refusal → `failed` with Problem Details or
  `referred`; wrong input class → `failed(input-not-accepted)`. Exceptions are for programmer and
  configuration errors (`ContractViolation`, `PolicyError`, `UnknownAgent`, `RegistryError`).
- **A canonicalisation is registered, never invented.** `evidence.CANONICALISATIONS`; a new
  projection is a new name, and an existing name's bytes never change.
- **A rule with missing inputs returns `None`, never `0.0`** (`agents/r3/rank.py`).
- **Every test that substantiates a requirement carries `@pytest.mark.requirement("<ID>")`**, and
  the ID must be in `docs/requirements.yaml`. Do not mark a test with an ID it does not actually
  exercise; a demonstration agent does not substantiate a Blueprint `R` it does not meet.
- **R3 is xfailed, not deleted.** `agents/r3/factory.py` raises `NotImplementedError`; the port is
  a TODO there. Do not "fix" R3 tests by widening the harness.
- **`data/fairsharing/snapshot.jsonl` is CC BY-SA 4.0** (see its LICENCE.md). Rebuild with
  `scripts/build_snapshot.py`; do not hand-edit records.
- **Cassettes must not contain credentials.** `conftest.py` filters the auth headers and the
  sign-in password; check a new cassette before committing it.

British English, declarative prose, `TODO` rather than a plausible guess (root `CLAUDE.md`).
