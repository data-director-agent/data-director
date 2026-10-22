# Standards advisor

Retrieve → rank → explain over FAIRsharing. See the [contract](../../../../sdk/src/dd_sdk/schema/data_director.yaml)
for the shape every agent returns; this file covers what is specific to this one.

`standards.advisor` accepts a `DatasetProfile`, declares grounding mode `retrieval` and
returns `Recommendations`. Serve it with `uv run dd-standards serve --port 8105`.

## Configuration

`build()` in `factory.py` reads these environment variables:

| Variable | Values | Default |
|---|---|---|
| `DD_STANDARDS_RETRIEVAL` | `snapshot`, or `live` (falls back to the snapshot, marked stale) | `snapshot` |
| `DD_STANDARDS_EXPLAINER` | `template` or `anthropic` | `template` |
| `DD_MODEL_ID` | model id for the Anthropic explainer | `explain.DEFAULT_MODEL` |
| `DD_SNAPSHOT_PATH` | path to a snapshot JSONL file | `data/fairsharing/snapshot.jsonl` |
| `ANTHROPIC_API_KEY` | the Anthropic explainer's key, in development | none |
| `ANTHROPIC_API_KEY_FILE` | a file holding that key, in deployment; a relative path is under `$CREDENTIALS_DIRECTORY` | none |

An unknown value is a configuration error and stops the service at start-up. So is the Anthropic
explainer without exactly one of the two key variables. The key is passed to the Anthropic client
explicitly: the SDK's own credential chain, such as an `ant auth login`, is never used
(ADR-0026). In development, put the key in `workbench/agents/standards.env`, which only this
agent reads. In deployment, the key is loaded as a systemd credential (`deploy/README.md`).

With the Anthropic explainer the advisor sends Anthropic the dataset profile's title,
description, keywords, themes and field names and types, and the candidate records' names,
descriptions and subjects (`AnthropicExplainer._prompt`). It never sends data values. Its
manifest then declares the model (`models`), and the app's About tab names it. The app runs the
advisor in its own process only with the template explainer. For the model, run it as a
service.

## Grounding

Each `Recommendation` carries one `GroundingRef` for the FAIRsharing record it recommends, and
names the record nowhere else. The record's name, status and DOI are in the matching evidence
item's `content`, the `json-sorted-utf8-v1` projection its hash covers. The linter re-hashes
that content (E1, ADR-0015), so what a reader is shown is what was retrieved. The root
`Recommendations.grounded_on` lists every cited record once.

## Honest limits

- **Ranking is lexical and naive.** BM25 over name, abbreviation, description and subject
  labels, weighted with subject overlap and curation status. Over the 169-record snapshot the
  soil-chemistry sample gets sensible formats (CSV, Tabular Data Package, ISO 8601 for its date
  fields) and plausible but arguable terminologies (a chemistry vocabulary ranks above AGROVOC).
  Every recommendation carries its score and signals so a reviewer can disagree. The
  [seeded-defect evaluation](evals/README.md) measures this: ENVO is never recommended for the
  soil sample, AGROVOC only once the title is removed, and the Food Ontology is.
- **Vocabulary versus ontology** (the standards advisor's one explicit distinction) is decided lexically from the
  record's name and description, recorded as `classification_derivation: lexical`, with
  `terminology_unclassified` when neither pattern fires. FAIRsharing's curated subtype is not
  exposed on the public record route. **TODO:** read it from the authenticated API.
- **Live search needs a FAIRsharing account** (`FAIRSHARING_LOGIN` / `FAIRSHARING_PASSWORD`);
  record fetch does not. No live-search cassette is committed, so that path is unsubstantiated in
  `CONFORMANCE.md` until someone with an account records one.
- **The Anthropic explainer** (`DD_STANDARDS_EXPLAINER=anthropic`) is tested only against a
  hand-written cassette (`tests/cassettes/test_key_not_stored/`), which shows that its key stays
  out of every stored record. No real reply has been recorded, so the quality of its rationales
  is unsubstantiated.
