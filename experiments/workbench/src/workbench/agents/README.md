# Agents

An agent is an `AgentSpec` plus one method, `run(request, ctx) -> AgentResult` (`base.py`). The
conductor holds every agent to its spec: it refuses inputs the agent did not declare, rejects a
payload of a class other than the one declared, records the declared grounding mode on the
envelope, and runs the grounding linter's rules for that mode. An agent never sets identifiers,
timestamps, telemetry or its grounding mode.

| Package | Agent id | Accepts | Mode | Payload | Status |
|---|---|---|---|---|---|
| `quality/` | `quality.reviewer` | `MetadataRecord` | `input_only` | `QualityReview` | Demonstration: weighted completeness from `checks.yaml`. |
| `factcheck/` | `fact.checker` | `Claim` | `retrieval` | `FactCheck` | Demonstration: lexical verdict over packaged `sources.json`. |
| `hello/` | `hello.world` | `Salutation` | `none` | `Greeting` | **Template.** Greets whoever the input names; the worked example of every step below. |
| `abstain.py` | `stub.abstain` | every input class | `none` | — | Abstains unconditionally. |
| `r3/` | `r3.standards-advisor` | `DatasetProfile` | `retrieval` | `Recommendations` | **Not ported** to this interface; registered as unavailable (`r3/factory.py`). TODO. |

## Start from `hello/`

`hello/agent.py` is the smallest agent that walks the whole of the recipe below — its own input
class, its own payload class, a declared grounding mode, a uischema fragment, an entry point, a
profile entry, a sample and marked tests — with no domain logic in the way. It is commented
against the numbered steps. Copy the package, rename it, and delete the greeting.

It is also the check on the claim in the last line of this file: `hello.world` has no reason to
fail other than the harness, so if adding an agent ever starts to require an edit to the
conductor, linter, CLI, transports or shell, it is the agent that will show it.

## Adding an agent

1. **Decide what it reads and returns.** If an existing input class (`DatasetProfile`,
   `MetadataRecord`, `Claim`, `Salutation`) or payload class (`Recommendations`, `QualityReview`,
   `FactCheck`, `Greeting`) fits, use it. Otherwise add a class to `schema/data_director.yaml` —
   `Salutation` and `Greeting` are the worked example; an input class carries
   `schema_class`; a payload class carries `schema_class` and `mixins: [Grounded]` — add it to
   the relevant `any_of`, run `scripts/gen_schema.py`, and mirror it in `contract/models.py`
   (`INPUT_TYPES` / `PAYLOAD_TYPES`). See ADR-0007.
2. **Decide its grounding mode** (ADR-0008). `retrieval` if it consults external records: emit one
   `tracing.retrieval_span(tracer, source_id, content_hash)` per record consulted, before any
   model call, and put a `GroundingRef` for each record the payload rests on in `grounded_on`.
   `input_only` if it works over the input and may call a model; `none` if it is deterministic.
   In both, `grounded_on` and `evidence` cite `ctx.input_ref` / `ctx.input_hash` and nothing else.
3. **Hash what you retrieved** with a registered canonicalisation from `evidence.py`
   (ADR-0009). Register a new name there if none fits; never invent one in the agent.
4. **Write the package**: a class with `spec = AgentSpec(...)` and `run`, and a module-level
   `build(settings) -> Agent`. Read the agent's own `DD_<AGENT>_*` environment variables in
   `build`, not in `settings.py`. A content problem is an outcome (`abstained` with a reason
   code), not an exception.
5. **Register it**: one line under `[project.entry-points."workbench.agents"]` in
   `pyproject.toml`, then `uv sync`.
6. **Enable it** in the profiles that should run it (`profiles/default.yaml`,
   `profiles/test-permissive.yaml`).
7. **Ship a sample input** in `samples/` with `schema_class` set, and a `uischema.json` fragment
   for the payload if it has one (`spec.uischema`): a field a model may write points its badge at
   the sibling that records how the value came about (`dd:derivation_field`).
8. **Test it** through the conductor (`tests/fakes.make_conductor`) and mark each test with the
   requirement identifiers it actually exercises (`docs/requirements.yaml`). Do not claim a
   Blueprint `R` a demonstration does not meet.

Nothing in the conductor, linter, CLI, transports or shell is edited.
