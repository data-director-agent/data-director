# Provenance

## Intent and scope

A project's provenance is the whole history of how its outputs came about: what each person
did, what each agent did and for whom, and which models were called. The Blueprint asks for it in
R10 (record all actions taken by AI agents on data and metadata, so that they can be verified,
validated and audited, with PROV-O as the candidate standard), C13 (actions attributable and
under human oversight) and C14 (explanations kept alongside metadata records).

The record already exists in three parts: the project log ([Projects](projects.md)), the run
store with a Process Run Crate per run ([Contract](contract.md#boundaries-and-contracts),
[Storage](storage.md)), and the disclosure of each approved document
([Disclosure](disclosure.md)). This spec says what the whole history is, and how it is read from
those parts as one PROV-O graph per project: the **provenance graph**. The app shows it and the
deposit package carries it (#797).

**What "all actions" means.** The provenance graph of a project records, from its creation to
its deposit:

- every event in the project's log, of every type, including a person's decisions, edits and
  answers, a refused change, the project's validation and each package build;
- every run in the project's conversations, and within each run:
  - each delegation to another agent, as the child run it started;
  - each model call;
  - each retrieval, as the evidence it produced;
  - each tool call (an `execute_tool` span);
  - the policy gate's decision when it refused or referred the run;
  - the harness's checks: the grounding linter, the source check and the payload shape check;
- each conversation turn: the message a person sent and the reply the run returned;
- each deposit, once one is recorded (TODO(#647)).

Out of scope:

- security events (sign-in, refused access, grants and enrolments), which are a separate audit
  stream with other readers and other retention ([Security baseline](security.md), invariant 5);
- runs outside any project, which have their envelope and crate but no project to belong to;
- what an agent did and did not report. An agent is trusted to report its own model calls and
  spans ([Disclosure](disclosure.md#boundaries-and-contracts)). The harness makes an omission
  detectable where it can (invariant 3), not impossible.

What is built: the Process Run Crate of each run (`dd_harness.provenance`), and the project
graph (`dd_harness.provenance_graph.project_graph`): every event of the log, every run of the
project with its agent's delegation, model calls, child runs, retrievals, tool calls and the
policy gate's refusals and referrals, checked against SHACL shapes. The disclosure graph of each
approved version is read from it (`dd_harness.disclosure`). The checks' activities and
conversation turns, the app's view and the package's copy are not built yet; each part says which
issue builds it.

## Invariants

1. **The graph is read from the record and changes nothing.** It is built from the project log
   and the run store on request, is never stored as a record of its own, and writes neither
   source. Built twice from the same record, it gives the same bytes.
2. **Every event type has a mapping.** Each event type the project log can write has a row in
   the mapping table below and a mapping in the code. A test compares the log's event types with
   the mappings in both directions, so an event type added without a mapping (such as membership,
   steward actions, deposit, refused turns, or deleting and restoring a project) fails until it
   has one. Every type is listed once, in `dd_harness.projects.EVENT_TYPES`, and the log refuses
   to write a type that is not.
3. **Nothing recorded is missing from the graph.** Every event in the log appears by its
   identifier. Every run of the project appears, and so does each of its model calls,
   delegations, retrievals, tool calls and policy decisions. A run that fails still reports the
   model calls it made, and the grounding linter reports a `chat` span with no matching model
   call, both TODO(#800).
4. **People and agents are different kinds.** A principal of kind `person` is a `prov:Person`.
   One of kind `accountable_role` is a `prov:Agent` typed `dd:AccountableRole`, never a
   `prov:Person`. An agent, and the harness itself, is a `prov:SoftwareAgent`. A software agent
   acts for a principal only through a qualified `prov:Delegation` whose `prov:hadActivity` is the
   run, so the graph says for whom it acted in that run and in no other.
5. **Content is named, not carried.** Prompts, conversation messages, a person's answers to a
   draft's questions and to the intake, file contents, inventories, documentation text, ORCID
   records, validation reports and packages are entities named by an RFC 6920 `ni:` URI of their
   SHA-256 digest. Their text is not in the graph. A document version carries its digest and not
   its text. Titles a person gave (the project's, a document's) and documentation file names are
   carried, as the package already publishes them.
6. **About a person, the graph holds only what identifies them.** It holds a principal's
   identifier, display name, kind, assurance and the issuer that vouched for them, and nothing
   else: no email address and no part of an ORCID record (see
   [Personal data](#personal-data)).
7. **One thing, one IRI.** The provenance graph, the disclosure graph, each Process Run Crate and
   the package's root crate name the same run, agent, model, prompt, person and version by the
   same IRI. Today the crates use local identifiers (`#run-…`, `#model-…`, `#prompt-…`) for some
   of these, TODO(#800, #803).
8. **Refusals and rejections are recorded, not only authorisations.** A refused change, a run the
   policy gate refused or referred, and a version a person rejected are activities in the graph,
   as the Blueprint's consultation log asks (#26).
9. **The graph validates.** It is read as RDF and checked against committed SHACL shapes (see
   [Completeness and validation](#completeness-and-validation)).
10. **The disclosure graph is part of the provenance graph.** It is the part reachable from each
    document's latest approved version, with the same IRIs, so the two cannot disagree.

## Boundaries and contracts

### Identifiers

| What | IRI |
|---|---|
| Project | `urn:uuid:{project_id}` |
| Conversation | `urn:uuid:{conversation_id}` |
| Document | `urn:uuid:{document_id}` |
| Document version | `urn:uuid:{document_id}#v{version}` |
| Log event | `urn:uuid:{event_id}` |
| Run | `urn:uuid:{invocation_id}` |
| Part of a run | the run's IRI with a fragment: `#model-call-{n}`, `#retrieval-{n}`, `#tool-{n}`, `#policy-gate`, `#grounding`, `#source-check`, `#shape-check` |
| Content named by digest | `ni:///sha-256;{digest}`, the digest in unpadded base64url, as a prompt is named today (`dd_harness.disclosure.ni`) |
| Person or accountable role | the principal's identifier, an absolute IRI: an ORCID iD URL, a `mailto:` IRI or a URN ([Policy and identity](policy-and-identity.md)) |
| Agent | `https://w3id.org/data-director/agents/{agent_id}` |
| Model | `https://w3id.org/data-director/models/{provider}/{model_id}` |
| The harness | `https://w3id.org/data-director/harness` |
| Terms the graph mints | under `dd:` = `https://w3id.org/data-director/` |

Every identifier the record already holds (project, conversation, document, event, invocation)
is a UUID, unique across deployments without a resolver, so it becomes an IRI as a `urn:uuid:`.
A `ni:` URI names content without carrying it, so anyone who holds the content can show it is the
content named. The w3id namespace, under which agents, models, the harness and the `dd:` terms
are named, is not yet registered, TODO(#3).

A node the graph makes to qualify a relation, or to name what an event made that has no
identifier of its own, takes the IRI of what it belongs to with a fragment, so the graph has no
blank nodes and serialises to the same bytes however it was built:

| What | IRI |
|---|---|
| The delegation through which an agent, or the harness, acted for a principal in one activity | the activity's IRI with `#delegation` |
| A model call's association with its model and prompt | the call's IRI with `-association` |
| A run's Process Run Crate | the run's IRI with `#process-run-crate` |
| Evidence with no SHA-256 content hash | the run's IRI with `#evidence-{n}` |
| A fact proposed or decided | the event's IRI with `#fact` |
| An escalation | its opening event's IRI with `#escalation` |
| A deposit recorded | the event's IRI with `#deposit` |

The `dd:` terms are few: a class for each event type (named in the table below),
`dd:Invocation` and `dd:AccountableRole`, and the properties `dd:causedBy`, `dd:titleSource`,
`dd:outcome`, `dd:reasonCode`, `dd:referredTo`, `dd:problem`, `dd:decision`, `dd:refusal`,
`dd:conforms`, `dd:modelAccount`, `dd:derivation`, `dd:parentInvocation`, `dd:principalKind`,
`dd:assurance`, `dd:vouchedBy`, `dd:member`, `dd:role`, `dd:entry`, `dd:entrySource`, `dd:step`,
`dd:mark`, `dd:question`, `dd:factKind`, `dd:factSubject`, `dd:sourceId`, `dd:toolServer`,
`dd:repository`, `dd:transport`, `dd:sandbox`, `dd:status`, `dd:team`, `dd:origin`,
`dd:scopeShared`, `dd:actingAs` and `dd:note`. A PROV-O or schema.org term is used wherever one
fits.

### The mapping

**A person's event.** An event whose `caused_by` is a command a person ran or a request to the
app is a `prov:Activity` with the event's IRI and the event's `dd:` class. It
`prov:wasAssociatedWith` the principal it `acted_for`, its `prov:startedAtTime` and
`prov:endedAtTime` are the event's `at`, and `dd:causedBy` gives the command or request as a
literal. Where the harness carried out the action (a validation, a package build), the harness
is associated too, and acts for the principal through a qualified delegation (invariant 4).

**A run's event.** An event whose `caused_by` is an `invocation_id` records what a run did:

- where it records an entity the run produced, such as a drafted version, the run is the activity
  that generated it, and the event's IRI names that generation (`prov:qualifiedGeneration`, a
  `prov:Generation` with `prov:atTime`). PROV gives an entity one generation, and the disclosure
  already says a drafted version `prov:wasGeneratedBy` its run;
- otherwise, such as an entry point a model chose, the event is a `prov:Activity` that
  `prov:wasInformedBy` the run and `prov:wasAssociatedWith` the run's agent.

**Project log events.** Each row adds to the rule above. "Generates" means the entity
`prov:wasGeneratedBy` the activity and `prov:wasAttributedTo` the principal; "uses" means the
activity `prov:used` the entity.

| Event | Class | Adds |
|---|---|---|
| `project_created` | `dd:ProjectCreation` | Generates the project, a `prov:Entity`, with `schema:name` its title if given. |
| `project_renamed` | `dd:ProjectRenaming` | Uses the project; `schema:name` the title, `dd:titleSource` researcher or model. |
| `conversation_started` | `dd:ConversationStart` | Generates the conversation, `schema:isPartOf` the project. |
| `inventory_added` | `dd:InventoryAddition` | Generates the inventory, named by its digest, which `prov:wasRevisionOf` the inventory it replaces. |
| `documentation_added` | `dd:DocumentationAddition` | Generates the documentation, named by its digest, with `schema:name` and `schema:encodingFormat`. |
| `researcher_added` | `dd:ResearcherFactsAddition` | Generates the researcher facts, named by the digest of the record kept. |
| `researcher_withdrawn` | `dd:ResearcherFactsWithdrawal` | The facts `prov:wasInvalidatedBy` this activity. |
| `repository_chosen` | `dd:RepositoryChoice` | Uses the repository's re3data record and each requirement set, named by their digests; generates the merged set, named by its digest. |
| `entry_chosen` | `dd:EntryChoice` | The entry point; a person's activity, or a run's when a model chose it. |
| `step_marked` | `dd:StepMarking` | The step and its mark. |
| `intake_answered` | `dd:IntakeAnswer` | Generates the answer, named by the digest of its values; the question it answers. |
| `intake_dismissed` | `dd:IntakeDismissal` | Nothing further. |
| `document_version_added`, drafted | `dd:VersionDrafting` | The version, a `prov:Entity`, `prov:wasGeneratedBy` the run, with this event as its generation; it `prov:wasRevisionOf` the version it revises, and carries `schema:sha256` and `dd:derivation`. |
| `document_version_added`, edited | `dd:VersionEdit` | Generates the version, which `prov:wasRevisionOf` the version it revises. |
| `document_version_decided` | `dd:VersionDecision` | Uses the version; `dd:decision` approved or rejected, and the reason as `schema:description`. |
| `document_change_refused` | `dd:ChangeRefusal` | Uses the version it names, where it names one; `dd:refusal` the reason code. |
| `document_question_answered` | `dd:QuestionAnswer` | Uses the version; generates the answer, named by its digest. |
| `document_revision_requested` | `dd:RevisionRequest` | Uses the version; the person's words as `schema:description`. The run that revises it is a run as below, whose version `prov:wasRevisionOf` the one named. |
| `fact_proposed` | `dd:FactProposal` | Generates the proposed fact, a `prov:Entity` with `dd:factKind` and `dd:factSubject`, which `prov:wasGeneratedBy` the run that proposed it. |
| `fact_decided` | `dd:FactDecision` | Uses the proposal, where it names one; generates the fact that stands, with `dd:decision` confirmed, changed or rejected, and the reason as `schema:description`. A rejection invalidates the fact it removes (`prov:wasInvalidatedBy`). |
| `project_validated` | `dd:ProjectValidation` | Uses the inventory, the merged set and the versions validated; generates the report, named by its digest, with `dd:conforms`. |
| `deposit_item_decided` | `dd:DepositItemDecision` | Uses the inventory, named by its digest; the item's file as `schema:about`, `dd:decision` keep, leave out or change, and the note as `schema:description`. |
| `deposit_checks_confirmed` | `dd:DepositChecksConfirmation` | Uses the inventory, named by its digest; the statements confirmed as `schema:description`. |
| `package_built` | `dd:PackageBuild` | Uses each version, the report, the merged set and the runs it holds; generates the package, named by its digest. |
| `project_deleted`, `project_restored` | `dd:ProjectDeletion`, `dd:ProjectRestoration` | Uses the project. |
| `conversation_deleted`, `conversation_restored` | `dd:ConversationDeletion`, `dd:ConversationRestoration` | Uses the conversation. |
| `member_added`, `member_role_changed`, `member_removed` | `dd:MemberAddition`, `dd:MemberRoleChange`, `dd:MemberRemoval` | Uses the project; `dd:member` the member, a `prov:Agent` named by their principal's identifier alone, and `dd:role` their role. |
| `deposit_approved` | `dd:DepositApproval` | Uses the package and the item deposited, named by their digests; `dd:repository`, `dd:transport` and `dd:sandbox`. |
| `deposit_recorded` | `dd:DepositRecording` | The harness is associated too. `prov:wasInformedBy` the approval it was made under; uses the package and the item; generates the deposit, with its DOI or deposit identifier as `schema:identifier` and its draft as `schema:url`, which `prov:wasDerivedFrom` the item. |
| `deposit_failed` | `dd:DepositFailure` | The harness is associated too. `prov:wasInformedBy` the approval; uses the package and the item; `dd:status` and the reason as `schema:description`. |
| `support_team_chosen` | `dd:SupportTeamChoice` | Uses the project; `dd:team` the team. |
| `escalation_opened` | `dd:EscalationOpening` | Generates the escalation, with `dd:team`, `dd:origin` and `dd:scopeShared`; `prov:wasInformedBy` the run it came from, where one; the note, named by its digest, as `dd:note`. |
| `escalation_rerouted` | `dd:EscalationRerouting` | Uses the escalation, with `dd:team`; carried out by the harness for the deployment, an accountable role ([Data stewards](stewardship.md), invariant 13). |
| `escalation_taken`, `_released`, `_waiting`, `_replied`, `_resolved`, `_handed_back`, `_withdrawn`, `_reopened` | `dd:EscalationTaking`, `dd:EscalationRelease`, `dd:EscalationWaiting`, `dd:EscalationReply`, `dd:EscalationResolution`, `dd:EscalationHandBack`, `dd:EscalationWithdrawal`, `dd:EscalationReopening` | Uses the escalation; `dd:actingAs` steward where a steward acted; the note, named by its digest, as `dd:note`. |
| `steward_viewed`, `steward_message` | `dd:StewardView`, `dd:StewardMessage` | Uses the project; `dd:actingAs` steward; the message's note, named by its digest, as `dd:note`. |
| `project_paused`, `project_resumed` | `dd:ProjectPause`, `dd:ProjectResumption` | Uses the project; `dd:team` the team that holds the pause; `dd:actingAs` steward; the reason, named by its digest, as `dd:note`. |
| `gate_cleared`, `gate_refused` | `dd:GateClearance`, `dd:GateRefusal` | `prov:wasInformedBy` the referred run; `dd:actingAs` steward; the reason, named by its digest, as `dd:note`. |

**Runs and what happens within them.**

| Record | Maps to |
|---|---|
| Run (its envelope) | A `prov:Activity` typed `dd:Invocation`, which `prov:wasAssociatedWith` the agent, a `prov:SoftwareAgent` with `schema:softwareVersion`. The agent acts for the principal the run acted for through a `prov:Delegation` whose `prov:hadActivity` is the run. The run has `prov:endedAtTime`, `dd:outcome` and `dd:reasonCode`, `dd:referredTo` where it was referred, and `dd:problem` the problem type's IRI where it failed. It uses its input, named by its input hash, and the policy it ran under, named by its digest. It `prov:has_provenance` its Process Run Crate. |
| Delegation | The child run is a run as above, acting for the same principal; it has `dd:parentInvocation` the parent run, and the parent `prov:wasInformedBy` it. |
| Model call | As in the [disclosure](disclosure.md), invariant 7: a `prov:Activity` the run `prov:wasInformedBy`, associated with the model, with the prompt as `prov:hadPlan`; and `dd:modelAccount`, whether a person's own account or the deployment's paid, never whose. |
| Retrieval | A `prov:Activity` the run `prov:wasInformedBy`, which used the source (its `source_uri`) and generated the evidence, named by its content hash; the run uses the evidence. The agent reports it today, not the harness, TODO(#246). |
| Tool call | A `prov:Activity` the run `prov:wasInformedBy`. |
| Policy gate | Where it refused or referred the run, a `prov:Activity` associated with the harness, which used the policy and which the run `prov:wasInformedBy`, with the decision. |
| Checks | The grounding linter, the source check and the shape check are each a `prov:Activity` associated with the harness, which used the payload and which the run `prov:wasInformedBy`; the shape check generates its report, named by its digest. TODO(#800). |
| Conversation turn | The message a person sent is an entity named by its digest, attributed to them and `schema:isPartOf` the conversation, which the run used. The reply is an entity named by its digest, which the run generated. TODO(#801). |

The mapping in the code is the authority on property names; this table is the authority on
which records appear, as what kind, and in which relations.

### Relation to the records already fixed

- **The project log** stays the record of what happened in a project; the graph is a reading of
  it. Making the log tamper-evident, so a reader can tell an event was altered, removed or
  reordered, is TODO(#802).
- **The disclosure** keeps its statement and its graph's meaning ([Disclosure](disclosure.md)).
  Its graph becomes the part of the provenance graph reachable from each approved version
  (invariant 10). A person's edit and an approval take their events' IRIs.
- **The Process Run Crate** stays the record of one run, written after it ([Contract](contract.md#boundaries-and-contracts)).
  The graph does not copy it; it links each run to its crate. The crate's `CreateAction` takes the
  run's IRI, and the crate names agents, models and prompts by the graph's IRIs (invariant 7),
  TODO(#800). Delegations, refusals, referrals and retrievals become distinct actions in the
  crate, with the child's `invocation_id` where there is one, TODO(#800).
- **The deposit package** carries, as `provenance.jsonld`, the provenance graph as it stood when
  the package was built, linked from the root crate. Its `CreateAction` and `AssessAction`
  entities take the graph's IRIs, so the two agree, and each run under `runs/` is reachable from
  the graph by its `invocation_id`. Today `provenance.jsonld` is the disclosure graph,
  TODO(#803).
- **The trace** and the `dd.*` attributes are unchanged. Spans are one source the graph is read
  from, through the envelope and the stored span records ([Transport and tracing](transport.md)).

### Serialisation

The graph is JSON-LD 1.1, compacted with one fixed context (`prov`, `schema`, `dd`, `xsd`), with
its nodes in `@graph` sorted by `@id` and every object's keys sorted, so the same record gives
the same bytes. Turtle is given on request, converted from the same RDF. The app's route is
`GET /api/projects/{project_id}/provenance`, behind the project access check, TODO(#804).

### Completeness and validation

A test decides that nothing is missing in three ways:

1. **Every type is mapped.** The event types the log can write and the event types the mapping
   covers are compared, in both directions (invariant 2).
2. **Every record appears.** For a project that uses every event type and holds a delegated run,
   a referred run, a failed run, a rejected version and a refused change, every event, run, model
   call, delegation and refusal is found in the graph by its IRI (invariant 3).
3. **The graph is PROV-O, as this spec reads it.** The JSON-LD is parsed into RDF with rdflib and
   checked with pySHACL against SHACL shapes kept in the harness, written from the mapping above.
   The shapes require, among other things, that every activity is associated with an agent or a
   person; that every software agent associated with a run acts for a person or an accountable
   role in it; that a document version has one generation; and that no node carries a property
   for message, prompt or answer text.

The same check runs on the deposit package's `provenance.jsonld` (TODO(#803)). This answers the
open question in #26: the graph is validated as RDF against shapes, not by asserting on its
JSON-LD.

### Personal data

The graph names a person by their principal: its identifier, display name, kind, assurance and
the issuer that vouched for it (invariant 6). The display name is the label the authentication
boundary gave; an ORCID holder who keeps their name private is shown by their iD. What a person
wrote (messages, answers) is named by digest only (invariant 5). In a shared conversation the app
may show speakers pseudonymously; the graph, read only by those who may read the project, names
them by principal (TODO(#388)).

Because the graph is read from the log and the run store and is not stored, it holds no personal
data the record does not, and data erased from the record is gone from every graph built later.
A package already built holds its own copy, as it holds its own copy of the log
([Projects](projects.md), invariant 26). What erasure removes from the record, and what it leaves
of the provenance P5 requires, is TODO(#156).

## Rationale

PROV-O is the standard R10 names, and RO-Crate, which the run crates and the package already use,
draws on it. Reading the graph from the record already kept, rather than writing provenance as a
second record, means the history says what the log and the run store say and cannot drift from
them. Every fact it needs is recorded for another reason: the log for review, the envelope for
audit, the crate for archiving.

People and agents are kept apart, and an agent acts for a person only through a delegation tied
to one run, because C13 asks who is accountable for each action. One agent serves many people,
so an unqualified `prov:actedOnBehalfOf` between the agent and a person would say the agent acts
for every one of them in every run.

The graph names content by digest because it travels further than the run store: to everyone who
may read the project, and in the package to an archive. A digest lets it name a prompt, a message
or an answer exactly, and lets the person who holds it show that it is the one recorded, without
publishing it ([Disclosure](disclosure.md#rationale)).

A run's event names the run's generation, rather than being a second generating activity, so the
graph keeps PROV's rule that an entity has one generation, and keeps what the disclosure already
publishes about a drafted version.

The graph is checked as RDF against SHACL shapes because a test on the JSON-LD's shape checks one
serialisation, while the shapes check what it means. The harness already depends on rdflib and
pySHACL and already validates payloads and projects with SHACL ([Contract](contract.md)), and an
auditor can run the same shapes on a package with any SHACL processor.

## Rejected alternatives

- **PROV-JSON as the primary form.** It is not RDF, so it cannot sit in an RO-Crate or be checked
  with SHACL, and its tooling is little maintained. A consumer that wants it can convert.
- **PROV-N or PROV-XML.** Neither is linked data, and neither is what RO-Crate uses.
- **Provenance stored apart from the log**, written alongside each event and run. It would double
  every write and could disagree with the record it describes.
- **Asserting on the JSON-LD rather than its RDF.** It checks a serialisation, and breaks when an
  equivalent one is chosen.
- **Validating against all of PROV-CONSTRAINTS.** No maintained Python validator exists; the
  reference one is Java. The shapes check the constraints this spec relies on.
- **Each run's event as an activity of its own that generates the version.** A version would then
  have two generations, the run and the event, and the disclosure's statement would change.
- **Unqualified `prov:actedOnBehalfOf`.** It cannot say in which run an agent acted for whom.
- **An accountable role as a `prov:Person`**, as the Process Run Crate records it today. A role is
  not a person, and C13 depends on telling them apart.
- **Message and prompt text in the graph, or in the package.** See
  [Disclosure](disclosure.md#rejected-alternatives).
- **Resolvable `https` IRIs for a deployment's projects and runs.** Each deployment would need a
  resolver, and the IRI would name the host that keeps the record.
- **Signing the log or anchoring it externally.** Digests chained through the log detect a change;
  signing or anchoring waits until a need is shown (TODO(#802)).

## Non-functional requirements

- **Privacy.** The graph carries only a principal's identifying facts and names content by digest
  (invariants 5 and 6). A non-member reads none of it, as for the rest of the project
  ([Projects](projects.md)).
- **Auditability.** The graph can be rebuilt from the record at any time and gives the same
  bytes, and a package states which graph it holds (TODO(#803)).
- **Accessibility.** The app shows the history as plain prose a person can read without the
  graph, in order, by keyboard and screen reader (TODO(#804)).
- **Performance.** The graph is built for one project at a time, and the app pages a long history
  (TODO(#804)).

## Open questions

- The w3id namespace for agents, models, the harness and the `dd:` terms, and where those terms
  are defined: TODO(#3).
- What erasure removes, and what it leaves of provenance: TODO(#156).
- The harness recording what an agent read, rather than the agent: TODO(#246).
- Mappings for event types not yet written, each needed before its type can be logged
  (invariant 2): a steward's further actions ([Data stewards](stewardship.md), invariant 12;
  TODO(#1481)) and a refused turn (TODO(#390)).
- How a package built after the project changed names the one before it: TODO(#649).
- Whether R10 is also assessed by independent review, as the Blueprint's guidance suggests:
  TODO(#26).
