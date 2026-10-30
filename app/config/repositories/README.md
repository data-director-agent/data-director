# Repository profiles

A repository profile says what one repository requires of a deposit: the metadata fields it
requires or recommends, the documents it needs, and the formats, sizes and licences it accepts.
Before it builds a deposit package, the harness checks a project against the profile of the
repository the researcher chose
([ADR-0037](../../../docs/adr/0037-repository-profile-and-deposit-package.md)). A drafter is given
the same profile, so that it knows what to write.

Profiles are YAML so that the people who know the repository, its research data management team
and the deployment's stewards, can read them and propose changes. A new repository is a new file
here, not new code. None of this is built yet (#199, #202).

## Which profiles apply

The harness loads every profile in the directory that `DD_REPOSITORIES_DIR` names, and a
researcher chooses among them. The project records the profile it was given as
`<repository_id>@v<version>`, with the SHA-256 of the file, so a later reader can tell which
requirements a package was checked against.

## What a profile contains

| Key | Meaning |
|---|---|
| `repository_id`, `version` | Identify the profile. Raise `version` on every change. |
| `repository_name`, `url` | What people call the repository, and where it is. |
| `re3data_id` | The repository's [re3data](https://www.re3data.org/) record. |
| `conforms_to` | The URI of the metadata schema a record for this repository follows. DataCite for ORDA. |
| `fields` | The metadata the depositor supplies (below). |
| `required_documents` | Document kinds that must be approved before a package is built: `metadata_record`, `readme`, `data_dictionary`, `dmp` or `other`. |
| `recommended_documents` | Document kinds whose absence is a warning. |
| `media_types` | The media types the repository accepts. An empty list means any. |
| `max_file_size`, `max_item_size` | Size limits in bytes. Leave a key out if the repository does not state it. |
| `licences` | SPDX identifiers, or the URL of the repository's own terms. |
| `guidance` | The pages the values were taken from. |

Each entry of `fields` has:

- `property`: the schema's property, such as DataCite's `titles`;
- `qualifier` (optional): a value that narrows it, such as a subject scheme;
- `schema_org`: the schema.org term it maps to, used to read the record for checking and to
  describe the dataset in the package;
- `obligation`: `required` (a missing value stops the package) or `recommended` (a warning);
- `form_label`: the label of the field in the repository's deposit form, where a person
  depositing by hand puts the value.

A key outside this list is refused. A value the repository's guidance does not state is left out
with a `TODO(#…)`, never guessed.

## Files

| File | Repository |
|---|---|
| `orda.yaml` | ORDA, the University of Sheffield's repository on Figshare. What its public pages leave open is TODO(#385). |
