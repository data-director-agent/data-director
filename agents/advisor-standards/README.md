# advisor.standards

**Model-backed alpha** (`0.1.1-alpha.4`): the Standards Librarian persona
([Agents](../../docs/specs/agents.md)). It recommends vocabularies, ontologies and formats from
FAIRsharing and chooses none of them for the researcher.

The Standards Librarian serves three steps of the process flow (§8.2), one of them this
repository's addition:

| Step | What it does |
|---|---|
| `setup.vocabularies` | Recommends controlled vocabularies and ontologies for the dataset's subject. |
| `setup.formats` | Before collection: recommends data formats for the media types the researcher plans to save the data in, so that they are collected in an open format from the start. Our addition to Figure 1. The profile may have no fields yet. |
| `preparation.formats` | Recommends data formats for the declared media types, and a field-level standard such as ISO 8601 for date and time fields. |

## Input and output

`advisor.standards` accepts a `DatasetProfile` (`schema_class`, `title`, `description`,
`keywords`, `themes`, `media_types` and `fields`), declares grounding mode `retrieval` and returns
`Recommendations`: `items`, `searched`, `limitations`, `grounded_on` and `proposed_facts`. See the
[contract](../../sdk/src/dd_sdk/schema/data_director.yaml) for the shape every agent returns; this
file covers what is specific to this one. Its classes are in
`src/dd_agent_advisor_standards/schema/standards.yaml`.

It abstains, and does not return an empty list, in four cases:

| Reason code | When |
|---|---|
| `insufficient_input` | The profile has no title, keywords, themes, media types or temporal fields to search on. |
| `registry_unavailable` | The registry could not be searched (live search failed and the snapshot could not be used). |
| `no_candidates_retrieved` | The search returned nothing. |
| `no_qualifying_resource` | Records were retrieved but none scored at or above the confidence floor in `ranking.yaml`. |

Each `Recommendation` has a `kind` (`controlled_vocabulary`, `ontology`, `terminology_unclassified`,
`data_format` or `field_format`), a `target` (`dataset` or `field:<name>`), a `score` where the
rules chose it, a `rationale`, and `concern` and `notes` where there are any. Its
`rationale_derivation`, `classification_derivation` and `selection_derivation` say whether each
came from the rules (`lexical`, `template`) or from a model.

Retrieval is the committed snapshot by default. With `DD_STANDARDS_RETRIEVAL=live` it searches
FAIRsharing through a local cache (`dd_sdk.registry.fairsharing`): a search or record read again
within its time to live is answered from the cache and cited as `cache`, and an expired copy
answers, cited as `cache (stale)`, while FAIRsharing cannot be asked. With no cached copy either,
it uses the snapshot and marks the snapshot reference stale.

## Configuration

`build()` in `factory.py` reads these environment variables:

| Variable | Values | Default |
|---|---|---|
| `DD_STANDARDS_RETRIEVAL` | `snapshot`, or `live` (falls back to the snapshot, marked stale) | `snapshot` |
| `DD_STANDARDS_EXPLAINER` | `model` or `template` (`anthropic`, the older value, still works) | `model` |
| `DD_REGISTRY_CACHE_DIR` | the directory for the live route's local cache; `DD_REGISTRY_CACHE_TTL_RECORD`, `_SEARCH` and `_MISSING` set its times to live, in seconds ([example](../../config/examples/agents.env)) | in memory |
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
([Policy and identity](../../docs/specs/policy-and-identity.md)). In development, put the key in `config/local/credentials/` and name it in
`config/local/agents/advisor-standards.env`, which only this agent reads. In deployment, the key is loaded as a systemd credential ([deploy](../../deploy/README.md)).

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
sends data values. Its card declares the model (`models`).
The search tool reaches FAIRsharing from the agent, not yet through the harness's tool gateway
(TODO(#1143)).

## Grounding

Each `Recommendation` carries one `GroundingRef` for the FAIRsharing record it recommends, and
names the record nowhere else. The record's name, status and DOI are in the matching evidence
item's `content`, the `json-sorted-utf8-v1` projection its hash covers. The linter re-hashes
that content (E1, [Evidence and grounding](../../docs/specs/grounding.md)), so what a reader is shown is what was retrieved. The root
`Recommendations.grounded_on` lists every cited record once.

## Proposing a choice

A recommendation is advice. So that the researcher can record which they choose, `Recommendations`
also carries `proposed_facts` (`ProposesFacts`, `propose.py`): one `standard` project fact for each
recommendation, naming the record's name, its DOI as a URL (else its FAIRsharing page), its kind
and what it is for (`dataset` or `field:<name>`), with a sentence saying why for the person
deciding ([Projects](../../docs/specs/projects.md), invariant 28; #1391). This is the one
place the record's name is copied: a later agent is given the decided fact, not this run's
evidence. In a project the harness records each as a proposal; a person confirms the ones they
will use and rejects the others on the project page, and only those reach the Metadata Librarian
and the Documentation Editor.

## What it does not do

- **Ranking is lexical and naive.** BM25 over name, abbreviation, description and subject
  labels, weighted with subject overlap and curation status. Over the 169-record snapshot the
  soil-chemistry sample gets sensible formats (CSV, Tabular Data Package, ISO 8601 for its date
  fields) and plausible but arguable terminologies (a chemistry vocabulary ranks above AGROVOC).
  Every recommendation carries its score and signals so a reviewer can disagree. The
  [seeded-defect evaluation](src/dd_agent_advisor_standards/evals/README.md) measures this: ENVO is never recommended for the
  soil sample, AGROVOC only once the title is removed, and the Food Ontology is.
- **Vocabulary versus ontology** (the standards advisor's one explicit distinction) is decided lexically from the
  record's name and description, recorded as `classification_derivation: lexical`, with
  `terminology_unclassified` when neither pattern fires. FAIRsharing's curated subtype is not
  exposed on the public record route. **TODO(#4):** read it from the authenticated API.
- **It does not judge whether a format is open.** FAIRsharing's records do not say, and the
  ranking does not weigh it; the model is asked to prefer open formats and say why. Whether a file
  already saved is in an open format is the File Archivist's judgement (`advisor.files`,
  `preparation.files`), once there are files.
- **It does not choose.** A recommendation is advice; a person confirms or rejects each proposal. A model can add a record or note a doubt but never removes a rule's pick.
- **Live search needs a FAIRsharing account** (`FAIRSHARING_LOGIN` / `FAIRSHARING_PASSWORD`);
  record fetch does not. No live-search cassette is committed, so that path is unsubstantiated in
  `CONFORMANCE.md` until someone with an account records one.
- **The model advisor** is tested with a scripted model (`tests/test_standards_advise.py`) and a
  hand-written cassette (`tests/cassettes/test_key_not_stored/`), which shows that its key stays
  out of every stored record. No real reply has been recorded and the seeded-defect evaluation
  runs `template`, so whether its additions and concerns are right is unsubstantiated; it stays
  alpha until an evaluation of the model path (#415, #22).

## Run it

```bash
uv run dd-advisor-standards serve --port 8105
uv run workbench invoke --agent advisor.standards --input samples/soil-chemistry.profile.json
uv run pytest agents/advisor-standards
```

The model is on by default and needs a key (see Configuration). To run without one, set
`DD_STANDARDS_EXPLAINER=template`.
