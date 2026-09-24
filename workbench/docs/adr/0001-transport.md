# ADR-0001: Tier 1 transport is A2A JSON-RPC; AG-UI carries run events to the shell

**Status:** Accepted
**Date:** 2026-09-04

## Context

Agents must be invocable by other software (Blueprint C5: "expose open APIs … a harmonised API
for core features to enable inter-Director interactions"), and a read-only shell must be able to
show what an agent returned. The MVP plan left open whether to bind the contract to A2A JSON-RPC,
to a plain REST `POST /invoke`, or both.

Three facts decided it. The conductor is a plain function (`workbench.conductor.invoke`), so any
transport is a thin wrapper and a second one adds test surface without adding capability. A2A is
the only candidate designed for agent-to-agent invocation with an agent card describing skills,
which is what C5's inter-Director interaction needs. AG-UI is the only candidate designed for the
agent-to-frontend direction, and its `RUN_FINISHED` event carries an arbitrary result, which is
all a synchronous read-only shell needs.

## Decision

- **Agent invocation** uses the A2A protocol's JSON-RPC binding, served by `a2a-sdk`. The request
  is an `InvocationRequest` document carried as a data part of the user message; the response is
  an `Envelope` document carried as a data part of the task's single artifact. The agent card lists
  one skill per agent identifier.
- **Shell delivery** uses AG-UI: `POST /agui` accepts a `RunAgentInput` whose `forwarded_props`
  carry the `InvocationRequest`, and streams `RUN_STARTED` then `RUN_FINISHED` with the envelope as
  `result`. `GET /agui/runs/{invocation_id}` replays the same two events from the store, so a
  workshop can show a fixed output. No other AG-UI event is emitted at v0; streaming and the
  `suspended` interrupt arrive with the events that need them.
- **No REST `POST /invoke`.** The CLI (`workbench invoke`) covers offline and CI use.
- **Testing consequence:** contract tests drive the A2A application in-process with an httpx ASGI
  transport and the SDK's own client, so the transport is tested without a network.

## Dependencies introduced

| Dependency | Tier | Fallback if this dependency is abandoned |
|---|---|---|
| `a2a-sdk[http-server]` | Runtime path | The conductor is a function; a hand-written JSON-RPC 2.0 handler over Starlette reproduces `message/send` in under a hundred lines. The `InvocationRequest`/`Envelope` documents are unchanged. |
| `ag-ui-protocol` | Runtime path | Two pydantic event models and an SSE encoder; trivially re-implemented. The shell reads `RUN_FINISHED.result` only. |

## Consequences

- One agent transport to keep conformant; the agent card is the machine-readable statement of
  which requirements an instance claims to serve.
- Callers who want plain HTTP must speak JSON-RPC 2.0. This is a deliberate cost.
- The `suspended` outcome has a natural home (A2A `input-required` task state; AG-UI interrupt
  outcome) when it is implemented, without changing the envelope.
