# Data Director Workbench

**Status:** development environment. It is where sub-agents are built and tested, not the
reference implementation itself; changes to its contract and formats follow the ADR process in
[`docs/adr/`](docs/adr/) and, where they affect the project as a whole,
[GOVERNANCE.md](../GOVERNANCE.md).

A test-bed for developing Data Director sub-agents against one contract and one harness. An
agent declares what it reads, what it returns and how it grounds its output; the harness holds it
to that: a policy gate, an input check, an OpenTelemetry trace, a grounding linter whose rules
follow the agent's declared mode, JSON Schema validation, an append-only store and a Process Run
Crate per invocation. A generated [`CONFORMANCE.md`](CONFORMANCE.md) reports which Blueprint
requirements the tests substantiate; its default verdict for any requirement without a passing
test is *unsubstantiated*. The plan is [`docs/MVP_PLAN.md`](docs/MVP_PLAN.md); the decisions are
in [`docs/adr/`](docs/adr/).

Two rules govern it: **decide formats now, build components later** (identifiers, envelope, trace
attributes, canonicalisations and slot URIs are fixed; everything behind an interface can
change), and **adopt the plumbing, own the governance** (bespoke code only where a decision is
made: whether an action is permitted, whether evidence suffices, whether to decline).

## Quick start

Requires Python 3.14 and [`uv`](https://docs.astral.sh/uv/). No account or API key is needed.

```sh
uv sync --all-extras
uv run pytest                                          # network blocked; everything offline
uv run workbench agents                                # what is registered, what each accepts
uv run workbench invoke --agent quality.reviewer --input samples/orda-record.metadata.json
uv run workbench invoke --agent fact.checker     --input samples/claim.json
uv run workbench invoke --agent hello.world      --input samples/hello.salutation.json
uv run workbench invoke --agent quality.reviewer --input samples/claim.json   # failed: input-not-accepted
uv run workbench invoke --agent stub.abstain     --input samples/claim.json   # abstained
uv run workbench serve                                 # then open http://127.0.0.1:8000/shell/
```

`invoke` prints the envelope, the grounding linter's verdict, and the run directory
(`runs/<invocation_id>/` with `envelope.json`, `request.json`, `spans.jsonl`, `grounding.txt` and a
Process Run Crate). `workbench lint <spans.jsonl> <envelope.json>` re-runs the linter offline.

## Agents

| Agent | Accepts | Grounding mode | Payload | What it is |
|---|---|---|---|---|
| `quality.reviewer` | `MetadataRecord` | `input_only` | `QualityReview` | Weighted completeness of an existing record against fixed criteria. A demonstration of an agent that grounds on its input, not a quality framework. |
| `fact.checker` | `Claim` | `retrieval` | `FactCheck` | A lexical verdict grounded on the sources it retrieved. A demonstration of a retrieval agent that is not R3; the rule checks word overlap and negation, not meaning. |
| `hello.world` | `Salutation` | `none` | `Greeting` | The template agent. Greets whoever the input names; the smallest complete walk through the recipe, commented to be copied. |
| `stub.abstain` | every input class | `none` | — | Abstains unconditionally; exercises the non-success path. |
| `r3.standards-advisor` | `DatasetProfile` | `retrieval` | `Recommendations` | Recommends vocabularies, ontologies and formats over FAIRsharing. **Not yet ported** to the generalised interface; registered as unavailable, tests xfailed. TODO — see [`src/workbench/agents/r3/factory.py`](src/workbench/agents/r3/factory.py). |

Adding one: a package, a `build` factory, one entry-point line, `uv sync`. The recipe is
[`src/workbench/agents/README.md`](src/workbench/agents/README.md) and `hello.world` is its
worked example; nothing in the conductor, linter, CLI, transports or shell changes.

## What is here

| Path | Contents |
|---|---|
| `schema/data_director.yaml` | The contract, in LinkML: `InvocationRequest`, `Envelope`, `Outcome`, `ProblemDetails`; input classes `DatasetProfile`, `MetadataRecord`, `Claim`, `Salutation`; payload classes `Recommendations`, `QualityReview`, `FactCheck`, `Greeting`, all mixing in `Grounded`; `GroundingRef`, `EvidenceItem`, `Telemetry`. `schema/generated/` holds the JSON Schema and SHACL it generates (never hand-edited). |
| `src/workbench/contract/` | Pydantic mirrors of the schema (discriminated `Input` and `Payload` unions), JSON Schema validation, the conditional rules, RFC 9457 problem types. |
| `src/workbench/agents/base.py`, `registry.py` | `AgentSpec`, the `Agent` protocol, the manifest; discovery through entry points. |
| `src/workbench/conductor.py` | Policy gate → input check → agent → grounding linter → validation → store → provenance. A plain function every transport wraps; it knows no payload class. |
| `src/workbench/tracing.py`, `grounding.py`, `evidence.py` | OpenTelemetry span tree with the owned `dd.*` attributes; the per-mode grounding rules; the registry of evidence canonicalisations. |
| `src/workbench/policy.py`, `profiles/` | The YAML institutional profile and the two questions the gate answers. |
| `src/workbench/agents/quality/`, `factcheck/`, [`hello/`](src/workbench/agents/hello/agent.py), `abstain.py`, [`r3/`](src/workbench/agents/r3/README.md) | The agents; `hello/` is the template to copy. |
| `src/workbench/transport/` | A2A JSON-RPC (agent invocation), AG-UI run events (shell), the Starlette app with `/agents` and `/samples`. |
| `shell/` | The read-only, no-build shell: RJSF from a CDN, rendering from the generated schema; agent and sample pickers from the manifest; per-agent payload fragments with derivation badges; an evidence drawer. |
| `data/fairsharing/` | The committed FAIRsharing snapshot R3 uses (CC BY-SA 4.0; see its `LICENCE.md`) and the script that builds it. |
| `docs/requirements.yaml`, `scripts/conformance_report.py`, `CONFORMANCE.md` | The requirements register, the traceability rule, and the generated report. |
| `docs/adr/` | 0001 transport · 0002 OpenTelemetry · 0003 policy profiles · 0004 UUIDv7 and Problem Details · 0005 `DatasetProfile` and validation format · 0006 dependency tiering · 0007 polymorphic contract · 0008 grounding modes · 0009 evidence canonicalisations · 0010 agent registry. |

## The contract in one paragraph

An agent receives an `InvocationRequest` (UUIDv7 `invocation_id`, agent id, policy bundle
reference, and an `input` that is one of the input classes, discriminated by `schema_class`) and
returns an `Envelope` whose `outcome.status` is one of **succeeded, abstained, referred, failed,
suspended**. `abstained` and `referred` carry a bespoke `reason_code`; `failed` and `suspended`
carry RFC 9457 Problem Details. Every envelope records the agent's declared `grounding_mode`, has
`requires_human_review: true` as a schema constant, an `evidence` list of content-hashed records
each naming its canonicalisation, and `telemetry` with the trace id, model id, token counts and
energy slots (null, `not_measured`). A `payload`, present only when succeeded, is one of the
payload classes and always carries `grounded_on`: the identities and hashes it rests on. The
Blueprint defines no outcome vocabulary; this one is the workbench's specification contribution.

## The grounding invariant

Every agent declares a grounding mode, and the linter applies that mode's rules to the trace and
the envelope after every run (ADR-0008):

- **`retrieval`** — the agent retrieves before it reasons. G1 every model call starts after a
  retrieval ended; G2 every identity the payload asserts was retrieved, matched on source id
  *and* content hash; G3 every cited evidence hash is in the trace; G4 every asserted hash is in
  the evidence.
- **`input_only`** — the agent works over what it was given and may call a model. No retrieval
  span may appear; everything it cites is the input, whose hash the conductor computed.
- **`none`** — deterministic over the input: as `input_only`, and no model call.

In every mode a payload the linter cannot ground — no `grounded_on`, no `schema_class` — is a
violation, never a pass. A violation downgrades `succeeded` to `failed` with problem
`grounding-violation`. Nothing ungrounded leaves the system, and nothing passes because the
linter did not recognise it.

## Limitations

- **R3 is not ported.** The FAIRsharing agent, the workbench's one agent with real retrieval and
  an optional model explainer, predates the generalised interface. It is registered as
  unavailable and its tests are xfailed until the port (TODO in `agents/r3/factory.py`).
- **The demonstration agents are demonstrations.** `quality.reviewer`'s criteria and weights are
  hand-chosen; `fact.checker`'s verdict is word overlap and negation parity over four packaged
  sources. Each exists to exercise a grounding mode and the input check, and says so in its
  rationale.
- **Energy** (P14) is a slot, not a measurement.
- **Structured validation output** is fixed as the SHACL Validation Report vocabulary but not
  produced; only JSON Schema validation runs.
- **Frictionless has no RDF namespace**, so `TableField` slots carry `see_also` rather than a URI.
- **The w3id namespace** used for problem types and agent identifiers is not registered.
- **The shell is not tested in a browser** in CI.
- **One shot.** One request produces one envelope; there is no conversation, orchestration or
  streaming yet (deferred, `docs/MVP_PLAN.md` §6).

## Environment

See [`env.example`](env.example). Defaults run entirely offline.
