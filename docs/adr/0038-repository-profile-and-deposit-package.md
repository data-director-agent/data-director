# ADR-0038: The repository profile and the deposit package

**Status:** Proposed
**Date:** 2026-10-30

Answers #197. Builds on [ADR-0005](0005-dataset-profile-and-validation.md),
[ADR-0017](0017-policy-is-the-deployments.md),
[ADR-0021](0021-ro-crate-is-a-record-not-a-message.md),
[ADR-0034](0034-project-and-its-files.md), [ADR-0035](0035-project-documents.md) and
[ADR-0036](0036-proposed-changes-and-approval.md).

## Context

The minimum loop of the MVP ends with a package that is validated and ready to deposit in a
repository the researcher chose. The first repository is ORDA, the University of Sheffield's
research data repository, which runs on Figshare and mints DataCite DOIs. Three things were
undecided: how a repository's requirements are described, what "validated" means, and what the
package is.

Several decisions already constrain the answer:

- **No data files on the platform.** The project holds an inventory of the data files, never their
  content, and the package holds no data files (ADR-0034 decisions 3 and 8). Whatever is validated
  about the files is validated from the inventory.
- **Documents are text with a schema.** A project document is a `Document` payload whose
  `conforms_to` names the schema it follows. Checking it against that schema is the validator's
  work, not the contract's (ADR-0035 decision 2). The package takes each document's latest
  approved version (ADR-0035 decision 6). How a version is approved is decided by
  [ADR-0036](0036-proposed-changes-and-approval.md).
- **The validation format is fixed.** Structured validation output is a SHACL Validation Report,
  with a Frictionless report for tables. No bespoke report type is defined (ADR-0005).
- **The crate for the deliverable was left open.** ADR-0021 decided that the Process Run Crate is a
  record written after each run. It left open which component writes a crate of the dataset, and
  how that crate refers to the runs that produced it.
- **Policy is the deployment's** (ADR-0017). What an institution accepts is configuration that its
  stewards can read, as the institutional profile is (ADR-0003).

Three parties need to know a repository's requirements, and none of them knows the others. The
drafter of the metadata record has to know what to write. The harness has to know what to check.
`advisor.repository` (#320) needs to prefer the deployment's own repositories.

## Decision

1. **A repository profile describes one repository's requirements.** It is a core contract class,
   `RepositoryProfile`, so that the harness, a drafter and `advisor.repository` read the same
   description without knowing one another. Its slots are:

   | Slot | Meaning |
   |---|---|
   | `repository_id`, `version` | Identify the profile. The version is raised on every change, as an institutional profile's is. |
   | `repository_name`, `url` | What a person calls the repository, and where it is. |
   | `re3data_id` | The repository's re3data record, which `advisor.repository` already reads. |
   | `conforms_to` | The URI of the metadata schema a record for this repository must follow. |
   | `fields` | The metadata the repository requires or recommends (below). |
   | `required_documents` | The `DocumentKind`s that must have an approved version before a package is built. |
   | `recommended_documents` | The `DocumentKind`s whose absence is a warning. |
   | `media_types` | The media types the repository accepts. Empty means any. |
   | `max_file_size`, `max_item_size` | Size limits in bytes, for one file and for the deposit. Absent means none is stated. |
   | `licences` | The licences the repository offers, each an SPDX identifier or, for terms of the repository's own, the URL of those terms. |
   | `guidance` | The pages each value was taken from, so that a steward can check it. |

   Each entry of `fields` gives a property of the schema (a DataCite property for ORDA), optionally
   qualified (a subject in a named scheme), the schema.org term it maps to, an obligation of
   `required` or `recommended`, and `form_label`, the label of the deposit form's field that the
   value goes in, so that a person depositing by hand knows where to put it. Properties the
   repository fills itself, such as the identifier and the publisher, are not listed. A value the
   guidance does not state is left out and marked as undecided with an issue reference, never guessed. The class's LinkML follows this record, as an additive change to the core
   contract (ADR-0019 decision 1).

2. **Profiles are deployment configuration.** A profile is a YAML file that a steward can read and
   propose changes to (ADR-0003). The harness loads the profiles in the directory that
   `DD_REPOSITORIES_DIR` names. There is no default (ADR-0022), and a profile with a key outside its
   class is refused at start-up, as an institutional profile is. The app's profiles are in
   `app/config/repositories/`, and ORDA's is the first. Each workspace member that needs profiles
   keeps its own copies (ADR-0031). When a researcher chooses a repository (#199), the project log
   records the profile as `<repository_id>@v<version>` with the SHA-256 of its bytes, as a run
   records `policy_digest`. A drafter is given the chosen profile in its input (ADR-0034 decision
   6). Which repositories an institution approves, and preferring them for its researchers, are
   TODO(#320). Fee amounts and who pays for PIDs are TODO(#322).

3. **The metadata record follows DataCite.** The drafter writes it as a `Document` of kind
   `metadata_record`, in DataCite's JSON form, with `conforms_to` set to the profile's
   `conforms_to`. DataCite is the schema ORDA's DOIs are registered in, and a record in it serves
   any other repository that mints DataCite DOIs. The profile's `form_label`s say where each value
   goes in ORDA's form. A record in Figshare's own item format, for deposit through Figshare's API,
   is TODO(#383).

4. **Validation is a harness step, and its result is one SHACL Validation Report.** No agent
   decides whether a package is valid. The harness checks the project against the chosen profile:

   - every kind in `required_documents` has an approved version and, as warnings, every kind in
     `recommended_documents`;
   - the approved metadata record has every `required` field and, as warnings, every
     `recommended` one;
   - the record's licence is one of the profile's `licences`;
   - every inventory entry has an accepted media type and is within the size limits, and the
     inventory as a whole is within `max_item_size`.

   The harness generates SHACL shapes from the profile's `fields`, and reads the record as RDF
   through the same DataCite to schema.org mapping that decision 5 uses for the crate. The other
   checks write their results in the same vocabulary. A failed `required` check is an
   `sh:Violation` and a `recommended` one an `sh:Warning`. The package is **valid** when the report
   has no `sh:Violation`. Warnings are shown to the researcher and do not block. The harness records
   the report by its digest in the project log.

   Validity covers the data files only as far as the inventory describes them (ADR-0034 decision
   8). Checking a table's contents against its Frictionless schema needs the data, so it runs where
   the data live, in the inventory command, and its report travels with the inventory,
   TODO(#198, #19). `advisor.quality` stays advisory: a person may weigh its findings, but they do
   not decide validity.

5. **The deposit package is an RO-Crate.** The harness builds it only from a valid report. It is
   one zip file, whose root `ro-crate-metadata.json` describes the dataset:

   ```text
   ro-crate-metadata.json         the dataset, mapped from the metadata record
   metadata/datacite.json         the approved metadata record
   documents/                     the other approved documents, such as README.md
   inventory.json                 the FileInventory (ADR-0034)
   repository/<repository_id>.yaml  the profile the package was validated against
   validation/report.ttl          the SHACL Validation Report, and a Frictionless report if any
   audit/events.jsonl             the project log
   audit/runs/<invocation_id>/    the Process Run Crate of each run behind an approved version
   ```

   The root dataset's properties come from the approved metadata record through the DataCite to
   schema.org mapping, and the dataset `conformsTo` the profile. Each data file in the inventory is
   a `File` entity with its path, size and SHA-256, marked as not included: the researcher adds the
   files when depositing, and the digests show that they are the files that were described. Each
   document entity names the version it is, the run or the person that produced it, and the
   decision that approved it. A full PROV-O account of those links is TODO(#26). The harness keeps
   the package by its digest among the project's blobs and records it in the project log. This
   answers ADR-0021's crate for the deliverable.

6. **Deposit-ready means that a person can upload it.** The tool does not deposit, and it does not
   mint or reserve a persistent identifier (R7). Depositing through a repository's API, after a
   person approves it (ADR-0017's `deposit` action class), is TODO(#383).

Rejected:

- **A record in Figshare's item format.** It is closest to what ORDA's API takes, but it serves
  only Figshare, and the DataCite record ORDA registers would still be derived from it.
- **SHACL shapes written by hand for each repository.** They can say more, but a steward cannot
  read or review them. Shapes generated from the YAML say only what the profile says.
- **A JSON Schema for each repository.** Its errors would have to be translated into the SHACL
  vocabulary, or ADR-0005 changed.
- **A validator agent.** Validity would become an agent's claim about its own input, and the
  package would travel in an envelope.
- **A folder with a crate inside.** The folder's layout and the crate would be two descriptions of
  one package.

## Dependencies introduced

| Dependency | Tier | Fallback if this dependency is abandoned |
|---|---|---|
| [pySHACL](https://github.com/RDFLib/pySHACL) | Runtime path, harness only | Checks written in Python that emit the same `sh:` vocabulary. Validation is one module of the harness, so the replacement is local. |

`rocrate` is already listed in ADR-0006, with writing `ro-crate-metadata.json` directly as its
fallback.

## Consequences

- A new repository is a new YAML file, not new code, as long as its records follow a schema the
  harness can map to schema.org. Another schema needs its own mapping.
- A steward can read what the tool will check for their repository, and a researcher can see
  which page each requirement came from.
- A package says what was checked and against which version of which profile, and its audit trail
  goes with it.
- The package cannot show that the files a researcher deposits are complete or correct beyond what
  the inventory describes. The digests can be checked at deposit, but nothing in the tool checks
  them.
- `advisor.quality` reads a `MetadataRecord` of DCAT terms, not a DataCite record. Moving it to
  DataCite is TODO(#22).
- A future contributor must not let an agent decide validity, build a package from a report that
  has an `sh:Violation`, put data files into the package, or write requirements into code rather
  than a profile, without revisiting this decision.
