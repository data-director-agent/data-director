# One run, step by step

This page follows one request through the workbench, from the command line to the files it
leaves behind. It is meant to be read first, before [`architecture.md`](architecture.md),
[`conductor.md`](../../harness/docs/conductor.md) and [`grounding.md`](../../harness/docs/grounding.md), which give the detail and the
reasons.

The output shown here was produced by running the commands below. Long hashes are shortened
with `…`.

## Why there are so many steps

An agent, particularly one that calls a language model, can go wrong in ways that are hard to see
from its answer alone. It may run where the institution has not allowed it. It may be given an
input it does not understand. It may cite a source it never read, or a source that does not say
what it claims. And once it has answered, nobody may be able to reconstruct what it did.

The Blueprint asks that every result can be traced to the person it was made for, the sources it
rests on, and the steps that produced it. Each step of a run answers one question towards that:

| Step | Question it answers |
|---|---|
| 1. Policy gate | May this agent run here at all? |
| 2. Input check | Does this agent read this kind of input? |
| 3. The agent runs | What did the agent produce, and what does it say it did? |
| 4. Grounding linter | Does what the agent cites match what it says it did? |
| 5. Source check | Do the cited records exist, and say what the agent says they say? |
| 6. Validate and store | Is the response well formed, and can someone audit it later? |

The agent's author writes none of these steps. An agent is a specification and a `run`
function (see `agents/hello/`). The conductor applies every step, in the same way, to every agent
and from every front end.

## The example

`fact.checker` checks a short claim against a few packaged reference documents. It is a
`retrieval` agent: it fetches records, then reasons over them. The input is
[`samples/claim.json`](../samples/claim.json):

```json
{
  "schema_class": "Claim",
  "text": "A DOI does not change when the object moves.",
  "context": "Asserted in a draft data management plan."
}
```

With the agents running (`scripts/run-agents.sh`) and `DD_PRINCIPAL_ID` and `DD_PRINCIPAL_NAME`
set (see the [README](../README.md#who-an-invocation-acts-for)), from `workbench/`:

```sh
uv run workbench invoke --agent fact.checker --input samples/claim.json
```

The CLI wraps the input in a request, giving it a new `invocation_id`, and hands it to the
conductor. The viewer and the A2A endpoint do the same, so what follows is identical whichever
front end is used.

## Before any step: is the request usable?

The conductor validates the request against the JSON Schema, checks that its `invocation_id` has
not been used before, and looks up the agent. A failure here is the caller's mistake, so the
conductor raises an error and records nothing.

It then sets what the agent must not decide for itself:

- the timestamps and the trace identifier;
- **the input hash**: a SHA-256 fingerprint of the input. The input is given the source id
  `input:<invocation_id>`, so an agent that works only from its input can cite it like any other
  source;
- **`acting_for`**: the person the run is for, taken from the caller's authentication, not from
  the request ([ADR-0018](../../docs/adr/0018-acting-for.md)).

It opens the root span of the run's trace, `invoke_agent`. Everything that happens next is
recorded inside it.

## 1. Policy gate

The conductor asks the deployment's institutional profile (`profiles/default.yaml` unless
another is configured) whether `fact.checker` is enabled, whether it declares the action class
the profile assigns it, and whether that class needs a data steward's approval.

Here it is enabled and needs no approval, so the run continues. Had it not been enabled, the
envelope would say `failed` with problem `agent-not-permitted`, and the agent would not be
called. Had it needed approval, the envelope would say `referred`. The profile's reference and
digest are recorded on every envelope, so a reader can see which rules applied.

## 2. Input check

`fact.checker` declares that it reads `Claim`. The input is a `Claim`, so the run continues.

Sending it the wrong kind of input shows what a refusal looks like:

```sh
uv run workbench invoke --agent fact.checker --input samples/hello.salutation.json
```

```json
"outcome": {
  "status": "failed",
  "statement": "fact.checker accepts Claim, not Salutation. The agent was not run."
},
"problem": {
  "type": "https://w3id.org/data-director/problems/input-not-accepted",
  "detail": "Agent 'fact.checker' accepts Claim; the request carried 'Salutation'."
}
```

From this point on, every problem becomes an outcome in the envelope rather than an error. The
caller, the run store and a reviewer all see the same record.

## 3. The agent runs

The conductor calls the agent over A2A. The agent runs in its own process and sends back three
things:

- **an outcome and a payload**: the answer, here the verdict `supported` with a rationale;
- **evidence**: the agent's bibliography, one item per record it relied on, each with the
  record's id, where it came from, and a hash of its content;
- **spans**: the agent's diary of what it did, in OpenTelemetry format.

The payload names its sources in `grounded_on`:

```json
"payload": {
  "schema_class": "FactCheck",
  "verdict": "supported",
  "rationale": "Supported by lexical match against wb:doi-handbook (2 source(s) consulted). …",
  "rationale_derivation": "template",
  "grounded_on": [
    { "source_id": "wb:doi-handbook", "content_hash": "e5e32e7d…" },
    { "source_id": "wb:cc-by-4",      "content_hash": "d65e06f6…" }
  ]
}
```

The conductor adds the agent's spans to the run's trace. The finished tree is:

```text
invoke_agent   fact.checker, mode retrieval, input hash 07445efc…   (conductor)
├── policy_gate                                                      (conductor)
├── retrieval  wb:doi-handbook, hash e5e32e7d…                       (agent)
└── retrieval  wb:cc-by-4,      hash d65e06f6…                       (agent)
```

An agent that called a language model would also have a `chat` span, recording the model and
the token counts.

The conductor also checks that the payload is of the class the agent declared. A wrong class, or
an exception in the agent, becomes `failed` with problem `agent-error`.

## 4. Grounding linter

The agent has now given two accounts of its run: what it cites (`grounded_on` and its evidence)
and what it did (its spans). The linter checks that they agree. For a `retrieval` agent:

- every source in `grounded_on` was retrieved in this run, with the same hash (G2);
- every evidence hash appears on a retrieval (G3);
- every source in `grounded_on` is also in the evidence (G4);
- any model call came after at least one retrieval (G1).

Here they agree:

```text
grounding: passed [retrieval] (2 retrieval, 0 chat spans)
```

To see what a failure looks like, take the stored envelope and add a citation the agent never
retrieved. The linter can be run over any finished run:

```sh
uv run workbench lint runs/<invocation_id>/spans.jsonl tampered.json
```

```text
grounding: FAILED [retrieval]
  - G2: payload rests on 'wb:made-up' (000000000000…) which was not retrieved in this invocation
  - G4: payload rests on 'wb:made-up' (000000000000…) absent from evidence
```

In a live run, a violation turns a `succeeded` outcome into `failed`, with problem
`grounding-violation`, and removes the payload and the evidence. The caller does not receive an
answer that rests on something the run does not account for.

The linter is a consistency check. The spans are written by the agent, so a pass shows that the
agent's story is consistent, not that it is true. That is what the next step is for.

## 5. Source check

The workbench holds its own copies of the sources agents cite, listed in
[`sources.yaml`](../sources.yaml) and pinned by hash. For each evidence item, the source check
looks up the record in the copy named by the item's `snapshot_ref` and hashes it again
([ADR-0016](../../docs/adr/0016-source-check.md)):

- the record must exist in the copy (S1), which catches an invented record;
- it must hash to the evidence item's `content_hash` (S2), which catches a record the agent
  changed.

```text
sources: 2 verified, 0 unresolved
```

The hash is what makes this possible. It is computed in a fixed, registered way (a
canonicalisation, [ADR-0009](../../docs/adr/0009-evidence-canonicalisations.md)), so the same record
always gives the same hash, and a single changed character gives a different one. Changing the
hash an envelope claims for `wb:doi-handbook`:

```sh
uv run workbench verify tampered.json
```

```text
sources: 1 verified, 0 unresolved; FAILED
  - S2: evidence 'wb:doi-handbook' hash 111111111111… does not match 'packaged:sources.json', where the record hashes to e5e32e7d…
```

A violation withholds the result in the same way as a linter violation. An item whose source
has no copy in `sources.yaml` is reported as unresolved, and never counted as verified.

## 6. Validate and store

The finished envelope is validated against the JSON Schema. If what the agent returned breaks
the contract, the run is stored as `failed` with `agent-error`.

The envelope is then appended to `runs/invocations.jsonl`, and a folder is written for the run:

```text
runs/<invocation_id>/
├── request.json     the request as received
├── envelope.json    the response returned
├── spans.jsonl      the trace: the tree shown in step 3, with times
├── grounding.txt    the linter's verdict
├── sources.txt      the source check's verdict
└── crate/           a Process Run Crate: a standard provenance record of the run
```

Each file answers a question a reviewer may ask later: what was asked, what came back, what the
agent did, whether the checks passed, and, in a format other tools read, who ran what for whom.
`DD_WRITE_CRATE=0` stops the crate being written.

## The response

The envelope returned to the caller brings the pieces together. Abridged:

```json
{
  "invocation_id": "01a14011-d50a-72ad-b07f-5eadabedcfc9",
  "agent_id": "fact.checker",
  "agent_version": "0.1.0",
  "grounding_mode": "retrieval",
  "policy_bundle_ref": "profile:default@v2",
  "acting_for": { "name": "Josiah Carberry", "assurance": "asserted", "…": "…" },
  "outcome": {
    "status": "succeeded",
    "statement": "Verdict supported, grounded in 2 retrieved source(s). Human review is required."
  },
  "payload": { "verdict": "supported", "grounded_on": ["…"], "…": "…" },
  "evidence": [
    {
      "source_id": "wb:doi-handbook",
      "source_uri": "https://www.doi.org/the-identifier/resources/handbook",
      "snapshot_ref": "packaged:sources.json",
      "canonicalisation": "dd-json-document-v1",
      "content_hash": "e5e32e7d…"
    }
  ],
  "telemetry": { "trace_id": "511a8dfc7269b29841f499efd7788967" },
  "requires_human_review": true
}
```

Every field in it was either set by the conductor, or returned by the agent and checked by the
steps above.

## Other kinds of agent

The steps are the same for every agent. What changes with the agent's grounding mode is which
rules the linter applies ([`grounding.md`](../../harness/docs/grounding.md#grounding-modes)):

- `input_only` and `none` agents may not retrieve anything, and cite only the input, by the
  `input:<invocation_id>` id and the input hash the conductor computed. `none` agents may not
  call a model either. `hello.world` is the simplest example.
- `delegation` agents, such as the orchestrator `director.stub`, ask the workbench to run other
  agents for them. Each of those runs goes through every step on this page as a run of its own,
  and the orchestrator may cite only runs the conductor recorded
  ([ADR-0012](../../docs/adr/0012-conversation-and-orchestration.md)).

## What the checks do not show

The checks show that a result is consistent with its sources, not that it is correct. A pass
does not show that a model's rationale is faithful to the records it cites, or that a
`*_derivation` badge is accurate. Those are matters for evaluation
([ADR-0013](../../docs/adr/0013-evaluation.md)) and for the human review that every envelope asks for.
