# ADR-0021: RO-Crate is a record written after a run, not a message format

**Status:** Proposed
**Date:** 2026-10-16

## Context

[RO-Crate](https://www.researchobject.org/ro-crate/) is a way of packaging a research object
with a machine-readable description of it: a root dataset, its files and contextual entities,
written as JSON-LD in `ro-crate-metadata.json`. The Blueprint refers to it twice. R10 requires
that every agent action on data and metadata is recorded so that it can be verified and
audited, and names PROV-O as the candidate standard. R4 lists the RO-Crate validator among the
tools for checking metadata quality.

The workbench already writes a
[Process Run Crate](https://www.researchobject.org/workflow-run-crate/profiles/process_run_crate/)
for every invocation (`workbench/src/workbench/provenance.py`), but no decision records what
RO-Crate is for in this project. A contributor could reasonably ask whether agents should
exchange crates with each other, or whether a crate is only for packaging the final metadata.
The two uses have different audiences. A message is read by the next agent, immediately, and
must be validated against the contract. A crate is read later, by a person or an archive, to
find out what happened or what was produced.

## Decision

- **RO-Crate is not a message format.** Callers, the workbench and agents exchange
  `InvocationRequest` and `Envelope` over A2A (ADR-0001, ADR-0011), validated against the
  contract schema. No agent reads or writes a crate as part of a call. The request, envelope and
  trace are what the governance checks run on; a crate adds a root dataset and a JSON-LD graph
  that those checks do not need.
- **The Process Run Crate is written after the run, from the run folder.** Once the checks are
  done, the conductor writes `runs/<invocation_id>/crate/`, holding one `CreateAction`:

  | Crate entity | Role in the action | Source |
  |---|---|---|
  | The agent, a `SoftwareApplication` with `agent_id` and `agent_version` | `instrument` | the envelope |
  | The human it acted for (ADR-0018) | `agent` | `acting_for` |
  | `request.json` | `object` | the request as received |
  | `envelope.json`, `spans.jsonl` | `result` | the envelope and the trace |

  The crate is derived. The envelope remains authoritative, and nothing in the workbench reads a
  crate back. `DD_WRITE_CRATE=0` turns it off without changing any outcome.
- **The crate's library stays behind one module.** `provenance.py` is the only importer of
  `rocrate` (ADR-0006).

## Not yet decided

- TODO: a crate for the deliverable. The metadata a Data Director run produces for a dataset
  could itself be packaged as an RO-Crate and checked with the RO-Crate validator (R4). Which
  agent or component would write it, and how it would refer to the Process Run Crates of the
  runs that produced it, are not settled.
- TODO: whether an agent whose payload describes a research object may return
  `ro-crate-metadata.json` as that payload. It would travel inside an envelope, as any payload
  does, and would not change the message format above.
- TODO: the Process Run Crate names the workbench's own files as the action's object and
  result, not the records the agent read or the metadata it changed. The evidence items
  (ADR-0015) are the obvious source for those entities.
- TODO: a delegated run's crate is not linked to its parent's (ADR-0012). A Workflow Run Crate
  or Provenance Run Crate may suit orchestrated runs better.
- TODO: the outcome status is recorded as a `PropertyValue` that the action does not refer to.
- TODO: an accountable role is recorded as a `Person` (ADR-0018), and the crate does not name
  the schema digests (ADR-0019).
- TODO: no test checks the crate against the Process Run Crate profile with
  `rocrate-validator`, and PROV-O alignment is not exercised (`docs/requirements.yaml`, R10).
- TODO: the Data Director app (`app/`) writes no provenance record of this kind.

## Dependencies introduced

None. `rocrate` is already listed in ADR-0006 as a runtime dependency whose fallback is writing
`ro-crate-metadata.json` directly.

## Consequences

- A contributor adding an agent never builds or parses a crate. If you find yourself passing a
  crate between agents, or reading one back to make a governance decision, stop.
- The crate can change shape, or be replaced by another provenance format, without touching the
  contract, the agents or the checks.
- Meeting R10 in full depends on the gaps listed above, not on the existence of the crate.
