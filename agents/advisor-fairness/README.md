# advisor.fairness

**Model-backed alpha** (`0.3.0a1`): the FAIR Assessor persona
([Agents](../../docs/specs/agents.md)). Rules decide what the record meets, and a model, on by
default, writes the recommendations. It gives no FAIRness evaluation.

The FAIR Assessor looks at a dataset's metadata: a published dataset's, or the project's draft
metadata record while it is written. It serves two steps of the Blueprint's process flow (§8.2):

| Step | What it does |
|---|---|
| `post.fairness` (R12) | Checks the metadata given for the dataset against a short list of FAIR-related presence checks. |
| `post.retrofit` (R9) | Recommends what to add to the record for each check not met. |

Both steps are optional and advisory. The agent changes no record: the researcher decides what to
submit to the repository.

It also gives **feedback on the project's draft metadata at any time** (#430, #432), for no step
of its own, so that each improvement to the record is visible as it is made: a positive feedback
loop. The orchestrator asks it whenever a researcher wants to know how FAIR their description is
so far. The draft is the Metadata Librarian's (`advisor.metadata`); the assessor takes no step from
it, nor from the Metadata Reviewer (`advisor.quality`, `deposit.validate`), which checks that a
record is complete enough to deposit.

## Input and output

It accepts two classes:

- `PublishedRecord` holds a published dataset's metadata as the researcher gives it: `identifier`
  (a DOI or URL), `title`, `description`, `licence`, `keywords`, `creators`,
  `creator_identifiers` (such as ORCID iDs), `formats` (media types), `related_identifiers` and
  `access_protocol`. With neither an identifier nor a title, the agent abstains.
- `ProjectMetadataDraft` asks for feedback on the project's metadata record. It mixes in the
  core's `GivenProjectMetadataRecord`, so in a project the conductor gives the record's latest
  version, whatever its state (`project_metadata_draft`), and the version a person approved last
  (`project_metadata_approved`). Outside a project, a caller sends the record as `draft_text`.
  The record is in DataCite's JSON form, as the librarian drafts it, and a value it leaves null
  reads as not given (`datacite.py`). With no record, or text that is not a JSON object, the agent
  abstains and says what it needs.

`FairnessReport` holds one `FairCheck` per rule: the FAIR sub-principle (`F1`, `R1.1`, …), the
check's short identifier, whether it is `met`, and, for a check to act on, a `recommendation` with
its `recommendation_derivation` (`template` or `model`). The feedback is shaped to be constructive:

- **What is met comes first.** `checks` lists the checks met, then those to act on, most
  important first, then those left until deposit.
- **A tally for each of F, A, I and R** (`principle_tallies`): how many of its assessed checks the
  record meets. It is a count of presence checks, not a FAIR score (R4).
- **Next steps** (`next_steps`): the one or two checks to act on that matter most, by the rule
  table's `priority`.
- **What has changed.** For a draft, `newly_met` marks each check met now that the approved
  version (`compared_with`) did not meet. `assessed_version` names the version assessed.
- **What a draft cannot meet yet.** The DOI, the identifier in the record and how the data are
  accessed are supplied by the repository at deposit. A draft that lacks them has those checks
  marked `after_deposit`, with no recommendation, and they are not counted.

It also lists the assessor's `limitations`. The app shows the tallies in the project area,
recognising the report by its class ([FAIR feedback](../../docs/ui/fair-feedback.md)). Comparing
with the previous assessment, rather than the approved version, is TODO(#1417).

## What it does

It applies the twelve rules in `src/dd_agent_advisor_fairness/checks.yaml` to its input
(`rules.py`): for example, whether the identifier is a DOI (F1), keywords are given (F2), at least
one format is open (I1), related identifiers are given (I3), there is a licence (R1.1) and every
creator has an identifier (R1.2). Whether a check is met is always decided by these rules, and so
are the order, the tallies and the next steps (`feedback.py`).

The recommendation for each check to act on comes from a writer (`write.py`):

- `template`: the rule table's own text, the same for every record. It needs no key.
- `model` (the default): a model is sent the record as given and the unmet checks with their template text, and
  writes a recommendation tailored to the record, such as naming the creator who has no
  identifier or saying what the description leaves out. Each is checked before it is used: one
  for a check not sent, an empty or overlong one, or one naming a DOI, ORCID iD or web address the
  record does not give, is dropped, and that check keeps its template text, marked `template`. A
  refusal, a reply that does not match the schema or a model that cannot be reached leaves every
  recommendation as the template's. The statement says which happened.

Its grounding mode is `input_only`, and it cites only its input.

## Settings

| Variable | Values |
|---|---|
| `DD_FAIRNESS_WRITER` | `model` (default) or `template` (no model, no key). `anthropic` is the older name for `model` with `DD_MODEL_PROVIDER=anthropic`. |
| `DD_MODEL_PROVIDER`, `DD_MODEL_ID`, `DD_MODEL_BASE_URL` and the provider's key | Unless `template` (`dd_sdk.model_provider`). The default model for Anthropic is `claude-sonnet-5-5`. |

Unless it is set to `template`, the record's metadata as the researcher gave them, or as the draft holds them, are sent to the configured model
([AI models](../../docs/guide/operations/ai-models.md)). An unknown value or an unusable model
setting stops `dd-advisor-fairness serve` at start-up.

## What it does not do

- It is not a FAIRness evaluation, and the Blueprint does not ask the tool to replicate one (R4).
- It retrieves nothing: it does not resolve the identifier or read the repository's record, files
  or landing page, so it cannot tell whether what was given is true. Resolving the record and
  running a community FAIRness tool such as F-UJI is TODO(#704).
- It does not discover related datasets or outputs: TODO(#954).
- It changes no record, draft or published.

## Reuse

`datacite.py` reads a DataCite record in DataCite's JSON form and imports nothing from the Data
Director contract, so it can be lifted into a neutral library.

## Run it

```sh
uv run dd-advisor-fairness serve --port 8117
uv run workbench invoke --agent advisor.fairness --input workbench/samples/published-record.json
uv run workbench invoke --agent advisor.fairness --input workbench/samples/project-metadata-draft.json
uv run pytest agents/advisor-fairness
```

With no model key, set `DD_FAIRNESS_WRITER=template` first. The model path runs against `dd_sdk.testing.FakeModel`;
no test needs a key.
