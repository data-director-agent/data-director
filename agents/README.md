# Agents

Each directory here is one agent: its own package, its own tests, and its own service. The
workbench does not import any of them. It reaches each agent over A2A at the URL listed in
`workbench/agents.yaml` ([ADR-0011](../workbench/docs/adr/0011-remote-agents.md)).

An agent is an `AgentSpec` plus one method, `run(request, ctx) -> AgentResult`
(`dd_sdk.agent`). `dd_sdk.serve` puts it behind A2A: it publishes the agent card with the spec,
runs the agent under a tracer parented to the workbench's span, and returns the result with the
spans the agent recorded. The workbench's conductor then holds the agent to its spec:

- it refuses inputs the agent did not declare;
- it rejects a payload of a class other than the one declared;
- it records the declared grounding mode on the envelope;
- it runs the grounding linter's rules for that mode over the returned spans.

An agent never sets identifiers, timestamps, telemetry or its grounding mode.

| Package | Agent id | Accepts | Mode | Payload | Serve | Status |
|---|---|---|---|---|---|---|
| `quality/` | `quality.reviewer` | `MetadataRecord` | `input_only` | `QualityReview` | `dd-quality`, port 8102 | Demonstration: weighted completeness from `checks.yaml`. |
| `factcheck/` | `fact.checker` | `Claim` | `retrieval` | `FactCheck` | `dd-factcheck`, port 8103 | Demonstration: lexical verdict over packaged `sources.json`. |
| `hello/` | `hello.world` | `Salutation` | `none` | `Greeting` | `dd-hello`, port 8101 | **Template.** Greets whoever the input names; the worked example of every step below. |
| `stub/` | `stub.abstain` | every input class | `none` | — | `dd-stub`, port 8104 | Abstains unconditionally. |
| `r3/` | `r3.standards-advisor` | `DatasetProfile` | `retrieval` | `Recommendations` | `dd-r3`, port 8105 | **Not ported** to this interface. `dd-r3 serve` exits, so the workbench lists R3 as unavailable (`r3/src/dd_agent_r3/factory.py`). TODO. |

Start every agent with `scripts/run-agents.sh` from the repository root, or one agent with
`uv run dd-hello serve --port 8101`.

## Start from `hello/`

`hello/src/dd_agent_hello/agent.py` is the smallest agent that walks the whole of the recipe
below with no domain logic in the way. It has:

- its own input class and its own payload class;
- a declared grounding mode;
- a uischema fragment;
- a console script;
- a profile entry;
- a sample;
- marked tests.

It is commented against the numbered steps. Copy the directory, rename it, and delete the
greeting.

It is also the check on the claim in the last line of this file. `hello.world` has no reason to
fail other than the harness. If adding an agent ever needs an edit to the conductor, linter,
CLI, transports or shell, this agent will show it.

## Adding an agent

1. **Decide what it reads and returns.** If an existing input class (`DatasetProfile`,
   `MetadataRecord`, `Claim`, `Salutation`) or payload class (`Recommendations`,
   `QualityReview`, `FactCheck`, `Greeting`) fits, use it. Otherwise add a class to the central
   contract, `sdk/src/dd_sdk/schema/data_director.yaml` (ADR-0007). `Salutation` and `Greeting`
   are the worked example:
   - an input class carries `schema_class`;
   - a payload class carries `schema_class` and `mixins: [Grounded]`.

   Add the class to the relevant `any_of`, run `uv run python sdk/scripts/gen_schema.py`, and
   mirror it in `sdk/src/dd_sdk/contract/models.py` (`INPUT_TYPES` / `PAYLOAD_TYPES`). An agent
   cannot bring a class of its own: the workbench rejects a card that names one.
2. **Decide its grounding mode** (ADR-0008).
   - `retrieval` if it consults external records. Emit one
     `dd_sdk.tracing.retrieval_span(ctx.tracer, source_id, content_hash)` per record consulted,
     before any model call. Put a `GroundingRef` for each record the payload rests on in
     `grounded_on`.
   - `input_only` if it works over the input and may call a model.
   - `none` if it is deterministic.

   In `input_only` and `none`, `grounded_on` and `evidence` cite `ctx.input_ref` /
   `ctx.input_hash` and nothing else. Always use `ctx.tracer`. A span started some other way is
   outside the invocation's trace, and the linter's G0 rule withholds the output.
3. **Hash what you retrieved** with a registered canonicalisation from `dd_sdk.evidence`
   (ADR-0009). Register a new name there if none fits; never invent one in the agent.
4. **Write the package.** Copy `hello/`. You need:
   - `pyproject.toml` depending on `data-director-sdk`, with a console script
     `dd-<name> = "dd_agent_<name>.agent:main"`;
   - a class with `spec = AgentSpec(...)` and `run`;
   - a module-level `build() -> Agent` and `main() -> int` that returns `serve.main(build)`.

   Read the agent's own `DD_<AGENT>_*` environment variables in `build`. A content problem is an
   outcome (`abstained` with a reason code), not an exception.
5. **Add it to the workspace.** Add the distribution to the `dependencies` and
   `[tool.uv.sources]` of the root `pyproject.toml`, then run `uv sync --all-packages`. A package
   that lives outside this repository skips this step; it only has to be served.
6. **Register it with the workbench.** Add one entry to `workbench/agents.yaml` with a name and
   the URL it is served at, and its port to `scripts/run-agents.sh`.
7. **Enable it** in the profiles that should run it (`workbench/profiles/default.yaml`,
   `workbench/profiles/test-permissive.yaml`). Registration is not permission.
8. **Ship a sample input and a uischema fragment.**
   - Put a sample input, with `schema_class` set, in `workbench/samples/`.
   - If the agent has a payload, ship a `uischema.json` fragment for it in the package
     (`spec.uischema`). A field a model may write points its badge at the sibling that records
     how the value came about (`dd:derivation_field`).
9. **Test it** in `<name>/tests/`, with a test module name no other package uses. Test the
   agent through a conductor with `workbench.testing.make_conductor(runs_dir, YourAgent())`,
   which serves it in memory over A2A exactly as the workbench calls it. Mark each test with the
   requirement identifiers it actually exercises (`workbench/docs/requirements.yaml`). Do not
   claim a Blueprint `R` a demonstration does not meet.

Nothing in the conductor, linter, CLI, transports or shell is edited.
