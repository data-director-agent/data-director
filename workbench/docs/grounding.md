# Grounding

An agent's output is *grounded* when every source it relies on can be traced to something the
agent actually read during the run. The workbench checks this after every run with the grounding
linter in [`src/workbench/grounding.py`](../src/workbench/grounding.py)
([ADR-0008](adr/0008-grounding-modes.md)).

The linter compares two things. The first is the payload's `grounded_on` list, where the agent
names its sources ([`contract.md`](contract.md)). The second is the trace of the run, which
records each source the agent retrieved and each model call it made. Each source is identified by
an id and a content hash. The hash is computed with a registered canonicalisation, so the same
record always gives the same hash ([ADR-0009](adr/0009-evidence-canonicalisations.md)).

## Grounding modes

Each agent declares one grounding mode. The mode says what the agent's output may rest on.

| Mode | The agent… | Rules applied |
|---|---|---|
| `retrieval` | retrieves external records, then may call a model to reason over them. | G0, G1–G4 |
| `input_only` | works only on its input, and may call a model. | G0, R1–R3 |
| `none` | works only on its input, with no model call. Its output is deterministic. | G0, R1–R3, N1 |

## Rules

**G0** applies in every mode. The trace must have exactly one root span for the agent. The
envelope's grounding mode must match the mode recorded in the trace. A payload must have a
`schema_class` and a `grounded_on` list, and every entry in that list must be well formed.

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

## When a rule is broken

If any rule is broken, the conductor changes a `succeeded` outcome to `failed` with problem type
`grounding-violation`. It removes the payload and evidence. The violations are listed in the
outcome statement and in `grounding.txt` in the run folder.

The linter does not need to know the payload class. It looks for `grounded_on` lists wherever
they appear in the payload. A payload the linter cannot check, for example one with no
`grounded_on`, counts as a violation. No output passes because the linter failed to recognise
it.

The linter also runs offline over a finished run:

```sh
uv run workbench lint runs/<invocation_id>/spans.jsonl runs/<invocation_id>/envelope.json
```
