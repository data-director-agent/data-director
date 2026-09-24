# ADR-0011: Agents are separate services the workbench calls over A2A

**Status:** Accepted
**Date:** 2026-09-24

Supersedes [ADR-0010](0010-agent-registry.md). Extends [ADR-0001](0001-transport.md), which
already uses A2A for callers of the workbench, to the workbench's calls to agents.

## Context

Under ADR-0010 every agent was a package inside the workbench distribution, found through Python
entry points and run in the conductor's process. The workbench and the agents were one program.
An agent could not be written, versioned, deployed or scaled apart from the harness that governs
it. Its dependencies (a retrieval index, a model client) were also the workbench's dependencies.

The workbench needs only an agent's inputs and outputs, and the evidence of what the agent did.
Its governance does not depend on where the agent's code runs:

- the policy gate;
- the input check;
- the payload check;
- the grounding linter;
- validation, storage and provenance.

Several constraints followed:

- **One wire format.** The workbench already serves A2A JSON-RPC to its callers, with an
  `InvocationRequest` in and an `Envelope` out (ADR-0001). Using a second protocol from the
  workbench to its agents would double the transport surface.
- **The linter needs the agent's spans.** The G, R and N rules are checked against the
  `retrieval` and `chat` spans the agent records. When an agent runs in another process, those
  spans must come back with its result, or there is nothing to check.
- **The contract stays central.** Input and payload classes remain defined in one LinkML schema
  (ADR-0007). An agent may not introduce a class the workbench does not know.

Three protocols were considered: A2A, MCP and a plain REST endpoint. MCP exposes tools to a
model. These agents decide outcomes, including `referred`, and `suspended` will need a
long-running task state. A plain REST endpoint would need a capability manifest designed from
scratch. A2A has both: the agent card is the manifest, and the task lifecycle has
`input-required`. It is also the protocol Blueprint C5 points towards for interactions between
Directors.

## Decision

1. **Each agent is its own package and its own service.** It lives under
   `agents/<name>/` in this repository, in a uv workspace with `sdk/` and `workbench/`. It has
   its own `pyproject.toml` and a console script, `dd-<name> serve --port N`. The workbench
   distribution contains no agent code.
2. **What both sides share is `data-director-sdk`.** This is the contract models and generated
   schema, evidence canonicalisations, span helpers, `AgentSpec` / `AgentResult` / `RunContext`,
   the wire keys (`dd_sdk.wire`) and the A2A server (`dd_sdk.serve`). The schema moves into the
   SDK because both sides import it; it is still one file, and changing it is still an ADR.
3. **Workbench → agent** is one A2A `message/send` using the JSON-RPC binding:
   - The message's single data part is the `InvocationRequest`.
   - The message's `metadata` carries `dd.input_ref`, `dd.input_hash` and the W3C `traceparent`
     of the conductor's `invoke_agent` span.
4. **Agent → workbench** is a completed task. Its single artifact, `agent-result`, holds one data
   part: `{"result": <AgentResult>, "spans": [<span JSON>, ...]}`.
   - Each span is the string `ReadableSpan.to_json` produced. It is carried as a string because
     protobuf's `Struct` would turn its integers into floating-point numbers.
   - The agent does not return an `Envelope`. The conductor still builds it and fills every
     identifier, timestamp, telemetry field, grounding mode and input hash.
5. **The agent card declares the extension** `https://w3id.org/data-director/a2a/agent-spec/v0`.
   Its `params` are `describe(spec)`. The workbench rebuilds the `AgentSpec` from the extension
   and resolves class names against the contract. A card without the extension, or one naming a
   class the contract lacks, is rejected.
6. **Discovery is configuration.** `workbench/agents.yaml` lists each agent's base URL, with an
   optional name and timeout, and `DD_AGENTS_CONFIG` overrides the path. The registry reads each
   card at start-up. An agent whose card cannot be read or is rejected is recorded as
   unavailable with the reason, and the others still load. The policy gate still decides, per
   profile, which registered agents may run.
7. **`RemoteAgent` keeps the conductor unchanged.** It satisfies the same `Agent` protocol. Its
   `run` sends the message and returns the `AgentResult` with the spans attached. The conductor
   imports the spans into its trace before linting. A transport error, a timeout, a failed task
   or a result outside the contract raises, and the conductor's existing exception branch records
   it as `failed` with problem type `agent-error`.
8. **G0 checks the span tree.** Every span in the invocation must be in the root's trace and
   descend from `invoke_agent`, and only the root may carry `dd.grounding_mode`, `dd.input_hash`
   or `dd.outcome`. Imported spans are kept under the conductor's trace identifier whatever
   trace they name, so a span placed outside the tree is reported, not silently dropped. A
   breach is a grounding violation.
9. **Agents run in process only in tests.** `workbench.testing.in_process` serves an agent with
   `dd_sdk.serve` on an in-memory httpx ASGI transport and builds the `RemoteAgent` from its
   card. Harness tests therefore exercise the real wire without a network.

Rejected:

- **Keeping entry points as an alternative mode.** Two ways to reach an agent would mean two
  sets of behaviour to keep conformant.
- **Returning an `Envelope` from the agent.** The agent would be filling fields only the
  conductor may fill.
- **Exporting spans to a collector the workbench queries.** A run would depend on a third
  service being up and complete. Returning the spans inline keeps each run self-contained.

## Dependencies introduced

| Dependency | Tier | Fallback if this dependency is abandoned |
|---|---|---|
| `a2a-sdk` client (`a2a.client`) | Runtime path | Already a runtime dependency for the server side (ADR-0001). `workbench.remote` is its only importer in the workbench and `dd_sdk.serve` the only one in the SDK; a hand-written JSON-RPC 2.0 `message/send` over httpx replaces the client in either. |
| `opentelemetry` W3C trace-context propagator | Runtime path | Part of `opentelemetry-api`, already present. The `traceparent` header format is a W3C Recommendation and can be written and parsed by hand. |

## Consequences

- Adding an agent means adding a package under `agents/` (or anywhere else), serving it, and
  adding one line to `agents.yaml`. The conductor, linter, CLI, transports and shell are not
  edited.
- An agent can be deployed, scaled and restarted on its own. It can also be unreachable, and the
  workbench reports it as unavailable and carries on.
- The trust boundary moves. The linter checks what the agent reports about its spans, and it
  did so before too, but the report now crosses a network. Independently re-fetching retrieved
  sources to verify their hashes is TODO.
- Authentication between the workbench and its agents is TODO (mutual TLS, bearer tokens or a
  gateway). Until it exists, agent ports must not be exposed beyond the host or a private network.
- Invocations are blocking `message/send`. Streaming, and mapping `suspended` to A2A
  `input-required`, arrive with the outcome that needs them.
- A persistent identifier for the extension URI is TODO, as it is for the problem-type namespace
  (ADR-0004).
- Container images and a `compose.yaml` are TODO. `scripts/run-agents.sh` starts every agent
  locally.
- Test module basenames must be unique across the workspace, because test directories are not
  packages and pytest imports each module by its basename.
