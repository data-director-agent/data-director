# advisor.quality

**Demonstration alpha** (`0.1.1-alpha.2`): the Metadata Reviewer persona
([Agents](../../docs/specs/agents.md)). It scores how complete a metadata record is against six
fixed criteria. It is not a quality framework.

The Metadata Reviewer serves one step of the Blueprint's process flow (§8.2):

| Step | What it does |
|---|---|
| `deposit.validate` | Reviews an existing metadata record for completeness: a weighted score, one finding per criterion, and a short summary for the researcher. |

A person reviews the result. The agent does not edit the record or say that it is ready to publish.

## Input and output

`MetadataRecord` (a DCAT dataset) may give `identifier`, `title`, `description`, `licence`,
`creators` and `keywords`. A slot that is absent, blank or an empty list counts as missing. A record
that is missing every one of the six abstains with `INSUFFICIENT_INPUT`.

`QualityReview` holds:

- `score`: the weighted share of criteria met, from 0 to 1, rounded to three places;
- `findings`: one per criterion, each with `criterion` (`<slot>_present`), `severity`
  (`info`, `warning` or `error`), `message` and `derivation`;
- `summary`: a short summary of the findings in plain language;
- `summary_derivation`: `model` where a model wrote the summary, `template` where the rules' own
  text stands.

Every finding and the score are `lexical`. The payload is grounded on the input alone
(`grounded_on` cites it), and the outcome's statement gives the score and the number of unmet
criteria.

## How it decides

Rules decide, over `src/dd_agent_advisor_quality/checks.yaml`. Each check names a slot, a weight
and the message shown when the slot is empty:

| Slot | Weight | Severity when missing |
|---|---|---|
| `identifier` | 3 | error |
| `licence` | 3 | error |
| `title` | 2 | error |
| `description` | 2 | warning |
| `creators` | 2 | warning |
| `keywords` | 1 | info |

The weights were chosen by hand. A community assessment framework would replace them (TODO(#18)).
A met criterion is an `info` finding.

A summariser then writes the `summary` beside the findings (`dd_sdk.summary`), chosen by
`DD_QUALITY_SUMMARISER` (`factory.py`):

- `model` (the default) sends the model the record as given (without `schema_class`), the score,
  and each finding's criterion, severity and message, with the instructions in `system_prompt.md`.
  It asks for at most three sentences. It cannot add, remove or change a finding or the score. A
  reply that is missing, refused, or names a DOI, ORCID iD or web address that the record and
  findings do not give is replaced by the rules' own summary, marked `template`. A model that
  cannot be reached leaves the rules' summary with a note saying so.
- `template` gives the rules' own summary (the unmet criteria's messages, or "Every criterion is
  met."). It calls no model and needs no key.

The card declares the model only when one is configured.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `DD_QUALITY_SUMMARISER` | `model` | `model` or `template`. |
| `DD_MODEL_PROVIDER`, `DD_MODEL_ID`, `DD_MODEL_BASE_URL`, `DD_MODEL_API_KEY` | `anthropic`, `claude-sonnet-5-5` | The model for the `model` summariser, as for every model-backed agent ([AI models](../../docs/guide/operations/ai-models.md)). |

Whether a deployment may send a record to a hosted model is a profile choice, not a variable of this
agent.

## What it does not do

- It checks that a slot is present, not that it is right: a title of "x" or a made-up DOI meets
  its criterion. It resolves no identifier and checks no licence against SPDX.
- It reads six slots only. Widening the record to what a real repository export carries is
  TODO(#22).
- Its criteria and weights are not a community framework such as FAIRsFAIR's metrics (TODO(#18)).
  The FAIR Assessor persona assesses published records against FAIR-related checks.
- It retrieves nothing and has no evaluation set.
- The model writes the summary only, and the summary is not checked beyond the identifier test
  above.

## Run it

```sh
uv run dd-advisor-quality serve --port 8102
DD_QUALITY_SUMMARISER=template uv run dd-advisor-quality serve --port 8102   # no model
uv run workbench invoke --agent advisor.quality --input samples/orda-record.metadata.json
uv run pytest agents/advisor-quality
```

The sample is a record with no licence: it succeeds with one unmet `error` criterion.
