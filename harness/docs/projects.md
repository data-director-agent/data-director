# The project record

A project is the unit of work: a record of its own that outlives any one conversation
([Projects](../../docs/specs/projects.md)). The harness keeps each project as an
append-only log of what changed in it, in `dd_harness.projects`. The run store is separate and
unchanged. Conversations are still derived from it, and the project is not.

## Where it is kept

Under `DD_PROJECTS_DIR`, which has no default ([System and boundaries](../../docs/specs/system.md)):

```text
<project_id>/events.jsonl                one event per line, in the order they happened
<project_id>/blobs/sha256/<digest>       content an event added, kept once by its digest
```

A `project_id` is a UUIDv7. An event is never changed or removed: each is appended as one line
and flushed to disk before the call returns.

## Events

Every event has these members:

| Member | What it is |
|---|---|
| `event` | What happened: `project_created`, `project_renamed`, `project_deleted`, `project_restored`, `conversation_started`, `conversation_deleted`, `conversation_restored`, `inventory_added`, `researcher_added`, `researcher_withdrawn`, `repository_chosen`, `document_version_added`, `document_version_decided`, `document_question_answered`, `document_change_refused`, `fact_proposed`, `fact_decided`, `project_validated` or `package_built`. |
| `event_id` | A UUIDv7, so events sort in the order they happened. |
| `project_id` | The project. |
| `at` | When, in UTC. |
| `acted_for` | The `Principal` the change was made for ([Policy and identity](../../docs/specs/policy-and-identity.md)). |
| `caused_by` | What caused it: the command a person ran, such as `dd-harness project add-inventory`; the request, such as `POST /api/projects/…/decisions` or `…/answers`; or the `invocation_id` of the run that drafted a version. |

`project_created` also gives `title`, if one was given: free text of at most `TITLE_MAX_LENGTH`
(200) characters that tells the project apart from others. A blank title is none.

`project_renamed` gives the project a new `title`, under the same rules except that a blank one is
refused, and `title_source`: `researcher` for a person (`PUT /api/projects/…/title`) or `model`
for a name an orchestrator's model wrote, caused by its run. The latest title counts. A title given
at creation is a person's, and once a person has given one, `ProjectStore.rename` refuses a model's
and records nothing ([Projects](../../docs/specs/projects.md), invariant 21).

`project_deleted` and `project_restored` carry nothing beyond the envelope. A project is deleted
while the last of them in its log is a deletion (`dd_harness.projects.deletion`). A deleted
project takes no change but `restore` and a run's draft (`record_draft`), so that a run already
going is recorded; every other change raises `ProjectDeletedError` and records nothing.
`restore` raises `RestoreRefusedError` for a project not deleted, or once the store's
`restore_period` from the deletion is over: 30 days, or `DD_PROJECT_RESTORE_DAYS` whole days,
where 0 makes a deletion final. A summary gives `deleted` (when, by whom and until when it may be
restored, or null) and `restore_days`. `project_access` gives no one but an owner a role in a
deleted project, and leaves it out of `readable_projects`, so its conversations and runs leave
every list too ([Projects](../../docs/specs/projects.md), invariants 22 to 25).

`conversation_started` also gives the `conversation_id` (a UUIDv7) of a conversation started from
the project. `ProjectStore.project_of(conversation_id)` says which project, if any, a conversation
was started in, from what the logs hold when asked, so it holds after a restart and agrees with
any other harness over the same directory. A conversation's project never changes once recorded,
so the answers found are kept; a conversation not found is looked for again in every log, which
does not scale past one deployment's projects. A deployment that outgrows it keeps its projects in
the database, where finding a conversation's project is an indexed query
([Storage](../../docs/specs/storage.md)).

`conversation_deleted` and `conversation_restored` also give the `conversation_id` of a
conversation started in the project. A conversation is deleted while the last of them for it is a
deletion (`dd_harness.projects.conversation_deletions`). `delete_conversation` raises
`UnknownConversationError` for a conversation not started in the project and
`ConversationDeletedError` for one already deleted; `restore_conversation` raises
`RestoreRefusedError` as `restore` does, over the same `restore_period`. `deleted_conversations`
lists those that stand, and a summary's `conversation_count` leaves them out. Who may delete one is
`project_access.may_delete_conversation`: whoever started it while they may contribute, and an
owner. `project_access.hidden_in` names the deleted ones in the logs of the projects a person may
read, already read in one query (`readable_logs`), which a `Readable` leaves out of every listing
([Projects](../../docs/specs/projects.md), invariants 29 to 31).

`inventory_added` also gives:

| Member | What it is |
|---|---|
| `digest` | The SHA-256 of the inventory's canonical bytes, under which the blob is kept. |
| `canonicalisation` | `dd-input-json-v1`. The digest is therefore the input hash the conductor records when an agent is given this inventory. |
| `file_count` | How many files the inventory lists. |
| `inventory_made_at` | When `dd-inventory` made it. |
| `revises` | The digest of the inventory the project held before, when it held one: this one revises it. The store finds it in the log; no caller gives it. |
| `part_count` | How many parts the inventory is made of, when it is made of parts (`inventory_parts`); absent for an inventory of one folder. |

`researcher_added` keeps the facts a person chose from their own public ORCID record
([Projects](../../docs/specs/projects.md), invariant 27). It also gives:

| Member | What it is |
|---|---|
| `orcid_id` | The person's iD URL; always the iD of the principal in `acted_for`. |
| `digest` | The SHA-256 of the `ResearcherRecord`'s canonical bytes, under which the blob is kept. |
| `canonicalisation` | `dd-input-json-v1`. |
| `record_retrieved_at` | When the record was read from ORCID's public API. |

The latest `researcher_added` for an iD counts. `researcher_withdrawn` gives the `orcid_id` whose
record is no longer given to agents; it may be added again later. `ProjectStore.researchers` gives
the records that stand, the one kept first first.

`repository_chosen` also gives:

| Member | What it is |
|---|---|
| `re3data_id`, `repository_name` | The repository chosen, by its re3data identifier. |
| `declared_standards` | The metadata standards its re3data record declares, as re3data names them. |
| `requirement_sets` | Each set the choice resolved to, as `ref` (`<requirement_set_id>@v<version>`) and the `sha256` of its file. |
| `digest` | The SHA-256 of the merged requirements' canonical bytes, under which the blob is kept. |
| `canonicalisation` | `dd-input-json-v1`. |
| `warnings` | What the researcher was told: that the repository does not list DataCite, or that the deployment has no override for it. |

`project_validated` records a validation of the project against the merged requirements of the
repository chosen last ([Deposit](../../docs/specs/deposit.md)), made by `dd-harness project
validate` or before a package is built. It also gives:

| Member | What it is |
|---|---|
| `digest` | The SHA-256 of the SHACL Validation Report's canonical bytes, under which the blob is kept. |
| `canonicalisation` | `dd-input-json-v1`. |
| `conforms` | Whether the report has no violation. |
| `requirements_digest` | The digest of the merged requirements checked against, or null if no repository was chosen. |

`package_built` records a deposit package, built only after a `project_validated` event that
conforms. It also gives:

| Member | What it is |
|---|---|
| `digest` | The SHA-256 of the package's zip, under which the blob is kept. |
| `report_digest` | The digest of the validation report the package was built from. |
| `requirements_digest` | The digest of the merged requirements it was validated against. |
| `documents` | Each approved version it holds, as `document_id`, `document_kind`, `version` and `digest`. |
| `runs` | The `invocation_id` of each run behind those versions. |
| `file_count` | How many data files it describes, none of which it holds. |

`ProjectStore.package(project_id, digest)` reads back a package the log records.

Who may do what in a project is read from this log by `dd_harness.project_access`, the one access
check the conductor and the app use ([Projects](../../docs/specs/projects.md), invariant 17):
`project_created` makes its creator the owner. Changes of membership will be events of the same
log that `project_access.roles` folds, TODO(#389).

## The inventory

What a project holds of its research data is a `FileInventory`, made by
[`dd-inventory`](../../inventory/README.md) where the data live, and never the files. The store
checks an inventory against the core class schema before adding it, so a document of another
class, or one that gives an absolute path, is refused and nothing is recorded. So is an inventory
made of parts whose folders overlap, or with a file under no part's folder
(`dd_sdk.contract.models.inventory_part_problems`). The latest inventory added is the project's
inventory: updating one part of it is a whole new inventory, with the other parts as they were.

```console
$ export DD_PROJECTS_DIR=… DD_PRINCIPAL_ID=… DD_PRINCIPAL_NAME=…
$ uv run dd-inventory path/to/dataset -o inventory.json
$ uv run dd-harness project create --title "Soil cores 2024"
0192f3a4-…
$ uv run dd-harness project add-inventory 0192f3a4-… inventory.json
$ uv run dd-harness project events 0192f3a4-…
$ uv run dd-harness project list
$ uv run dd-harness project delete 0192f3a4-…
$ uv run dd-harness project restore 0192f3a4-…
```

`project list`, and `ProjectStore.projects()`, give a summary of each project in the order they were
created. A summary has the latest title and who gave it (`title_source`), who created it and when, the latest inventory (digest, file
count and when it was made), the repository chosen last and its warnings, how many conversations
were started in it, and how many documents have a latest version in each state.

## The repository chosen

A researcher may choose any repository in re3data, usually one `advisor.repository` shortlisted.
The choice names only its re3data identifier. The repository's name and the metadata standards
its record declares are read from the latest re3data export pinned in the deployment's
`sources.yaml` (`DD_SOURCES_CONFIG`, under `re3data:export:YYYY-MM`), so nothing is typed by hand
and the choice cannot disagree with the registry. The event records that `snapshot_ref` and the
record's content hash. An identifier the export does not hold is refused, as is a choice when no
export is pinned or the pinned one is not built (`uv run dd-sources prepare` builds it).
What a deposit to it must or should have comes from the deployment's requirement sets under
`DD_REPOSITORIES_DIR`, loaded and checked by `dd_harness.requirements`
([Deposit](../../docs/specs/deposit.md)): the repository's override, if there is one, merged on the set of the standard it names, or
else the set of a standard the repository declares, or DataCite's. The merged set is kept as a
blob, and the requirements of the repository chosen last are the project's. Sets that are
malformed or contradict one another stop the command before anything is recorded.

```console
$ export DD_REPOSITORIES_DIR=app/config/repositories DD_SOURCES_CONFIG=workbench/sources.yaml
$ uv run dd-harness project choose-repository 0192f3a4-… --re3data r3d100012124
```

## Documents and decisions

A document is a sequence of versions; a person decides on each ([Projects](../../docs/specs/projects.md)).
`ProjectStore` adds a version in one of two ways:

- `record_draft(project_id, envelope)` takes a succeeded run's `Document` payload. A draft that
  revises nothing is version 1 of a new document; one whose `revises` names a version of this
  project is the next version of that document. Anything else is refused and nothing is
  recorded. The event acts for whom the run acted for and its `caused_by` is the run's
  `invocation_id`.
- `edit(...)` takes a person's text and the version and digest they edited. It names no run.

`decide(project_id, decision, acted_for=…, caused_by=…)` records a `Decision`: the version, the
digest of the text shown, `approved` or `rejected`, a reason, and to approve an edit, the edited
text. Whoever `acted_for` names decided: a `Decision` cannot name a decider. A rejection, or
an approval of an edit, needs a reason of at most `REASON_MAX_LENGTH` (2,000) characters;
`review_rules()` states that rule for the app to draw. An edit and its approval are appended
in one write.

`document_version_added` also gives:

| Member | What it is |
|---|---|
| `document_id`, `version` | The version: the document's UUIDv7, and a number counted from 1 within it. |
| `digest` | The SHA-256 of the text as UTF-8, under which the text is kept as a blob. |
| `document_kind`, `media_type` | As the `Document` gave them; a person's version keeps its parent's. |
| `document_title`, `conforms_to` | As the `Document` gave them, if it did. |
| `revises` | `{document_id, version}` of the version it replaces or was edited from, if any. |
| `drafted_by` | For an agent's version only: `agent_id`, `agent_version`, `invocation_id` and `document_derivation`. |
| `questions` | For an agent's version that asks any: its `document_questions` as the `Document` gave them ([Drafting documents](../../docs/specs/drafting.md)). A person's version asks none. |

`document_version_decided` also gives `document_id`, `version`, `digest`, `decision`
(`approved` or `rejected`) and, if one was given, `reason`. Its `acted_for` is the decider.

`document_question_answered` records one answer a person gave to a question the document's latest
version asks ([Drafting documents](../../docs/specs/drafting.md), invariant 6). It gives
`document_id`, `version`, `question_id` and `answer_text`, stripped of surrounding white space and
at most `ANSWER_MAX_LENGTH` (2,000) characters. Its `acted_for` is whoever answered. Answers sent
together are appended in one write. A decided version's questions may still be answered: the
answers go into the next draft, not into that version.

`fact_proposed` records one fact a check agent proposed for a person to decide
([Projects](../../docs/specs/projects.md), invariant 28). It gives `agent_id`, the agent that
proposed it, and `fact`, the `ProjectFact` as proposed, with `proposed_because`; its `caused_by`
is the run, and its `event_id` names the proposal. A run's proposals are appended in one write.

`fact_decided` records a person's decision. It gives `verdict` (`confirmed`, `changed` or
`rejected`), `fact` (the fact that now stands, without `proposed_because`; for a rejection, only
its `fact_kind` and `fact_subject`), `proposal` if the decision names one, and `reason` if one was
given, at most `FACT_REASON_MAX_LENGTH` (2,000) characters. Its `acted_for` is the decider.
`decisions(project_id)` gives the fact that stands for each kind and subject, the last decision
counting and a rejection removing it; `proposals(project_id)` gives the proposals no decision on
their kind and subject has followed, the latest for each.

`document_change_refused` records a decision, edit or answer refused because it named no document
of the project (`document-not-found`), not the latest version (`version-not-latest`), a version
already decided (`version-decided`), another text (`digest-mismatch`) or a question the latest
version does not ask (`question-not-asked`), or a decision on a fact that named a proposal the
project does not hold (`proposal-not-found`) or changed a proposal's kind or subject
(`fact-not-proposed`), which gives the `proposal` named. It gives `document_id` and `version` as sent, the
`digest` for a decision or edit, the `questions` not asked for an answer, the `refusal`, and the
`latest_version` if there is one. A change malformed in itself, such as a rejection without a
reason or a blank answer, is refused with `ProjectError` and records nothing.

`documents(project_id)` folds the log into each document, in the order first drafted, with every
version oldest first, its text and its `state` (`proposed`, `approved` or `rejected`) with the
`decision` on it, and the document's `answers`: the latest answer to each question, with the
`version` it answered, `answered_by` and `answered_at`. It is what the app serves at
`GET /api/projects/{id}/documents`.

`answers(project_id, document_kind)` is the latest answer to each question of any document of that
kind, as `DraftAnswer`s, in the order last answered, or None. A question's identifier is derived
from the gap it fills, so it is the same in every draft of that kind, and a project drafted before
redrafts kept their document may hold two of one kind. The conductor gives these answers to every
drafter of that kind in the project.

`current_version(project_id, document_kind, document_id=None)` is the version a drafter
regenerates, as a `CurrentVersion`: the latest version of `document_id`, or of the document of
that kind drafted or revised last, with its text, its state and the reason for any decision on
it. It is None if the project holds no document of the kind, and raises `ProjectError` for a
`document_id` that is not the project's or is of another kind.

`metadata_record(project_id)` is the version of a `metadata_record` document named by the last
approval in the log, as an `ApprovedMetadataRecord`: its `version_ref`, `media_type`,
`conforms_to` and text. A version proposed or rejected since does not displace it, and it is None
until a person approves one. The conductor gives it to every drafter in the project.

## Not yet built

- Membership is not built, so a project's creator is its only owner and no one else has a
  role in it, TODO(#389).
- A drafter is not yet given the text of a document a researcher attached; only an
  orchestrator is told, without its text, that the project holds it.
- How long a project is kept once it can no longer be restored, and what erasing one removes,
  TODO(#156).
