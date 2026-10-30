# advisor.metadata

**Alpha** (`0.1.0a1`) and a **mock** (ADR-0033): it gives no real advice, and its results say so.

The Metadata Librarian drafts a metadata record for a dataset, for the researcher to review before
submission (R2). It serves two steps of the Blueprint's process flow (§8.2):

| Step | What the mock does |
|---|---|
| `preparation.metadata-standard` | Uses the standard the researcher names, if it knows it, and DataCite otherwise, saying which and why. |
| `preparation.metadata` | Drafts a record in that standard, filling each property it can from the researcher's input. |

## Input and output

`MetadataDraftRequest` gives the dataset's `title`, `description`, `creators`, `keywords` and
`publication_year`, and optionally the `target_standard` (for example `DataCite`, `Dublin Core` or
`DDI`). Without a title the mock abstains with `insufficient_input`.

`MetadataDraft` holds the `standard` used, `standard_reason`, one entry in `fields` per property
of the standard, and `limitations`. Each field is `filled`, with the value copied from the input,
or `needs_researcher`, with no value. A list such as `creators` is joined with `; `.

## How it decides

`src/dd_agent_advisor_metadata/standards.yaml` is the whole rule table. For DataCite (its six
mandatory properties and two recommended ones), a subset of the Dublin Core elements and a minimal
DDI-Codebook study description, it lists each property and the input field that fills it, if
any. The mock never invents a value: an identifier, publisher or resource type is always left to
the researcher. It reads no source and calls no model, so its grounding mode is `none` and it
cites only its input.

## What it does not do

- It does not choose a standard for the discipline or the repository.
- It uses no controlled vocabularies, and does not split names or add identifiers such as ORCID.
- It does not map a record between schemas (R6).
- It does not check that a value is correct, only that the input gave one.

The real librarian, which drafts with a model against controlled vocabularies and maps between
schemas, is TODO(#357) (see also #200, #220 and #321).
