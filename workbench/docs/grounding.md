# Grounding

An agent's output is *grounded* when everything it relies on can be traced to something the
agent actually read during the run. The workbench checks this after every run with the grounding
linter in [`src/workbench/grounding.py`](../src/workbench/grounding.py)
([ADR-0008](adr/0008-grounding-modes.md)).

## Why it matters

Language models can produce confident, plausible text that is not true. If a model is asked to
recommend a metadata standard, it may name a record that does not exist, or one the agent never
looked up. Grounding rules this out. An agent may only present something as a result if the run
shows where it came from. If the agent claims something it cannot back up, the workbench
withholds the result rather than passing it on.

## What the check compares

The check compares two accounts of the run.

1. **What the agent says it relied on.** Each result lists its sources in a `grounded_on` list
   ([`contract.md`](contract.md)). The envelope's evidence repeats those sources.
2. **What the trace says the agent did.** The trace records each step of the run.

A result passes only if the two agree.

The two accounts come from different places. Some facts are recorded by the conductor: the
grounding mode, the hash of the input, the `invoke_agent` span, and the runs it performed for a
delegating agent. The agent cannot change these. Other facts are declared by the agent: its
`retrieval` and `chat` spans and their times, its `grounded_on` lists, its evidence and its
derivation badges. An agent runs as a separate service and sends its spans back with its result
([ADR-0011](adr/0011-remote-agents.md)), so a `retrieval` span is the agent's statement that it
read a record, not the workbench's observation of it.

The linter is therefore a **consistency check**
([ADR-0016](adr/0016-source-check.md)). See [What a pass shows](#what-a-pass-shows-and-what-it-does-not).

## Traces and spans

A *trace* is a timed record of one run, in the [OpenTelemetry](https://opentelemetry.io/) format
([ADR-0002](adr/0002-opentelemetry.md)). OpenTelemetry is a widely used open standard for
recording what software does while it runs.

A trace is made of *spans*. A span is one step, such as fetching a record or calling a model. Each
span records when the step started and ended, and a few facts about it, called *attributes*.
Spans nest: the steps an agent takes sit inside one span for the whole run. The result is a
*span tree*. A typical run of a `retrieval` agent looks like this:

```text
invoke_agent    the whole run: which agent, its grounding mode, a hash of the input
├── retrieval   fetched one source record: its id and a hash of its content
├── retrieval   fetched another source record
└── chat        called a language model: which model, how many tokens
```

The workbench uses only these three span names. It also uses a small set of its own attributes,
whose names start with `dd.`, defined in `dd_sdk/tracing.py`. The check reads the tree in two
ways:

- the **start and end times** show whether the agent's declared fetches came before it called a
  model;
- the **retrieval spans** list the records the agent says it fetched, so every source the result
  names can be matched against them.

Each finished run keeps its trace in `runs/<invocation_id>/spans.jsonl`.

## Source ids and content hashes

Each source is identified by two things: an id, which says *which* record it is, and a content
hash, which is a short fingerprint of *what the record said* when it was read. Checking both
catches a result that names the right record but relies on a different version of it. The hash
is computed with a registered canonicalisation, a fixed way of turning the record into bytes, so
the same content always gives the same hash
([ADR-0009](adr/0009-evidence-canonicalisations.md)).

## Grounding modes

Agents do different kinds of work, so they rely on different things. Each agent declares one
grounding mode, which says what its output may rest on. There is no default.

| Mode | The agent… | May call a model? | Its result must cite… | Rules applied | Used by |
|---|---|---|---|---|---|
| `retrieval` | fetches records from outside sources, then reasons over them. | Yes, but only after it has fetched something. | only records it fetched in this run. | G0, E1, G1–G4 | `fact.checker`, `r3.standards-advisor` |
| `input_only` | works only on the input it was given. | Yes. | only the input. | G0, E1, R1–R3 | `quality.reviewer` |
| `none` | works only on its input, by fixed rules, with no model. The same input always gives the same result. | No. | only the input. | G0, E1, R1–R3, N1 | `hello.world`, `stub.abstain` |
| `delegation` | works on its input and on the envelopes of runs it delegated through the workbench. | Yes. | the input, and runs the conductor recorded as delegated. | G0, E1, R1, D1–D3, G4 | `director.stub` |

The modes run from least to most restricted: `input_only` forbids fetching, and `none` also
forbids model calls. Every mode still requires a successful result to cite something, even if
that is only the input.

The declared mode is a claim, and the check tests it. The conductor records the mode on the
envelope and on the trace. The linter then applies that mode's rules to what the trace says the
agent did. For example, a `none` agent that calls a model breaks rule N1 and its result
is withheld.

## Rules

**G0** applies in every mode. The trace must have exactly one `invoke_agent` span, the one that
covers the whole run. The envelope's grounding mode must match the mode recorded on that span. A payload must have a
`schema_class` and a `grounded_on` list, and every entry in that list must be well formed.

**E1** also applies in every mode. An evidence item may carry `content`, the projection its hash
covers. If it does, the content must hash to the item's `content_hash`. A payload names a
record only in `grounded_on`; what the reader is shown about that record (its name or status,
say) is the `content` of the evidence item with the same id and hash. E1 therefore checks what
the reader sees, without the linter knowing the payload class
([ADR-0015](adr/0015-evidence-carries-content.md)).

For `retrieval` agents:

- **G1**: every model call starts after at least one retrieval has finished.
- **G2**: every source in `grounded_on` matches a retrieval in the trace, on both its id and its
  hash. A successful payload that names no sources at all also breaks G2.
- **G3**: every hash in the envelope's evidence appears on a retrieval in the trace.
- **G4**: every hash in `grounded_on` also appears in the envelope's evidence.

For `input_only` and `none` agents:

- **R1**: the trace contains no retrievals.
- **R2**: every source in `grounded_on` and in the evidence is the input itself. Its id is
  `input:<invocation_id>` and its hash is the input hash the conductor computed.
- **R3**: a successful envelope cites the input at least once.

For `none` agents only:

- **N1**: the trace contains no model calls.

For `delegation` agents ([ADR-0012](adr/0012-conversation-and-orchestration.md)), R1 and G4 apply,
and:

- **D1**: every source in `grounded_on` is either the input (as R2 defines it) or a run listed in
  the envelope's `delegations`. A delegated run is cited as `invocation:<child_id>`, with the
  `dd-envelope-json-v1` hash of that run's stored envelope.
- **D2**: every evidence item meets the same condition.
- **D3**: a successful envelope cites the input.

The conductor writes `delegations` from the runs it performed for the agent, so these rules
check the agent's citations against the harness's own record, not against the agent's account
of what it delegated.

## When a rule is broken

If any rule is broken, the conductor changes a `succeeded` outcome to `failed` with problem type
`grounding-violation`. It removes the payload and evidence. The violations are listed in the
outcome statement and in `grounding.txt` in the run folder.

The linter does not need to know the payload class. It looks for `grounded_on` lists wherever
they appear in the payload. A payload the linter cannot check, for example one with no
`grounded_on`, counts as a violation. No output passes because the linter failed to recognise
it.

## What a pass shows, and what it does not

| Mode | A pass shows | A pass does not show |
|---|---|---|
| `retrieval` | The agent's citations, evidence and declared retrievals agree, and the agent declared a retrieval before any model call. | That the agent retrieved anything, or when. The source check covers part of this. |
| `input_only`, `none` | The result cites only the input, by the hash the conductor computed, and the agent declared no retrieval (or no model call). | That a model's rationale is faithful to the input. That is for evaluation ([ADR-0013](adr/0013-evaluation.md)). |
| `delegation` | The result cites only the input and runs the conductor itself performed for the agent. | That a relayed reply is faithful to the runs it relays. |

In every mode, a derivation badge such as `rationale_derivation` is the agent's declaration of
how a value was made. Neither check verifies it.

## The source check

After the linter, the conductor re-hashes what the evidence cites against a copy of the source
that the workbench holds ([ADR-0016](adr/0016-source-check.md)). `sources.yaml` lists each copy
by the evidence `snapshot_ref` it serves, and pins the file by its SHA-256 hash, so the copy
does not depend on the agent.

- **S1**: the copy holds a record with the evidence item's `source_id`. An invented record
  breaks S1.
- **S2**: that record, projected under the item's canonicalisation, hashes to the item's
  `content_hash`. A record the agent altered and re-hashed passes E1 and breaks S2.

An item whose `snapshot_ref` has no listed copy is *unresolved*: it is reported, and it is never
counted as verified. R3's `live` route is unresolved for now. A violation withholds the result
in the same way as a linter violation. The verdict is written to `sources.txt` in the run
folder, separately from `grounding.txt`.

The source check shows that a cited record exists in the source and says what the evidence says.
It does not show that the agent read the record during the run. Showing that would need
retrieval to go through the workbench, as delegation does (TODO, ADR-0016).

## Running the checks offline

The linter also runs offline over a finished run:

```sh
uv run workbench lint runs/<invocation_id>/spans.jsonl runs/<invocation_id>/envelope.json
```

and the source check over its envelope:

```sh
uv run workbench verify runs/<invocation_id>/envelope.json
```
