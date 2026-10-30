# advisor.fairness

**Alpha** (`0.1.0a1`), and a **mock** (ADR-0033): it shows where the FAIR Assessor sits in the
process flow, and gives no real assessment.

The FAIR Assessor looks at a dataset that is already published. It serves two steps of the
Blueprint's process flow (§8.2):

| Step | What the mock does |
|---|---|
| `post.fairness` (R12) | Checks the metadata given for the dataset against a short list of FAIR-related presence checks. |
| `post.retrofit` (R9) | Suggests what to add to the record for each check not met. |

Both steps are optional and advisory. The agent changes no record: the researcher decides what to
submit to the repository.

## Input and output

`PublishedRecord` holds the dataset's metadata as the researcher gives it: `identifier` (a DOI or
URL), `title`, `licence`, `keywords`, `creators`, `creator_identifiers` (such as ORCID iDs),
`formats` (media types), `related_identifiers` and `access_protocol`. With neither an identifier
nor a title, the agent abstains.

`FairnessReport` holds one `FairCheck` per rule: the FAIR sub-principle (`F1`, `R1.1`, …), the
check's short identifier, whether it is `met`, and a `recommendation` when it is not. It also
lists the mock's `limitations`. There is no score.

## What it does

It applies the twelve rules in `src/dd_agent_advisor_fairness/checks.yaml` to its input: for
example, whether the identifier is a DOI (F1), keywords are given (F2), at least one format is
open (I1), related identifiers are given (I3), there is a licence (R1.1) and every creator has an
identifier (R1.2). Its grounding mode is `none`, and it cites only its input.

## What it does not do

- It is not a FAIRness evaluation, and the Blueprint does not ask the tool to replicate one (R4).
- It retrieves nothing: it does not resolve the identifier or read the repository's record, files
  or landing page, so it cannot tell whether what was given is true.
- It does not discover related datasets or outputs.
- It changes no record.

The real assessor, drawing on community tools such as F-UJI and discovering related datasets (for
example through DataCite's search), is TODO(#361).
