# Glossary

Terms used in the workbench, in alphabetical order.

| Term | Meaning |
|---|---|
| Agent | A program that takes one input and returns one result. In the Blueprint these are the Data Director's sub-agents. Each declares what it reads, what it returns and its grounding mode in an `AgentSpec`. See [`../src/workbench/agents/README.md`](../src/workbench/agents/README.md). |
| Canonicalisation | A fixed, named way of turning a record into bytes before hashing it, so the same record always gives the same hash. See [`grounding.md`](grounding.md). |
| Conductor | The function that runs an agent and applies every check. See [`conductor.md`](conductor.md). |
| Conformance report | `CONFORMANCE.md`, generated from the test results. It lists which Blueprint requirements the tests demonstrate. |
| Envelope | The response to one request: the outcome, the payload if any, the evidence and the telemetry. See [`contract.md`](contract.md). |
| Evidence | The list of source records an envelope rests on, each with a content hash. |
| Grounding | Tying an agent's output to the sources it actually read. See [`grounding.md`](grounding.md). |
| Grounding linter | The checker that applies the grounding rules after every run. |
| Grounding mode | What an agent's output may rest on: `retrieval`, `input_only` or `none`. |
| Outcome | What happened in a run: `succeeded`, `abstained`, `referred`, `failed` or `suspended`. See [`contract.md`](contract.md). |
| Payload | The agent's result, present only when the outcome is `succeeded`. |
| Policy profile | A YAML file in `profiles/` that says which agents an institution enables and which actions need approval. |
| Problem Details | The RFC 9457 format used to describe a `failed` or `suspended` outcome. |
| Process Run Crate | An RO-Crate provenance record of one run: which agent ran, on what input, and what it produced. |
| Shell | The read-only browser page in `shell/` for trying agents and inspecting envelopes. |
| Span, trace | A trace is the OpenTelemetry record of one run. It is made of spans, one per step, such as a retrieval or a model call. |
