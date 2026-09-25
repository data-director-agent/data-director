# ADR-0016: The manifest declares derivations; the viewer works out presentation

**Status:** Accepted
**Date:** 2026-09-25

## Context

ADR-0010 gave `AgentSpec` an optional RJSF fragment for its payload (`uischema`), and ADR-0011
carried it into the manifest on each agent's A2A card. Every consumer of the manifest (the
workbench's own card, `workbench agents`, `GET /agents`) therefore carried presentation detail
that only the viewer reads. The five fragments mixed three kinds of content:

1. Rules each fragment repeated: hide `schema_class`, hide `grounded_on`, hide each derivation
   sibling. These follow from the schema.
2. Claims about the agent's method: which fields a model, a template or a keyword rule
   produces, and which sibling records, per value, how it actually came about. This is
   provenance. It belongs in a manifest, but as data rather than as RJSF options.
3. Field order. Each agent had to declare it only because gen-json-schema emits `properties` in
   alphabetical order.

Nothing checked a fragment against its payload class, so a mistyped field name was silently
ignored.

## Decision

1. `AgentSpec.uischema` is replaced by `AgentSpec.derivations`: a mapping from a dotted payload
   field path (list items transparent, e.g. `findings.message`) to `Derived(how, recorded_in)`.
   `how` is the contract's `Derivation`. `recorded_in`, when present, names a sibling field of
   type `Derivation`. A field that is not listed is copied from input or evidence (the viewer's
   unbadged `verified`). `AgentSpec` refuses a path or a recorder the payload class does not
   have, and refuses derivations on an agent with no payload. The manifest key `uischema`
   becomes `derivations`.
2. The viewer builds the payload's uiSchema per render from the payload class's JSON Schema and
   the agent's `derivations` (`payloadUi` in `viewer/js/payload.js`). `schema_class`, the
   payload's own `grounded_on`, and every field named as `recorded_in` are hidden. An item's
   `grounded_on` comes first and resolves through evidence (ADR-0015). A declared field is
   badged. Fields otherwise keep schema order.
3. `sdk/scripts/gen_schema.py` puts each class's `properties` back in LinkML induced-slot order
   (own slots, then mixins). The generated JSON Schema's meaning is unchanged: property order
   carries no semantics in JSON Schema. The source order of slots in `data_director.yaml` is now
   also the order a reader sees.
4. The envelope-level `viewer/uischema.json` is unchanged. It belongs to the viewer, not to any
   agent.

This reverses ADR-0010 decisions 3 (as far as the fragment goes) and 5.

Rejected:

- Moving the fragments into the viewer, keyed by payload class. That keeps presentation out of
  the manifest, but the derivation claims describe the agent's method, not the class.
- LinkML annotations as rendering hints. ADR-0010 rejected these for the same reason as before.
- Inferring the recorder from a naming convention. `Finding.derivation` and
  `Recommendation.classification_derivation` do not follow `<field>_derivation`, and renaming
  them is a contract change for no gain.

## Dependencies introduced

| Dependency | Tier | Fallback if this dependency is abandoned |
|---|---|---|
| `linkml_runtime.utils.schemaview.SchemaView` (already installed with `linkml`) | Evaluation/CI path (schema generation only) | Read slot order from the YAML source directly; the reordering is confined to `_pin_constants`. |

## Consequences

- An agent ships no presentation file. Adding an agent that reuses a payload class needs only its
  `derivations`. A new payload class is laid out by its LinkML slot order.
- A derivation that names a missing field fails when the spec is built, both in the agent and
  when the workbench rebuilds the spec from a card.
- Two visible changes: R3's resource column is headed `grounded_on`, not `resource`. The
  quality reviewer's per-finding `grounded_on` is shown, as the input reference.
- TODO: decide whether an item's `grounded_on` column should take a per-class title. If it
  should, that is a schema-level `title`, not an agent-level hint.
- Do not reintroduce an RJSF fragment, widget name or layout hint into `AgentSpec` or the
  manifest without revisiting this decision.
