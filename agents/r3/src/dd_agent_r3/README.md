# R3 — standards advisor

Retrieve → rank → explain over FAIRsharing. See the [contract](../../../../sdk/src/dd_sdk/schema/data_director.yaml)
for the shape every agent returns; this file covers what is specific to this one.

`r3.standards-advisor` accepts a `DatasetProfile`, declares grounding mode `retrieval` and
returns `Recommendations`. Serve it with `uv run dd-r3 serve --port 8105`.

## Configuration

`build()` in `factory.py` reads these environment variables:

| Variable | Values | Default |
|---|---|---|
| `DD_R3_RETRIEVAL` | `snapshot`, or `live` (falls back to the snapshot, marked stale) | `snapshot` |
| `DD_R3_EXPLAINER` | `template` or `anthropic` | `template` |
| `DD_MODEL_ID` | model id for the Anthropic explainer | `explain.DEFAULT_MODEL` |
| `DD_SNAPSHOT_PATH` | path to a snapshot JSONL file | `data/fairsharing/snapshot.jsonl` |

An unknown value is a configuration error and stops the service at start-up.

## Grounding

Each `Recommendation` carries one `GroundingRef` for the FAIRsharing record it recommends. The
agent builds `resource` and `grounded_on` from the same retrieved record. The root
`Recommendations.grounded_on` lists every cited record once. The linter reads only
`grounded_on`, so it is R3's own tests that check `resource.fairsharing_id` agrees with it.

## Honest limits

- **Ranking is lexical and naive.** BM25 over name, abbreviation, description and subject
  labels, weighted with subject overlap and curation status. Over the 169-record snapshot the
  soil-chemistry sample gets sensible formats (CSV, Tabular Data Package, ISO 8601 for its date
  fields) and plausible but arguable terminologies (a chemistry vocabulary ranks above AGROVOC).
  Every recommendation carries its score and signals so a reviewer can disagree. The
  [seeded-defect evaluation](evals/README.md) measures this: ENVO is never recommended for the
  soil sample, AGROVOC only once the title is removed, and the Food Ontology is.
- **Vocabulary versus ontology** (R3's one explicit distinction) is decided lexically from the
  record's name and description, recorded as `classification_derivation: lexical`, with
  `terminology_unclassified` when neither pattern fires. FAIRsharing's curated subtype is not
  exposed on the public record route. **TODO:** read it from the authenticated API.
- **Live search needs a FAIRsharing account** (`FAIRSHARING_LOGIN` / `FAIRSHARING_PASSWORD`);
  record fetch does not. No live-search cassette is committed, so that path is unsubstantiated in
  `CONFORMANCE.md` until someone with an account records one.
- **The Anthropic explainer** (`DD_R3_EXPLAINER=anthropic`) is implemented but no cassette is
  committed; the trace shape it produces is exercised with a fake model in tests.
