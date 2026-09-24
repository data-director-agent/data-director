# ADR-0009: Evidence names a registered canonicalisation; the input hash is one of them

**Status:** Accepted
**Date:** 2026-09-04

## Context

`EvidenceItem.canonicalisation` existed at v0 with one possible value, `json-sorted-utf8-v1`,
whose meaning (project a FAIRsharing record to nine fields, sort label lists, dump sorted JSON)
lived in one function. A second agent kind retrieves records of a different shape; an
input-grounded agent (ADR-0008) needs a hash over the invocation's input document. The string
had to start doing the work its name implied: identify a projection a reader can reproduce.

## Decision

1. `dd_sdk.evidence` holds a registry `CANONICALISATIONS: dict[str, Canonicalisation]`; each
   entry is a name, a one-line description and a function from a document to canonical bytes.
   `canonicalise` and `content_hash` take the name; an unknown name raises (programmer error), and
   `contract.validate` rejects an envelope whose evidence cites one.
2. Three names are registered:
   - `json-sorted-utf8-v1` — the FAIRsharing projection R3 uses. Name and bytes unchanged from
     v0, so hashes in stored runs still verify.
   - `dd-input-json-v1` — the whole `input` document of an invocation as `to_document` emits it
     (sorted keys, no whitespace, UTF-8, lists in document order because order is meaningful
     there). What an `input_only` or `none` agent cites, with `source_id = input:<invocation_id>`.
   - `dd-json-document-v1` — a whole retrieved record, unprojected. For sources whose records are
     already small and self-describing (the fact checker's packaged sources).
3. A projection is never edited in place. Changing what a hash covers means registering a new
   name; the old one stays so old runs remain verifiable.

## Dependencies introduced

None. `hashlib` and `json` from the standard library, as before. RFC 8785 (JCS) canonicalisation
was considered and not adopted: every registered projection carries strings, string lists and
nulls only, so `json.dumps(sort_keys=True)` is sufficient and a JCS library would be a dependency
without a difference in output.

## Consequences

- An agent whose source records need their own projection registers one (a name and a
  function) in `evidence.py`; it does not invent a name in its own package.
- `PROJECTED_FIELDS` remains a module constant for `agents/r3/fairsharing/records.py` but now
  belongs to the `json-sorted-utf8-v1` entry.
- A future contributor must not change the bytes a registered name produces.
