# Writing an agent

Each agent is one package and one A2A service under `agents/<name>/`. Agents share the contract
and helpers in `sdk/`, and are governed by the harness in `harness/`. An agent must not import
the workbench, the app or another agent.

## Create the package

From the repository root:

```sh
uv run scripts/dd.py new-agent advisor-foo
uv sync --all-packages --all-extras
```

This writes `agents/advisor-foo/`, a working mock agent with the id `advisor.foo`, its own input
and payload classes, and tests. It also registers the agent everywhere the repository lists
agents: the root `pyproject.toml`, the Compose files, the agent lists, the profiles,
`deploy/agents/`, the docs navigation and the roster table in `docs/specs/agents.md`. The new
agent passes the test suite, mypy, Import Linter, `scripts/check_boundaries.py` and
`scripts/check_members.py` before you change anything. Then replace its placeholder advice
with your own.

## The agent kit

What every agent's `run` builds is in `dd_sdk.agent`, so no agent keeps its own copy:

| Helper | Returns |
|---|---|
| `abstain(reason, statement)` | An abstention, with no payload or evidence. |
| `input_ref(ctx)` | The grounding reference to the invocation's input. |
| `input_evidence(ctx)` | The evidence item for the input, which `input_ref(ctx)` cites. |

A `none` or `input_only` agent cites the input and nothing else, so these two are all it puts
in `grounded_on` and `evidence`. `dd_harness.testing` re-exports them for tests.

See `agents/README.md` for the full recipe, and for the version convention that marks an agent
as alpha. `agents/example-hello/` is the worked example, commented against each step.

TODO(#250): a worked example, following the `hello` agent.
