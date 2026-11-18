# Standards Librarian

Retrieve → rank → advise over FAIRsharing. See the [contract](../../../../sdk/src/dd_sdk/schema/data_director.yaml)
for the shape every agent returns; this file covers what is specific to this one.

`advisor.standards` accepts a `DatasetProfile`, declares grounding mode `retrieval` and
returns `Recommendations`. Serve it with `uv run dd-advisor-standards serve --port 8105`.

## Configuration

`build()` in `factory.py` reads these environment variables:

| Variable | Values | Default |
|---|---|---|
| `DD_STANDARDS_RETRIEVAL` | `snapshot`, or `live` (falls back to the snapshot, marked stale) | `snapshot` |
| `DD_STANDARDS_EXPLAINER` | `model` or `template` (`anthropic`, the older value, still works) | `model` |
| `DD_STANDARDS_MAX_LOOKUPS` | the most FAIRsharing searches the model may make in one run, 0 to 30 | `4` |
| `DD_MODEL_PROVIDER` | `anthropic`, `openai`, `gemini` or `openai-compatible` | `anthropic` |
| `DD_MODEL_ID` | the model the explainer calls; required with any provider but Anthropic | `explain.DEFAULT_MODEL` (`claude-sonnet-5-5`) with Anthropic |
| `DD_MODEL_BASE_URL` | the endpoint, with `openai-compatible` only | none |
| `DD_SNAPSHOT_PATH` | path to a snapshot JSONL file | `data/fairsharing/snapshot.jsonl` |
| `ANTHROPIC_API_KEY`, or the configured provider's (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `DD_MODEL_API_KEY`) | the explainer's key, in development | none |
| the same name with `_FILE` | a file holding that key, in deployment; a relative path is under `$CREDENTIALS_DIRECTORY` | none |

An unknown value is a configuration error and stops the service at start-up. So is the model,
which is on by default, without exactly one of its provider's two key variables, except for a
local `openai-compatible` endpoint, which may have none; the error says to set
`DD_STANDARDS_EXPLAINER=template` to run without a model. The model must support tool calls. The key is passed to the provider's client
explicitly: the provider SDK's own credential chain, such as an `ant auth login`, is never used
([Policy and identity](../../../../docs/specs/policy-and-identity.md)). In development, put the key in `config/local/credentials/` and name it in
`config/local/agents/advisor-standards.env`, which only this agent reads. In deployment, the key is loaded as a systemd credential (`deploy/README.md`).

## The model advisor

With the model (`advise.ModelAdvisor`), the rules still search and rank first. The model is then
given every record the first search retrieved, numbered `S1`, `S2`…, with the rules' picks marked,
and may search FAIRsharing for more with `search_fairsharing`, at most `DD_STANDARDS_MAX_LOOKUPS`
times; each record a search returns is retrieved by the agent, with its `retrieval` span, and
numbered before it may be cited. It ends with `submit_recommendations`, a checked structured reply:

- a **rationale** for each rule pick (`rationale_derivation: model`; a pick it leaves out keeps the
  template's);
- a **concern** beside a rule pick it doubts. The pick is never removed; a person decides;
- **additions**: records the rules did not pick. The agent keeps one only if its number names a
  record retrieved in this run, the record is not deprecated, its kind fits the record's FAIRsharing
  type, its target is the dataset or a field the profile has, it repeats no other recommendation,
  and no more than `max_per_kind` (`ranking.yaml`) of its kind were added. A kept addition has
  `selection_derivation: model`, `classification_derivation: model`, no score, and a note saying a
  model chose it.

Whatever the agent drops is named in the run's statement. A rationale that names a FAIRsharing
identifier other than its record's is replaced by the template's. If the model declines, cannot be
reached or never submits, the template is used and the statement says so.

The advisor sends the provider the dataset profile's title, description, keywords, themes, media
types and field names and types, and the records' names, types, statuses, subjects and
descriptions (`ModelAdvisor._prompt`), and FAIRsharing receives the model's search words. It never
sends data values. Its manifest declares the model (`models`), and the app's About tab names it.
The search tool reaches FAIRsharing from the agent, not yet through the harness's tool gateway
(TODO(#1143)). The app runs the advisor in its own process only with `template`. For the model, run
it as a service.

## Grounding

Each `Recommendation` carries one `GroundingRef` for the FAIRsharing record it recommends, and
names the record nowhere else. The record's name, status and DOI are in the matching evidence
item's `content`, the `json-sorted-utf8-v1` projection its hash covers. The linter re-hashes
that content (E1, [Evidence and grounding](../../../../docs/specs/grounding.md)), so what a reader is shown is what was retrieved. The root
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
  exposed on the public record route. **TODO(#4):** read it from the authenticated API.
- **Live search needs a FAIRsharing account** (`FAIRSHARING_LOGIN` / `FAIRSHARING_PASSWORD`);
  record fetch does not. No live-search cassette is committed, so that path is unsubstantiated in
  `CONFORMANCE.md` until someone with an account records one.
- **The model advisor** is tested with a scripted model (`tests/test_standards_advise.py`) and a
  hand-written cassette (`tests/cassettes/test_key_not_stored/`), which shows that its key stays
  out of every stored record. No real reply has been recorded and the seeded-defect evaluation
  runs `template`, so whether its additions and concerns are right is unsubstantiated; it stays
  alpha until an evaluation of the model path (#415, #22).
