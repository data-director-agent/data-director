# ADR-0038: Repository requirements and the deposit package

**Status:** Proposed
**Date:** 2026-10-30

Answers #197 and, for how a choice is recorded, #199. Builds on
[ADR-0005](0005-dataset-profile-and-validation.md),
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

The researcher does not choose from a short list the deployment keeps. `advisor.repository`
shortlists from re3data, which lists thousands of repositories, and the researcher may choose any
of them (#199). Almost none publishes its deposit requirements in a form a machine can read, so
a description written by hand for each one would never be complete and would go stale. What
re3data does record is the metadata standards each repository uses, and most general-purpose
repositories register DataCite DOIs.

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
`advisor.repository` (#320) needs to know which repositories the deployment knows best.

## Decision

1. **Requirements are described per metadata standard, with optional overrides per repository.**
   Both are a core contract class, `RequirementSet`, so that the harness, a drafter and
   `advisor.repository` read the same description without knowing one another. A set is one of
   two kinds:

   - A **standard's set** says what any record in a metadata standard must or should have. It
     names the standard in `conforms_to` and the names re3data uses for it in `re3data_names`.
     DataCite's is the first and, for the MVP, the only one: decision 3 makes every metadata
     record DataCite. Sets for other standards, such as DDI, are TODO(#401).
   - A **repository override** adds what one repository asks beyond its standard. It names the
     repository in `re3data_id` and the standard's set it builds on in `conforms_to`. ORDA's is the
     first. An override is written only for a repository the deployment knows well, usually its
     own institution's.

   Their slots are:

   | Slot | Meaning |
   |---|---|
   | `requirement_set_id`, `version` | Identify the set. The version is raised on every change, as an institutional profile's is. |
   | `title`, `url` | What a person calls the standard or the repository, and where it is described. |
   | `conforms_to` | The URI of the metadata schema. |
   | `re3data_names` | A standard's set only: the `metadataStandardName` values in re3data that select it. |
   | `re3data_id` | An override only: the repository's re3data record, which `advisor.repository` already reads. |
   | `fields` | The metadata required or recommended (below). |
   | `required_documents` | The `DocumentKind`s that must have an approved version before a package is built. |
   | `recommended_documents` | The `DocumentKind`s whose absence is a warning. |
   | `media_types` | An override only: the media types the repository accepts. Absent or empty means any. |
   | `max_file_size`, `max_item_size` | An override only: size limits in bytes, for one file and for the deposit. Absent means none is stated. |
   | `licences` | An override only: the licences the repository offers, each an SPDX identifier or, for terms of the repository's own, the URL of those terms. Absent means none is stated. |
   | `guidance` | The pages each value was taken from, so that a steward can check it. |

   Each entry of `fields` gives a property of the schema, optionally qualified (a subject in a
   named scheme), the schema.org term it maps to and an obligation of `required` or
   `recommended`. An override's entries may add `form_label`, the label of the deposit form's
   field that the value goes in, so that a person depositing by hand knows where to put it.
   Properties the repository fills itself, such as the identifier and the publisher, are not
   listed. A value the guidance does not state is left out and marked as undecided with an issue
   reference, never guessed. The class's LinkML follows this record, as an additive change to the
   core contract (ADR-0019 decision 1).

2. **Sets are deployment configuration, and a choice records the sets it resolved to.** A set is a
   YAML file that a steward can read and propose changes to (ADR-0003). The harness loads the sets
   in the directory that `DD_REPOSITORIES_DIR` names: standards' sets in `standards/`, overrides in
   `overrides/`. There is no default (ADR-0022), and a set with a key outside its class, or of
   neither kind, is refused at start-up, as an institutional profile is. The app's sets are in
   `app/config/repositories/`. Each workspace member that needs them keeps its own copies
   (ADR-0031).

   The researcher chooses a repository by its re3data identifier, usually from
   `advisor.repository`'s shortlist, and the choice carries the metadata standards its re3data
   record declares. The harness resolves the choice:

   - **the standard's set** is the one whose `re3data_names` include a declared standard. When none
     does, it is DataCite's, with a warning that the repository does not list DataCite, because
     every repository that mints DataCite DOIs accepts a DataCite record;
   - **the override** is the one whose `re3data_id` is the repository's, if there is one;
   - **merged**, a field is identified by its property, qualifier and schema.org term. An
     override's field adds to the standard's or, for the same field, raises its obligation from
     `recommended` to `required` and gives its `form_label`. An override that lowers an obligation
     is refused at start-up. Documents are the union of both, and a kind required by either is
     required. Media types, sizes and licences come from the override alone.

   The project log records the choice as a `repository_chosen` event: the re3data identifier and
   name, the declared standards, each set used as `<requirement_set_id>@v<version>` with the
   SHA-256 of its bytes (as a run records `policy_digest`), any warning, and the merged set, kept
   by its digest among the project's blobs. The last choice counts. A drafter is given the merged
   set in its input (ADR-0034 decision 6), and validation reads the same one. A repository without
   an override is checked only against its standard, and the event says so as a warning. Which repositories an institution approves,
   and preferring them for its researchers, are TODO(#320). Fee amounts and who pays for PIDs are
   TODO(#322). Choosing in the app is TODO(#400).

3. **The metadata record follows DataCite.** The drafter writes it as a `Document` of kind
   `metadata_record`, in DataCite's JSON form, with `conforms_to` set to the merged set's
   `conforms_to`. DataCite is the schema ORDA's DOIs are registered in, and a record in it serves
   any repository that mints DataCite DOIs. An override's `form_label`s say where each value goes
   in that repository's form. A record in Figshare's own item format, for deposit through
   Figshare's API, is TODO(#383).

4. **Validation is a harness step, and its result is one SHACL Validation Report.** No agent
   decides whether a package is valid. The harness checks the project against the merged set
   recorded for the chosen repository:

   - every kind in `required_documents` has an approved version and, as warnings, every kind in
     `recommended_documents`;
   - the approved metadata record has every `required` field and, as warnings, every
     `recommended` one;
   - the record's licence is one of the set's `licences`, when it lists any;
   - every inventory entry has an accepted media type and is within the size limits, and the
     inventory as a whole is within `max_item_size`, when they are stated.

   The harness generates SHACL shapes from the set's `fields`, and reads the record as RDF
   through the same DataCite to schema.org mapping that decision 5 uses for the crate. The other
   checks write their results in the same vocabulary. A failed `required` check is an
   `sh:Violation` and a `recommended` one an `sh:Warning`. The package is **valid** when the report
   has no `sh:Violation`. Warnings, including a warning from resolving the choice, are shown to the
   researcher and do not block. The harness records the report by its digest in the project log.

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
   repository/requirements.json   the merged set the package was validated against
   validation/report.ttl          the SHACL Validation Report, and a Frictionless report if any
   audit/events.jsonl             the project log
   audit/runs/<invocation_id>/    the Process Run Crate of each run behind an approved version
   ```

   The root dataset's properties come from the approved metadata record through the DataCite to
   schema.org mapping, and the dataset `conformsTo` the standard. Each data file in the inventory
   is a `File` entity with its path, size and SHA-256, marked as not included: the researcher adds
   the files when depositing, and the digests show that they are the files that were described.
   Each document entity names the version it is, the run or the person that produced it, and the
   decision that approved it. A full PROV-O account of those links is TODO(#26). The harness keeps
   the package by its digest among the project's blobs and records it in the project log. This
   answers ADR-0021's crate for the deliverable.

6. **Deposit-ready means that a person can upload it.** The tool does not deposit, and it does not
   mint or reserve a persistent identifier (R7). Depositing through a repository's API, after a
   person approves it (ADR-0017's `deposit` action class), is TODO(#383).

Rejected:

- **A profile for every repository the researcher may choose.** Written by hand, it would cover a
  handful of the repositories `advisor.repository` can recommend, and the rest could not be chosen.
- **Requirements drafted by an agent from a repository's web pages.** It would cover any
  repository, but a misread page would become the definition of valid, and validity must not be an
  agent's claim. A person approving each draft (ADR-0036) would make every new repository wait for
  a steward.
- **Choosing only among repositories with an override.** The researcher's choice would be limited
  by what the deployment has written, not by what suits the data.
- **A record in Figshare's item format.** It is closest to what ORDA's API takes, but it serves
  only Figshare, and the DataCite record ORDA registers would still be derived from it.
- **SHACL shapes written by hand.** They can say more, but a steward cannot read or review them.
  Shapes generated from the YAML say only what the sets say.
- **A JSON Schema for each standard or repository.** Its errors would have to be translated into
  the SHACL vocabulary, or ADR-0005 changed.
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

- Any repository in re3data can be chosen with no configuration. It is checked against its
  standard's set, which for the MVP is DataCite's.
- A repository's own rules, such as a required field in its form or the licences it offers, are
  checked only where a steward has written an override. Without one, a package can be valid and
  still be refused at deposit; the researcher is told that no override exists.
- A new override is a new YAML file, not new code. A new standard needs its set, its mapping to
  schema.org and a drafter (#401).
- A steward can read what the tool will check, and a researcher can see which page each
  requirement came from.
- A package says what was checked and against which versions of which sets, and its audit trail
  goes with it.
- The package cannot show that the files a researcher deposits are complete or correct beyond what
  the inventory describes. The digests can be checked at deposit, but nothing in the tool checks
  them.
- `advisor.quality` reads a `MetadataRecord` of DCAT terms, not a DataCite record. Moving it to
  DataCite is TODO(#22).
- A future contributor must not let an agent decide validity or write the requirements validation
  enforces, build a package from a report that has an `sh:Violation`, put data files into the
  package, or write requirements into code rather than a set, without revisiting this decision.
