# ADR-0004: UUIDv7 for `invocation_id`; RFC 9457 Problem Details for `failed` and `suspended`

**Status:** Accepted
**Date:** 2026-09-04

## Context

Every invocation needs an identifier that is unique across instances, sortable by time so an
append-only JSONL store needs no secondary index, and free of any information about the dataset.
Failure and suspension need a structured shape that other software already understands.

## Decision

- `invocation_id` is a UUIDv7 (RFC 9562), generated with the standard library's `uuid.uuid7()`
  (Python 3.14). The contract pins the version nibble in a pattern.
- `failed` and `suspended` outcomes carry an RFC 9457 Problem Details object in the envelope's
  `problem` slot. Problem types are URIs under `https://w3id.org/data-director/problems/`
  (TODO: register the w3id namespace). Two extension members, `resume_condition` and
  `resume_after`, carry the resumption condition for `suspended`.
- `abstained` and `referred` are **not** problems. They are outcomes of equal standing with
  `succeeded`, expressed by the bespoke `ReasonCode` enumeration in the contract. The Blueprint
  defines no outcome vocabulary; this enumeration is the workbench's specification contribution.

## Dependencies introduced

| Dependency | Tier | Fallback if this dependency is abandoned |
|---|---|---|
| Python 3.14 `uuid.uuid7` | Runtime path (standard library) | `uuid-utils` or a twenty-line implementation of RFC 9562 §5.7. |

## Consequences

- Any store or index sorts invocations chronologically by identifier alone.
- Consumers that already handle Problem Details need nothing new for failures.
- Adding a reason code is a contract change and needs a schema edit and an ADR note.
