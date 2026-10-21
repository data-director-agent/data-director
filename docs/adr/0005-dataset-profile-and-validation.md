# ADR-0005: A minimal `DatasetProfile` with external slot URIs; SHACL Validation Report as the validation format

**Status:** Accepted
**Date:** 2026-09-04

## Context

R3 reads a small amount of information about a dataset: what it is about, what formats it uses,
and what its tabular fields are. A rich profile would tempt every agent to read the input
directly. Inventing a Data Director vocabulary for those slots would create one more mapping
problem for every repository that already speaks DCAT.

Structured validation output will eventually be needed (C15), but nothing at v0 consumes it, and
a bespoke `ValidationReport` type would be a second thing to maintain.

## Decision

- `DatasetProfile` has six slots: `title`, `description`, `keywords`, `themes`, `media_types`,
  `fields`. Each of the first five has a `slot_uri` in Dublin Core Terms or DCAT. `fields` is a
  list of `TableField`, mirroring a Frictionless Table Schema field descriptor (`name`, `type`,
  `format`, `description`). Frictionless publishes no RDF namespace, so those slots carry
  `see_also` links to the specification rather than invented URIs. **TODO:** revisit if
  Frictionless publishes term IRIs.
- Adding a slot to `DatasetProfile` requires naming the agent that reads it and its external URI.
- The format for structured validation output is the W3C SHACL Validation Report vocabulary
  (`sh:ValidationReport`, `sh:ValidationResult`), with a Frictionless validation report for
  tabular data. No bespoke type is defined. At v0 the only validation implemented is JSON Schema
  validation that raises `ContractViolation`.

## Dependencies introduced

| Dependency | Tier | Fallback if this dependency is abandoned |
|---|---|---|
| `linkml` (generation) | Evaluation/CI path | The generated JSON Schema and SHACL files are committed; a hand-maintained JSON Schema is the fallback, with the LinkML source kept as documentation. |
| `jsonschema` (runtime) | Runtime path | `fastjsonschema` or pydantic-only validation; `contract/validate.py` is the single call site. |
| `pyshacl` | Deferred to v0.2 | — |

## Consequences

- A DCAT-speaking repository can populate a profile without a mapping table.
- The profile cannot describe anything R3 does not read; that is the point.
- When runtime SHACL validation arrives, the report format is already decided.
