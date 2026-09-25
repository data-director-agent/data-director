# ADR-0016: The linter checks consistency; a source check verifies citations against the source

**Status:** Accepted (amends ADR-0008)
**Date:** 2026-09-25

## Context

Under `retrieval`, G1–G3 compare a payload's `grounded_on` and evidence with `retrieval` spans.
Since ADR-0011 an agent writes those spans in its own process and sends them back over A2A. R3
and fact.checker open each span after the search has finished and close it at once
(`with retrieval_span(...): pass`). The span does not time a retrieval. It is a statement the
agent makes about itself, stored in a telemetry format. G1's "retrieval before chat" compares
timestamps the agent recorded. E1 (ADR-0015) shows that evidence `content` hashes to its
`content_hash`, but nothing compared that hash with the source it names. A `retrieval` pass
therefore meant that the agent's claims agreed with one another, not that it retrieved anything.
`grounding.md` said the opposite: that the workbench writes the trace, so that an agent cannot
make a step up. That has not been true since ADR-0011.

The facts a run records have two different origins:

| Fact | Origin | Rules that rely on it |
|---|---|---|
| `grounding_mode`, `dd.input_hash`, `invoke_agent` span | the conductor | G0, R2, R3, D1, D3 |
| `delegations` and each child's envelope hash | the conductor | D1, D2 |
| `retrieval` and `chat` spans, and their timing | the agent | G1, G2, G3, R1, N1 |
| `grounded_on`, evidence, `*_derivation` values | the agent | every rule |

The delegation rules (ADR-0012) are sound because they check the agent's citations against the
conductor's record of the child runs it performed. The input rules are sound for what they
claim: an `input_only` agent cites only the hash the conductor computed. They do not show that
a model's rationale is faithful to that input. R1 and N1 show only that the agent reported no
retrieval or model call. A derivation badge is the agent's declaration of how a value was made.

Two fixes were considered. Routing retrieval through the workbench, as `ctx.delegate` routes
delegation, would let the conductor see each retrieval happen and time it. It needs a registry of
source services, a callback like the delegation grant, and changes to every retrieving agent.
Re-resolving what the evidence cites against a copy of the source that the workbench holds needs
none of that. ADR-0009 made the projection reproducible, and ADR-0015 put it in the envelope.

## Decision

1. The grounding linter is a **consistency check**: it tests the agent's account of its run
   against itself and against what the conductor recorded. Documentation, the conformance
   register and the linter's docstring say so. Its rules, names and output format are unchanged.
2. A **source check** (`workbench/src/workbench/sources.py`) runs in the conductor after the
   linter, and offline through `workbench verify`. For each evidence item it looks up the copy
   of the source listed in `workbench/sources.yaml` for the item's `snapshot_ref`. It then
   applies two rules:
   - **S1**: that copy holds a record with the item's `source_id`.
   - **S2**: the record, projected under the item's `canonicalisation`, hashes to its
     `content_hash`.

   With E1, a pass means that what the reader is shown about a cited record is the source's own
   projection of it.
3. An item whose `snapshot_ref` has no listed copy is **unresolved**. It is reported, it is not
   a violation, and it is never counted as verified. In the `input_only`, `none` and
   `delegation` modes, an item citing `input:` or `invocation:` is skipped, because R2, D1 and
   D2 have already checked it against hashes the conductor computed. In `retrieval` mode no
   rule does that, so such an item is unresolved.
4. An S1 or S2 violation withholds a succeeded result, as a linter violation does. It becomes
   `failed`, with problem type `grounding-violation` and no payload or evidence. The two verdicts
   are stored separately, in `grounding.txt` and `sources.txt`, and never combined.
5. A copy is independent of the agent because its bytes are pinned by `sha256` in
   `sources.yaml`, not because of where the file lives. A file that does not match its pin is a
   configuration error, and the workbench does not start. A rebuilt snapshot is a new entry.
6. `sources.yaml` lists a file path, an id field and a pin, and nothing more. The workbench
   imports no agent to resolve a source.

Not decided here:

- TODO: route retrieval through the workbench, so that the conductor, not the agent, records
  when each record was read. Until then, G1 is a consistency check of the agent's own timeline.
- TODO: a resolver for R3's `live` route. The FAIRsharing API needs credentials and network
  access. Live runs are unresolved.
- TODO: whether an unresolved item in `retrieval` mode should be a violation for some profiles.
- TODO: show the source-check verdict in the viewer.

Whether a model's rationale is faithful to its input or to what it retrieved is a question for
evaluation (ADR-0013), not for either check.

## Dependencies introduced

None. `hashlib`, `json` and PyYAML, as before.

## Consequences

- `retrieval`-mode evidence from a source listed in `sources.yaml` is checked end to end. The
  content is what the hash covers (E1), and the hash is what the source holds (S2).
- Adding a retrieving agent with a packaged or snapshot source adds one entry to
  `sources.yaml`. Nothing central changes.
- A test conductor holds no copies by default (`Sources.none()`), so scripted agents citing
  synthetic sources are unresolved, not failed.
- A future contributor must not count an unresolved item as verified. They must not describe a
  `grounding: passed` as proof of retrieval. They must not let a source check read the agent's
  own copy of a source without a pin.
