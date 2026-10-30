# The project record

A project is the unit of work: a record of its own that outlives any one conversation
([ADR-0034](../../docs/adr/0034-project-and-its-files.md)). The harness keeps each project as an
append-only log of what changed in it, in `dd_harness.projects`. The run store is separate and
unchanged. Conversations are still derived from it, and the project is not.

## Where it is kept

Under `DD_PROJECTS_DIR`, which has no default (ADR-0022):

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
| `event` | What happened: `project_created` or `inventory_added`. |
| `event_id` | A UUIDv7, so events sort in the order they happened. |
| `project_id` | The project. |
| `at` | When, in UTC. |
| `acted_for` | The `Principal` the change was made for (ADR-0018). |
| `caused_by` | What caused it: the command a person ran, such as `dd-harness project add-inventory`. |

`inventory_added` also gives:

| Member | What it is |
|---|---|
| `digest` | The SHA-256 of the inventory's canonical bytes, under which the blob is kept. |
| `canonicalisation` | `dd-input-json-v1`. The digest is therefore the input hash the conductor records when an agent is given this inventory. |
| `file_count` | How many files the inventory lists. |
| `inventory_made_at` | When `dd-inventory` made it. |

Documents ([ADR-0035](../../docs/adr/0035-project-documents.md)), approval decisions
([ADR-0036](../../docs/adr/0036-proposed-changes-and-approval.md)) and changes of membership
([ADR-0037](../../docs/adr/0037-shared-projects.md)) will be events of the same log.

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

## Not yet built

- The request and the envelope do not carry a `project_id` yet, and the conductor does not give
  an agent its project's facts or apply `hosted_models` (ADR-0034 decisions 1, 6 and 7),
  TODO(#394).
- The app cannot add an inventory to a project, TODO(#395).
- How long a project is kept, and what deleting one removes, TODO(#141).
