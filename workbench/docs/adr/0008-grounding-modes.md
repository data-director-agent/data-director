# ADR-0008: Agents declare a grounding mode; the linter applies that mode's rules

**Status:** Accepted (amends ADR-0002)
**Date:** 2026-09-04

## Context

The v0 grounding linter encoded one agent shape. G2 read
`payload.items[i].resource.fairsharing_id`; G3 read `items[i].evidence_hashes`. Given any other
payload, `payload.get("items", [])` returned an empty list and both rules passed with nothing
checked: the invariant "nothing ungrounded leaves the system" quietly stopped applying to the
second agent kind. G1 required a `retrieval` span before any `chat` span, which made an agent that
scores the input it was given — a legitimate shape, with or without a model — impossible.

The workbench needed grounding rules that (a) hold for every agent kind without the linter
knowing any payload class, (b) fail loudly on a shape they cannot check, and (c) admit agents
that ground on their input rather than on external retrieval, without weakening the rules for
agents that do retrieve.

## Decision

1. Every agent declares one of three **grounding modes** in its `AgentSpec`; the conductor writes
   it to `Envelope.grounding_mode` and to the root `invoke_agent` span as `dd.grounding_mode`. The
   agent cannot set either.
   - `retrieval` — the agent retrieves external records before any model call; every identity it
     asserts was retrieved.
   - `input_only` — the agent works over its input; it may call a model; it retrieves nothing.
   - `none` — deterministic over its input; no retrieval and no model call.
2. The conductor computes the **input hash** (`dd-input-json-v1`, ADR-0009) of the request's
   `input` document, writes it to the root span as `dd.input_hash`, and hands it to the agent in
   `RunContext` together with `input_ref = "input:<invocation_id>"`. An input-grounded agent cites
   exactly that pair.
3. The linter reads the mode from the envelope and applies a **rule table** per mode:
   - **G0**, all modes: exactly one root; envelope mode valid and equal to the root span's; a
     payload, if present, has `schema_class` and a root `grounded_on`; every `GroundingRef` is
     well formed. *An unrecognised or ungroundable payload is a violation, not a pass.*
   - `retrieval`: G1 (chat after first retrieval ended); G2 (every `GroundingRef` at any depth
     matches a retrieval span on both `dd.source_id` and `dd.content_hash`; a succeeded payload
     resting on nothing is a violation); G3 (every evidence hash was retrieved); G4 (every
     `grounded_on` hash appears in evidence).
   - `input_only`: R1 (no retrieval span); R2 (every `GroundingRef` and evidence item is the
     input pair); R3 (a succeeded envelope cites the input).
   - `none`: R1–R3 and N1 (no chat span).
   The linter finds grounding references by walking the payload document for `grounded_on`
   keys; it imports no payload class.
4. `contract.validate` enforces the document-only half of the same rules (mode/evidence
   consistency, `grounded_on` present), so an envelope produced outside Python is checked too.
5. `dd.grounding_mode` and `dd.input_hash` join the owned attribute set of ADR-0002.

Rejected: keeping one strict rule set (forces every agent to fake a retrieval span for its own
input); making grounding optional per institutional profile (moves a safety invariant into
configuration); per-payload Python adapters (see ADR-0007).

## Dependencies introduced

None. The rules are bespoke code over the ADR-0002 span records, as before.

## Consequences

- A fourth mode is a table entry in `grounding.RULES` plus an enum value, not a redesign.
- A test that wants the linter to pass must produce a payload with `grounded_on`; there is no
  shape that slips through. `tests/test_grounding.py` pins each rule with hand-built span trees.
- R3 does not yet emit `grounded_on` and is not registered as usable until ported (TODO).
- A future contributor must not weaken G0 to tolerate a payload without `grounded_on`, nor allow
  an agent to write `grounding_mode` or `dd.input_hash` itself.
