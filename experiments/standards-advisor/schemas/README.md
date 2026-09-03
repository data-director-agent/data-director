# Generated schemas

**Do not edit these files by hand.** They are generated from the Pydantic models in
`src/standards_advisor/models/` and byte-compared against a regeneration by
`tests/test_schemas_current.py`, so a manual edit fails the test suite rather than taking
effect.

Regenerate after changing a model:

```bash
uv run python scripts/export_schemas.py
# or
uv run standards-advisor export-schemas
```

§6 of `docs/architecture.md` says the JSON Schemas are written before any code and are
definitive. The models are the single source of truth here because keeping two hand-written
definitions in step is a discipline that lasts about a month; generating one from the other
makes the committed files authoritative-by-construction for anything outside Python.

| File | Model | §6 |
|---|---|---|
| `dataset-profile.schema.json` | `models.profile.DatasetProfile` | §6.1 |
| `recommendations.schema.json` | `models.recommendations.RecommendationsDocument` | §6.2 |
| `provenance.schema.json` | `models.provenance.ProvDocument` | §6.3 |

Internal stage payloads (`models/candidates.py`) are deliberately **not** exported. They cross
node boundaries but they are not part of the §6 contract, and publishing them would imply a
stability promise we have no reason to make.

## A note on `provenance.schema.json`

This one is advisory. It describes the *shape* of the JSON-LD document we emit — that there is
an `@context`, that `@graph` holds nodes with `@id` and `@type`. JSON Schema cannot express
PROV-O conformance, so validating against this file tells you the document is structurally what
we intended, not that it is valid PROV-O. Checking the latter needs a PROV validator or a SHACL
shape, and neither is in scope at v0.1.

## `requires_human_review`

`recommendations.schema.json` carries `"const": true` for `requires_human_review`, because the
model declares it as `Literal[True]`. That is deliberate and load-bearing: C15 makes human
review mandatory, and expressing it in the published schema means a consumer written in another
language cannot produce a document claiming otherwise.
