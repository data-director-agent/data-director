# Storage

## Intent and scope

The harness keeps two records: the **run storage**, which holds every invocation the conductor ran,
and the **project storage**, which holds each project's log ([Projects](projects.md)). Both are
kept in files today. A deployment that grows past one host, or that wants queries the files cannot
answer quickly, will move them to a database, PostgreSQL or MongoDB for example.

This spec covers what the harness asks of a store, so that such a move replaces one backend with
another and changes no caller. Each store is a `typing.Protocol` in `dd_harness.storage`:
`RunStorage` and `ProjectStorage`. The file backends, `RunStore` (`dd_harness.store`) and
`ProjectStore` (`dd_harness.projects`), implement them.

It does not cover what a run or a project contains ([Contract](contract.md), [Projects](projects.md),
[Disclosure](disclosure.md)), nor which database to use.

## Invariants

1. **Callers reach a store through its protocol.** The conductor, conversations, disclosure, the
   project facts, the app and the workbench name `RunStorage` and `ProjectStorage`, never a file
   backend's layout. Only a backend's own tests read its files (`RunStore.root`, `run_dir`,
   `ProjectStore.root`). Enforced by mypy over the callers' annotations.
2. **A run is written once.** Storing an envelope whose `invocation_id` is already stored raises
   `FileExistsError` and changes nothing the store returns. The conductor refuses a duplicate
   request before it runs ([Contract](contract.md)), so this is the last guard, not the first.
3. **Envelopes come back in the order stored.** The conductor stores a run when it finishes, so
   this is the order runs finished in, which is the turn order of a conversation
   ([Orchestration](orchestration.md)). A store may be asked for one conversation's envelopes
   alone; it returns them in the same order.
4. **Everything else a run keeps is a named artifact.** Beside the envelope, the request, the
   prompts and the class schemas, the conductor keeps `spans.jsonl`, `grounding.txt`,
   `sources.txt` and, unless `DD_WRITE_CRATE=0`, the Process Run Crate as one artifact per file
   under `crate/`. An artifact belongs to a stored run, is written once, and is read back byte for
   byte. Its name is a relative path of plain segments and cannot name the run's own files.
5. **A class schema is kept once under its digest**, and its bytes never change
   ([Contract](contract.md)).
6. **Prompts are read only through `get_prompts`**, by whoever may read the run. No envelope,
   artifact or crate carries one ([Disclosure](disclosure.md)).
7. **A malformed name names nothing.** An `invocation_id`, digest, artifact name or `project_id`
   that is not well formed returns nothing or is refused, so no caller can reach outside the
   store.
8. **A project's log is append-only and ordered.** Events are never changed or removed and come
   back in the order appended ([Projects](projects.md), invariant 2).
9. **A checked change is atomic for its project.** An edit, a decision or a draft reads the log
   and appends its events with no other change to that project between, and the events it writes
   together are kept together or not at all. Projects do not wait on one another. The file backend
   holds a lock per project, which serialises changes within one harness process only; a database
   backend uses a transaction or a conditional insert, which also holds across processes.
10. **A conversation's project is found from what is stored**, so `project_of` holds after a
    restart.
11. **A backend is chosen by its location.** `DD_RUNS_DIR` and `DD_PROJECTS_DIR` each name a
    path or a `file://` URL, which select the file backends. Any other scheme stops start-up with
    `SettingsError`, naming the schemes this build supports (`dd_harness.settings.run_storage`,
    `project_storage`; `harness/tests/test_storage.py`).
12. **The file backends keep their layout.** A run is `<invocation_id>/` beside
    `invocations.jsonl` and `schemas/`; a project is `<project_id>/events.jsonl` beside its
    blobs. The layout is in the docstrings of `store.py` and `projects.py`, and
    `harness/tests/test_harness.py` and `test_projects.py` read it.

Invariants 2 to 10 are the guarantees in the protocols' docstrings. The conformance kit
(`dd_harness.testing.check_run_storage`, `check_project_storage`) checks each of them through the
protocol alone, and `harness/tests/test_storage.py` runs it against the file backends.

## Boundaries and contracts

- The protocols are structural. A backend implements their methods; it neither imports nor
  subclasses anything from `dd_harness.storage`, so it can live in a package of its own.
- `append` stores the documents it is given. The conductor has already checked them against the
  contract; a backend does not check them again, and may index any field of the envelope.
- `where` names a run's location for a person (a path, or a URI for a database). Nothing parses it.
- `dd_harness.provenance` builds the crate in a temporary directory and returns its files, and the
  conductor keeps each as an artifact. The crate's content does not depend on the backend, and the
  file backend holds the same `<run>/crate/` it did before artifacts existed.
- Conversations are derived from the run storage, through `iter_envelopes(conversation_id=…)` and
  `get_request` ([Orchestration](orchestration.md), invariant 2).

## Adding a backend

A database backend:

1. lives in a package of its own, which depends on the harness and is not imported by it
   ([System and boundaries](system.md));
2. implements `RunStorage` or `ProjectStorage`, keeping every guarantee above;
3. passes the conformance kit, run from its own tests against a real database;
4. is selected by its location's scheme, such as `postgresql://`.

How the factories find a backend in another package, and which database comes first, are open,
TODO(#141). Moving existing file stores into a database is part of the same work.

## Rationale

The file layout used to leak: `RunStore.append` returned the run's directory, the conductor wrote
the trace, the reports and the crate into it, and the app and the workbench CLI read files beside
the envelope. Each of those callers would have had to change with the backend. Named artifacts
give every such file one way in and out, and keep the file backend's layout as it was, so existing
run stores are read without migration.

Protocols rather than abstract base classes keep a backend free of an import from the harness and
let the file backends keep their names and constructors. The guarantees are stated in the
protocols' docstrings and checked by a kit any backend can run, because a type checker sees the
methods but not the ordering, atomicity or write-once rules that callers rely on.

## Rejected alternatives

- **A conversation store beside the run store.** A conversation is derived from its runs
  ([Orchestration](orchestration.md)); a second record would drift from them. The conversation
  filter on `iter_envelopes` lets a database answer the same question with an indexed query.
- **Returning a path from the run store.** It ties every caller to files, which is the leak this
  design removes.
- **Building the crate inside the store.** The crate is provenance, not storage. Built apart and
  kept as artifacts, it is the same whatever the backend.

## Non-functional requirements

- **Security.** No name a caller supplies reaches outside the store (invariant 7). Prompts are
  kept apart from everything that leaves the store (invariant 6).
- **Portability.** The file backends need only a local file system, and are the default for
  development and for a single-host deployment.
- **Performance.** The file backends scan: conversations read every envelope, and the first call
  to `project_of` reads every project's log. An index, or a database that keeps one, is
  TODO(#141).

## Open questions

- Which database backend comes first, how the factories find it, and how existing stores move
  into it, TODO(#141).
- Indexing the file backends, or retiring them for anything but development, TODO(#141).
