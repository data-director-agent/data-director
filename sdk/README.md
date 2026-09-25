# Data Director SDK

What an agent and the workbench share. The workbench calls each agent over A2A
([ADR-0011](../workbench/docs/adr/0011-remote-agents.md)), so they share no code except this
package.

| Module | What it holds |
|---|---|
| `dd_sdk.contract` | The invocation contract: Pydantic models, JSON Schema validation, Problem Details. |
| `dd_sdk/schema/` | The core contract's LinkML source (`data_director.yaml`), what is generated from it, and `dd-gen-schema` (`gen.py`). |
| `dd_sdk.contract.classes` | `ClassSchema`: an input or payload class carried as JSON Schema, pinned by digest. |
| `dd_sdk.contract.version` | The contract version and the compatibility rule. |
| `dd_sdk.evidence` | The registered evidence canonicalisations and hashes (ADR-0009). |
| `dd_sdk.tracing` | The span helpers and owned `dd.*` attributes the grounding linter reads (ADR-0002). |
| `dd_sdk.agent` | `AgentSpec`, `AgentResult`, `RunContext`, the `Agent` protocol, and `describe`. |
| `dd_sdk.wire` | How a request, a result, its spans and a spec cross A2A. |
| `dd_sdk.serve` | `app(agent)` and `main(build)`: serve one agent over A2A. |

## Contract

The core contract is `src/dd_sdk/schema/data_director.yaml`
([ADR-0019](../workbench/docs/adr/0019-core-contract-and-agent-owned-classes.md)). It holds what
the workbench governs every agent by:

- the `InvocationRequest` and the `Envelope`;
- outcomes and Problem Details;
- grounding (`GroundingRef`, the `Grounded` mixin) and evidence;
- telemetry, delegation and the principal;
- the conversation classes `Message`, `Reply` and `ConversationTurn`.

`input` and `payload` are open: any object that names its class in `schema_class` (and, for a
payload, mixes in `Grounded`). Every other input and payload class belongs to the agent that
reads or returns it, declared in the agent's own LinkML file, which imports this one as
`data_director`. The agent's card carries each such class's JSON Schema, pinned by its digest,
and the workbench checks inputs and payloads against those. Changing the core is an ADR.

The core's `version` is the **contract version**. Each card declares the one its agent was built
against. The workbench governs an agent whose version has the same major version and, while the
major version is 0, the same minor version (the caret rule); any other is listed as
incompatible.

`dd-gen-schema` regenerates `generated/`: with no argument the core's envelope and request
schemas, SHACL shapes and the `Message` and `Reply` class schemas; given an agent's LinkML file,
that agent's class schemas. After editing the core, regenerate and keep `contract/models.py` in
step:

```sh
uv run dd-gen-schema
```

`tests/test_contract.py` checks that the generated files are current and that the models match
them. `ClassSchema.of(model)` refuses a model whose fields differ from its generated schema.
