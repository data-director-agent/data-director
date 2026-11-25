# Case files

## Intent and scope

A case file is the record of one run, conversation or project, exported so that a developer or a
coding agent can see exactly what happened and reproduce a failure off the deployment. A problem
report carries only identifiers ([The app](app.md)); a smoke test's findings are what a tester
saw. A case is the record behind them.

A case is exported by an operator, on the deployment's command line (`dd-harness case export`) or
from the admin service's run, conversation and project pages ("Download case"), and checked by
whoever receives it (`dd-harness case verify`). The test kit opens one as stores
(`dd_harness.testing.open_case`), so a reported failure becomes a failing test, which is how a case
reaches the conformance report and the only way it does ([Evaluation and conformance](evaluation.md)).

A case can carry the service journal's lines that name it, and a case that must leave the
institution can name its content by digest instead of carrying it.

Out of scope here: a person's own download from the app (TODO(#1586)), and the workbench's import
of a case (#15).

## Invariants

1. **A case is a filtered copy of the stores, in the file layout.** Its `runs/` directory is a
   run store and its `projects/` directory a project store, as the file backends write them
   ([Storage](storage.md)), whatever backend the deployment uses. Every reader of the stores opens
   a case unchanged: point `DD_RUNS_DIR` and `DD_PROJECTS_DIR` at it. Nothing in them is
   rewritten: each envelope, request, prompt set, class schema, artifact, event and blob is as the
   deployment stored it (`harness/tests/test_casefile.py`).
2. **What a scope holds is fixed.**
   - A run holds the run and every run delegated from it, however deep.
   - A conversation holds every turn and every delegated child, and the log of the project it was
     started in.
   - A project holds its log, every blob an event names, and the same runs its provenance graph
     reads ([Provenance](provenance.md)).
3. **`case.json` names every other file by its SHA-256**, with the format (`dd-case-1`), the
   scope, who exported it and when, the harness and contract versions, and the agents and policy
   digests of its runs, and whether its content is `carried` or `named`. Its own digest, which
   the export and `case verify` print and the admin service sends as `X-Case-Digest`, names the
   whole case.
4. **A case is checked, not trusted.** `case verify` checks:
   - every file against `case.json`;
   - every envelope against the contract;
   - the input hash on each run's root span against the hash of its stored request's input;
   - the grounding linter over each run's stored trace against the report the run stored.
     The linter reads `withheld.json` where there is one, since that was what it linted.

   It does not fetch a source outside the case again, and its report says so. In a case whose
   content is named it checks the files only, and its report says why. Opening a case writes
   nothing to it.
5. **`CASE.md` and `timeline.jsonl` are derived.** `CASE.md` lists the runs that did not succeed
   first, with what to open for each. `timeline.jsonl` merges project events, stage records, run
   completions and journal lines by time, each naming its file. Neither is authoritative; the
   stores are.
6. **Exporting is a security event**, `case.exported`, naming who exported which scope
   ([Security baseline](security.md)).
7. **A zip depends on its content alone**: fixed entry times, entries in path order.
8. **Named content fails safe** (`--content-named`; `dd_harness.casefile.naming`). Each record is
   named on its way into the case, before the file backends write it, so every copy of it they
   write (an envelope is in the index and in its run's directory) says the same. A string is kept
   only when the key it sits under says it is structure: an identifier, a time, a status, a code,
   a version, a digest, a schema, a title or a name, the checks' violations, and the trace's
   `dd.*` attributes. Every other string is the RFC 6920 `ni:` URI of its UTF-8 bytes, so a field
   added later is named, not carried. Numbers, booleans and keys are kept, and so are class
   schemas, which are code, and the checks' text reports (`grounding.txt`, `sources.txt`). No
   project blob is copied: the events name each by its digest. This follows
   [Provenance](provenance.md), invariants 5 and 6: titles, file names and a principal's
   identifier and display name are carried; text is not. `CASE.md` and `timeline.jsonl` are
   derived from the named records. A named case opens as stores like any other, and the root
   span's input hash lets whoever holds the original match a run to its request.
9. **The journal is read, not trusted, and only what names the case is kept** (`--journal`;
   `dd_harness.casefile.journal`). The lines of the deployment's units (`data-director*`) from
   five minutes before the case's first record to five after its last that name one of its runs,
   conversations, project or traces are kept in `journal.jsonl`, each as its time, unit, priority
   and either its message or, for a line that is a JSON object (the security log), that object.
   A journal that cannot be read stops the export rather than leaving the lines out silently.

## Boundaries and contracts

- **Privacy.** A case holds research content and personal data: messages, answers, names,
  drafts, and the output a check withheld from the researcher ([Storage](storage.md),
  invariant 5). There is no redaction pass ([Security baseline](security.md), rejected
  alternatives). Secrets never reach a record, so none reaches a case, and the span-scrub
  sentinel checks a case too. A case travels **out of band**: the operator hands it to the
  developer privately, and a public issue names only its scope, identifier and `case.json` digest.
- **Who may export.** Only someone with the deployment's command line and its stores, who can
  already read every record. The admin service adds nobody: it has no sign-in and answers on
  loopback only, so whoever reaches it has an SSH session on the VM. It names itself as the
  exporter (`urn:dd:deployment:admin`). A profile key decides who may export once a surface that
  people sign in to does, with a person's own download from the app (TODO(#1586)).
- **Compatibility.** A case is read by the build that reads its stores. A change to the store
  layout or the manifest that an older reader would misread changes the format's version.

## Rationale

The record a developer needs already exists: each run is stored whole, with its trace, checks,
stages and crate, and each project keeps its log. A new format would be a second copy that could
disagree with the first, and would need a reader of its own. A filtered copy in the file layout
needs no reader: the admin service, the workbench and the test kit already read it. Exporting
through the storage protocols and writing through the file backends means a PostgreSQL deployment
exports the same layout as a file one.

## Rejected alternatives

- **The provenance graph as the export.** It names content by digest and carries none
  ([Provenance](provenance.md), invariant 5), so it cannot show what an agent was given or said.
- **A backup (`deploy/backup.sh`).** It holds every person's records and the deployment's
  secrets, not one case.
- **A redaction step on export.** It would be a second, weaker version of the security baseline's
  invariant 2, and would hide what a developer needs to see. Naming content by digest is not
  redaction: it is all or nothing, decided by key, and `case.json` says so.
- **Naming content by a list of the keys that hold it.** A field added to a record later would be
  carried until someone added it to the list; an allow-list of structure fails safe.

## Non-functional requirements

- Exporting a conversation reads its runs through the store's conversation filter. A project or a
  run outside any conversation may scan the run index once, which is acceptable for an operator
  command. The admin service builds a case in its private `/tmp` and removes it once sent.
- Reading the journal for a case reads only the case's time span, padded.

## Open questions

- TODO(#1586): who may download a case from the app, as a profile key, and what such a case
  leaves out (`withheld.json`).
