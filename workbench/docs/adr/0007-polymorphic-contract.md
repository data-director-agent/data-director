# ADR-0007: Polymorphic input and payload, discriminated by `schema_class`, grounded by mixin

**Status:** Accepted (amends ADR-0005)
**Date:** 2026-09-04

## Context

At v0 the contract had one input class (`DatasetProfile`) and one payload class
(`Recommendations`, with a required `fairsharing_id`). Both were R3's shape. The workbench is
meant to be a test-bed for many kinds of Data Director sub-agent — a quality reviewer reads an
existing metadata record and returns a score; a fact checker reads a claim and returns a
verdict — and none of those fit either class. `Envelope.payload` was already `range: Any` with
one `any_of` arm; `InvocationRequest.input` was not polymorphic at all.

Two constraints shaped the answer. First, every input class of interest has optional slots
only, so without a discriminator `{}` would parse as a `DatasetProfile` and a JSON Schema
`anyOf` could match more than one arm. Second, the grounding linter (ADR-0008) must be able to
find what a payload rests on without knowing the payload class; otherwise every new agent kind
would mean editing the linter, and an unedited linter would silently pass an unfamiliar shape.

## Decision

1. `InvocationRequest.input` and `Envelope.payload` are `range: Any` with an `any_of` list of
   concrete classes. Adding an input or payload class is an additive schema change: a new class
   and a new `any_of` arm.
2. Every input and payload class carries `schema_class`, a LinkML type designator
   (`designates_type: true`) whose value is the class name. It is required. The generated JSON
   Schema emits it as a one-value `enum`; the Pydantic mirrors use it as the discriminator of
   `Input` and `Payload` unions.
3. Every payload class, and every item class within a payload that asserts an identity (an
   R3 `Recommendation`, a quality `Finding`), mixes in `Grounded`, which contributes one
   required slot: `grounded_on: list[GroundingRef]`. A `GroundingRef` is a `source_id` and a
   `content_hash`. It is the only way a payload may name an external thing as decided identity;
   descriptive strings (`ResourceRef.name`, a URL) are not verified and reviewers read identity
   from `grounded_on`.
4. An agent declares the input classes it accepts (`AgentSpec.accepts`) and the payload class it
   returns (`AgentSpec.payload_type`). The conductor refuses an input of another class before the
   agent runs, as a `failed` outcome with Problem Details `input-not-accepted` (HTTP 422). The
   request was valid and named a real agent, so the refusal is an envelope a reviewer and an A2A
   client can see, as a policy refusal is. An agent that returns a payload of a class other than
   the one it declared has contradicted its own specification; the conductor converts that to
   `failed` with `agent-error`, as it does an exception.
5. Generation repair: for a required polymorphic slot gen-json-schema emits
   `{"$ref": "#/$defs/Any", "anyOf": [...]}`. Under Draft 7 a `$ref` overrides its siblings, so the
   `anyOf` would never be checked. `scripts/gen_schema.py` drops the `$ref` in that case, in the
   same place it pins `requires_human_review`.

Rejected: a bare `grounded_on` convention without the mixin (nothing enforces it); Python
adapters registered per payload class (an unregistered class reintroduces the silent pass, and
the linter changes per agent); a `context` map on a fixed `DatasetProfile` instead of
polymorphic input (weaker typing, and it would make every agent pretend to read a dataset
profile).

## Dependencies introduced

| Dependency | Tier | Fallback if this dependency is abandoned |
|---|---|---|
| LinkML `designates_type` and `mixin` | Evaluation/CI path (schema generation only) | Both are plain LinkML metamodel features; the generated JSON Schema and the Pydantic mirrors carry the result and do not depend on LinkML at runtime. |

## Consequences

- A new agent kind that needs a new input or payload class edits `schema/data_director.yaml`
  (class + `any_of` arm), regenerates, and adds the Pydantic mirror to `contract/models.py`
  (`INPUT_TYPES` / `PAYLOAD_TYPES`). Nothing else changes.
- `Recommendations` and `Recommendation` now carry `grounded_on`; R3's `evidence_hashes` slot is
  redundant and should be removed when R3 is ported. It was removed with the port, in contract
  0.4.0.
- The `DatasetProfile` description no longer says "the only view of the input an agent gets".
- The contract version moves to 0.2.0. Stored v0 envelopes lack `grounding_mode` and
  `schema_class` and do not validate against the current schema; the workbench keeps no such
  runs in the repository.
- A future contributor must not add a payload class without `Grounded`, nor an input class
  without `schema_class`; `contract.validate` and the linter both reject the result.
