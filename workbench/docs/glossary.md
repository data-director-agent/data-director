# Glossary

Terms used in the workbench, in alphabetical order.

| Term | Meaning |
|---|---|
| A2A | Agent2Agent, an open protocol for one agent service to call another over HTTP. Each service publishes an agent card describing itself, and callers send it messages using JSON-RPC. The workbench uses A2A in both directions: callers reach the workbench over it, and the workbench reaches each agent over it. See [`adr/0001-transport.md`](adr/0001-transport.md) and [`adr/0011-remote-agents.md`](adr/0011-remote-agents.md). |
| Agent | A program that takes one input and returns one result. In the Blueprint these are the Data Director's sub-agents. Each declares what it reads, what it returns and its grounding mode in an `AgentSpec`. Each runs as its own service and is reached over A2A. See [`../../agents/README.md`](../../agents/README.md). |
| Agent card | The JSON document an A2A service publishes at `/.well-known/agent-card.json`. A Data Director agent's card carries its `AgentSpec` in an extension. See [`registry.md`](registry.md). |
| Canonicalisation | A fixed, named way of turning a record into bytes before hashing it, so the same record always gives the same hash. See [`grounding.md`](grounding.md). |
| Conductor | The function that runs an agent and applies every check. See [`conductor.md`](conductor.md). |
| Conformance report | `CONFORMANCE.md`, generated from the test results. It lists which Blueprint requirements the tests demonstrate. |
| Content hash | A short fingerprint of a record's content when it was read. If the content changes, the hash changes. See [`grounding.md`](grounding.md#source-ids-and-content-hashes). |
| Envelope | The response to one request: the outcome, the payload if any, the evidence and the telemetry. See [`contract.md`](contract.md). |
| Evidence | The list of source records an envelope rests on, each with a content hash. |
| Grounding | Tying an agent's output to the sources it actually read during the run, so that it cannot present something it made up. See [`grounding.md`](grounding.md). |
| Grounding linter | The check applied after every run. It compares the sources a result names with what the trace shows the agent did, and withholds the result if they disagree. Also called the grounding check. See [`grounding.md`](grounding.md). |
| Grounding mode | What an agent's output may rest on, declared by each agent: `retrieval` (records it fetched), `input_only` (only its input, possibly with a model) or `none` (only its input, with no model). See [`grounding.md#grounding-modes`](grounding.md#grounding-modes). |
| OpenTelemetry | A widely used open standard for recording what software does while it runs. The workbench uses it for traces. |
| Outcome | What happened in a run: `succeeded`, `abstained`, `referred`, `failed` or `suspended`. See [`contract.md`](contract.md). |
| Payload | The agent's result, present only when the outcome is `succeeded`. |
| Policy profile | A YAML file in `profiles/` that says which agents an institution enables and which actions need approval. |
| Problem Details | The RFC 9457 format used to describe a `failed` or `suspended` outcome. |
| Process Run Crate | An RO-Crate provenance record of one run: which agent ran, on what input, and what it produced. |
| Registry | The workbench's list of agents it can call, built at start-up from `agents.yaml` and each agent's card. See [`registry.md`](registry.md). |
| Shell | The read-only browser pages in `shell/` (Inspect and Chat) for trying agents and inspecting envelopes. |
| Span, trace | A trace is a timed record of one run, in the OpenTelemetry format, written by the workbench rather than the agent. It is made of spans, one per step, such as fetching a record or calling a model. Spans nest inside one span for the whole run, forming a span tree. See [`grounding.md#traces-and-spans`](grounding.md#traces-and-spans). |
| Unavailable agent | An agent listed in `agents.yaml` whose card could not be read or was rejected. It is shown with the reason and cannot be run. See [`registry.md`](registry.md#when-something-is-wrong). |
