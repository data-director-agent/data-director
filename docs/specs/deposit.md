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

Deposit-ready means that a person can upload the package. The harness may also deposit it for
them: after the researcher approves it, it creates a **draft** item in the chosen repository through
the repository's API, with the person's own credential, and records where it went. The researcher
then adds the data files and publishes the item in the repository's own interface. How this works,
for Figshare, Zenodo and Dataverse alike, is in *Depositing through an API* below; none of it is
built yet, TODO(#383).

Out of scope: publishing an item through an API, and minting or reserving a persistent identifier
(R7, TODO(#322)); uploading data files, which the platform never holds ([Projects](projects.md));
and a copy-ready sheet of a repository's form fields, TODO(#644).

What is built:

- the `RequirementSet` class, loading and checking the sets, resolving a choice and recording it
  in the project (`dd_harness.requirements`, `dd-harness project choose-repository`). A choice
  names only the repository's re3data identifier: its name and the metadata standards it declares
  are read from the pinned re3data export, which the harness reads through `sources.yaml`
  (`DD_SOURCES_CONFIG`, `dd_harness.sources`) and never from the agent's directory
  ([System](system.md)). An identifier that export does not hold is refused;
- the DataCite and ORDA sets;
- validation and the package (`dd_harness.deposit`, `dd-harness project validate` and
  `dd-harness project package`);
- validating and building the package in the app, which calls `dd_harness.deposit` in process
  and draws its results ([The app](app.md)): `POST /api/projects/{id}/validation` checks the
  project and keeps the report; `POST /api/projects/{id}/package` builds the package, or answers
  `409` with the validation that stopped it; `GET /api/projects/{id}/packages/{digest}` downloads
  a package the project log records as built (`app/tests/test_deposit_package.py`);
- what to do after downloading the package: the Deposit panel lists the manual steps for the
  chosen repository, naming its form's fields by their `form_label`, linking to its
  `repository_url` and listing its `unconfirmed` items, all read from the merged set; the user
  guide's *Depositing your data* covers the same steps.

A researcher chooses a repository in the app from an advisor's shortlist
(`PUT /api/projects/{id}/repository`, [App](app.md)). Giving a drafter the merged set is
TODO(#394, #200).

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
6. **A choice records exactly what it resolved to.** The project log names the re3data record the
   repository's name and declared standards were read from, by its `snapshot_ref` (the latest
   `re3data:export:YYYY-MM` pinned) and its content hash under `dd-json-document-v1`, the hash
   evidence citing that record carries ([Grounding](grounding.md)). It names each set used by
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

Invariants 11 to 15 hold for depositing through an API, which is not built yet; each names the
issue that will build and test it.

11. **A connector is configuration, never code for one repository.** A repository is reachable
    through its API when its override names an API kind, a base URL and a target. Each API kind has
    one implementation, shared by every repository of that kind; adding a repository of a known
    kind is a new override, not new code (invariant 1). TODO(#383, #648, #857).
12. **No deposit without a person's recorded approval.** The harness deposits only on a
    `deposit_approved` event that a person made, naming the package by its digest and the
    repository it goes to, and only a package the log records as built from a valid report
    (invariant 9). No agent deposits, and no agent's output starts one. TODO(#383).
13. **The credential reaches no record.** A person's repository token appears in no project log
    event, run, trace, prompt, Process Run Crate, package, error message or app response, and the
    app and the harness never hold it at rest. TODO(#383).
14. **A deposit creates a draft and never publishes.** Nothing the harness sends publishes an item,
    mints a persistent identifier or makes a file public. TODO(#383).
15. **Every deposit ends in one outcome event, manual or automatic.** A `deposit_recorded` event
    names the package digest, the repository and the draft's URL, whether the harness made it or a
    person reported it, so the two read alike; a failed attempt is a `deposit_failed` event, not an
    exception. TODO(#647, #383).

## Boundaries and contracts

**The class.** `RequirementSet` is a core contract class ([Contract](contract.md)) so that the
harness, a drafter and `advisor.repository` read one description without knowing one another. Each
field names a property of the standard's schema, optionally qualified, the schema.org term it maps
to, and its obligation. Properties the repository fills itself, such as the identifier and the
publisher, are not listed. A value the guidance does not state is left out and marked with an
issue reference, never guessed; each set cites the pages its values came from, so a steward can
check them. What the guidance leaves open is also listed in the set's `unconfirmed`, one
statement per item naming its issue, so that a person depositing by hand sees it; the merged set
carries both sets' items. What ORDA's public pages leave open is TODO(#385).

**The metadata record follows DataCite.** The drafter writes a `Document` of kind
`metadata_record` in DataCite's JSON form, with `conforms_to` set to the merged set's. DataCite is
the schema ORDA's DOIs are registered in, and a DataCite record serves any repository that mints
DataCite DOIs. An override's form labels tell a person depositing by hand where each value goes, and its
`url`, carried in the merged set as `repository_url`, where to deposit; a standard's `url`
describes the standard and is not carried.
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
inventory, TODO(#651).

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
graph of each approved version, `provenance.jsonld` ([Disclosure](disclosure.md)). Both name
each prompt by its digest; the prompts themselves stay in the run store and are not packaged.
PROV-O alignment of the whole package is TODO(#26) (R10). The harness keeps the package by the SHA-256 of its bytes and records it in
the project log with a `package_built` event, which names the report, the merged set, each
document version and each run it holds.

### Depositing through an API

None of this section is built yet. Figshare, starting with ORDA, is TODO(#383); Zenodo is
TODO(#648); Dataverse is TODO(#852).

**A connector is an override's `deposit` block.** An override that the harness may deposit to
gives:

- `api`: the API kind, one of `figshare`, `zenodo` or `dataverse`;
- `base_url`: the installation's API root, such as `https://api.figshare.com/v2`, Zenodo's own
  or its sandbox, or one Dataverse installation's;
- `target`: where the item is created, in the kind's own terms: a Figshare group, a Zenodo
  community, a Dataverse collection's alias. Optional where the kind has a default.

The block holds no credential. A standard's set has no `deposit` block, so a repository without an
override is deposited to by hand. What varies between installations of one kind, such as a
Dataverse installation's required fields and controlled subjects, belongs in its override's fields
and in the kind's mapping, never in code for that installation, TODO(#854, #856). The keys are
added to `RequirementSet` with the first connector, and refused until then (invariant 2).

**Each API kind renders the approved DataCite record.** The kind's mapping turns the record into
the item metadata its API takes, through the same field table validation reads: one mapping for
Figshare items, one for Zenodo deposits, one for Dataverse's citation block. The DataCite record
stays the record of truth; a rendered item is derived from it on each deposit and never edited or
stored as a document. A value the API requires that DataCite cannot supply, such as Dataverse's
contact email or subject, is a field of the repository's requirements, so validation asks for it
before the package is built (TODO(#855)). A record value the mapping cannot place is reported on
the outcome, not dropped silently. What a mapping does with an unmapped field, and with a licence
the API does not list, is decided once for every kind, TODO(#648, #855).

**What is sent.** The rendered metadata, and the package's zip as one file of the draft, so the
documents, the inventory, the validation report and the audit trail travel with the deposit. No
data file is sent: the platform never holds the data, and the researcher uploads the files to the
draft in the repository's own interface. The package's `File` entities, each with its SHA-256,
let a later check show that the uploaded files are the ones described, TODO(#645). Dataverse
unpacks an uploaded zip unless told otherwise; how its connector keeps the package whole is
TODO(#854).

**The person's own credential.** A deposit uses the API token of the researcher who approves it,
for the repository the deposit goes to, so the item is theirs and the deployment holds no
repository-wide write access. The token is kept as a person's own model key is
([A person's own model account](model-accounts.md)): the person gives it to a service outside the
app and the harness, through a form that service serves. That service makes the repository's API
calls itself, as the broker makes model calls, on a short-lived grant the harness mints for one
approved deposit; the harness never sees the token. Whether the service is the model broker or a
sibling of it, and the grant's format, are decided with the first connector, TODO(#383). A person who has given no
token for the repository is told so and deposits by hand; nothing falls back to a deployment's
token. No agent ever holds a token (Blueprint P4).

**Approval is a decision, not a run.** Depositing is the harness's action, not an agent's, and the
profile's `deposit` action class applies to it. A person approves a deposit as they approve a
document version ([Projects](projects.md)): the app passes their request, and the harness checks
that they may deposit in the project, that the package is the project's latest built from a valid
report, and that its project has not changed since in a way that makes the package stale
(TODO(#649)). It appends a `deposit_approved` event naming the principal, the package digest, the
repository's re3data identifier and the connector's `api`, `base_url` and `target` as configured
at that moment, and then deposits. Whether a profile may require a second person, such as a data
steward, to approve a deposit is TODO(#372, #154).

**The outcome is one event, manual or automatic.** A deposit that creates a draft appends a
`deposit_recorded` event naming the approval it acted on, the package digest, the repository, the
draft's URL in the repository and its identifier there, a reserved DOI only if the repository
reports one unasked, and `method: api`. A person who deposited by hand records the same event with
`method: manual` and the URL and DOI they give ([Projects](projects.md), TODO(#647)). A call that
fails, or a draft the repository refuses, appends a `deposit_failed` event with the API's status
and a reason code, never the request's headers; trying again needs a new approval. A second approval of a package already recorded as deposited to the same repository is
refused, and names the earlier draft.

**Publishing stays with the researcher.** A draft can be changed or deleted; a published item and
its DOI cannot, and some institutions pay for each DOI. So the harness stops at the draft, and the
researcher publishes in the repository's own interface. Publishing through the API, with its own
approval and the fees it may incur, is TODO(#322).

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
- **One deposit mechanism, a mapping per API kind.** Many repositories run on one of a few
  platforms: these three cover ORDA, Zenodo and every Dataverse installation. A repository of a known kind then costs a steward an override, as a repository's
  requirements do.
- **The person's own token**, because the item is the researcher's, the repository's own rules
  about who may deposit where then apply unchanged, and no one token opens every researcher's
  items.
- **A draft, not a published item**, because a draft can be corrected or deleted, the data files
  still have to be added by someone who holds them, and publishing mints an identifier that cannot
  be withdrawn.

## Rejected alternatives

- **A profile for every repository the researcher may choose.** It would cover a handful, and the
  rest could not be chosen.
- **Requirements drafted by an agent from a repository's web pages.** A misread page would become
  the definition of valid; approving each draft would make every new repository wait for a steward.
- **Choosing only among repositories with an override.** The deployment's configuration, not the
  data, would limit the choice.
- **A record in Figshare's item format.** It serves only Figshare, and ORDA's DataCite record would
  still be derived from it. Depositing renders a Figshare item from the DataCite record instead,
  and never keeps it as a document.
- **A connector for each repository.** Each would be code to review and keep working, and every
  Dataverse installation would need its own. A connector per API kind, configured per repository,
  costs one implementation per platform.
- **A deployment's service token.** The tool would hold write access to every item the account
  can reach, items would belong to the service account rather than the researcher, and one leaked
  token would expose every researcher's drafts.
- **Publishing through the API.** It would mint a persistent identifier that cannot be undone,
  before the data files are on the item, and may cost the institution money (TODO(#322)).
- **Uploading the data files from the platform.** The platform never holds them
  ([Projects](projects.md)). Uploading from where the data live, as `dd-inventory` describes them
  there, may follow; it is not part of this design.
- **An agent that deposits.** It would need the write credential, and the policy gate cannot stop
  an agent's service doing what it did not declare (Blueprint P4).
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
