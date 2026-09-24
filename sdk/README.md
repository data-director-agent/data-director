# Data Director SDK

What an agent and the workbench share. The workbench calls each agent over A2A
([ADR-0011](../workbench/docs/adr/0011-remote-agents.md)), so they share no code except this
package.

| Module | What it holds |
|---|---|
| `dd_sdk.contract` | The invocation contract: Pydantic models, JSON Schema validation, Problem Details. |
| `dd_sdk/schema/` | The LinkML source (`data_director.yaml`) and the JSON Schema and SHACL generated from it. |
| `dd_sdk.evidence` | The registered evidence canonicalisations and hashes (ADR-0009). |
| `dd_sdk.tracing` | The span helpers and owned `dd.*` attributes the grounding linter reads (ADR-0002). |
| `dd_sdk.agent` | `AgentSpec`, `AgentResult`, `RunContext`, the `Agent` protocol, and `describe`. |
| `dd_sdk.wire` | How a request, a result, its spans and a spec cross A2A. |
| `dd_sdk.serve` | `app(agent)` and `main(build)`: serve one agent over A2A. |

After editing `src/dd_sdk/schema/data_director.yaml`, regenerate and keep
`contract/models.py` in step:

```sh
uv run python sdk/scripts/gen_schema.py
```

A change to the contract is an ADR (ADR-0007). `tests/test_contract.py` checks that the
generated files are current and that the models match them.
