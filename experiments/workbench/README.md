# Data Director Workbench (MVP)

**Status:** experiment. Not the reference implementation; promotion out of `experiments/` is an
RFC decision under [GOVERNANCE.md](../../GOVERNANCE.md).

The smallest workbench that demonstrates the Data Director contract end to end: one real agent
(R3, recommending vocabularies, ontologies and formats over FAIRsharing), one non-success path (a
stub that always abstains), and a generated [`CONFORMANCE.md`](CONFORMANCE.md) whose default
verdict for any requirement without a passing test is *unsubstantiated*. The plan it implements
is [`docs/MVP_PLAN.md`](docs/MVP_PLAN.md); the decisions are in [`docs/adr/`](docs/adr/).

Two rules govern it: **decide formats now, build components later** (identifiers, envelope, trace
attributes and slot URIs are fixed at v0; everything behind an interface can change), and **adopt
the plumbing, own the governance** (bespoke code only where a decision is made: whether an action
is permitted, whether evidence suffices, whether to decline).

## Quick start

Requires Python 3.14 and [`uv`](https://docs.astral.sh/uv/). No account or API key is needed.

```sh
uv sync --all-extras
uv run pytest                                         # network blocked; everything offline
uv run workbench invoke --agent r3.standards-advisor --input samples/soil-chemistry.profile.json
uv run workbench invoke --agent stub.abstain           --input samples/soil-chemistry.profile.json
uv run workbench serve                                 # then open http://127.0.0.1:8000/shell/
```

`invoke` prints the envelope, the grounding linter's verdict, and the run directory
(`runs/<invocation_id>/` with `envelope.json`, `request.json`, `spans.jsonl`, `grounding.txt` and a
Process Run Crate).

## What is here

| Path | Contents |
|---|---|
| `schema/data_director.yaml` | The contract, in LinkML: `InvocationRequest`, `Envelope`, `Outcome`, `ProblemDetails`, `DatasetProfile`, `Recommendations`, `EvidenceItem`, `Telemetry`. `schema/generated/` holds the JSON Schema and SHACL it generates (never hand-edited). |
| `src/workbench/contract/` | Pydantic mirrors of the schema, JSON Schema validation, the conditional rules, RFC 9457 problem types. |
| `src/workbench/conductor.py` | Policy gate → agent → grounding linter → validation → store → provenance. A plain function every transport wraps. |
| `src/workbench/tracing.py`, `grounding.py`, `evidence.py` | OpenTelemetry span tree with the owned `dd.*` attributes; the three grounding rules; evidence canonicalisation and hashing. |
| `src/workbench/policy.py`, `profiles/` | The YAML institutional profile and the two questions the gate answers. |
| [`src/workbench/agents/r3/`](src/workbench/agents/r3/README.md) | Retrieve → rank → explain. Retrieval adapter with snapshot and live FAIRsharing backends; bespoke ranking; template and Anthropic explainers. |
| `src/workbench/agents/abstain.py` | The stub: `abstained(capability_not_implemented)`, unconditionally. |
| `src/workbench/transport/` | A2A JSON-RPC (agent invocation), AG-UI run events (shell), the Starlette app. |
| `shell/` | The read-only, no-build shell: RJSF from a CDN, rendering from the generated schema with derivation badges and an evidence drawer. |
| `data/fairsharing/` | The committed FAIRsharing snapshot (CC BY-SA 4.0; see its `LICENCE.md`) and the script that builds it. |
| `docs/requirements.yaml`, `scripts/conformance_report.py`, `CONFORMANCE.md` | The requirements register, the traceability rule, and the generated report. |
| `docs/adr/` | ADR-0001 transport · 0002 OpenTelemetry · 0003 policy profiles · 0004 UUIDv7 and Problem Details · 0005 `DatasetProfile` and validation format · 0006 dependency tiering. |

## The contract in one paragraph

An agent receives an `InvocationRequest` (UUIDv7 `invocation_id`, agent id, policy bundle
reference, a minimal `DatasetProfile` on DCAT and Dublin Core slot URIs) and returns an
`Envelope` whose `outcome.status` is one of **succeeded, abstained, referred, failed,
suspended**. `abstained` and `referred` carry a bespoke `reason_code`; `failed` and `suspended`
carry RFC 9457 Problem Details. Every envelope has `requires_human_review: true` as a schema
constant, an `evidence` list of content-hashed registry records, and `telemetry` with the trace
id, model id, token counts and energy slots (null, `not_measured` at v0). The Blueprint defines
no outcome vocabulary; this one is the workbench's specification contribution.

## The grounding invariant

Retrieval precedes any model call, and the model never determines the identity of a
recommendation. This is a shape (the explainer receives ranked records and returns rationale)
and a check: after every run, `grounding.lint` walks the trace and confirms (G1) every `chat`
span started after a `retrieval` span ended, (G2) every recommended identifier was retrieved,
and (G3) every cited evidence hash appears on a retrieval span. A violation downgrades
`succeeded` to `failed` with problem `grounding-violation`. Nothing ungrounded leaves the system.

## Limitations

- **Energy** (P14) is a slot, not a measurement.
- **Structured validation output** is fixed as the SHACL Validation Report vocabulary but not
  produced; only JSON Schema validation runs.
- **Frictionless has no RDF namespace**, so `TableField` slots carry `see_also` rather than a URI.
- **The w3id namespace** used for problem types and agent identifiers is not registered.
- **The shell is not tested in a browser** in CI.

## Environment

See [`env.example`](env.example). Defaults run entirely offline from the snapshot with the
template explainer.
