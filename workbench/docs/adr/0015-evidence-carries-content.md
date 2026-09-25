# ADR-0015: Evidence carries the content its hash covers; a payload states an identity once

**Status:** Accepted
**Date:** 2026-09-25

## Context

An R3 `Recommendation` named its record twice: in `resource`, a `ResourceRef` carrying
`fairsharing_id`, `doi`, `name`, `url`, `record_type` and `status`, for the reader; and in
`grounded_on`, a `GroundingRef` carrying `source_id` and `content_hash`, for the linter. The
linter reads only `grounded_on` (ADR-0008), so the identity the reader saw was never checked. An
agent that changed `resource` alone passed every rule, and the viewer showed the changed record
as verified.

Two narrower fixes do not close the gap. Building `resource` from the grounding reference states
the identifier once but leaves the name, status and DOI unchecked, because `GroundingRef`
carries none of them. Having the linter compare `resource` with `grounded_on` would teach the
linter one payload class, which the linter must not know (ADR-0008) and which adding an agent
must not require (ADR-0010).

Separately, ADR-0009 made the canonicalisation name identify a projection "a reader can
reproduce", but the envelope did not contain the projected content. Reproducing a hash meant
fetching the record again, from a source that may since have changed.

## Decision

1. `EvidenceItem` gains an optional `content`: the document the named canonicalisation turns
   into bytes, already projected. For `json-sorted-utf8-v1` it is the nine-field projection with
   its label lists sorted. `dd_sdk.evidence.project` produces it; `canonicalise(project(d))`
   equals `canonicalise(d)` for every registered name.
2. The linter applies **E1** in every grounding mode: every evidence item that carries `content`
   hashes to its `content_hash` under its `canonicalisation`. E1 is a generic check on evidence
   and knows no payload class.
3. A payload item states an external identity only in `grounded_on`. It carries no second copy
   of the identified record. A reader resolves what a reference identifies by joining it to the
   evidence item with the same `source_id` and `content_hash`, and reads that item's `content`.
4. `Recommendation.resource` and the `ResourceRef` class are removed from the schema.
5. No canonicalisation changes its bytes. Hashes in stored runs still verify. Stored envelopes
   written before this decision keep `resource` and have no evidence `content`; they are not
   migrated. TODO: decide whether the viewer must keep rendering such runs.

The chain from what the reader sees to what was retrieved is then checked end to end. The
content is what the hash covers (E1). The hash is in the evidence (G4) and on a retrieval span
(G2, G3).

## Dependencies introduced

None.

## Consequences

- An agent that names a retrieved record puts its description in evidence `content` and cites it
  from `grounded_on`. It does not repeat the description in its payload. A second copy would be
  unchecked again.
- `content` is optional. An agent that omits it still passes E1, but the viewer can show only
  the bare `source_id` for what it cites. TODO: decide whether `retrieval`-mode evidence must
  carry `content`.
- Envelopes grow by one projected record per cited source. For R3 that is at most a few
  kilobytes.
- The re-hash described in ADR-0009 becomes possible offline, from the envelope alone.
- A future contributor must not add a descriptive copy of a grounded record to a payload class,
  and must not make E1 depend on the payload class.
