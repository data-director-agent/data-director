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
The file backends, `RunStore` (`dd_harness.store`) and `FileProjectLog`
(`dd_harness.project_files`), implement them today; `ProjectStore` (`dd_harness.projects`) is the
project rules over the file log. The PostgreSQL backend, `PostgresRunStore` and
`PostgresProjectLog` (`dd_harness.postgres`), implements them for a deployment; `Projects` over
`PostgresProjectLog` is its project storage.

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
    `harness/tests/test_storage.py`). A `postgresql://` location needs the harness's `postgres`
    extra; without it, start-up stops naming the extra. A location that cannot be used (a
    directory that cannot be made, a database that cannot be reached or whose schema is not this
    build's) stops start-up with `SettingsError` too, naming the variable.
15. **The file backends keep their layout.** A run is `<invocation_id>/` beside
    `invocations.jsonl` and `schemas/`; a project is `<project_id>/events.jsonl` beside its
    blobs. The layout is in the docstrings of `store.py` and `project_files.py`, and
    `harness/tests/test_harness.py` and `test_projects.py` read it.

Invariants 2 to 12 are the guarantees in the protocols' docstrings. The conformance kit checks
each of them through the protocols alone: `dd_harness.testing.check_run_storage` a run storage,
`check_project_log` a project log, and `check_project_rules` the project rules over a project log
(it runs `check_project_storage` on them). The kit checks concurrent changes from threads sharing
one store. `check_shared_record` checks two logs opened over one record contending for one
project, as two harness instances over one database do; only a backend whose section holds across
instances passes it, so the file backend does not run it. `harness/tests/test_storage.py` runs the
kit against the file backends, and `harness/tests/test_postgres.py` against the PostgreSQL
backend, with every check above and a contention between processes.

## Boundaries and contracts

- The protocols are structural. A backend implements their methods; it neither imports nor
  subclasses anything from `dd_harness.storage`.
- `append` stores the documents it is given. The conductor has already checked them against the
  contract; a backend does not check them again, and may index any field of the envelope.
- `where` names a run's location for a person (a path, or a URI for a database). Nothing parses it.
- `dd_harness.provenance` builds the crate in a temporary directory and returns its files, and the
  conductor keeps each as an artifact. The crate's content does not depend on the backend, and the
  file backend holds the same `<run>/crate/` it did before artifacts existed.
- Conversations are derived from the run storage, through `iter_envelopes(conversation_id=…)`,
  `list_conversations` and `get_request` ([Orchestration](orchestration.md), invariant 2). A
  backend may index them; it does not keep a second record of them. An index written in the
  transaction that stores each run, and rebuilt from the runs by the migration that adds it, is
  an index in this sense: it can never disagree with the runs.
- Artifacts and project blobs are kept in the store itself: as files in the file backends, as
  bytes in the database in the PostgreSQL backend.

## Listing

`RunStorage.list_runs` and `list_conversations` answer the run history and the list of
conversations a page at a time, for the reader allowed to see them (`dd_harness.listing`).

- **Order.** Runs come newest first, in reverse stored order (invariant 3); conversations by the
  stored place of their latest turn, the most recently active first. A delegated child is listed
  as a run, never as a turn.
- **Reader.** A `Readable` names a principal and the projects they may read: a run in one of those
  projects is included, and a run in no project if it acted for the principal. A conversation is
  judged on its first turn. Which projects a person may read is the caller's to decide, from the
  project log ([Projects](projects.md)): `ProjectStorage.project_ids(naming=…)` finds the projects
  whose events name the principal (`dd_harness.listing.principals_named`), and
  `dd_harness.project_access.readable_projects` keeps those in which their role lets them read.
  The log finds where to look and never decides; the roles are read from each project's own log.
- **Cursors.** A page names the cursor of the next, or none on the last. A cursor is the stored
  place of the page's last item, opaque to the caller: the next page holds what was stored before
  it, so a run stored while a person pages comes before the first page, not inside a later one.
  A malformed cursor names an empty page (invariant 8).
- **Cost.** The file backend scans `invocations.jsonl` for every page (`scan_runs`,
  `scan_conversations`, which define the answer every backend gives). The PostgreSQL backend reads
  one page from an index, whatever the size of the store (see below).
- **Projects.** `GET /api/projects` lists a person's projects most recently active first, by
  their latest conversation's last turn or else their creation, and reads only those projects,
  never every project in the store. A cursor names the last project of a page by that time and
  its identifier, so a project worked in while a person pages comes before the first page.
- **Over HTTP.** `GET /api/runs`, `GET /api/conversations` and `GET /api/projects` in the app, and
  `/runs` and `/conversations` in the workbench, take `?limit=` (50 unless given, at most 200) and
  `?before=`, answer the page's items as a JSON list, and name the next page in a `Link` header
  with `rel="next"` (`dd_harness.transport.paging`).

The conformance kit checks that a backend's pages hold what the scan does, in the same order, for
every reader, and that a malformed cursor names nothing
(`check_runs_are_listed_newest_first_a_page_at_a_time`,
`check_conversations_are_listed_by_their_latest_turn`,
`check_a_listing_includes_what_its_reader_may_read`, `check_a_malformed_cursor_names_an_empty_page`).

## Project rules and the project log

`ProjectStorage` is what callers use, and its methods carry the project rules: folding the log
into documents and versions, refusing a stale change, checking a decision, an answer or an
inventory against its schema. Those rules are written **once**, in the harness, over a
`ProjectLog`: the part a backend provides. A project log can read a project's events in order,
run an exclusive section in which the rules read and append (invariants 10 and 11), keep and read
content by digest, find a conversation's project, and list projects. Nothing in a `ProjectLog`
decides whether a change is allowed.

The rules are `dd_harness.projects.Projects`, constructed over a `ProjectLog`. Every change runs
in a section of the log: the rules read the log there, decide, and append the change's events in
one call, or a `document_change_refused` event, and raise `ChangeRefusedError` once the section has
ended. The rules fill each event's identifier and timestamp, so every backend stores the same
events. Content is kept by digest before the event that names it is appended, outside the
section; content kept for a change that is then refused is named by nothing and harms nothing.
`FileProjectLog` (`dd_harness.project_files`) is the file log, and `ProjectStore` is `Projects`
over it, keeping the file backend's name and constructor.

## Adding a backend

A backend:

1. is a module of the harness, whose driver is an optional extra of `data-director-harness`
   named after it, as `serve` is for `uvicorn` ([System and boundaries](system.md)). The settings
   factory imports the module only when its scheme is named, so a deployment on files does not
   install the driver;
2. implements `RunStorage` and `ProjectLog`, keeping every guarantee above;
3. passes the conformance kit (`check_run_storage`, `check_project_log` and
   `check_project_rules`), run from the harness's tests against a real database. Those tests
   are skipped when no database is named for them, and CI names one;
4. changes its schema only through numbered SQL files, applied by an explicit command. Start-up
   refuses a database whose schema is older or newer than the build expects, naming the command.
   Nothing alters a schema as a side effect of serving.

The PostgreSQL backend uses `psycopg` (version 3) and plain SQL
([dependency register](dependencies.md#the-register)).

## The PostgreSQL backend

`dd_harness.postgres` keeps both records in one database, or in two: `DD_RUNS_DIR` and
`DD_PROJECTS_DIR` may name the same location. Its tables are in the first schema of the
connection's `search_path`, which a location may choose with
`?options=-csearch_path%3D<schema>`.

- **Schema.** The numbered files in `dd_harness/postgres/migrations/` are the schema, and
  `dd_schema` records which have been applied. `dd-harness storage migrate [LOCATION]` applies
  those a database lacks, under a lock so that two commands never apply one file twice;
  `dd-harness storage status` prints the version and exits 1 if it is not this build's. With no
  location they act on the `postgresql://` locations `DD_RUNS_DIR` and `DD_PROJECTS_DIR` name.
  Opening a store reads the version and refuses any other (invariant 14, "Adding a backend").
- **Runs.** `runs` holds each run's envelope, request and prompts in one row, with its
  `conversation_id` in a column of its own and indexed, so a conversation is an indexed query.
  `seq` is the stored order: a run takes it in a transaction that holds a lock for the length of
  one insert, so runs are committed in the order of their `seq` and a reader never sees a later
  run before an earlier one (invariant 3). Class schemas are in `run_schemas` by digest and
  artifacts in `run_artifacts`, as bytes.
- **Listing.** A run's `parent_invocation_id`, `project_id` and principal are copied into columns
  of `runs`, indexed with `seq` for each way a reader may see a run. `conversation_index` has a
  row per conversation, written in the transaction that stores each turn: its first turn's
  project, principal, agent and time, how many turns it has, and its latest turn's place, status
  and time. A page is one scan of an index per way in (the reader's own runs, and each of their
  projects), each stopping after a page, so it reads entries in proportion to the page and the
  reader's projects, not to the store. `harness/tests/test_postgres.py` asks the database for the
  plan of each listing over twenty thousand runs and checks that no table is read whole.
- **Projects.** `projects` has a row per project, which a section locks with
  `select … for no key update`: sections of one project exclude one another, and keeping a blob,
  whose foreign key takes a weaker lock on the same row, is not held up by one. Events are in
  `project_events` in the order of `seq`; a `conversation_started` event's conversation is in an
  indexed column, so `project_of` is an indexed query. `project_principals` has a row for each
  principal a project's events name, written in the transaction that appends them, so
  `project_ids(naming=…)` is an indexed query; the test asks the database for its plan over twenty
  thousand projects and checks that it reads that principal's entries, not the table. Content is
  in `project_blobs`.
- **Documents are `json`, not `jsonb`.** `jsonb` refuses an escaped NUL (`\u0000`), which a
  researcher's text may hold, and does not keep the order of keys. A document is read back as it
  was given; what the backend looks up is copied into a column of its own.
- **Connections.** Each call opens a connection and closes it, so a store is safe to share between
  threads and needs no closing. A connection pool is a performance step, TODO(#712).

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
  scan moves to the database. In the database, listing runs and conversations reads a page from
  an index ("Listing"), and finding a conversation's project, or the projects whose events name a
  principal, is an indexed query. The file backends find a principal's projects by reading every
  project's log.
- **Operations.** A documented and tested backup and restore of the database, and a health check,
  are TODO(#525).

## Open questions

- How long runs, conversations and projects are kept, what deleting one removes, and how a
  person's data in them is erased, now that the record is a database from which rows can be
  deleted, TODO(#156).
- Whether deposit packages and other large blobs move to object storage, TODO(#525).
