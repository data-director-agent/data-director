# Data Director SDK

[![CI](https://github.com/data-director-agent/data-director/actions/workflows/ci.yml/badge.svg)](https://github.com/data-director-agent/data-director/actions/workflows/ci.yml) [![Coverage](https://codecov.io/gh/data-director-agent/data-director/graph/badge.svg?flag=sdk)](https://codecov.io/gh/data-director-agent/data-director?flags[0]=sdk)

What an agent and the harness share. The harness calls each agent over A2A
([Agents](../docs/specs/agents.md)), so they share no code except this
package.

| Module | What it holds |
|---|---|
| `dd_sdk.contract` | The invocation contract: Pydantic models, JSON Schema validation, Problem Details. |
| `dd_sdk/schema/` | The core contract's LinkML source (`data_director.yaml`), what is generated from it, and `dd-gen-schema` (`gen.py`). |
| `dd_sdk.contract.classes` | `ClassSchema`: an input or payload class carried as JSON Schema, pinned by digest. |
| `dd_sdk.contract.version` | The contract version and the compatibility rule. |
| `dd_sdk.evidence` | The registered evidence canonicalisations and hashes ([Evidence and grounding](../docs/specs/grounding.md)). |
| `dd_sdk.tracing` | The span helpers and owned `dd.*` attributes the grounding linter reads ([Transport and tracing](../docs/specs/transport.md)). |
| `dd_sdk.agent` | `AgentSpec` (with the `models` it sends data to), `AgentResult`, `RunContext`, the `Agent` protocol, and `describe`. |
| `dd_sdk.wire` | How a request, a result, its spans and a spec cross A2A. |
| `dd_sdk.serve` | `app(agent)` and `main(build)`: serve one agent over A2A. |
| `dd_sdk.prompts` | `ModelCallLog`: the model calls of one run and the prompts they name by digest ([Disclosure](../docs/specs/disclosure.md)). |
| `dd_sdk.model` | `call`: one model call, with its `chat` span, token counts and `ModelCallLog` entry, through a `Model` adapter ([Agents](../docs/specs/agents.md)). |
| `dd_sdk.model_anthropic` | `AnthropicModel`, the adapter for Claude; needs the `anthropic` extra ([Dependencies](../docs/specs/dependencies.md)). |
| `dd_sdk.testing` | `FakeModel`, a `Model` for tests that needs no key. |
| `dd_sdk.credentials` | `api_key(env)`: a model key, read once at start-up, and `ConfigError` ([Policy and identity](../docs/specs/policy-and-identity.md)). |
| `dd_sdk.sources` | `BuiltSource`, how an agent declares a source copy it builds outside git, and `dd-sources`, which prepares them all ([Evidence and grounding](../docs/specs/grounding.md)). |

## Contract

The core contract is `src/dd_sdk/schema/data_director.yaml`
([Contract](../docs/specs/contract.md)). It holds what
the harness governs every agent by:

- the `InvocationRequest` and the `Envelope`;
- outcomes and Problem Details;
- grounding (`GroundingRef`, the `Grounded` mixin) and evidence;
- telemetry, delegation and the principal;
- the conversation classes `Message`, `Reply` and `ConversationTurn`.

`input` and `payload` are open: any object that names its class in `schema_class` (and, for a
payload, mixes in `Grounded`). Every other input and payload class belongs to the agent that
reads or returns it, declared in the agent's own LinkML file, which imports this one as
`data_director`. The agent's card carries each such class's JSON Schema, pinned by its digest,
and the harness checks inputs and payloads against those. Changing the core changes the [contract spec](../docs/specs/contract.md).

The core's `version` is the **contract version**. Each card declares the one its agent was built
against. The harness governs an agent whose version has the same major version and, while the
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
