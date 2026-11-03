# advisor.metadata

**Alpha** (`0.1.0a1`) and a **mock** (ADR-0033), and the stub drafter of a project's metadata
record (#200). It gives no real advice, and its results say so.

The Metadata Librarian drafts a metadata record for a dataset, for the researcher to review before
submission (R2). It serves two steps of the Blueprint's process flow (§8.2):

| Step | What the mock does |
|---|---|
| `preparation.metadata-standard` | Follows the standard of the repository chosen. In the MVP that is always DataCite (ADR-0038 decision 3). |
| `preparation.metadata` | Drafts a record in it with every property the repository requires or recommends. |

## Input and output

It accepts the core `DraftRequest` with `document_kind: metadata_record`, and returns the core
`Document`, so its draft becomes a project document
([ADR-0035](../../docs/adr/0035-project-documents.md)) and the real librarian can replace it
without its caller changing.

The record is DataCite's JSON form, the form of the DataCite REST API's attributes, with
`media_type: application/json` and `conforms_to` set to the requirements' `conforms_to`. Every
property in the request's `requirements` is written:

- A property whose value is a list of objects gets one entry per field, with the field's
  qualifier, such as ORDA's `subjectScheme: ANZSRC Fields of Research`, and a `null` value for the
  researcher.
- `types.resourceTypeGeneral` is `Dataset`, since that is what the project deposits.
- A property `datacite.yaml` does not know is written as `null`.

From the inventory it adds `formats` (the files' media types) and `sizes` (the number of files
and their total bytes). `schemaVersion` names the schema.

It abstains with `insufficient_input` when no repository has been chosen (the request has no
`requirements`). It abstains with `capability_not_implemented` when the requirements follow a
schema other than DataCite, and with `outside_agent_scope` for any other kind. When the request
gives a `current_version`, the mock drafts afresh and names that version in `revises`.

Its grounding mode is `none`: it cites only its input. The core `Document` has no `limitations`
slot, so the outcome's statement says what the mock does not do (ADR-0033 decision 5).

## What it does not do

- It fills no property that only the researcher can, such as the title, creators, subjects or
  licence.
- It uses no controlled vocabularies, and does not split names or add identifiers such as ORCID.
- It does not map a record between schemas (R6), or write Figshare's own item format (#383).
- It does not check that a value is correct. Validating the record is the harness's work (#19).
- It does not read an earlier version, or the reason a person gave for a decision on it.

The real librarian, which drafts with a model against controlled vocabularies and maps between
schemas, is TODO(#357) (see also #220 and #321).
