# workbench

The Data Director Workbench MVP: the invocation contract, a harness (conductor, policy gate,
OpenTelemetry trace, grounding linter, evidence hashes, JSONL store, Process Run Crate), one real
agent (R3 over FAIRsharing), one abstaining stub, a read-only shell, and a generated
`CONFORMANCE.md`. `docs/MVP_PLAN.md` is the plan; `docs/adr/` records the decisions.

Two rules from the plan govern everything here:

1. **Formats are decided; components sit behind interfaces.** The LinkML schema, the owned
   `dd.*` trace attributes, the evidence canonicalisation and the outcome vocabulary are fixed.
   Changing any of them is an ADR. Backends (retrieval, explainer, transport) are swappable.
2. **Adopt the plumbing; own the governance.** Bespoke code is limited to: the outcome vocabulary
   and reason codes, the policy gate, the grounding linter, evidence hashing, R3 ranking, and the
   traceability rule in the conformance report. Everything else is a maintained library behind a
   thin module (ADR-0006 lists them and their fallbacks).

## Working on the code

Python 3.14, `uv`. All of it lives in this directory; nothing goes at the repository root.

```bash
uv sync --all-extras
uv run pytest                                   # network blocked; no credentials needed
uv run ruff check . && uv run ruff format .
uv run mypy
uv run python scripts/gen_schema.py             # after editing schema/data_director.yaml
uv run pytest --json-report --json-report-file=.report.json && uv run python scripts/conformance_report.py
```

## Load-bearing things

- **`schema/generated/` is generated.** Edit `schema/data_director.yaml`, regenerate, and keep
  `contract/models.py` in step; `tests/test_contract.py` checks both.
- **Only the conductor fills identifiers, timestamps and telemetry.** An agent returns an
  `AgentResult` (outcome, payload, evidence). If you find yourself setting `invocation_id` in an
  agent, stop.
- **Retrieval precedes any model call, and the model never decides identity.** An explainer
  receives ranked records and returns rationale. `grounding.lint` checks G1–G3 after every run and
  a violation downgrades `succeeded` to `failed`. Do not weaken the linter to make a test pass.
- **A content problem is an outcome, not an exception.** Empty search → `abstained`; registry down
  → `abstained(registry_unavailable)`; policy refusal → `failed` with Problem Details or
  `referred`. Exceptions are for programmer and configuration errors (`ContractViolation`,
  `PolicyError`, `UnknownAgent`).
- **A rule with missing inputs returns `None`, never `0.0`** (`agents/r3/rank.py`).
- **Every test that substantiates a requirement carries `@pytest.mark.requirement("<ID>")`**, and
  the ID must be in `docs/requirements.yaml`. Do not mark a test with an ID it does not actually
  exercise; the conformance report is only worth publishing if the markers are honest.
- **`data/fairsharing/snapshot.jsonl` is CC BY-SA 4.0** (see its LICENCE.md). Rebuild with
  `scripts/build_snapshot.py`; do not hand-edit records.
- **Cassettes must not contain credentials.** `conftest.py` filters the auth headers and the
  sign-in password; check a new cassette before committing it.

British English, declarative prose, `TODO` rather than a plausible guess (root `CLAUDE.md`).
