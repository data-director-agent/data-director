# The conductor

The conductor is the part of the workbench that runs an agent. It takes a request, applies every
check, calls the agent, and returns an envelope. It lives in
[`src/workbench/conductor.py`](../src/workbench/conductor.py) as `Conductor.invoke`.

Every front end calls the conductor. The CLI, the A2A endpoint and the web viewer are thin
wrappers around it ([ADR-0001](adr/0001-transport.md)). This means an agent is held to the same
rules however it is called.

The conductor does not know about any particular payload class. It treats every agent the same
way, using only what the agent declares in its `AgentSpec`. Adding an agent never requires a
change to the conductor.

## What the conductor fills in

Some parts of an envelope must not be decided by the agent that produced it. The conductor sets
these itself:

- the invocation identifier and timestamps;
- the telemetry, including the trace identifier;
- the grounding mode the agent declared, which the linter then enforces;
- the hash of the input.

An agent returns only an `AgentResult`: an outcome, an optional payload, and the evidence it
used, plus the model id and token counts if it called a model.

## The steps

The conductor first validates the request against the JSON Schema, checks its `invocation_id` is
new, and looks up the agent. A malformed request, an `invocation_id` that is already stored or
still running, or an unknown agent id is a mistake by the caller, so the conductor raises an
exception rather than returning an envelope. A stored run is never overwritten.

After that, every problem becomes an outcome in the envelope. The caller, the run store and a
reviewer all see the same record.

| Step | What it checks | If the check fails |
|---|---|---|
| 1. Policy gate | Is the agent enabled in the institution's profile? Does its action class need approval? | Not enabled: `failed`, problem `agent-not-permitted`. Needs approval: `referred` to a data steward. The agent does not run. |
| 2. Input check | Does the agent read this input class? | `failed`, problem `input-not-accepted`. The agent does not run. |
| 3. Run the agent | The agent runs. The conductor checks it returned the payload class it declared. | An exception, or a payload of the wrong class: `failed`, problem `agent-error`. |
| 4. Grounding linter | Is the output based only on what the agent's grounding mode allows? See [`grounding.md`](grounding.md). | A `succeeded` envelope becomes `failed`, problem `grounding-violation`. The payload and evidence are removed. |
| 5. Validate and store | The envelope is validated against the JSON Schema, then stored. | An invalid envelope raises an exception; it is a bug in the workbench. |

The policy profile is a YAML file in `profiles/`. The gate answers only the two questions in
step 1 ([ADR-0003](adr/0003-policy-profiles.md)).

## Delegation

An agent in grounding mode `delegation`, such as an orchestrator, may ask the workbench to run
other agents for it ([ADR-0012](adr/0012-conversation-and-orchestration.md)). It never calls
them directly.

1. When the conductor runs such an agent, it issues a grant: a random token, valid only while
   that run is in progress. The token and the workbench's own A2A address travel to the agent
   with the request. `workbench serve` uses its own host and port as the address;
   `DD_WORKBENCH_URL` overrides it. `workbench invoke` issues no grant.
2. The agent calls `ctx.delegate(agent_id, input)`. The SDK sends a new request back to the
   workbench's A2A endpoint with the token.
3. `Conductor.invoke_delegated` checks the token and refuses an unknown or expired one, or an
   agent delegating to itself. It then runs the request through every step above, as a run of
   its own, in a trace of its own linked to the parent's. It takes the conversation and policy
   profile from the grant, and sets `parent_invocation_id`.
4. The conductor records the child's id, agent, version, status and envelope hash against the
   grant. When the parent finishes, the grant is revoked and those records become the parent
   envelope's `delegations`, even if the parent then fails.

A delegated run is never given a grant, so delegation is one level deep. A delegated run refused
by the policy gate is a `failed` child envelope, which the orchestrator relays. A caller may not
set `parent_invocation_id`; `invoke` refuses a request that does.

## What a run leaves behind

Each run appends the envelope to `runs/invocations.jsonl` and writes a folder,
`runs/<invocation_id>/`, containing the files below. A delegated run gets its own folder and
line, written before its parent's.

| File | Contents |
|---|---|
| `request.json` | The request as received. |
| `envelope.json` | The envelope returned. |
| `spans.jsonl` | The OpenTelemetry trace of the run. |
| `grounding.txt` | The grounding linter's verdict and any violations. |
| `sources.txt` | The source check's verdict: how many cited records were verified, which were unresolved, and any violations. |
| `ro-crate-metadata.json` | A Process Run Crate: a standard provenance record naming the agent, the request and the outputs. |

`DD_RUNS_DIR` changes where runs are written. `DD_WRITE_CRATE=0` stops the Process Run Crate
being written.
