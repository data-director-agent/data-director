# Deposit

## Intent and scope

The minimum loop ends with a package that is validated and ready to deposit in a repository the
researcher chose. This spec covers how a repository's requirements are described, how a choice of
repository resolves to them, what "validated" means, and what the deposit package is. The project
that holds the inventory, the documents and the decisions is in [Projects](projects.md).

A researcher may choose any repository listed in re3data, usually from `advisor.repository`'s
shortlist, with no configuration written for it first. Almost no repository publishes its deposit
requirements in a form a machine can read, but re3data records the metadata standards each one
uses, and most general-purpose repositories register DataCite DOIs. Requirements are therefore
described per metadata standard, with optional overrides for the few repositories a deployment
knows well, usually its own institution's. The sets and how they are written are described in
[`app/config/repositories/README.md`](../../app/config/repositories/README.md).

Out of scope: depositing, and minting or reserving a persistent identifier (R7). Deposit-ready
means that a person can upload the package. Depositing through a repository's API, after a person
approves it under the profile's `deposit` action class, is TODO(#383).

What is built:

- the `RequirementSet` class, loading and checking the sets, resolving a choice and recording it
  in the project (`dd_harness.requirements`, `dd-harness project choose-repository`);
- the DataCite and ORDA sets;
- validation and the package (`dd_harness.deposit`, `dd-harness project validate` and
  `dd-harness project package`).

Choosing a repository in the app is TODO(#400). Validating and building the package in the app
is TODO(#623). Giving a drafter the merged set is TODO(#394, #200).

## Invariants

1. **Requirements live in sets, never in code.** A requirement set is deployment configuration a
   steward can read and propose changes to, as an institutional profile is
   ([Policy and identity](policy-and-identity.md)). A new override is a new file, not new code.
2. **A set is either a standard's set or a repository override, and says only what its kind may.**
   A standard's set names its standard's re3data names; an override names one re3data repository
   and the standard it builds on, and alone may give media types, size limits, licences and deposit
   form labels. A key outside the class, a set of neither kind, or two sets that collide stops the
   harness before anything is recorded (`harness/tests/test_requirements.py`).
3. **A DataCite set always exists**, since it is the fallback for a repository that declares no
   known standard (`dd_harness.requirements`, checked on load).
4. **An override adds or raises, never lowers.** It may add a field, or raise one from
   `recommended` to `required` and label it; lowering one is refused on load. Documents are the
   union of both sets, and a kind either requires is required. Media types, sizes and licences
   come from the override alone (`harness/tests/test_requirements.py`).
5. **A choice resolves deterministically.** The override is the one for the repository's re3data
   identifier. The standard is the one the override names, because a steward who wrote the
   override knows the repository better than its registry record (re3data lists only Dublin Core
   for ORDA, which registers DataCite DOIs); without an override, a set matching a standard the
   repository declares; else DataCite's, with a warning. A repository without an override gets a
   warning that its own form, formats, sizes and licences are not checked
   (`harness/tests/test_requirements.py`, `app/tests/test_repositories.py`).
6. **A choice records exactly what it resolved to.** The project log names each set used by
   `<requirement_set_id>@v<version>` and the SHA-256 of its file, keeps the merged set by its
   digest, and records the warnings. The last choice counts (`harness/tests/test_projects.py`).
   A set's version is raised on every change; nothing checks this.
7. **The drafter and validation read the same merged set**, the one recorded for the choice.
   Validation reads it (`dd_harness.deposit`); giving it to the drafter is TODO(#394).
8. **Validity is the harness's, never an agent's.** The harness checks the project against the
   recorded merged set and writes one SHACL Validation Report. A failed `required` check is an
   `sh:Violation`, a failed `recommended` one an `sh:Warning`. The package is valid when the report
   has no violation; warnings, including those from resolving the choice, are shown and do not
   block. `advisor.quality` stays advisory. Every validation, valid or not, is kept by its digest
   in the project log
   (`test_a_missing_required_field_is_a_violation_and_a_recommended_one_a_warning`,
   `test_the_validation_report_is_a_shacl_validation_report`).
9. **A package is built only from a valid report, and holds no data file.** A violation stops
   the package and names each reason; the report is still kept
   (`test_a_project_without_a_required_document_is_refused_and_says_why`,
   `test_a_valid_project_writes_a_package_with_its_audit_trail`).
10. **The package passes the RO-Crate validator** at its REQUIRED level, against the RO-Crate
    version `rocrate` writes (`test_the_package_passes_the_ro_crate_validator`).

## Boundaries and contracts

**The class.** `RequirementSet` is a core contract class ([Contract](contract.md)) so that the
harness, a drafter and `advisor.repository` read one description without knowing one another. Each
field names a property of the standard's schema, optionally qualified, the schema.org term it maps
to, and its obligation. Properties the repository fills itself, such as the identifier and the
publisher, are not listed. A value the guidance does not state is left out and marked with an
issue reference, never guessed; each set cites the pages its values came from, so a steward can
check them. What ORDA's public pages leave open is TODO(#385).

**The metadata record follows DataCite.** The drafter writes a `Document` of kind
`metadata_record` in DataCite's JSON form, with `conforms_to` set to the merged set's. DataCite is
the schema ORDA's DOIs are registered in, and a DataCite record serves any repository that mints
DataCite DOIs. An override's form labels tell a person depositing by hand where each value goes.
Sets for other standards, such as DDI, each need a set, a mapping to schema.org and a drafter,
TODO(#401).

**Validation** checks, against the merged set:

- every required document kind has an approved version, and, as warnings, every recommended one;
- the approved metadata record has every required field and, as warnings, every recommended one;
- the record's licence is one the set lists, when it lists any;
- every inventory entry has an accepted media type and is within the file size limit, and the
  inventory's files together within the item size, when they are stated. A limit on the number of
  files in an item is not in the class, TODO(#385).

A project with no repository chosen, or no inventory, has a violation that says so.

The record is read as RDF through the set's own field table, the same DataCite to schema.org
mapping the package uses. A field's property, and its qualifier when it has one, select the
record's entries; each entry's value becomes a value of the field's schema.org term. SHACL shapes
are generated from the fields, one `sh:minCount 1` property shape per field, with the severity
its obligation gives and a message naming the field by its form label. pySHACL runs them. The
other checks write their results in the same `sh:` vocabulary, which is the fixed validation
format ([Contract](contract.md)), and the warnings from resolving the choice are carried as
warnings. The harness keeps the report by its digest in the project log, with a
`project_validated` event saying whether it conforms. Validity covers the data files only as far as the
inventory describes them: checking a table's contents against its Frictionless schema needs the
data, so it runs where the data live, in the inventory command, and its report travels with the
inventory, TODO(#19).

**The package** is one zip file whose root `ro-crate-metadata.json` describes the dataset. It
holds the approved metadata record, the other approved documents (each document's latest approved
version), the inventory, the merged set it was validated against, the validation report, the
project log, and the Process Run Crate of each run behind an approved version
([Contract](contract.md)). The root dataset's properties come from the approved metadata record
through the DataCite to schema.org mapping. Each approved document is under `documents/`, an
entity that names its version and conforms to the document's standard. The run that drafted it
or the person who edited it is a `CreateAction` with the version as its result. The decision that
approved it is an `AssessAction`, with the person who made it, when, and their reason. Each run
behind an approved version is attached as its Process Run Crate under `runs/<invocation_id>/`;
a run that kept no crate is named and says so. Each data file is a `File` entity with a local
identifier, its path, size and SHA-256, marked as not included (`includedInPackage`): the
researcher adds the files at deposit, and the digests show they are the files described. Beside
them are `inventory.json`, `requirements.json`, `validation-report.jsonld` and
`project-log.jsonl`, the log as it stood when the package was built. The package carries the
project's disclosure of generative AI: its statement, `use-of-generative-ai.md`, and its PROV-O
graph of each approved version, `provenance.jsonld` ([Disclosure](disclosure.md)). Whether a
researcher may include the prompts themselves is TODO(#624). PROV-O alignment of the whole package
is TODO(#26) (R10). The harness keeps the package by the SHA-256 of its bytes and records it in
the project log with a `package_built` event, which names the report, the merged set, each
document version and each run it holds.

**Elsewhere.** Which repositories an institution approves, and preferring them, are TODO(#320).
Fees and who pays for PIDs are TODO(#322) (R7). `advisor.quality` reads a record of DCAT terms, not
DataCite; moving it is TODO(#22).

## Rationale

- **Per standard, not per repository**, because a hand-written profile for every repository would
  never be complete and would go stale, while re3data already says which standards each uses.
- **Overrides in the hands of stewards**, because a repository's own rules (a required form field,
  the licences it offers) are known to the people who run it, and a steward can review YAML.
- **Validity in the harness, recorded with the sets' versions and digests**, so a package says
  what was checked and against which requirements, and its audit trail goes with it.

## Rejected alternatives

- **A profile for every repository the researcher may choose.** It would cover a handful, and the
  rest could not be chosen.
- **Requirements drafted by an agent from a repository's web pages.** A misread page would become
  the definition of valid; approving each draft would make every new repository wait for a steward.
- **Choosing only among repositories with an override.** The deployment's configuration, not the
  data, would limit the choice.
- **A record in Figshare's item format.** It serves only Figshare, and ORDA's DataCite record would
  still be derived from it. It may come with deposit through the API, TODO(#383).
- **SHACL shapes written by hand.** A steward cannot read or review them; generated shapes say only
  what the sets say.
- **A JSON Schema per standard or repository.** Its errors would have to be translated into the
  SHACL vocabulary, or the validation format changed.
- **A validator agent.** Validity would become an agent's claim about its own input, and the
  package would travel in an envelope.
- **A folder with a crate inside.** The folder's layout and the crate would be two descriptions of
  one package.
- **Data files in the package.** The platform never holds them ([Projects](projects.md)).

## Non-functional requirements

- **Honesty about coverage.** Without an override, a package can be valid and still be refused at
  deposit; the researcher is told no override exists. The package cannot show that the files
  deposited are complete or correct beyond the inventory, and nothing in the tool checks their
  digests at deposit.
- **Traceability** (R4, R10): every requirement can be traced to the page it came from, and every
  report to the versions and digests of the sets it applied.
- **Portability.** pySHACL is a runtime dependency of the harness only, with a fallback of checks
  written in Python that emit the same vocabulary ([Dependencies](dependencies.md)).
