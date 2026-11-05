# Architecture

This page gives a short overview of how the workbench is put together. For the whole system,
including the app and its deployment, start with [`docs/architecture.md`](../../docs/architecture.md). Why it is built this way
is in the [specifications](../../docs/specs/README.md). For one request followed through every step, with real output,
see [`walkthrough.md`](walkthrough.md).

## How a run works

A caller sends a request naming an agent and giving it an input. The harness returns one
response, called an envelope. The harness is a package of its own, and every front end is a way
in to it ([System and boundaries](../../docs/specs/system.md)). The harness serves an A2A
JSON-RPC endpoint for other systems. The workbench adds the command line and the web viewer for
development. Every way in hands the request to the same function, the
[conductor](../../harness/docs/conductor.md), so an agent behaves the same whichever front end is used.

Agents are separate services. The conductor reaches each one over A2A and gets back the
agent's result together with the trace spans the agent recorded
([Agents](../../docs/specs/agents.md)). The conductor runs a fixed sequence of steps:

```mermaid
flowchart LR
    T["Front end<br/>CLI · A2A · viewer"] --> P[Policy gate]
    P --> I[Input check]
    I --> A["Agent service<br/>over A2A"]
    A -. "ctx.delegate<br/>(delegation mode)" .-> P
    A --> G[Grounding linter]
    G --> C[Source check]
    C --> V[Schema validation]
    V --> S["Run store<br/>trace · Process Run Crate"]
    S --> T
```

1. The **policy gate** checks that the institution's profile allows this agent to run.
2. The **input check** confirms the agent reads this kind of input.
3. The **agent** does its work in its own process and returns an outcome, a payload, its
   evidence and its trace spans. The conductor adds the spans to the run's trace. An agent in
   grounding mode `delegation`, such as an orchestrator, may ask the workbench to run another
   agent through `ctx.delegate`. Each delegated run goes through every step here as a run of its
   own, and the conductor records it in the parent envelope's `delegations`
   ([Orchestration](../../docs/specs/orchestration.md)).
4. The **grounding linter** checks that the agent's account of its run is consistent: the
   output cites only what its grounding mode allows, and what the agent says it retrieved
   ([`grounding.md`](../../harness/docs/grounding.md)). It is a consistency check, not proof of retrieval.
5. The **source check** re-hashes each cited record against a pinned copy of the source that
   the workbench holds ([Evidence and grounding](../../docs/specs/grounding.md)).
6. The envelope is **validated** against the JSON Schema.
7. The run is **stored**, with its trace and a provenance record.

If a step refuses, later steps still record the refusal. The caller always gets an envelope that
says what happened. [`conductor.md`](../../harness/docs/conductor.md) describes each step in detail.

## Components

The repository is a uv workspace. `sdk/` holds everything an agent and the harness share.
`harness/` governs every invocation and depends only on `sdk/`. `workbench/` is the development
way in to the harness: the CLI, the viewer, evaluation and the conformance report.
`agents/` holds one package per agent, each run as its own service. `app/` is the Data Director
app (alpha), which calls the standards advisor through the conductor. Paths below are relative to the repository
root.

| Component | What it does | Where |
|---|---|---|
| Contract | Defines the request, the envelope and every input and payload class, in LinkML. The JSON Schema and SHACL in `generated/` are produced from it. | `sdk/src/dd_sdk/schema/data_director.yaml` |
| Contract models | Python (Pydantic) versions of the schema classes, schema validation and the RFC 9457 problem types. | `sdk/src/dd_sdk/contract/` |
| Agent interface | `AgentSpec`, `AgentResult`, `RunContext`, and the one manifest (`describe`). | `sdk/src/dd_sdk/agent.py` |
| Agent server | Serves one agent over A2A. It publishes the agent card with the spec extension, runs the agent under a tracer parented to the caller's span, and returns the result and spans. | `sdk/src/dd_sdk/serve.py`, `wire.py` |
| Tracing | Records each run as an OpenTelemetry span tree with the workbench's own `dd.*` attributes. | `sdk/src/dd_sdk/tracing.py` |
| Evidence | Hashes each source record in a fixed, named way (a canonicalisation). | `sdk/src/dd_sdk/evidence.py` |
| Conductor | Runs the steps above. Every front end calls it. | `harness/src/dd_harness/conductor.py` |
| Policy gate | Reads an institutional profile in YAML and decides whether an agent may run. | `harness/src/dd_harness/policy.py`, `workbench/profiles/` |
| Grounding linter | Checks the trace and the envelope against the rules for the agent's grounding mode. | `harness/src/dd_harness/grounding.py` |
| Source check | Re-hashes cited records against the pinned source copies listed in `sources.yaml`. | `harness/src/dd_harness/sources.py`, `workbench/sources.yaml` |
| Store and provenance | Appends each envelope to a JSONL file, writes a folder per run, and writes a Process Run Crate. | `harness/src/dd_harness/store.py`, `provenance.py` |
| Agent registry | Reads `agents.yaml`, fetches each agent's card and rebuilds its spec. `RemoteAgent` calls the agent over A2A. See [`registry.md`](../../harness/docs/registry.md). | `workbench/agents.yaml`, `harness/src/dd_harness/registry.py`, `remote.py` |
| Settings | Reads the deployment's configuration from `DD_*` variables, with defaults supplied by the caller, and builds a conductor. The workbench's development set is in `workbench.config`. | `harness/src/dd_harness/settings.py`, `workbench/src/workbench/config.py` |
| Front ends | The A2A JSON-RPC endpoint (part of the harness), and the workbench's CLI and the AG-UI event stream the viewer uses. | `harness/src/dd_harness/transport/a2a.py`, `workbench/src/workbench/cli.py`, `workbench/src/workbench/transport/` |
| Viewer | Read-only browser pages, Chat (the default), Inspect and Agents, that render requests and envelopes from the generated schema. No build step. | `workbench/viewer/` |
| Test kit | Serves an agent in memory for tests, and a scripted agent for harness tests. | `harness/src/dd_harness/testing/` |
| Conformance report | Maps passing tests and recorded human reviews to requirements and generates `CONFORMANCE.md`. See [`conformance.md`](../../docs/conformance.md). | `docs/requirements.yaml`, `docs/reviews.yaml`, `scripts/conformance_report.py` |
| Agents | One package and one service per agent. `example-hello/` is the template to copy. | `agents/` |
| FAIRsharing snapshot | The committed copy of FAIRsharing records that the standards advisor uses (CC BY-SA 4.0). | `agents/advisor-standards/data/fairsharing/` |

## Design principles

Two principles guide what is fixed and what is written here.

**Fix the formats now; the components can change later.** The data formats are settled. These
are the identifiers, the envelope, the trace attributes, the evidence canonicalisations and the
schema's slot URIs. Changing any of them changes a spec. The components that produce and consume
those formats sit behind interfaces and can be replaced. Agents, retrieval back ends, model
explainers and front ends are all replaceable.

**Use existing libraries for plumbing; write our own code for governance.** The workbench writes
its own code only where it makes a governance decision. These decisions are whether an action is
permitted, whether the evidence is enough, and whether to decline. Everything else, such as
tracing, schema validation and RO-Crate output, uses a maintained library behind a thin module
([Dependencies](../../docs/specs/dependencies.md)).

## Specifications

The reasons for the design, and what must stay true, are in the [specifications](../../docs/specs/README.md), one per topic.
