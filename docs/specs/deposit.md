# Deposit

## Intent and scope

The minimum loop ends with a package that is validated and ready to deposit in a repository the
researcher chose. This spec covers how a repository's requirements are described, how a choice of
repository resolves to them, what "validated" means, and what the deposit package is. The project
that holds the inventory, the documents and the decisions is in [Projects](projects.md).

A researcher may choose any repository listed in re3data, or, for one re3data does not list, any
data repository DataCite registers, usually from `advisor.repository`'s shortlist, with no
configuration written for it first. Many an institution's own repository is in DataCite and not in
re3data (#1342). A repository is identified by the registry that lists it: by its re3data
identifier (`r3d` and nine digits) where re3data lists it, else by its DataCite repository
identifier (such as `bl.durham`), which always holds a dot, so the two never collide and nobody
invents one (`REPOSITORY_ID_PATTERN`, `dd_sdk.contract.base`). A deployment may name its own
institution's repositories in its profile (`institution_repositories`, [Policy and
identity](policy-and-identity.md)), by those identifiers, and vouch for what no registry holds. Almost no repository publishes its deposit
requirements in a form a machine can read, but re3data records the metadata standards each one
uses, and most general-purpose repositories register DataCite DOIs. Requirements are therefore
described per metadata standard, with optional overrides for the few repositories a deployment
knows well, usually its own institution's. The sets and how they are written are described in
[`app/config/repositories/README.md`](../../app/config/repositories/README.md).

Deposit-ready means that a person can upload the package. The harness may also deposit it for
them: after the researcher approves it, it creates a **draft** item in the chosen repository through
the repository's API, with the person's own credential, and records where it went. The researcher
then adds the data files and publishes the item in the repository's own interface. How this works,
for Figshare, Zenodo and Dataverse alike, is in *Depositing through an API* below. Zenodo is
built (#648), to the Zenodo sandbox; Figshare is TODO(#383) and Dataverse TODO(#852).

One project can be rendered into any number of packages, and how a package reaches a repository
is a separate choice. A **packager** renders a project and its merged requirement set into the
bytes of a package in one format. A **transport** moves a package, or a record rendered for one
platform, into a repository: a platform's API connector, SWORD v2, or a person uploading by hand.
Packagers and transports are pluggable and configured apart, as *Packagers and transports* below
describes. The RO-Crate zip is the default package and the record of truth that every other format
wraps, travels with or names. SWORD v2 is a protocol, not a format: it carries a package in a
packaging such as BagIt, so it is a transport and the bag is a packager's output. The RO-Crate
packager, the manual transport and the `zenodo` transport are built, with the transport registry
(`dd_sdk.transports`); a registry of packagers is TODO(#870).

Out of scope: publishing an item through an API, and minting or reserving a persistent identifier
(R7, TODO(#322)); uploading data files, which the platform never holds ([Projects](projects.md));
and a copy-ready sheet of a repository's form fields, TODO(#644).

What is built:

- the `RequirementSet` class, loading and checking the sets, resolving a choice and recording it
  in the project (`dd_harness.requirements`, `dd-harness project choose-repository`). A choice
  names only the repository's identifier: its name and the metadata standards it declares are
  read from the pinned re3data export, or, for a DataCite identifier, from the pinned DataCite
  snapshot, which declares DataCite's standard since each repository in it registers DataCite
  DOIs. The harness reads both through `sources.yaml` (`DD_SOURCES_CONFIG`, `dd_harness.sources`)
  and never from the agent's directory ([System](system.md)). An identifier neither holds is
  refused;
- the DataCite and ORDA sets;
- validation and the package (`dd_harness.deposit`, `dd-harness project validate` and
  `dd-harness project package`);
- the pause before packaging, *The pause before packaging* below: what a person must decide and
  confirm before a package is built (`dd_harness.deposit_review`; `dd-harness project review`,
  `decide-item` and `confirm-checks`; in the app, `GET /api/projects/{id}/review` and
  `PUT /api/projects/{id}/review/items/{item_id}` and `.../review/confirmation`, drawn in the
  Deposit panel under *Decide before packaging*);
- validating and building the package in the app, which calls `dd_harness.deposit` in process
  and draws its results ([The app](app.md)): `POST /api/projects/{id}/validation` checks the
  project and keeps the report; `POST /api/projects/{id}/package` builds the package, or answers
  `409` with the validation that stopped it; `GET /api/projects/{id}/packages/{digest}` downloads
  a package the project log records as built (`app/tests/test_deposit_package.py`);
- what to do after downloading the package: the Deposit panel lists the manual steps for the
  chosen repository, naming its form's fields by their `form_label`, linking to its
  `repository_url` and listing its `unconfirmed` items, all read from the merged set, which also
  carries every set's `guidance` (the standard's first) for the Repository tab to cite; the user
  guide's *Depositing your data* covers the same steps;
- depositing a draft to Zenodo through its API, *Depositing through an API* below: the override's
  `deposit` block (`RequirementSet.deposit`, `Requirements.connector`), the `dd.transports`
  registry and the Zenodo item's mapping (`dd_harness.transports.zenodo`), the profile's
  `deposit_transports`, the deposit grant (`dd_sdk.deposit_grant`, `dd_harness.deposit_grants`),
  approval and outcome (`dd_harness.deposit_api`; `deposit_approved`, `deposit_recorded` and
  `deposit_failed`), the deposit broker that holds each person's token
  (`deposit-broker/`, [The deposit broker](../guide/operations/deposit-broker.md)), and in the app
  `GET` and `POST /api/projects/{id}/deposits`, `POST /api/repository-account/ticket`, the Deposit
  panel's *Deposit a draft* and the Settings page's *Repository accounts*
  (`harness/tests/test_deposit_api.py`, `deposit-broker/tests/`, `app/tests/test_deposit_draft.py`).

A researcher chooses a repository in the app, either from an advisor's shortlist or on the
project's page from the deployment's suggestions (its profile's own repositories first) or a
search of the pinned re3data export and DataCite snapshot (`GET /api/repositories`, `PUT /api/projects/{id}/repository`, [App](app.md)). Giving a drafter the merged set is
TODO(#394, #200).

## Invariants

1. **Requirements live in sets, never in code.** A requirement set is deployment configuration a
   steward can read and propose changes to, as an institutional profile is
   ([Policy and identity](policy-and-identity.md)). A new override is a new file, not new code.
2. **A set is either a standard's set or a repository override, and says only what its kind may.**
   A standard's set names its standard's re3data names; an override names one repository, by its
   re3data identifier in `re3data_id` or, for one re3data does not list, by its DataCite one in
   `repository_id`, never both,
   and the standard it builds on, and alone may give media types, size limits, licences and deposit
   form labels. A key outside the class, a set of neither kind, or two sets that collide stops the
   harness before anything is recorded (`harness/tests/test_requirements.py`).
3. **A DataCite set always exists**, since it is the fallback for a repository that declares no
   known standard (`dd_harness.requirements`, checked on load).
4. **An override adds or raises, never lowers.** It may add a field, or raise one from
   `recommended` to `required` and label it; lowering one is refused on load. Documents are the
   union of both sets, and a kind either requires is required. Media types, sizes and licences
   come from the override alone (`harness/tests/test_requirements.py`). Two fields of a set, or of
   an override merged on its standard, never share a term, compared as its full IRI, since a
   record's values are checked under their field's term and one field's value would pass for the
   other's; such sets are refused on load.
5. **A choice resolves deterministically, and says why.** The override is the one for the
   repository's identifier. The standard is, in order (`dd_harness.standard_choice`):
   - the one the override names, because a steward who wrote the override knows the repository
     better than its registry record (re3data lists only Dublin Core for ORDA, which registers
     DataCite DOIs): reason `override`. A person's choice of another standard is refused, since
     the override's fields, labels and licences are written for its own;
   - the one a person on the project chose (`PUT /api/projects/{id}/repository/standard`), which
     is recorded as a new choice of the repository, so the last choice still counts and choosing
     the repository again goes back to this rule: reason `chosen`;
   - the one standard the repository declares that the deployment has a set for: `declared`;
   - of several it declares, the first in the deployment's order of preference,
     `standard_preference.yaml` beside the sets, which names every standard's set once (DataCite's
     first, then the others by identifier, without it), with a warning naming the others:
     `declared_several`;
   - else DataCite's, with a warning that it was assumed: `fallback`.

   A repository without an override gets a warning that its own form, formats, sizes and
   licences are not checked. The Repository tab shows the standard and its reason, marks a
   fallback as assumed, and offers a person on the project the deployment's other standards
   unless an override names it (`harness/tests/test_standard_choice.py`,
   `harness/tests/test_requirements.py`, `app/tests/test_repositories.py`,
   `app/tests/test_standard_route.py`). One project has one chosen repository at a time; drafting
   the approved record converted to another standard is a package derived from it, kept and
   downloaded but not deposited ([Metadata standards](metadata-standards.md), *Converting a
   record*).
6. **A choice records exactly what it resolved to.** The project log names the repository by its
   `repository_id`, and its `re3data_id` where it has one (a choice recorded before there was a
   `repository_id` gives it from its `re3data_id`, as does a merged set kept then), and the
   registry record the repository's name and declared standards were read from, by its
   `snapshot_ref` (the latest `re3data:export:YYYY-MM` or `datacite:repositories:YYYY-MM-DD`
   pinned) and its content hash under `dd-json-document-v1`, the hash
   evidence citing that record carries ([Grounding](grounding.md)). It names each set used by
   `<requirement_set_id>@v<version>` and the SHA-256 of its file, keeps the merged set by its
   digest, and records the warnings. It names the standard's definition, its set's title and the
   reason the choice resolved to it; for a person's choice, the event's actor is who chose it, and
   its time when. The last choice counts (`harness/tests/test_projects.py`).
   A set's version is raised on every change; nothing checks this.
7. **The drafter and validation read the same merged set**, the one recorded for the choice.
   Validation reads it (`dd_harness.deposit`); giving it to the drafter is TODO(#394).
8. **Validity is the harness's, never an agent's.** The harness checks the project against the
   recorded merged set and writes one SHACL Validation Report. A failed `required` check is an
   `sh:Violation`, a failed `recommended` one an `sh:Warning`. The package is valid when the report
   has no violation; warnings, including those from resolving the choice, and information
   (`sh:Info`) are shown and do not block. `advisor.quality` stays advisory. Every validation,
   valid or not, is kept by its digest in the project log
   (`test_a_missing_required_field_is_a_violation_and_a_recommended_one_a_warning`,
   `test_each_missing_required_field_names_itself_and_the_page_it_is_supplied_on`,
   `test_what_the_repository_fills_in_is_information_and_never_blocks`,
   `test_the_validation_report_is_a_shacl_validation_report`).
9. **A package, in any format, is built only from a valid report, and holds no data file.** A
   violation stops the package and names each reason; the report is still kept
   (`test_a_project_without_a_required_document_is_refused_and_says_why`,
   `test_a_valid_project_writes_a_package_with_its_audit_trail`). Every packager runs behind the
   same check, TODO(#870).
10. **The default RO-Crate package passes the RO-Crate validator** at its REQUIRED level, against
    the RO-Crate version `rocrate` writes (`test_the_package_passes_the_ro_crate_validator`).
    Every other format states what it conforms to (*Packagers and transports*).

Invariants 20 to 22 hold for the pause before packaging
(`harness/tests/test_deposit_review.py`, `app/tests/test_deposit_package.py`).

20. **No package while something waits on a person.** A project is ready to package when its
    report has no violation and nothing waits on a person: every item the deposit check lists has
    a decision that stands, and the checks before deposit are confirmed for the inventory the
    project holds. Each open item, and a missing confirmation, is a `sh:Warning` of the report, so
    the report keeps SHACL's meaning of conforming, and `build_package` refuses the package until
    they are cleared. The pause is cleared by a person's decision, never by a violation that no
    decision can lift.
21. **A decision is a person's, never an agent's.** A decision on an item and the confirmation
    are recorded only through a way in that names the person signed in (the app's routes, or the
    command for the operator's principal), as `deposit_item_decided` and
    `deposit_checks_confirmed` events naming who and when. Nothing a run returns decides or
    confirms anything, and the conductor has no path to either.
22. **The decisions and the confirmation travel with the package.** The package's project log
    holds their events, its root `ro-crate-metadata.json` holds an `AssessAction` for each
    decision that stands and one for the confirmation, each naming the person and the time, and
    `package_built` names the items decided (`decided_items`).

Invariants 11 to 15 hold for depositing through an API. They are built and tested for Zenodo
(`harness/tests/test_deposit_api.py`, `deposit-broker/tests/`); each names the issue that builds
them for the other transports.

11. **A connector is configuration, never code for one repository.** A repository is reachable
    through a transport when its override names the transport, the format it carries, a base URL
    and a target. Each transport has one implementation, shared by every repository that uses it;
    adding a repository of a known transport is a new override, not new code (invariant 1).
    TODO(#383, #857, #872).
12. **No deposit without a person's recorded approval.** The harness deposits only on a
    `deposit_approved` event that a person made, naming the package by its digest and the
    repository it goes to, and only a package the log records as built from a valid report
    (invariant 9). No agent deposits, and no agent's output starts one.
13. **The credential reaches no record.** A person's repository token appears in no project log
    event, run, trace, prompt, Process Run Crate, package, error message or app response, and the
    app and the harness never hold it at rest.
14. **A deposit creates a draft and never publishes.** Nothing the harness sends publishes an item,
    mints a persistent identifier or makes a file public.
15. **Every deposit ends in one outcome event, manual or automatic.** A `deposit_recorded` event
    names the package digest, the repository and the draft's URL, whether the harness made it or a
    person reported it, so the two read alike; a failed attempt is a `deposit_failed` event, not an
    exception. A person reporting a manual deposit is TODO(#647).

Invariants 16 to 19 hold for packagers and transports. The RO-Crate packager, the manual transport
and the `zenodo` transport with its item exist; each invariant names the issue that will build and
test the rest.

16. **The RO-Crate package is the record of truth.** Every other format is built from the same
    valid report and either holds the RO-Crate package, travels with it, or names it by its digest.
    The validation report, the project log, the audit trail and the disclosure are therefore the
    same whatever the format, and no format carries its own copy of them in another form.
    TODO(#870).
17. **A packager or a transport is registered, never edited into the harness.** Each is found by
    its identifier under an entry-point group, and a deployment's configuration says which it
    offers. An identifier unknown or not offered is refused before anything is built, sent or
    recorded. An identifier names one format or one protocol for good. TODO(#870, #872).
18. **Only meaningful pairs are configured.** A repository's override names a transport and the
    format it carries, from the pairs *Packagers and transports* lists; any other pair stops the
    harness on load, as a malformed set does (invariant 2). TODO(#870, #872).
19. **Every package and every deposit names its format and transport.** `package_built` names the
    format and the digest; `deposit_approved`, `deposit_recorded` and `deposit_failed` name the
    package's format and digest and the transport, so any package or deposit reads alike in the
    log. TODO(#870, #647).

## Boundaries and contracts

**The class.** `RequirementSet` is a core contract class ([Contract](contract.md)) so that the
harness, a drafter and `advisor.repository` read one description without knowing one another. Each
field names a property of the standard's schema, optionally qualified, the `term` it maps to, its
obligation and, in `supplied_on`, the page of the project where a researcher supplies its
value: `documents` (the metadata record's questions, the default), `researchers`, `facts` or
`repository`. Properties the repository fills itself, such as the identifier, the publisher and the
publication year, are not fields; those the schema makes mandatory and the researcher might look
for are listed in `filled_by_repository` (DataCite's set lists the publisher and the publication
year), and a merged set carries both sets' entries. A value the guidance does not state is left out and marked with an
issue reference, never guessed; each set cites the pages its values came from, so a steward can
check them. What the guidance leaves open is also listed in the set's `unconfirmed`, one
statement per item naming its issue, so that a person depositing by hand sees it; the merged set
carries both sets' items. What ORDA's public pages leave open is TODO(#385).

**The metadata record follows the merged set's standard.** The drafter writes a `Document` of kind
`metadata_record` in the standard the merged set's `conforms_to` names, in a serialisation that
standard defines, with `media_type` set to it ([Metadata standards](metadata-standards.md)). DataCite
in its JSON form and Dublin Core as OAI-DC XML are built, and DataCite is the default: it is the schema ORDA's DOIs are
registered in, and a DataCite record serves any repository that mints DataCite DOIs. An override's
form labels tell a person depositing by hand where each value goes, and its `url`, carried in the
merged set as `repository_url`, where to deposit; a standard's `url` describes the standard and is
not carried. A set for another standard, such as ISO 19115 or DDI, needs a set and a definition of
the standard, not a drafter of its own, TODO(#1361, #401).

**Validation** checks, against the merged set:

- every required document kind has an approved version, and, as warnings, every recommended one;
- as a warning, a data dictionary: when the set neither requires nor recommends one and the project
  has none approved, a project whose inventory lists a table, or has no inventory, is warned that
  one helps others reuse the data. It never blocks a package, even when the repository does not
  list it;
- the approved metadata record has every required field and, as warnings, every recommended one;
- the record's licence is one the set lists, when it lists any;
- every inventory entry has an accepted media type and is within the file size limit, and the
  inventory's files together within the item size, when they are stated. A limit on the number of
  files in an item is not in the class, TODO(#385);
- as warnings, each item a person must decide before packaging, and the confirmation of the
  checks before deposit when it is missing (*The pause before packaging*);
- as information (`sh:Info`), what the repository fills in itself, from `filled_by_repository`,
  naming the repository: "Zenodo fills in the publisher and publication year". Information never
  makes a project invalid or holds its package.

A project with no repository chosen, or no inventory, has a violation that says so.

**Each result says where to act.** A result about a field or a document names it in `dd:field` (the
repository's form label, else the property; or the document kind) and the project's page where a
person supplies it in `dd:supplied_on`, beside the `sh:` terms: a missing field names the page its
set's `supplied_on` gives, a missing document, the metadata record among them, names `documents`,
and a missing repository choice names `repository`. With no metadata record approved, its fields
are not checked, and the one violation for the record names `documents`. The app links each result
to that page.

The record is read as RDF, the same reading the package uses, through the pivot of
[Metadata standards](metadata-standards.md): the record is first refused unless a registered
standard's definition covers its `conforms_to` and `media_type`, and is then read with that
definition, which maps each of the standard's properties to a term. A field may leave out its
`term`, and is read under the one the definition gives its property and qualifier; a field that
names its term does so as a CURIE of a registered prefix (`schema:`, `dcterms:`, `dcat:` or
`prov:`), such as `dcterms:provenance` for a lineage, or as the full IRI, and a set whose field
names a term other than the definition's is refused on load. A set kept before terms were IRIs,
which names a schema.org local name in `schema_org`, is read as `schema:` with a warning. A
field's property, and its qualifier when it has one, select the record's entries, the definition
saying which key holds each entry's value; each entry's value becomes a value of the field's
term. SHACL shapes
are generated from the fields, one `sh:minCount 1` property shape per field, with the severity
its obligation gives and a message naming the field by its form label. pySHACL runs them. The
other checks write their results in the same `sh:` vocabulary, which is the fixed validation
format ([Contract](contract.md)), and the warnings from resolving the choice are carried as
warnings. The harness keeps the report by its digest in the project log, with a
`project_validated` event saying whether it conforms. Validity covers the data files only as far as the
inventory describes them: checking a table's contents against its Frictionless schema needs the
data, so it runs where the data live, in the inventory command, and its report travels with the
inventory, TODO(#651).

**The RO-Crate package**, the default format (`ro-crate`), is one zip file whose root
`ro-crate-metadata.json` describes the dataset. It
holds the approved metadata record, the other approved documents (each document's latest approved
version), the inventory, the merged set it was validated against, the validation report, the
project log, and the Process Run Crate of each run behind an approved version
([Contract](contract.md)). The root dataset's properties come from the approved metadata record
read through its standard's definition: each field's values under its term, and the pivot's name,
description, keywords, creation date, type and creators where the set has no field for them. Each approved document is under `documents/`, an
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
The whole provenance graph of the project is to replace the disclosure graph as `provenance.jsonld`,
with the root crate's actions named by the same IRIs ([Provenance](provenance.md), TODO(#803)). The harness keeps the package by the SHA-256 of its bytes and records it in
the project log with a `package_built` event, which names the report, the merged set, each
document version and each run it holds.

### The pause before packaging

C2 asks that the tool pause the sharing workflow where possible identifiers are flagged or
detected, alert the person and give guidance, and that it ask them to confirm that ethics
approvals are in place before any deposit proceeds. The deposit check does both, from what the
project already holds, and records what the person decides (`dd_harness.deposit_review`).

**What it reads.** The inventory the project holds now, and nothing an agent said. Each item is
one of:

- a **name-level hint** (`source: name`): a file whose folder, file or field names, size or digest
  call for a person to look, by the rule table in `dd_sdk.inventory_hints` that the File Archivist
  reads too: free text, coordinates, a folder of someone else's material, terms or an agreement,
  an operating-system file, a configuration or credentials file, an empty file, and a
  byte-for-byte copy
  ([Personal data](personal-data.md), "Name-level hints");
- a **personal-data finding** (`source: finding`): each entry of the inventory's
  `inventory_personal_data`, which `dd-inventory` writes ([Personal data](personal-data.md)).

The harness works the hints out itself from the stored inventory, rather than reading what
`advisor.files` or the ethics adviser returned: an adviser's run may not have happened, may be of
an older inventory, and would make the check depend on an agent, against invariant 8. The rule
table moved from the File Archivist into `dd_sdk` so that the adviser and the harness read one
copy; the app's inventory view keeps its own in TypeScript. When #471 decides whether hints
become findings of the `file name` and `field name` kinds, the check reads them from the
inventory and the table leaves the harness's path. The rights adviser's third-party question
and the ethics adviser's sensitivity flags are not read: both rest on what their caller declares.

**An item and its identity.** An item names its source, its kind (a hint's kind, or a finding's
`PersonalDataKind`), the file, the column where a finding names one, what called for it, and the
question to put to the person, in the harness's words. It is identified by its source, kind,
file, column and the file's SHA-256, so a decision stands for that file as it was described: a
new inventory in which the file changed lists it again, undecided.

**A decision.** The person chooses one of `keep` (checked: deposited as it is), `leave_out` (left
out of the deposit) or `change` (a changed copy, such as a redacted or generalised one, is
deposited instead), with an optional note of at most 2,000 characters. The decision is recorded
as a `deposit_item_decided` event carrying the item as the check described it, the decision, the
note and the inventory's digest; the latest decision on an item stands. Data Director changes no
file: leaving a file out, or depositing a changed copy, is done by the person at deposit, and the
package still describes the files the inventory lists. A decision on an item the check does not
list now is refused.

**The confirmation.** Once per inventory, the person confirms three statements together: that the
ethics approvals and participants' consent that apply are in place and allow the deposit, that data protection advice has
been taken for data about living people or there are none, and that third-party material may be
shared and every agreement the data come under is in force and allows it
(`dd_harness.deposit_review.CONFIRMATIONS`). It is recorded as a `deposit_checks_confirmed` event
carrying the statements' words and the inventory's digest, and stands until the inventory
changes. It is asked of every project, including one with nothing to decide.

**In the report.** Each open item is a `sh:Warning` whose source constraint component is
`dd:PersonDecisionConstraintComponent` and whose focus is the file; a missing confirmation is one
whose component is `dd:DepositConfirmationConstraintComponent` and whose focus is the project.
The report also carries `dd:ready_to_package` and `dd:not_checked`, what the review did not
check. The app draws the items, the decisions that stand and the confirmation from the review it
sends beside the validation, and leaves those warnings out of *Worth fixing* so that they are not
shown twice.

**Wording.** No item means that nothing was flagged in what was checked, never that the data are
safe ([Personal data](personal-data.md), invariant 10). `not_checked` always says that the files'
contents were not read, and says whether a personal-data detector ran: an inventory without
`inventory_personal_data`, such as one made before findings existed, says that none ran; an empty
list says what the detector did not look at. The panel says the project is ready to package only
when nothing waits on a person.

### Packagers and transports

**A packager** renders a project into a package in one format. Its input is the project, the
latest approved version of each of its documents, the merged requirement set recorded for the
repository choice, and the valid report that check produced (invariant 9). Its output is the
package's bytes, its media type, and the SHA-256 of the bytes, by which the harness keeps it. A
packager holds no data file and sees no credential. Packaging is the harness's action, not an
agent's; a packager is code the harness runs, and nothing an agent returns chooses one.

**A transport** moves something into a repository. It accepts a package (SWORD v2 carries a bag),
a record and the package it travels with (a platform API connector sends the rendered item and
the RO-Crate zip), or nothing at all: **a person uploading by hand is the `manual` transport**,
which sends nothing and records what the person reports. A transport is configured per
repository in the override's `deposit` block (*Depositing through an API*), and a repository whose
sets have no such block is reached only by the manual transport. Invariants 12 to 15 apply to
every transport that sends anything: a person's approval, their own credential, a draft and never
a published item, and one outcome event. A manual deposit ends in the same outcome event
(invariant 15).

**The RO-Crate package is the one every other format refers to** (invariant 16). Building a format
other than `ro-crate` builds, from the same report, the RO-Crate package first unless the log
already records one built from that report, and the new package's `package_built` event names it
as `derived_from`. What stays fixed across formats, and how each format carries it:

| Format | Media type | Conforms to | Carries the report, the log, the audit trail and the disclosure | Status |
|---|---|---|---|---|
| `ro-crate` | `application/zip` | RO-Crate, at its REQUIRED level (invariant 10) | holds them | built |
| `bagit` | `application/zip` | BagIt (RFC 8493), with the RO-Crate zip as its payload | holds the RO-Crate package | TODO(#871) |
| a platform's item (`figshare-item`, `zenodo-deposit`, `dataverse-dataset`) | `application/json` | the platform's API, as far as its mapping's tests show | travels with the RO-Crate package, sent as one file of the draft | `zenodo-deposit` built; others TODO(#383, #857) |
| `deposit-sheet` | decided with TODO(#644) | no machine format; it is read by a person | names the RO-Crate package and the report by digest; the person uploads the package with it | TODO(#644) |

A rendered platform item is a package like any other: derived from the approved metadata record,
never edited and never a document, and kept by its digest, so that an approval names exactly the
bytes that are sent.

**Meaningful pairs.** A repository's override names a transport and the format it carries; only
these pairs are accepted (invariant 18):

| Transport | Carries | Example | Status |
|---|---|---|---|
| `manual` | `ro-crate`, and `deposit-sheet` beside it | any repository, with or without an override | `ro-crate` built; sheet TODO(#644) |
| `sword2` | `bagit` | Dataverse, DSpace, EPrints, where they offer SWORD v2 | TODO(#869, #871, #872) |
| `figshare`, `zenodo`, `dataverse` | that platform's item, with `ro-crate` | ORDA, Zenodo, a Dataverse installation | `zenodo` built; others TODO(#383, #857) |

Which repositories offer SWORD v2, with which packagings, how each keeps a deposit in progress
rather than published, and how each authenticates, are for the spike to settle, TODO(#869). Until
then `sword2` carries only `bagit`, and whether it replaces the Dataverse connector is open.

**Registering a format or a transport.** A packager is registered under the entry-point group
`dd.packagers` and a transport under `dd.transports`, each by an identifier, as a built source is
under `dd.sources` ([Evidence and grounding](grounding.md)). A new format or protocol is a new
registration, possibly in its own distribution, not an edit to the harness; a new repository of a
known transport is still a new override, not code (invariants 1 and 11). An identifier names one
format or one protocol for good: a changed format is a new identifier, as a canonicalisation's
name keeps its bytes. A deployment's configuration lists the packagers and transports it offers;
by default only `ro-crate` and `manual`. A packager or transport registered but not offered is
refused like an unknown one, before anything is built, sent or recorded. Where that list lives,
and whether a person chooses among the offered formats in the Deposit panel, are TODO(#870).

**A package is identified by its format and its digest.** A changed project needs a new package of
every format it is deposited in, and each new package names the report it was built from; what
becomes of a package built before the project changed is TODO(#649).

### Depositing through an API

Zenodo is built (#648). Figshare, starting with ORDA, is TODO(#383); Dataverse is TODO(#852); SWORD v2, a transport shared by every repository that offers
it, is TODO(#872). A platform's API and SWORD v2 are both transports (*Packagers and
transports*); what follows holds for each.

**A connector is an override's `deposit` block.** An override that the harness may deposit to
gives:

- `transport`: the transport, one of `figshare`, `zenodo` or `dataverse` (each a platform's API),
  or `sword2` (*Packagers and transports*), each registered under `dd.transports`;
- `format`: the format the transport carries, from the pairs *Packagers and transports* lists;
- `base_url`: the installation's API root, such as `https://api.figshare.com/v2`, Zenodo's own
  or its sandbox, or one Dataverse installation's;
- `target`: where the item is created, in the kind's own terms: a Figshare group, a Zenodo
  community, a Dataverse collection's alias. Optional where the kind has a default;
- `sandbox`: whether `base_url` is the platform's test installation, whose items and identifiers
  are not real. The app says so beside the deposit.

The block holds no credential. A standard's set has no `deposit` block, so a repository without an
override is deposited to by hand. What varies between installations of one kind, such as a
Dataverse installation's required fields and controlled subjects, belongs in its override's fields
and in the kind's mapping, never in code for that installation, TODO(#854, #856). A pair the table
above does not allow, or a `deposit` block in a standard's set, stops start-up (invariant 2). The
deployment's Zenodo override deposits to the sandbox; moving to Zenodo itself is TODO(#648).

**Each API kind renders the approved metadata record.** The kind's mapping turns the record, read
as the pivot of its standard's definition ([Metadata standards](metadata-standards.md)), into the
item metadata its API takes: one mapping for Figshare items, one for Zenodo deposits, one for
Dataverse's citation block. The record stays the record of truth. The mapping is the platform item's packager: a rendered item is
derived from the record, never edited and never stored as a document, and is kept by its digest
as a package `derived_from` the RO-Crate package (*Packagers and transports*), so the approval
names exactly what is sent. A value the API requires that the record's standard cannot supply, such as
Dataverse's
contact email or subject, is a field of the repository's requirements, so validation asks for it
before the package is built (TODO(#855)). A record value the mapping cannot place, under a term or
under none, is reported on the outcome by its property's path in the record's standard, not
dropped silently. What a mapping does with an unmapped field, and with a licence
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
approved deposit; the harness never sees the token. The service is the **deposit broker**, a
sibling of the model broker with its own user, store, keys and audience
([The deposit broker](../guide/operations/deposit-broker.md)). The person connects their account
there by signing in at the repository (OAuth, asking only for the scope that creates drafts, which
for Zenodo is `deposit:write` and cannot publish) or by pasting a personal token, which the broker
checks first. The grant (`dd_sdk.deposit_grant`) is a JWT the harness signs with its model-grant
key, for the deposit broker's audience alone, naming the person by their sealed pseudonym, the
repository, the transport, the API root, the target, the digests of the package and the rendered
item, and the approval event; the broker accepts each once, within five minutes, and only with the
bytes whose digests it names. The broker calls only the API roots its operator allows, so a
practice deployment cannot reach a production repository by a change to an override alone. A
person who has given no
token for the repository is told so and deposits by hand; nothing falls back to a deployment's
token. No agent ever holds a token (Blueprint P4).

**Approval is a decision, not a run.** Depositing is the harness's action, not an agent's, and the
profile's `deposit` action class applies to it. A person approves a deposit as they approve a
document version ([Projects](projects.md)): the app passes their request, and the harness checks
that they may deposit in the project, that the package is the project's latest built from a valid
report, and that its project has not changed since in a way that makes the package stale
(TODO(#649)). It appends a `deposit_approved` event naming the principal, the package's format and
digest (and, for a platform item, the RO-Crate package it travels with), the repository's
identifier (`repository_id`; an approval recorded before there was one named `re3data_id`) and the connector's `transport`, `base_url` and `target` as configured at that
moment, and then deposits. A profile may also require a data steward's co-approval of the same
package digest, which never replaces the researcher's ([Data stewards](stewardship.md), invariant 7), TODO(#1306).

**The outcome is one event, manual or automatic.** A deposit that creates a draft appends a
`deposit_recorded` event naming the approval it acted on, the package's format and digest, the
repository, the draft's URL in the repository and its identifier there, a reserved DOI only if
the repository reports one unasked, and the `transport`. A person who deposited by hand records
the same event with `transport: manual`, the package they uploaded, and the URL and DOI they
give ([Projects](projects.md), TODO(#647)). A call that fails, or a draft the repository
refuses, appends a `deposit_failed` event naming the package's format and digest and the
`transport`, with the repository's status and a reason code, never the request's headers; trying
again needs a new approval. A second approval of a package already recorded as deposited to the
same repository is refused, and names the earlier draft.

**Publishing stays with the researcher.** A draft can be changed or deleted; a published item and
its DOI cannot, and some institutions pay for each DOI. So the harness stops at the draft, and the
researcher publishes in the repository's own interface. Publishing through the API, with its own
approval and the fees it may incur, is TODO(#322).

**Elsewhere.** A deployment's own institution's repositories are its profile's
`institution_repositories` (#1342); which other repositories an institution approves, and
preferring them, are TODO(#320). A repository that mints no DataCite DOIs and that re3data does
not list cannot be chosen; OpenDOAR could list many such, once its licence is confirmed to allow a
pinned copy.
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
- **Packagers and transports apart**, because the same package reaches different repositories by
  different routes, and one route carries different packagings: SWORD v2 is a protocol that carries
  a BagIt bag, a ZIP or METS, not a format of its own. Choosing them apart lets a new format serve
  every transport that can carry it, and a new transport carry every format it accepts, with one
  implementation each.
- **RO-Crate as the record of truth**, because it is self-describing, it already holds the
  validation report, the log, the audit trail and the disclosure, and it passes a validator. A
  format that wraps, travels with or names it keeps one audit trail per build, whatever a
  repository takes.
- **Registered by entry point, offered by configuration**, because a format is code to review once
  and a deployment, not the harness, knows which repositories its researchers use. It is the
  pattern built sources already follow.
- **The person's own token**, because the item is the researcher's, the repository's own rules
  about who may deposit where then apply unchanged, and no one token opens every researcher's
  items.
- **A pause cleared by a decision**, because C2 asks the tool to pause and refer, not to decide:
  a violation would stop a project whose researcher has looked and decided, and a warning alone
  would let the package be built with nothing decided. A decision recorded with who and when is
  what a reviewer of the package needs to see.
- **Signals from the inventory, not from advisers' runs**, because validity is the harness's
  (invariant 8), and the inventory the project holds now is what is packaged.
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
- **A record in one repository's format as the canonical form**, such as a Figshare item. It
  serves only that platform, and ORDA's DataCite record would still be derived from it. A
  platform's item is rendered from the DataCite record instead, kept as a package, and never kept
  as a document.
- **SWORD v2 as the only output.** It is a protocol, not a format, and Figshare and Zenodo are not
  known to offer it (TODO(#869)); a person depositing by hand needs a package, not a protocol.
- **RO-Crate as the only output.** A repository that takes a BagIt bag over SWORD v2, or an item
  through its API, could not be reached, and a person filling in a form would have no sheet.
- **One packager per repository.** Formats are few and repositories many: each repository would be
  code, against invariant 1, and two repositories taking the same format would have two
  implementations of it.
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
- **Reading the latest `preparation.files` and `governance.*` outcomes by process-flow step.**
  The check would depend on whether, and on which inventory, an adviser ran, and an agent's
  output would decide what a person is asked.
- **A third copy of the hint rules in the harness.** Two Python copies would drift; the table is
  in `dd_sdk` instead.
- **Open items as violations.** A violation is lifted only by changing the project, so a file the
  researcher has checked and kept would stop the package for good.
- **A decision per file rather than per item.** A file can be marked for two reasons, such as
  free text that is also a copy, and each calls for its own answer.
- **Leaving out or redacting a file for the researcher.** Data Director flags and never fixes
  ([Personal data](personal-data.md), invariant 4), and it does not hold the files.
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
