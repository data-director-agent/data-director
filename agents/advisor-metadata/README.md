# advisor.metadata

**Alpha** (`0.2.0a1`), a model-backed alpha (docs/specs/agents.md, invariant 14), and the drafter
of a project's metadata record (#200). Its model is off by default; on, it only suggests values
beside the record's questions (#698).

The Metadata Librarian drafts a metadata record for a dataset, for the researcher to review before
submission (R2). It serves two steps of the Blueprint's process flow (§8.2):

| Step | What it does |
|---|---|
| `preparation.metadata-standard` | Follows the standard of the repository chosen. In the MVP that is always DataCite (docs/specs/deposit.md). |
| `preparation.metadata` | Drafts a record in it with every property the repository requires or recommends, and asks about every value it cannot fill. |

It follows the rules of [Drafting documents](../../docs/specs/drafting.md): it infers only from
the project's facts, asks the researcher for the rest, places their answers as given, and offers a
model's suggestion only beside a question.

## Input and output

It accepts the core `DraftRequest` with `document_kind: metadata_record`, and returns the core
`Document`, so its draft becomes a project document
([Projects](../../docs/specs/projects.md)).

The record is DataCite's JSON form, the form of the DataCite REST API's attributes, with
`media_type: application/json` and `conforms_to` set to the requirements' `conforms_to`. Every
property in the request's `requirements` is written:

- A property whose value is a list of objects gets one entry per field, with the field's
  qualifier, such as ORDA's `subjectScheme: ANZSRC Fields of Research`, and a `null` value for the
  researcher.
- `types.resourceTypeGeneral` is `Dataset`, since that is what the project deposits.
- Where the request gives `researchers`, the facts the project's researchers kept from their
  public ORCID records ([Projects](../../docs/specs/projects.md), invariant 27), and the
  repository asks for the property: `creators` lists each researcher with their name (or `null`
  if they did not keep it), their ORCID iD as a name identifier, and the employers they kept that
  they still work for, with ROR identifiers where ORCID gives them; `subjects` adds their keywords
  after the entries the repository's vocabularies ask for; and `fundingReferences` lists their
  grants, with the funder's identifier and the award number.
- A property `datacite.yaml` does not know is written as `null`.

From the inventory it adds `formats` (the files' media types) and `sizes` (the number of files
and their total bytes). `schemaVersion` names the schema.

It abstains with `insufficient_input` when no repository has been chosen (the request has no
`requirements`). It abstains with `capability_not_implemented` when the requirements follow a
schema other than DataCite, and with `outside_agent_scope` for any other kind. When the request
gives a `current_version`, it drafts afresh and names that version in `revises`.

## Questions and answers

Every value left `null` is a gap with one question in `document_questions`
(`questions.py`). The question names the value by its path in the record (`gap_property`, such as
`titles[0].title` or `subjects[1].subject`), and its identifier is derived from that path, so it
is the same in every draft. Its text is the rule table's `ask` for the property, with the
qualifiers the repository asks for.

The conductor puts the answers a person recorded into the request's `draft_answers`. Each is
placed in its gap as given, and that gap is asked no more. The record's text is the rule's: no
model writes a value.

## Suggestions

`DD_METADATA_SUGGESTER` chooses the suggester (`factory.py`, `config/examples/agents.env`):

- `template` (default) suggests nothing, calls no model and needs no key.
- `model` has a model suggest values for the questions on the properties `datacite.yaml` marks
  `suggest`: the title, the description, a free keyword and the language. A suggestion is
  offered in the question (`suggested_answer`, `suggestion_derivation: model`), never in the
  record, whose text stays the template's byte for byte. It becomes part of the record only when
  a person records it, or a correction of it, as their answer.

The model is given the chosen repository's name and requirements and the inventory's structure:
each file's path, media type and size, and its fields' names, types and formats. It is never given
the data, a description a person wrote, the researchers' ORCID records, an answer or an earlier
version. A suggestion is dropped if it answers a question the model was not offered, repeats one,
is longer than a short paragraph, is not one line of plain text, or names a link, DOI, email
address or ORCID iD that the facts do not give. The outcome's statement says how many were
offered and why any were dropped.

It is never asked to suggest a creator, contributor, date, rights statement, funder, related
identifier or place, which only the researcher can give, nor an entry the repository asks for from
a named vocabulary, such as an ANZSRC field of research.

Its grounding mode is `input_only`: it cites only its input. The core `Document` has no
`limitations` slot, so the outcome's statement says what it does not do (docs/specs/agents.md).

## What it does not do

- It fills no property that only the researcher can, such as the title or licence, except from
  their recorded answers, and fills creators, subjects and funding only from what researchers kept
  from their ORCID records.
- It uses no controlled vocabularies, and does not split names into given and family names:
  TODO(#703).
- It does not map a record between schemas (R6), or write Figshare's own item format (#383):
  TODO(#703).
- It does not use metadata extracted from the files themselves: TODO(#789).
- It does not check that a value is correct. Validating the record is the harness's work (#19).
- It does not read an earlier version, or the reason a person gave for a decision on it.
- It has no evaluation set; it leaves alpha only with one (docs/specs/agents.md), TODO(#703).

The fully designed librarian, which drafts against controlled vocabularies and maps between
schemas, is TODO(#357).
