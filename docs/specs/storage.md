# Storage

## Intent and scope

The harness keeps two records: the **run storage**, which holds every invocation the conductor ran,
and the **project storage**, which holds each project's log ([Projects](projects.md)). A deployment
keeps them in **PostgreSQL**, and the database is the record of what happened: nothing else holds a
copy that outranks it. The **file backends** keep the same records as files on one disk, for
development, tests and a deployment on a single host.

This spec covers what the harness asks of a store, so that a move between backends changes no
caller. Each store is reached through a `typing.Protocol` in `dd_harness.storage`: `RunStorage` for
runs, and `ProjectStorage` for projects, which the harness implements once over a narrower
`ProjectLog` that each backend provides (see [Project rules and the project log](#project-rules-and-the-project-log)).
The file backends, `RunStore` (`dd_harness.store`) and `ProjectStore` (`dd_harness.projects`),
implement them today. The PostgreSQL backend is not built yet, TODO(#522).

It does not cover what a run or a project contains ([Contract](contract.md), [Projects](projects.md),
[Disclosure](disclosure.md)), nor how long either is kept (see Open questions).

## Invariants

1. **Callers reach a store through its protocol.** The conductor, conversations, disclosure, the
   project facts, the app and the workbench name `RunStorage` and `ProjectStorage`, never a
   backend's layout. Only a backend's own tests read its files or tables (`RunStore.root`,
   `run_dir`, `ProjectStore.root`). Enforced by mypy over the callers' annotations.
2. **A run is written once.** Storing an envelope whose `invocation_id` is already stored raises
   `FileExistsError` and changes nothing the store returns. The conductor refuses a duplicate
   request before it runs ([Contract](contract.md)), so this is the last guard, not the first.
3. **Envelopes come back in the order stored.** The store assigns each run a place in a sequence
   when it stores it; that sequence, not the order of `invocation_id`s, is the order. The conductor
   stores a run when it finishes, so this is the order runs finished in, which is the turn order of
   a conversation ([Orchestration](orchestration.md)). A store may be asked for one conversation's
   envelopes alone; it returns them in the same order.
4. **A run is stored whole.** The envelope, its request, its prompts and the class schemas it was
   checked against are stored together or not at all. The database backend stores them in one
   transaction. The file backend falls short: it writes the run's files and then its line in
   `invocations.jsonl`, so a run interrupted part way is not listed but may leave its directory,
   and `has` may report it.
5. **Everything else a run keeps is a named artifact.** Beside the envelope, the request, the
   prompts and the class schemas, the conductor keeps `spans.jsonl`, `grounding.txt`,
   `sources.txt`, `validation-report.jsonld` when the payload's class carries shapes
   ([Contract](contract.md)) and, unless `DD_WRITE_CRATE=0`, the Process Run Crate as one artifact per file
   under `crate/`. An artifact belongs to a stored run, is written once, and is read back byte for
   byte. Its name is a relative path of plain segments and cannot name the run's own files, in
   every backend, including those whose keys could hold any string.
6. **A class schema is kept once under its digest**, and its bytes never change
   ([Contract](contract.md)).
7. **Prompts are read only through `get_prompts`**, by whoever may read the run. No envelope,
   artifact or crate carries one ([Disclosure](disclosure.md)).
8. **A malformed name names nothing.** An `invocation_id`, digest, artifact name or `project_id`
   that is not well formed returns nothing or is refused, so no caller can reach outside the
   store.
9. **A project's log is append-only and ordered.** Events are never changed or removed and come
   back in the order appended ([Projects](projects.md), invariant 2).
10. **A checked change runs in an exclusive section for its project.** An edit, a decision, an
    answer or a draft reads the log, applies the project rules and appends its events inside a
    section that no other change to that project enters. Projects do not wait on one another.
    The events a change writes together are kept together or not at all. The file backend's
    section is a lock per project and holds within one harness process only; the PostgreSQL
    backend's is a transaction that holds a lock on the project's row, and holds across processes
    and hosts.
11. **A refusal is recorded, then raised.** What the section appended is kept whether or not the
    rules refuse the change: the `document_change_refused` event is committed with the section,
    and `ChangeRefusedError` is raised after the section ends. A backend never loses a refusal by
    rolling back on the exception.
12. **What a store answers is what is stored when asked.** `project_of`, the list of projects and
    the list of conversations read what is stored at the time of the call, so several harness
    instances over one database agree, and each holds after a restart. A backend may cache only
    what can never change, such as a conversation's project once it is recorded.
13. **A location never carries a credential.** `where` and every error name a location without a
    password or token. The PostgreSQL backend takes its credentials from libpq's own sources (a
    password file, a service file or its environment variables), never from the location.
14. **A backend is chosen by its location.** `DD_RUNS_DIR` and `DD_PROJECTS_DIR` each name a path
    or a `file://` URL, which select the file backends, or a `postgresql://` URL, which selects
    the PostgreSQL backend. Any other scheme stops start-up with `SettingsError`, naming the
    schemes this build supports (`dd_harness.settings.run_storage`, `project_storage`;
    `harness/tests/test_storage.py`). This build supports files only, TODO(#522).
15. **The file backends keep their layout.** A run is `<invocation_id>/` beside
    `invocations.jsonl` and `schemas/`; a project is `<project_id>/events.jsonl` beside its
    blobs. The layout is in the docstrings of `store.py` and `projects.py`, and
    `harness/tests/test_harness.py` and `test_projects.py` read it.

Invariants 2 to 12 are the guarantees in the protocols' docstrings. The conformance kit
(`dd_harness.testing.check_run_storage`, `check_project_storage`) checks each of them through the
protocol alone, and `harness/tests/test_storage.py` runs it against the file backends. The kit
checks concurrent changes from threads sharing one store; a check with two store instances
contending for one project, which only a database backend can pass, is TODO(#522).

## Boundaries and contracts

- The protocols are structural. A backend implements their methods; it neither imports nor
  subclasses anything from `dd_harness.storage`.
- `append` stores the documents it is given. The conductor has already checked them against the
  contract; a backend does not check them again, and may index any field of the envelope.
- `where` names a run's location for a person (a path, or a URI for a database). Nothing parses it.
- `dd_harness.provenance` builds the crate in a temporary directory and returns its files, and the
  conductor keeps each as an artifact. The crate's content does not depend on the backend, and the
  file backend holds the same `<run>/crate/` it did before artifacts existed.
- Conversations are derived from the run storage, through `iter_envelopes(conversation_id=…)` and
  `get_request` ([Orchestration](orchestration.md), invariant 2). A backend may index them; it
  does not keep a second record of them.
- Artifacts and project blobs are kept in the store itself: as files in the file backends, as
  bytes in the database in the PostgreSQL backend.

## Project rules and the project log

`ProjectStorage` is what callers use, and its methods carry the project rules: folding the log
into documents and versions, refusing a stale change, checking a decision, an answer or an
inventory against its schema. Those rules are written **once**, in the harness, over a
`ProjectLog`: the part a backend provides. A project log can read a project's events in order,
run an exclusive section in which the rules read and append (invariants 10 and 11), keep and read
content by digest, find a conversation's project, and list projects. Nothing in a `ProjectLog`
decides whether a change is allowed.

Today the rules and the file log are one class, `ProjectStore`; separating them is
TODO(#521). Until then a second backend cannot be added without copying the rules, which this
design forbids.

## Adding a backend

A backend:

1. is a module of the harness, whose driver is an optional extra of `data-director-harness`
   named after it, as `serve` is for `uvicorn` ([System and boundaries](system.md)). The settings
   factory imports the module only when its scheme is named, so a deployment on files does not
   install the driver;
2. implements `RunStorage` and `ProjectLog`, keeping every guarantee above;
3. passes the conformance kit, run from the harness's tests against a real database. Those tests
   are skipped when no database is named for them, and CI names one;
4. changes its schema only through numbered SQL files, applied by an explicit command. Start-up
   refuses a database whose schema is older or newer than the build expects, naming the command.
   Nothing alters a schema as a side effect of serving.

The PostgreSQL backend uses `psycopg` (version 3) and plain SQL. Its entry in the
[dependency register](dependencies.md#the-register) is added with the code, TODO(#522).

## Moving file stores into a database

A command copies existing file stores into the database. It is one-way and can be run again
without duplicating anything. It verifies each run's hashes,
keeps the order of `invocations.jsonl` as the stored order and the order of each `events.jsonl`
as the log's order, reports what it cannot carry, and leaves the files as they were. Runs stored
under an older contract are copied as stored, not rewritten ([Contract](contract.md)). The command
is TODO(#523).

## Rationale

The file layout used to leak: `RunStore.append` returned the run's directory, the conductor wrote
the trace, the reports and the crate into it, and the app and the workbench CLI read files beside
the envelope. Each of those callers would have had to change with the backend. Named artifacts
give every such file one way in and out, and keep the file backend's layout as it was, so existing
run stores are read without migration.

Protocols rather than abstract base classes let the file backends keep their names and
constructors. The guarantees are stated in the protocols' docstrings and checked by a kit any
backend can run, because a type checker sees the methods but not the ordering, atomicity or
write-once rules that callers rely on.

A deployment that serves more than one instance, or answers questions across projects (shared
projects, a steward's queue), needs one record that every instance writes to and reads from with
the same guarantees. PostgreSQL gives transactions across several rows, row locks that hold
between processes and hosts, indexes over JSON documents, and an operational practice
(replication, point-in-time recovery, managed services) that university IT already runs. Making
the database the record, not an index, means there is one thing to back up and one thing that can
disagree with nothing.

The project rules are governance. A backend that re-implemented them could drift from them, and
the conformance kit samples the rules rather than proving them. Keeping them once, over a log that
only stores, makes a new backend a storage problem alone.

The exclusive section keeps the model the file backend already has, a lock per project, and
extends it across processes. A refused change appends its refusal in the same section as any
other change, so concurrent decisions on one version admit one and record the rest, whichever
backend runs them.

A backend in the harness, behind an extra, needs no discovery: the factory knows its schemes,
and the harness already keeps every store. The extra keeps the driver out of a deployment on
files.

## Rejected alternatives

- **A conversation store beside the run store.** A conversation is derived from its runs
  ([Orchestration](orchestration.md)); a second record would drift from them. The conversation
  filter on `iter_envelopes` lets a database answer the same question with an indexed query.
- **Returning a path from the run store.** It ties every caller to files, which is the leak this
  design removes.
- **Building the crate inside the store.** The crate is provenance, not storage. Built apart and
  kept as artifacts, it is the same whatever the backend.
- **JSONL files as the record, with a database as an index over them.** The files stay on one
  host, so several instances still cannot share them, and there would be two records that could
  disagree and an index to rebuild after every restore.
- **MongoDB.** A change that writes several documents needs a multi-document transaction, which
  needs a replica set even for one server; ordering a project's events and the row-lock model of
  an exclusive section would be built by hand.
- **SQLite.** One writer for the whole database and one host; it does not serve several
  instances. A single host is already served by the file backends.
- **A backend in a package of its own, found through entry points.** It needs a discovery
  mechanism and a package to release in step with the harness's protocols, to keep one driver out
  of the harness's base install, which an extra already does.
- **Each backend implementing the project rules.** See Rationale.
- **An ORM, or Alembic for schema changes.** Both bring SQLAlchemy into the runtime tier for a
  handful of tables whose queries are plain. Numbered SQL files read the same to an operator as to
  a reviewer.
- **A conditional insert (append only if the log has not grown) instead of a lock.** It needs a
  retry loop around every rule and makes recording a refusal a second race. A per-project lock is
  held only for the length of one change, and projects do not share it.
- **Object storage for artifacts, blobs and deposit packages.** A second service to secure, back
  up and keep consistent with the database. Revisit if packages grow large (see Open questions).

## Non-functional requirements

- **Security.** No name a caller supplies reaches outside the store (invariant 8). Prompts are
  kept apart from everything that leaves the store (invariant 7). No credential is written in a
  location or shown by one (invariant 13).
- **Portability.** The file backends need only a local file system, and are the default for
  development and for a single-host deployment. The PostgreSQL backend needs only PostgreSQL, no
  extension.
- **Durability.** A call that stores something returns after it is durable: flushed to disk in
  the file backends, committed in the database.
- **Performance.** The file backends scan: conversations read every envelope, and `project_of` reads
  every project's log for a conversation it has not found before (a conversation's project, once
  found, is kept, as invariant 12 allows). They are not indexed; a deployment that outgrows a
  scan moves to the database. In the database, listing runs, conversations and projects and
  finding a conversation's project are indexed queries, TODO(#524).
- **Operations.** A documented and tested backup and restore of the database, and a health check,
  are TODO(#525).

## Open questions

- How long runs, conversations and projects are kept, what deleting one removes, and how a
  person's data in them is erased, now that the record is a database from which rows can be
  deleted, TODO(#156).
- Whether deposit packages and other large blobs move to object storage, TODO(#525).
