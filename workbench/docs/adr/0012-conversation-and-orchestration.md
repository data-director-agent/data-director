# ADR-0012: Conversations, and orchestration through the workbench

**Status:** Proposed
**Date:** 2026-09-24

Amends [ADR-0002](0002-opentelemetry.md) (a new span name),
[ADR-0008](0008-grounding-modes.md) (a new grounding mode),
[ADR-0009](0009-evidence-canonicalisations.md) (a new canonicalisation) and
[ADR-0011](0011-remote-agents.md) (new wire keys, and a second importer of the A2A client in the
SDK).

## Context

The workbench ran one request against one agent and returned one envelope. Developers building
Data Director agents also need to converse with them: with the primary Data Director agent, an
orchestrator that hands work to specialist agents, and with each specialist directly. In a
development environment every reply must say which agent, at which version, produced it.

Several constraints shaped the answer:

- **Governance must not thin out in conversation.** The policy gate, the input check, the
  grounding linter, the store and provenance exist per invocation. A conversation that
  bypassed them, or an orchestrator that called other agents outside the workbench, would make
  its output ungoverned.
- **Agents are separate services (ADR-0011).** An orchestrator cannot reach the conductor in the
  workbench's process; its hand-offs cross the network.
- **The linter trusts only what the harness can check.** An agent's spans come back from the
  agent's process. What an orchestrator says it delegated is the agent's account, not a fact
  the workbench observed.
- **No orchestrator exists yet.** The contract must admit a model-backed orchestrator later
  without change, while a deterministic stand-in exercises it now.

## Decision

1. **A turn is one invocation.** A conversation is the set of top-level invocations that share a
   `conversation_id` (a UUIDv7, a new optional slot on `InvocationRequest` and `Envelope`). Each
   turn produces one envelope under every existing rule. Turn order is the order of the store's
   JSONL file; it is not stored.
2. **The conversation travels in the contract.** A new input class, `Message`, carries
   `message_text` and `history` (a list of `ConversationTurn`: `role`, `turn_text`, and for an
   agent turn `turn_agent_id`, `turn_agent_version`, `turn_invocation_id`). The history is part
   of the input, so the input hash covers what the agent was shown, and every transport gives
   the agent the same document. AG-UI's `threadId` is the `conversation_id`; its `messages` are
   mirrored by the viewer but not read.
3. **A new payload class, `Reply`** (`reply_text`, `reply_derivation`), mixes in `Grounded` as
   every payload does.
4. **Conversations are derived, not stored.** `workbench.conversations` reads them from
   `invocations.jsonl` and `request.json`: turns, the children each delegated, the stored inputs,
   version changes per agent, and the history for the next turn. `GET /conversations` and
   `GET /conversations/{id}` serve them.
5. **An orchestrator delegates only through the workbench, under a grant.** When the conductor
   runs an agent whose mode is `delegation`, and it knows its own A2A address, it issues a grant:
   a random token live only while that invocation runs. `RemoteAgent` sends the token and the
   callback URL as message metadata (`dd.delegation_token`, `dd.delegate_url`). `dd_sdk.serve`
   builds `ctx.delegate` from them, and `dd_sdk.delegate` sends a child `InvocationRequest` back
   to the workbench's A2A endpoint with the token and its `traceparent`.
   `Conductor.invoke_delegated` refuses an unknown or expired token and self-delegation, then
   runs the child as an ordinary invocation, with its `conversation_id` and policy taken from the
   grant and `parent_invocation_id` set to the parent. A child is never given a grant, so
   delegation is one level deep.
6. **Only the conductor sets lineage.** A caller's request carrying `parent_invocation_id` is
   refused. The parent envelope's `delegations` (a list of `Delegation`: child id, agent,
   version, status, and the child envelope's hash) is the conductor's record of the children it
   ran for that grant, kept even when the parent later fails.
7. **A new grounding mode, `delegation`.** The agent may call a model and may not retrieve (R1).
   Every `grounded_on` entry and every evidence item is either the input or a recorded delegation
   (D1, D2), a succeeded envelope cites its input (D3), and G4 applies. A relayed child is cited
   as `invocation:<child_id>` with the new canonicalisation `dd-envelope-json-v1`, the stored
   envelope document with sorted keys. D1 and D2 check against `delegations`, which the conductor
   filled, not against spans the agent reported.
8. **Each child has its own trace.** Its `invoke_agent` span starts a new trace with a span link
   to the orchestrator's new `delegate` span. Nesting the child in the parent's trace would give
   the parent two roots (G0) and, for a retrieval child, retrieval spans the parent may not have
   (R1).
9. **The envelope crosses the callback as text.** The workbench answers a delegated request with
   an `envelope-json` artifact holding the stored JSON as a string, so the hash the agent cites
   survives protobuf `Struct`, which turns integers into floating-point numbers.
10. **The callback address is the workbench's own.** `workbench serve` uses its host and port;
    `DD_WORKBENCH_URL` overrides it. `workbench invoke` issues no grant, so a delegation agent
    run from the CLI has no `delegate`.
11. **`director.stub` is the reference orchestrator** (`agents/director/`): rule-based routing
    from `routing.yaml`, a template reply, no model. It succeeds once it has delegated and
    relayed, whatever the child's outcome; the child's status is on its own envelope and in
    `delegations`.
12. **The viewer has two modes.** Inspect is the existing single-run screen. Chat holds a
    conversation with one agent, labels every reply and every delegated child
    `agent_id@agent_version`, marks version changes between turns, and links each card to its
    envelope in Inspect. The orchestrator is found by grounding mode, never by name.

Rejected:

- **The orchestrator calling other agents directly over A2A.** Faster to build, but the children
  would be ungoverned and unstored, and the parent could cite anything it liked.
- **Declaring `none` or `input_only` for the orchestrator.** Under R2 it could cite only its
  input, so a relayed answer would be ungrounded.
- **Declaring `retrieval`.** G1 requires a retrieval before any model call; a model-backed
  orchestrator decides what to delegate before it delegates.
- **Checking delegations against the agent's `delegate` spans.** Those spans are the agent's
  account; the conductor has its own record of what it ran.
- **History in AG-UI `messages` only.** The A2A and CLI paths would not carry it, and the input
  hash would not cover it.
- **A conversation store.** It would duplicate what the invocation store already holds.

## Dependencies introduced

| Dependency | Tier | Fallback if this dependency is abandoned |
|---|---|---|
| `a2a-sdk` client in the SDK (`dd_sdk.delegate`) | Runtime path | Already a runtime dependency of both sides (ADR-0011). `dd_sdk.delegate` and `dd_sdk.serve` are the SDK's only importers; a hand-written JSON-RPC 2.0 `message/send` over httpx replaces the client. |

## Consequences

- An orchestrator's every hand-off is a stored, linted, traced invocation that a reviewer can
  open on its own, and the parent envelope names each one with its agent and version.
- Contract 0.3.0. The new slots are optional and an empty `delegations` is omitted, so envelopes
  stored under 0.2.0 still validate and other agents' envelopes are unchanged.
- A model-backed orchestrator uses the same spec (`Message` in, `Reply` out, mode
  `delegation`), adds a `chat` span and `reply_derivation` `model`, and needs no contract change.
- The grant token is a bearer capability. ADR-0011's rule still holds: agent and workbench ports
  stay on the host or a private network until authentication exists (TODO).
- An orchestrator's timeout in `agents.yaml` must exceed the timeouts of the agents it delegates
  to.
- Conversations are found by scanning the JSONL file (TODO: an index if the store grows large).
- TODO, not decided here: mapping A2A `context_id` to `conversation_id`; delegation more than
  one level deep; delegation from the CLI; whether children inherit `requirement_ids`; the
  parent's Process Run Crate referencing its children's crates; checking a caller's history
  against the store; whether an orchestrator should mirror a failed child's status; streaming
  replies (`TEXT_MESSAGE_*`).
