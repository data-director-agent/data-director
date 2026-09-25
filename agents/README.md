# Agents

Each directory here is one agent: its own package, its own tests, and its own service. The
workbench does not import any of them. It reaches each agent over A2A at the URL listed in
`workbench/agents.yaml` ([ADR-0011](../workbench/docs/adr/0011-remote-agents.md)).

An agent is an `AgentSpec` plus one method, `run(request, ctx) -> AgentResult`
(`dd_sdk.agent`). `dd_sdk.serve` puts it behind A2A: it publishes the agent card with the spec,
runs the agent under a tracer parented to the workbench's span, and returns the result with the
spans the agent recorded. The workbench's conductor then holds the agent to its spec:

- it refuses an input of a class the agent did not declare, or one its class schema rejects;
- it rejects a payload of a class other than the one declared, or one its class schema rejects;
- it records the declared grounding mode on the envelope;
- it runs the grounding linter's rules for that mode over the returned spans.

An agent never sets identifiers, timestamps, telemetry or its grounding mode.

An agent owns its input and payload classes
([ADR-0019](../workbench/docs/adr/0019-core-contract-and-agent-owned-classes.md)). It declares
them in a LinkML file of its own, which imports the core contract, and its card carries each
class's JSON Schema pinned by a digest. The workbench checks inputs and payloads against those
schemas, so it needs no copy of an agent's classes, and adding one needs no SDK release. What
every agent shares is the core, `sdk/src/dd_sdk/schema/data_director.yaml`: the request, the
envelope, outcomes, grounding, evidence, delegation, the principal, and the chat classes
`Message` and `Reply`. Its `version` is the contract version each card declares; the workbench
lists an agent built against an incompatible one as **incompatible**.

| Package | Agent id | Accepts | Mode | Payload | Serve | Status |
|---|---|---|---|---|---|---|
| `quality/` | `quality.reviewer` | `MetadataRecord` | `input_only` | `QualityReview` | `dd-quality`, port 8102 | Demonstration: weighted completeness from `checks.yaml`. |
| `factcheck/` | `fact.checker` | `Claim` | `retrieval` | `FactCheck` | `dd-factcheck`, port 8103 | Demonstration: lexical verdict over packaged `sources.json`. |
| `hello/` | `hello.world` | `Salutation` | `none` | `Greeting` | `dd-hello`, port 8101 | **Template.** Greets whoever the input names; the worked example of every step below. |
| `stub/` | `stub.abstain` | every input class | `none` | — | `dd-stub`, port 8104 | Abstains unconditionally. |
| `director/` | `director.stub` | `Message` | `delegation` | `Reply` | `dd-director`, port 8106 | Rule-based stand-in for the orchestrator: routes each message by `routing.yaml` and delegates through the workbench (ADR-0012). |
| `r3/` | `r3.standards-advisor` | `DatasetProfile` | `retrieval` | `Recommendations` | `dd-r3`, port 8105 | Recommends vocabularies, ontologies and formats from FAIRsharing (committed snapshot, or live with the snapshot as fallback). Configured by `DD_R3_*` (`r3/src/dd_agent_r3/README.md`). |

Start every agent with `scripts/run-agents.sh` from the repository root, or one agent with
`uv run dd-hello serve --port 8101`.

## Start from `hello/`

`hello/src/dd_agent_hello/agent.py` is the smallest agent that walks the whole of the recipe
below with no domain logic in the way. It has:

- its own input class and its own payload class;
- a declared grounding mode;
- its payload fields' derivations;
- a console script;
- a profile entry;
- a sample;
- marked tests.

It is commented against the numbered steps. Copy the directory, rename it, and delete the
greeting.

It is also the check on the claim in the last line of this file. `hello.world` has no reason to
fail other than the harness. If adding an agent ever needs an edit to the conductor, linter,
CLI, transports or viewer, this agent will show it.

## Adding an agent

1. **Declare what it reads and returns.** A conversational agent can use the core's `Message`
   and `Reply`. Any other class belongs to the agent. `hello/` is the worked example:
   - `src/dd_agent_<name>/schema/<name>.yaml` declares the classes in LinkML. It imports
     `linkml:types` and `data_director` (the core), and has its own `id` and prefix. An input
     class carries the slot `schema_class`; a payload class carries `schema_class` and
     `mixins: [Grounded]`.
   - `uv run dd-gen-schema agents/<name>/src/dd_agent_<name>/schema/<name>.yaml` writes one JSON
     Schema per class to `generated/` beside it. Commit them; never edit them by hand.
   - `src/dd_agent_<name>/classes.py` holds a Pydantic model per class, subclassing
     `dd_sdk.contract.models.Frozen` (input) or `Grounded` (payload), with
     `schema_class: Literal["<Class>"]`.
   - The spec names each class as `ClassSchema.of(Model)`. It reads the generated schema from
     the model's package and refuses a model whose fields differ from it.

   A test calls `dd_sdk.schema.gen.stale(<path to the LinkML file>)` and expects `[]`, so a
   stale generated schema fails the agent's own suite. Two agents may define classes of the same
   name; the digest, not the name, identifies a class in a stored run.
2. **Decide its grounding mode** (ADR-0008).
   - `retrieval` if it consults external records. Emit one
     `dd_sdk.tracing.retrieval_span(ctx.tracer, source_id, content_hash)` per record consulted,
     before any model call. Put a `GroundingRef` for each record the payload rests on in
     `grounded_on`.
   - `input_only` if it works over the input and may call a model.
   - `none` if it is deterministic.
   - `delegation` if it answers by handing work to other agents (an orchestrator). Call
     `ctx.delegate(agent_id, input)`, never another agent directly; the workbench runs the child
     and returns a `Delegated` whose `ref` and `evidence` are what the payload cites for it
     (ADR-0012). `ctx.delegate` is `None` when no grant was issued (for example under
     `workbench invoke`); handle that as an outcome. `director/` is the worked example.

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
8. **Ship a sample input and declare the payload's derivations.**
   - Put a sample input, with `schema_class` set, in `workbench/samples/`. The viewer builds its
     input form from the class schema in the agent's card.
   - If the agent has a payload, declare in `spec.derivations` how it produces each field that
     it does not copy from input or evidence, for example
     `{"rationale": Derived(Derivation.MODEL, recorded_in="rationale_derivation")}`. A field a
     model may write names the sibling that records, per value, how it actually came about. The
     spec refuses a path or a sibling that the payload class does not have. Ship no presentation:
     the viewer lays the payload out from its schema, in LinkML slot order (ADR-0016).
9. **Test it** in `<name>/tests/`, with a test module name no other package uses. Test the
   agent through a conductor with `workbench.testing.make_conductor(runs_dir, YourAgent())`,
   which serves it in memory over A2A exactly as the workbench calls it. Mark each test with the
   requirement identifiers it actually exercises (`workbench/docs/requirements.yaml`). Do not
   claim a Blueprint `R` a demonstration does not meet.
10. **Optionally, evaluate it** (ADR-0013). Put an Inspect AI task in `<package>/evals/`, built
    on `workbench.evaluation.invoke_agent` and its generic scorers, with the agent's own cases
    and scorers beside it and a committed `baseline.json`. `dd_agent_r3.evals` is the worked
    example.

Nothing in the SDK, conductor, linter, CLI, transports or viewer is edited.
