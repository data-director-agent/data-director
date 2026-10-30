# Repository requirements

A requirement set says what a deposit must or should have: the metadata fields, the documents,
and, for one repository, the formats, sizes and licences it accepts. Before it builds a deposit
package, the harness checks a project against the requirements of the repository the researcher
chose ([ADR-0038](../../../docs/adr/0038-repository-requirements-and-deposit-package.md)). A
drafter is given the same requirements, so that it knows what to write.

The sets are YAML so that the people who know a repository, its research data management team
and the deployment's stewards, can read them and propose changes. The harness loads them and
records a researcher's choice (`dd-harness project choose-repository`); checking a project
against them is not built yet (#199, #202). `app/tests/test_repositories.py` checks that they
load and that ORDA resolves as intended.

## Standards and overrides

The researcher may choose any repository in [re3data](https://www.re3data.org/), usually from
`advisor.repository`'s shortlist. Nobody has to write a file for it first. Its requirements come
from two kinds of set:

- `standards/` holds one set per metadata standard: what any record in that standard needs.
  DataCite is the only standard so far; others are #401.
- `overrides/` holds what one repository asks beyond its standard, such as the fields its deposit
  form requires and the licences it offers. Write one only for a repository the deployment knows
  well. A repository without one is checked against its standard alone, with a warning.

An override names its standard in `conforms_to`, and that is the standard used: re3data lists
only Dublin Core for ORDA, which registers its DOIs with DataCite. Without an override, the
harness picks the standard whose `re3data_names` include one the repository's re3data record
declares. When none does, it uses DataCite's and warns.

The harness merges the two. A field is identified by its `property`, `qualifier` and
`schema_org`. An override may add a field, or raise one from `recommended` to `required` and give
its `form_label`; it may not lower one. Documents are the union of both. Media types, sizes and
licences come from the override alone.

The harness loads the directory that `DD_REPOSITORIES_DIR` names. When a researcher chooses a
repository, the project records each set it used as `<requirement_set_id>@v<version>`, with the
SHA-256 of the file, so a later reader can tell which requirements a package was checked against.

## What a set contains

| Key | Meaning |
|---|---|
| `schema_class` | Always `RequirementSet`. |
| `requirement_set_id`, `version` | Identify the set. Raise `version` on every change. |
| `title`, `url` | What people call the standard or the repository, and where it is described. |
| `conforms_to` | The URI of the metadata schema. An override names the standard it builds on. |
| `re3data_names` | Standards only: the names re3data uses for the standard. |
| `re3data_id` | Overrides only: the repository's re3data record. |
| `fields` | The metadata a depositor supplies (below). |
| `required_documents` | Document kinds that must be approved before a package is built: `metadata_record`, `readme`, `data_dictionary`, `dmp` or `other`. |
| `recommended_documents` | Document kinds whose absence is a warning. |
| `media_types` | Overrides only: the media types the repository accepts. Empty means any. |
| `max_file_size`, `max_item_size` | Overrides only: size limits in bytes. Leave a key out if the repository does not state it. |
| `licences` | Overrides only: SPDX identifiers, or the URL of the repository's own terms. |
| `guidance` | The pages the values were taken from. |

Each entry of `fields` has:

- `property`: the schema's property, such as DataCite's `titles`;
- `qualifier` (optional): a value that narrows it, such as a subject scheme;
- `schema_org`: the schema.org term it maps to, used to read the record for checking and to
  describe the dataset in the package;
- `obligation`: `required` (a missing value stops the package) or `recommended` (a warning);
- `form_label` (overrides only): the label of the field in the repository's deposit form, where a
  person depositing by hand puts the value.

A key outside this list is refused. A value the guidance does not state is left out with a marker
that cites an issue, never guessed.

## Files

| File | Set |
|---|---|
| `standards/datacite-4.yaml` | The DataCite Metadata Schema 4. |
| `overrides/orda.yaml` | ORDA, the University of Sheffield's repository on Figshare. What its public pages leave open is TODO(#385). |
