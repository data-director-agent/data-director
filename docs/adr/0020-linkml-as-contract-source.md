# ADR-0020: LinkML is the source of the contract; JSON Schema is what runtime checks

**Status:** Accepted
**Date:** 2026-10-15

## Context

The contract has been written in [LinkML](https://linkml.io/) since v0, but no record said why.
ADR-0005 lists `linkml` in its dependency table, and ADRs 0007, 0016 and 0019 rely on LinkML
features without justifying the choice. This ADR records that choice and the rules that follow
from it.

LinkML is a data modelling language written in YAML. A schema declares classes, their slots, the
type and cardinality of each slot, and enumerations. Generators turn one schema into JSON Schema,
SHACL, OWL, Python classes, documentation and other forms. Each class and slot can also carry a
URI (`class_uri`, `slot_uri`), which binds it to a term in an existing vocabulary.

The contract had to meet these constraints:

- Agents are separate A2A services and may be written in any language (ADR-0011). The contract
  therefore has to be published in a form that does not depend on Python.
- The records describe research data for an RDA audience. Repositories already describe datasets
  in Dublin Core and DCAT, and the provenance record uses PROV. Inventing new terms would add one
  more mapping problem (ADR-0005).
- ADR-0005 makes the SHACL Validation Report the format for structured validation output. SHACL
  shapes for the contract are therefore needed alongside JSON Schema.
- Both researchers and engineers read the contract, so its definitions must be legible
  without the code.

## Decision

1. **The LinkML schema is the contract.** `sdk/src/dd_sdk/schema/data_director.yaml` defines the
   core contract. Under ADR-0019, each agent's own classes are defined in
   `agents/<name>/schema/<name>.yaml`, which imports the core. A disagreement between the source
   and any other artefact is resolved in favour of the source.
2. **Slots and classes reuse external vocabularies where a term exists.** A slot that means
   `dcterms:title` says so with `slot_uri`. A slot without an external term carries `see_also` to
   its specification rather than an invented URI (ADR-0005).
3. **The JSON Schema and SHACL shapes are generated and committed.** `dd-gen-schema`
   produces `schema/generated/`. Nobody edits that directory by hand, and
   `test_generated_schemas_are_current` fails if it differs from a fresh generation.
4. **Generator gaps are repaired in one place.** Where `gen-json-schema` cannot express part of
   the source, `dd_sdk/schema/gen.py` repairs its output and its docstring names each repair.
   There are currently three: pinning `requires_human_review` to `const: true`, dropping the
   `$ref` that would mask a polymorphic `anyOf` (ADR-0007), and restoring slot order (ADR-0016).
   Rules that JSON Schema cannot state, such as "a `succeeded` outcome carries a payload", are
   written as prose in the LinkML source and enforced in `dd_sdk/contract/validate.py`.
5. **Runtime validation uses the generated JSON Schema, not LinkML.** `validate.py` is the
   single call site. LinkML stays in the evaluation/CI tier (ADR-0006). It is needed to
   regenerate the schemas, not to load or check a document.
6. **The Pydantic models in `dd_sdk/contract/models.py` mirror the source and are written by
   hand.** Their field names and enum values match the LinkML names. A test validates an instance
   of every model against the generated JSON Schema, so the models cannot drift away from the
   source unnoticed. **TODO(#249):** record whether LinkML's own Pydantic generator (`gen-pydantic`)
   was tried, and why hand-written mirrors were preferred.

### Alternatives

- **Hand-written JSON Schema as the source.** It carries no vocabulary URIs, so the linked-data
  reading in point 2 would need a separate mapping, and SHACL would have to be written and kept
  in step by hand. It remains the fallback below.
- **Pydantic models as the source, with JSON Schema exported from them.** This would make Python
  the definition of a language-neutral contract and would lose slot URIs. ADR-0019 rejected it
  for agent-owned classes for the same reasons.
- **SHACL or OWL as the source.** Engineers would find either harder to read and write than
  YAML. Neither produces a JSON Schema that conventional tooling can validate against.

## Dependencies introduced

| Dependency | Tier | Fallback if this dependency is abandoned |
|---|---|---|
| `linkml` (generators, and `linkml_runtime.SchemaView` in `dd_sdk/schema/gen.py`) | Evaluation/CI path | The committed JSON Schema files become the hand-maintained source. The LinkML YAML is kept as documentation of slot URIs. Runtime code reads only `schema/generated/` through `contract/validate.py`, so nothing outside the SDK changes. |

## Consequences

- One change to the contract touches up to three places: the LinkML source, the regenerated
  files, and the Pydantic mirror. The tests catch a missed regeneration or a mirror that no
  longer validates. They do not catch a field present in the source but missing from the mirror.
- A contributor reads and writes the contract in YAML and needs to know a small part of the
  LinkML metamodel: `slots`, `range`, `any_of`, `mixin`/`mixins`, `designates_type`, `slot_uri`
  and `imports`.
- Upgrading LinkML can change the generated output. The currency test makes that visible in the
  diff, and any new gap in the generator is repaired in `dd_sdk/schema/gen.py` under point 4.
- Do not make runtime code import `linkml` or `linkml_runtime`, and do not edit
  `schema/generated/` by hand. Either change needs this ADR revisited.
