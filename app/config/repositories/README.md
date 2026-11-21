# Repository requirements

A requirement set says what a deposit must or should have: the metadata fields, the documents,
and, for one repository, the formats, sizes and licences it accepts. Before it builds a deposit
package, the harness checks a project against the requirements of the repository the researcher
chose ([Deposit](../../../docs/specs/deposit.md)). A
drafter is given the same requirements, so that it knows what to write.

The sets are YAML so that the people who know a repository, its research data management team
and the deployment's stewards, can read them and propose changes. The harness loads them and
records a researcher's choice (`dd-harness project choose-repository`, which reads the
repository's name and declared standards from the pinned re3data export), and checks a project
against the merged set it recorded (`dd-harness project validate`). `app/tests/test_repositories.py` checks that they
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

## Suggested repositories

`suggested.yaml` lists, by re3data identifier and in order, the repositories the app offers on a
project's page before the researcher searches the pinned re3data export
(`GET /api/repositories`). Every repository with an override is offered first, whether or not it
is listed. An identifier the pinned export does not hold is left out, and one that is not a
re3data identifier stops start-up. The file is optional; without it only the overrides are
offered.

## What a set contains

| Key | Meaning |
|---|---|
| `schema_class` | Always `RequirementSet`. |
| `requirement_set_id`, `version` | Identify the set. Raise `version` on every change. |
| `title`, `url` | What people call the standard or the repository, and where it is described. An override's `url` is where the app tells a researcher to deposit. |
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
| `deposit` | Overrides only: the API a draft is deposited through (below). |
| `unconfirmed` | What the guidance leaves open, each a short statement that names its issue. The app shows them to a researcher depositing by hand. |

Each entry of `fields` has:

- `property`: the schema's property, such as DataCite's `titles`;
- `qualifier` (optional): a value that narrows it, such as a subject scheme;
- `schema_org`: the schema.org term it maps to, used to read the record for checking and to
  describe the dataset in the package. A record's values are checked under this term, so two
  fields may not share one, even across an override and its standard: a lineage mapped to
  `description` would pass on the abstract alone. Such sets are refused on load;
- `obligation`: `required` (a missing value stops the package) or `recommended` (a warning);
- `form_label` (overrides only): the label of the field in the repository's deposit form, where a
  person depositing by hand puts the value.

An override may also name the API the harness deposits a draft through, in a `deposit` block:

| Key | Meaning |
|---|---|
| `transport` | The transport, registered under `dd.transports`: `zenodo` so far. |
| `format` | The format it carries: `zenodo-deposit` for `zenodo`. Any other pair stops start-up. |
| `base_url` | The installation's API root, `https://` only, such as `https://sandbox.zenodo.org/api`. |
| `target` | Optional: where the draft is created, such as a Zenodo community. |
| `sandbox` | Whether `base_url` is the platform's test installation; the app says so beside the deposit. |

It holds no credential: each researcher uses their own account, kept by the deposit broker
([The deposit broker](../../../docs/guide/operations/deposit-broker.md)). A repository without it
is deposited to by hand. The design is in
[Deposit](../../../docs/specs/deposit.md#depositing-through-an-api).

A key outside this list is refused. A value the guidance does not state is left out with a marker
that cites an issue, never guessed, and listed under `unconfirmed` so a researcher sees it too.

## Files

| File | Set |
|---|---|
| `standards/datacite-4.yaml` | The DataCite Metadata Schema 4. |
| `overrides/orda.yaml` | ORDA, the University of Sheffield's repository on Figshare. What its public pages leave open is TODO(#385). |
| `overrides/zenodo.yaml` | Zenodo, from its developer documentation and help pages, with a `deposit` block that sends drafts to the Zenodo sandbox. Moving to Zenodo itself is TODO(#648). |
| `overrides/eidc.yaml` | The NERC EDS Environmental Information Data Centre (EIDC), from its Service Agreement and its DataCite records. It builds on DataCite until a UK GEMINI / ISO 19115 set exists (#401). What its public pages leave open is TODO(#1250). |
| `overrides/bodc.yaml` | The NERC EDS British Oceanographic Data Centre (BODC), from its metadata submission template and its DataCite records. What its public pages leave open is TODO(#1250). |
| `overrides/ceda.yaml` | The NERC EDS Centre for Environmental Data Analysis (CEDA), from its help pages and its metadata.yaml generator; its catalogue record form is behind a login. What its public pages leave open is TODO(#1250). |
| `overrides/ngdc.yaml` | The NERC EDS National Geoscience Data Centre (NGDC), from its metadata guidance and its deposit form's validation. What its public pages leave open is TODO(#1250). |
| `overrides/ukpdc.yaml` | The NERC EDS UK Polar Data Centre (UK PDC), from its metadata guidance template and its DataCite records. What its public pages leave open is TODO(#1250). |

Every NERC EDS centre builds on DataCite, with which it registers its DOIs, until a UK GEMINI /
ISO 19115 set exists (#401).
