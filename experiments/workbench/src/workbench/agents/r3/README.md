# R3 — standards advisor

Retrieve → rank → explain over FAIRsharing. See the [contract](../../../../schema/data_director.yaml)
for the shape every agent returns; this file covers what is specific to this one.

## Honest limits

- **Ranking is lexical and naive.** BM25 over name, abbreviation, description and subject
  labels, weighted with subject overlap and curation status. Over the 169-record snapshot the
  soil-chemistry sample gets sensible formats (CSV, Tabular Data Package, ISO 8601 for its date
  fields) and plausible but arguable terminologies (a chemistry vocabulary ranks above AGROVOC).
  Every recommendation carries its score and signals so a reviewer can disagree.
- **Vocabulary versus ontology** (R3's one explicit distinction) is decided lexically from the
  record's name and description, recorded as `classification_derivation: lexical`, with
  `terminology_unclassified` when neither pattern fires. FAIRsharing's curated subtype is not
  exposed on the public record route. **TODO:** read it from the authenticated API.
- **Live search needs a FAIRsharing account** (`FAIRSHARING_LOGIN` / `FAIRSHARING_PASSWORD`);
  record fetch does not. No live-search cassette is committed, so that path is unsubstantiated in
  `CONFORMANCE.md` until someone with an account records one.
- **The Anthropic explainer** (`DD_R3_EXPLAINER=anthropic`) is implemented but no cassette is
  committed; the trace shape it produces is exercised with a fake model in tests.
