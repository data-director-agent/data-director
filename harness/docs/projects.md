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
| `event` | What happened: `project_created`, `inventory_added`, `repository_chosen`, `document_version_added`, `document_version_decided` or `document_change_refused`. |
| `event_id` | A UUIDv7, so events sort in the order they happened. |
| `project_id` | The project. |
| `at` | When, in UTC. |
| `acted_for` | The `Principal` the change was made for ([Policy and identity](../../docs/specs/policy-and-identity.md)). |
| `caused_by` | What caused it: the command a person ran, such as `dd-harness project add-inventory`; the request, such as `POST /api/projects/…/decisions`; or the `invocation_id` of the run that drafted a version. |

`inventory_added` also gives:

| Member | What it is |
|---|---|
| `digest` | The SHA-256 of the inventory's canonical bytes, under which the blob is kept. |
| `canonicalisation` | `dd-input-json-v1`. The digest is therefore the input hash the conductor records when an agent is given this inventory. |
| `file_count` | How many files the inventory lists. |
| `inventory_made_at` | When `dd-inventory` made it. |

`repository_chosen` also gives:

| Member | What it is |
|---|---|
| `re3data_id`, `repository_name` | The repository chosen, by its re3data identifier. |
| `declared_standards` | The metadata standards its re3data record declares, as re3data names them. |
| `requirement_sets` | Each set the choice resolved to, as `ref` (`<requirement_set_id>@v<version>`) and the `sha256` of its file. |
| `digest` | The SHA-256 of the merged requirements' canonical bytes, under which the blob is kept. |
| `canonicalisation` | `dd-input-json-v1`. |
| `warnings` | What the researcher was told: that the repository does not list DataCite, or that the deployment has no override for it. |

Changes of membership ([Projects](../../docs/specs/projects.md)) will be events of the same
log, TODO(#389).

## The inventory

What a project holds of its research data is a `FileInventory`, made by
[`dd-inventory`](../../inventory/README.md) where the data live, and never the files. The store
checks an inventory against the core class schema before adding it, so a document of another
class, or one that gives an absolute path, is refused and nothing is recorded. The latest
inventory added is the project's inventory.

```console
$ export DD_PROJECTS_DIR=… DD_PRINCIPAL_ID=… DD_PRINCIPAL_NAME=…
$ uv run dd-inventory path/to/dataset -o inventory.json
$ uv run dd-harness project create
0192f3a4-…
$ uv run dd-harness project add-inventory 0192f3a4-… inventory.json
$ uv run dd-harness project events 0192f3a4-…
```

## The repository chosen

A researcher may choose any repository in re3data, usually one `advisor.repository` shortlisted.
What a deposit to it must or should have comes from the deployment's requirement sets under
`DD_REPOSITORIES_DIR`, loaded and checked by `dd_harness.requirements`
([Deposit](../../docs/specs/deposit.md)): the repository's override, if there is one, merged on the set of the standard it names, or
else the set of a standard the repository declares, or DataCite's. The merged set is kept as a
blob, and the requirements of the repository chosen last are the project's. Sets that are
malformed or contradict one another stop the command before anything is recorded.

```console
$ export DD_REPOSITORIES_DIR=app/config/repositories
$ uv run dd-harness project choose-repository 0192f3a4-… --re3data r3d100012124 \
    --name ORDA --standard "Dublin Core"
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

`document_version_decided` also gives `document_id`, `version`, `digest`, `decision`
(`approved` or `rejected`) and, if one was given, `reason`. Its `acted_for` is the decider.

`document_change_refused` records a decision or edit refused because it named no document of the
project (`document-not-found`), not the latest version (`version-not-latest`), a version
already decided (`version-decided`) or another text (`digest-mismatch`). It gives
`document_id`, `version` and `digest` as sent, the `refusal`, and the `latest_version` if
there is one. A decision malformed in itself, such as a rejection without a reason, is refused
with `ProjectError` and records nothing.

`documents(project_id)` folds the log into each document, in the order first drafted, with every
version oldest first, its text and its `state` (`proposed`, `approved` or `rejected`) with the
`decision` on it. It is what the app serves at `GET /api/projects/{id}/documents`.

## Not yet built

- The conductor does not yet record a run's draft (`record_draft`), so a version reaches a
  project only from code that calls the store, TODO(#394).
- Only owners are to decide, and membership is not built, TODO(#389).
- The request and the envelope do not carry a `project_id` yet, and the conductor does not give
  an agent its project's facts or apply `hosted_models` ([Projects](../../docs/specs/projects.md)),
  TODO(#394).
- The app cannot add an inventory to a project, TODO(#395), or choose a repository, TODO(#400).
- A drafter reads the merged requirements as `DraftRequest.requirements`, a core
  `RepositoryRequirements`, but the conductor does not yet put them in (TODO(#394)). Nothing
  checks a project against them, TODO(#19, #202).
- How long a project is kept, and what deleting one removes, TODO(#141).
