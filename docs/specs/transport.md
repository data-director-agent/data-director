# Transport and tracing

## Intent and scope

Data Director has one wire protocol between programs and one trace format.

- **A2A** (the JSON-RPC binding) is how the harness calls an agent, how a delegation agent calls
  the harness back, and how any other system, including another Data Director instance, calls the
  harness (Blueprint C5, C5.1). An `InvocationRequest` goes in; from the harness an `Envelope`
  comes out, and from an agent an `AgentResult` with the spans it recorded.
- **AG-UI** carries a run's events from the harness to a browser: its stages as they happen,
  its checks' reports, and its envelope.
- **OpenTelemetry** spans are the trace of every invocation, with a small attribute set under the
  `dd.` prefix that Data Director owns. The trace is what makes each action recorded,
  attributable and auditable (R10, C13), with its reasoning steps and decision points (C14), and
  it is what the grounding linter checks.

This spec covers the wire and the trace. What the linter concludes from spans is in
[Evidence and grounding](grounding.md); the registry and the manifest an agent card carries are
in [Agents](agents.md); delegation as a way of working is in [Orchestration](orchestration.md);
whom an invocation acts for, and how that is established, is in
[Policy and identity](policy-and-identity.md).

## Invariants

1. Every call from the harness to an agent is an A2A `message/send` over HTTP, in production and
   in tests alike. There is no in-process or entry-point path to an agent outside the test kit,
   and the test kit serves each agent with the same SDK server on an in-memory ASGI transport, so
   tests exercise the real wire without a network (`dd_harness.testing.serving`;
   `harness/tests/test_remote.py::test_an_in_process_agent_and_its_remote_twin_produce_the_same_outcome`).
2. A request carries exactly one data part, the `InvocationRequest` document. Anything else is a
   failed task and no run is made (`workbench/tests/test_transport.py::test_a2a_rejects_malformed_request`).
3. An agent returns an `AgentResult`, never an `Envelope`. The conductor alone fills identifiers,
   timestamps, telemetry, grounding mode and input hash ([Contract](contract.md)).
4. An agent returns its spans inline, beside its result, in the same reply. A run never depends on
   a third service to complete its trace.
5. A span crosses the wire as the JSON string the OpenTelemetry SDK wrote, not as a structured
   value, because A2A's protobuf `Struct` turns every integer into a floating-point number. For
   the same reason the harness answers a delegated request with the stored envelope as text, so
   its hash survives the wire, and an agent returns the prompts its model calls name as JSON
   strings keyed by digest, so each still hashes to its digest (`dd_sdk/wire.py`,
   [Disclosure](disclosure.md)).
6. The agent's spans join the conductor's trace under its `invoke_agent` span: the harness sends
   the W3C `traceparent` of that span, and the agent's server parents its tracer to it. Imported
   spans are kept under the conductor's trace identifier whatever trace they name, so a span
   placed outside the tree reaches the linter and is reported, never silently dropped
   (`harness/tests/test_remote.py::test_a_span_outside_the_invocations_trace_is_withheld`).
7. `dd.grounding_mode`, `dd.input_hash` and `dd.outcome` are set by the conductor on the root
   span only. A span from an agent that carries one is a grounding violation
   (`harness/tests/test_remote.py::test_a_span_carrying_a_conductor_attribute_is_withheld`).
8. A delegated invocation starts a trace of its own, linked to the delegating agent's `delegate`
   span rather than nested in it, so each invocation is linted over its own tree.
9. The span names and the owned attribute set are a fixed format, defined once in
   `dd_sdk/tracing.py`. Agents use its span helpers and never spell a name or key themselves.
   Changing either changes this spec. The span names are `invoke_agent`, `policy_gate`,
   `retrieval`, `chat`, `execute_tool` and `delegate`; the owned attributes are those in
   `OWNED_ATTRIBUTES`.
10. The linter and the provenance writer read only owned attributes, from a plain span record,
    never OpenTelemetry SDK objects. Any other attribute on a span (such as `dd.tool_name`) is
    informational and nothing in Data Director depends on it.
11. Every run's complete trace, the conductor's spans and the agent's, is written to the run store
    as the run's `spans.jsonl` artifact, one JSON span per line ([Storage](storage.md)).
12. An outcome the conductor decides, including a refusal by the input check or a grounding
    violation, is a completed task (or `RUN_FINISHED`) carrying an envelope. A failed task (or
    `RUN_ERROR`) means the harness could not make a run at all: a malformed request, an unknown
    agent, a request that tries to set its own profile or principal, or an unauthenticated
    caller (`harness/tests/test_transport_agui.py::test_a_request_that_makes_no_run_is_run_error_alone`).
13. A transport error, a timeout, a failed agent task or a reply outside the contract becomes a
    `failed` envelope with problem type `agent-error`; it never crashes the conductor
    (`harness/tests/test_remote.py`).
14. An agent card that does not declare the Data Director extension carrying its specification
    is rejected at registration (`harness/tests/test_registry.py::test_a_card_without_the_spec_extension_is_rejected`).
15. Whom an invocation acts for is never read from the A2A message or the AG-UI body; it comes
    from the caller's credentials ([Policy and identity](policy-and-identity.md);
    `workbench/tests/test_transport.py::test_a_request_saying_whom_it_acts_for_is_refused_by_both_transports`).
16. Every streamed run starts with `RUN_STARTED` then `CUSTOM dd.plan`, and ends with exactly one
    `RUN_FINISHED`. Between them, each of the conductor's stages that runs is a `STEP_STARTED` and
    a `STEP_FINISHED` whose `stepName` is the stage's id, in the plan's order; a stage that does
    not run sends neither (`harness/tests/test_transport_agui.py`).
17. `CUSTOM dd.grounding` and `CUSTOM dd.sources` carry the grounding linter's and the source
    check's reports for every run, inside their stages, before `RUN_FINISHED`
    (`harness/tests/test_transport_agui.py::test_a_grounding_violation_is_reported_before_the_failed_run`).
18. No text of a reply reaches a browser before the checks have run: a reply arrives only as the
    envelope in `RUN_FINISHED`, and a streamed run sends no `TEXT_MESSAGE_*` event.
19. A cancelled run ends its stream with `RUN_FINISHED` whose `outcome` is `cancelled` and which
    carries no `result`. The run itself is stored as `failed` with problem type `run-cancelled`,
    and nothing the agent answered is kept beyond its model calls. Only the principal who started
    a run may cancel it, and a stream the client leaves cancels its run
    (`harness/tests/test_transport_agui.py::test_a_cancelled_run_finishes_cancelled_and_is_stored_failed`).

## Boundaries and contracts

- **The SDK** (`dd_sdk`) holds both sides of the wire: the keys and artifact shapes, the agent
  server every agent package runs, and the tracing module. It is the only place the
  OpenTelemetry SDK is imported; elsewhere only the OpenTelemetry API (tracers, the trace-context
  propagator) is used. The agent server does no governance: it runs the agent under a fresh
  tracer and returns whatever the agent produced.
- **The harness** holds the A2A client that calls agents and the A2A server that serves the
  conductor. The harness's own card advertises one skill per registered agent and, through a
  second extension, the manifest a delegation agent routes from. Served without an
  authenticator, as the app serves it, the endpoint accepts only a delegation agent's callback
  under a live grant.
- **The agent card** is the machine-readable statement of what an instance serves. Its Data
  Director extension is marked required; the harness rebuilds the agent's specification from it
  and checks it against the contract ([Agents](agents.md)). The extension URIs are placeholders
  until a persistent identifier is registered, TODO(#3).
- **AG-UI** lives in the harness (`dd_harness.transport.agui`), and any way in mounts it. The
  workbench serves it to its viewer; the app does not serve it yet, TODO(#69).
  - `POST /agui` takes a `RunAgentInput` whose forwarded properties carry the
    `InvocationRequest`. The AG-UI thread is the contract's conversation, and a `threadId` naming
    another conversation is refused; the history an agent sees travels in the contract, not in
    AG-UI messages, so every transport gives an agent the same input.
  - `POST /agui/runs/{runId}/cancel` cancels the caller's run of that AG-UI `runId` while its
    stream is open, and answers 404 for any other.
  - `GET /agui/runs/{invocationId}` replays a stored run as `RUN_STARTED` then `RUN_FINISHED`
    with its envelope. A run's stages and reports are not stored as events, so a replay has none.
  - `dd_harness.transport.agui.stream_run` makes the events of any run started through
    `Conductor.ainvoke`, so a way in that wraps the conductor (the app's conversation turns,
    TODO(#69)) streams the same binding.
- **The AG-UI binding.** The conductor tells an observer (`dd_harness.observe`) what it is doing,
  and the binding turns that into AG-UI events, in this order:

  | Event | Carries |
  |---|---|
  | `RUN_STARTED` | `threadId`, `runId` |
  | `CUSTOM dd.plan` | `{steps: [{id, label}]}`, the conductor's fixed stages in order: `gate` (Policy gate), `input` (Input check), `agent` (Agent), `grounding` (Grounding check), `sources` (Source check). Human review joins them once it is built, TODO(#72). |
  | `STEP_STARTED`, `STEP_FINISHED` | `stepName`, a stage's id, for each stage that runs. After a policy refusal or referral the input check and the agent do not run; after an input refusal the agent does not. The checks run on every envelope. |
  | `CUSTOM dd.grounding` | The grounding linter's report, inside the `grounding` stage: `passed`, `mode`, `violations`, `retrieval_count`, `chat_count`. |
  | `CUSTOM dd.sources` | The source check's report, inside the `sources` stage: `passed`, `verified`, `unresolved`, `violations`. |
  | `RUN_FINISHED` | `result`: the envelope, as stored. When cancelled: `outcome: {type: "cancelled"}` and no `result`. |
  | `RUN_ERROR` | `message`, alone, for a request the harness could not make a run of (invariant 12). |

  The `dd.` prefix names Data Director's own events, as it names its own span attributes. A
  client ignores a `CUSTOM` name it does not know. `ag-ui-protocol` 1.x models
  `RUN_FINISHED.outcome` and `RunAgentInput.resume`, so nothing is sent as a raw dictionary.
- **Cancelling.** A blocking call to an agent cannot be stopped, so cancelling is a transport
  fact, not an outcome. The binding ends the stream at once with a cancelled `RUN_FINISHED`, and
  sets a flag the conductor looks at before each stage and when the agent answers. The run then
  carries on in its thread until the conductor next looks, and is stored as `failed` with problem
  type `run-cancelled` ([Contract](contract.md)): the store has a record of every run, and its
  outcome vocabulary is unchanged.
- **The app** must not import the workbench. Its shell runs agents through a JSON endpoint that
  answers when the run has ended, and draws its run view from the binding once it serves it,
  TODO(#69).

## Rationale

- **The conductor is a function**, so any transport is a thin wrapper around it. A second
  transport would add test surface and conformance work without adding a capability.
- **A2A fits both directions.** It is designed for agent-to-agent invocation, its agent card is a
  ready-made capability manifest, and its task lifecycle has `input-required` for the `suspended`
  outcome. It is also where C5's interaction between Directors points. Using it from harness to
  agent as well as from caller to harness keeps one wire format.
- **AG-UI is designed for the agent-to-frontend direction**, and `RUN_FINISHED` carries an
  arbitrary result, which is all a viewer of a finished envelope needs.
- **Calls are blocking, not streamed.** The policy gate, the grounding linter and the source check
  judge the whole envelope, so the conductor waits for the agent's finished reply and nothing
  reaches a person before those checks have run. Both card types declare `streaming: false`.
- **The stages stream; the reply does not.** The conductor holds the finished envelope while it
  checks it, so it can say which stage it is in without showing a person anything unchecked. A
  person waiting on a long run sees where it is, and the shell draws progress from events rather
  than guessing it afterwards from a problem type and the text of a stored summary.
- **Cancelled is stored as failed.** A new outcome status would change the contract and every
  client of it for a fact about the caller, not about the work. A problem type says the same
  thing within the vocabulary every client already reads.
- **The agent cannot be trusted to describe its own grounding.** Hence the conductor writes the
  root span's mode, input hash and outcome, and the linter checks that the agent's spans sit in
  the tree and carry none of them. The linter still relies on what the agent reports about its
  retrievals; independent re-fetching is the source check's concern ([Evidence and grounding](grounding.md)).
- **OpenTelemetry rather than a bespoke format**: a maintained SDK, a span tree that matches an
  invocation, and exporters for every backend, so traces are readable by any OpenTelemetry tool.
- **Owned `dd.*` attributes rather than the GenAI semantic conventions**: the `gen_ai.*`
  conventions are not yet stable and SDKs disagree on names. The owned attributes stay the source
  of truth. If convention names are emitted later, a span processor derives them from the owned
  ones, and nothing in Data Director reads them.
- **Each tracer is isolated**, not the global provider, so concurrent runs, tests and CLI runs never
  share state, and spans are held per trace and released once written, so a long-running
  conductor does not accumulate them.

## Rejected alternatives

- **A plain REST `POST /invoke`**, alone or beside A2A. It would need a capability manifest
  designed from scratch and has no task state for `suspended`; beside A2A it is a second transport
  to keep conformant. Callers who want plain HTTP must speak JSON-RPC 2.0; that cost is deliberate.
  The workbench CLI covers offline and CI use.
- **MCP between harness and agents.** MCP exposes tools to a model. Data Director agents decide
  outcomes, including `referred`, and need a long-running task state.
- **A different protocol from harness to agent than from caller to harness.** It would double the
  transport surface.
- **Running agents in the conductor's process, or keeping that as an alternative mode.** Two ways
  to reach an agent would mean two sets of behaviour to keep conformant.
- **The agent returning an `Envelope`.** The agent would fill fields only the conductor may fill.
- **Exporting agent spans to a collector the harness queries.** A run would depend on a third
  service being up and complete.
- **Carrying spans as structured data.** Integers would arrive as floating-point numbers and
  identifiers and token counts would no longer match.
- **Streaming before the checks.** Text shown to a person before the linter has judged it cannot
  be withdrawn.
- **A `cancelled` outcome status.** See the rationale above.
- **Cancelling only by dropping the connection.** The client would never hear from the harness
  that its run was cancelled, and would have to invent the ending itself. A dropped connection
  still cancels, so an abandoned run is not left to finish for nobody.
- **Not storing a cancelled run.** Its agent may have been called, and its model calls made;
  every call is recorded.

## Non-functional requirements

- **Security.** Calls between the harness and its agents are not authenticated, and a delegation
  grant is a bearer capability relying on the same boundary. Agent ports must not be exposed
  beyond the host or a private network, TODO(#17). `dd-harness serve` warns when bound beyond
  loopback without signing callers in. An unauthenticated caller of the harness is refused in
  the task rather than with HTTP 401, TODO(#17).
- **Testability.** Every transport is tested in process over an httpx ASGI transport with the A2A
  SDK's own client, so CI needs no network and no second process.
- **Portability.** Each wire dependency has a small hand-written fallback (a JSON-RPC 2.0
  `message/send` handler and client, the seven AG-UI event models the binding sends with an SSE
  encoder, a JSON-lines span writer); the register is in [Dependencies](dependencies.md). The `traceparent` header is
  a W3C Recommendation and can be written by hand.
- **Observability.** Exporting traces to an OTLP backend for viewing is not built; today a run's
  trace is read from its file in the run store, TODO(#10).

## Open questions

- Streaming an agent's reply to the app and the viewer, and how the linter and the store treat a
  partial reply that ends in failure, TODO(#159).
- Streaming a conversation turn to the app, with its delegated children as `SUBAGENT_*` events,
  TODO(#69).
- Mapping `suspended` to A2A `input-required` and an AG-UI interrupt, with resume, TODO(#72, #16).
- How the harness authenticates its agents and they authenticate it, TODO(#17).
- A persistent identifier for the A2A extension URIs, TODO(#3).
