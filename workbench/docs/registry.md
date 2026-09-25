# The agent registry

The registry is the workbench's list of agents it can call. The conductor, the CLI, the
transports and the viewer all read the agent list from it. None of them names an agent in code.
The decision behind this design is [ADR-0011](adr/0011-remote-agents.md). It replaced the
entry-point discovery of [ADR-0010](adr/0010-agent-registry.md).

The code is in `workbench/src/workbench/registry.py`. The A2A client it uses is in `remote.py`.

## Where the list comes from

Each agent is a separate service. The workbench finds them through one configuration file,
[`../agents.yaml`](../agents.yaml):

```yaml
agents:
  - name: hello                  # optional; labels the agent if it is unavailable
    url: http://127.0.0.1:8101   # required; the agent's base URL
    timeout_s: 30                # optional; seconds per call, default 60
```

Set `DD_AGENTS_CONFIG` to use a different file, for example one per deployment.

The file holds only addresses. Everything else about an agent comes from the agent itself:
its identifier, version, the input classes it reads, its payload class, its grounding mode, its
action class, its requirement identifiers and how it derives each payload field (`derivations`).

## What happens at start-up

The workbench builds the registry once, when it starts. For each entry in `agents.yaml` it:

1. fetches the agent card from `<url>/.well-known/agent-card.json`;
2. finds the Data Director extension, `https://w3id.org/data-director/a2a/agent-spec/v0`, in the
   card's capabilities;
3. rebuilds the agent's `AgentSpec` from the extension's parameters, resolving each class name
   against the central contract;
4. registers the agent under the `agent_id` from the spec.

The `agent_id` comes from the card, not from `name` in `agents.yaml`. Requests, profiles and
envelopes use the `agent_id`, for example `hello.world`.

The workbench does not read the file again while it runs. If an agent starts after the
workbench, or its URL changes, restart the workbench to pick it up. Each CLI command is a new
process, so it always reads the current state.

## When something is wrong

Some problems stop the workbench from starting. Others affect only one agent.

| Problem | What happens |
|---|---|
| `agents.yaml` is missing, has no top-level `agents:` list, or an entry has no `url` | `RegistryError`. The workbench does not start. |
| Two cards declare the same `agent_id` | `RegistryError`. The workbench does not start. |
| The card cannot be fetched (the service is down, the URL is wrong, or the request times out) | The agent is recorded as **unavailable**, with the reason. The other agents still load. |
| The card has no Data Director extension; names a class it carries no schema for; carries a schema that does not match its digest; or declares a payload class that does not mix in `Grounded` | The agent is recorded as unavailable, with the reason. A class the workbench has not seen before is not a reason: the card carries its schema ([ADR-0019](adr/0019-core-contract-and-agent-owned-classes.md)). |
| The card declares a `contract_version` this workbench cannot govern, or none | The agent is recorded as **incompatible**, with both versions. The other agents still load ([ADR-0019](adr/0019-core-contract-and-agent-owned-classes.md)). |
| A request names an agent that is not registered | The conductor raises `UnknownAgent`. The message lists the registered agents and the reason each unavailable or incompatible one is missing. No envelope is written, because no agent ran. |
| A registered agent cannot be reached when a request is sent, times out, or answers outside the contract | The run ends `failed`, with problem type `agent-error`, and the envelope is stored as usual. |

An unavailable or incompatible agent is listed under its `name`, or under its URL if it has no
name. The registry does not know its `agent_id`, because it could not read the card, or could not
trust what the card said.

An agent is compatible when its card's `contract_version` has the workbench's major version and,
while the major version is 0, its minor version as well. The contract version is the `version` of
the core schema, `sdk/src/dd_sdk/schema/data_director.yaml`.

## Registration is not permission

The registry says which agents can be reached. The policy profile named in each request decides
which of them may run ([ADR-0003](adr/0003-policy-profiles.md)). A registered agent that the
profile does not enable is refused at the policy gate, and the refusal is recorded in an
envelope. See [`conductor.md`](conductor.md).

## Where the registry is shown

Every view below uses the same manifest, `describe(spec)` from `dd_sdk.agent`. The views
therefore always agree with one another.

| Where | What it shows |
|---|---|
| `uv run workbench agents` | A table of registered agents, then each unavailable or incompatible agent with its reason. Add `--json` for the raw manifest. |
| `GET /agents` | `{"agents": [...manifest...], "unavailable": {name: reason}, "incompatible": {name: reason}}`. The viewer reads this. |
| The workbench's own A2A card | One skill per registered agent, tagged with its grounding mode, the classes it accepts and its requirement identifiers. |
| The viewer | The agent picker, grouped by the prefix of each `agent_id`. Unavailable and incompatible agents appear with their reason and cannot be run. The payload view badges fields from the agent's `derivations` in the manifest. |

## Adding or removing an agent

To add an agent, serve it and add one entry to `agents.yaml`. Then enable it in the profiles
that should run it. The full steps are in [`../../agents/README.md`](../../agents/README.md).
To remove an agent, delete its entry. No other part of the workbench is edited.

For local development, `scripts/run-agents.sh` at the repository root starts every agent on the
port `agents.yaml` expects.

## In tests

Tests do not read `agents.yaml`. `Registry.from_agents` takes agent objects directly, and
`workbench.testing.make_conductor` passes each agent through `in_process` unless called with
`remote=False`. This serves the agent
with `dd_sdk.serve` on an in-memory ASGI transport and builds a `RemoteAgent` from its card.
Tests therefore use the same card, the same extension and the same A2A messages as a deployed
agent, without a network.

## Not yet decided

- Authentication between the workbench and its agents. TODO (ADR-0011). Until it exists, do not
  expose agent ports beyond the host or a private network.
- Reloading the registry, or checking agent health, while the workbench runs. TODO.
- Container images and a `compose.yaml` for running the agents. TODO (ADR-0011).
