# Writing an agent

Each agent is one package and one A2A service under `agents/<name>/`. Agents share the contract
and helpers in `sdk/`, and are governed by the harness in `harness/`. An agent must not import
the workbench, the app or another agent.

See `agents/README.md` for the layout and the version convention that marks an agent as alpha.

TODO(#250): a worked example, following the `hello` agent.
