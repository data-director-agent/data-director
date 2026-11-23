# Case files

## Intent and scope

A case file is the record of one run, conversation or project, exported so that a developer or a
coding agent can see exactly what happened and reproduce a failure off the deployment. A problem
report carries only identifiers ([The app](app.md)); a smoke test's findings are what a tester
saw. A case is the record behind them.

A case is exported by an operator on the deployment's command line (`dd-harness case export`) and
checked by whoever receives it (`dd-harness case verify`). The test kit opens one as stores
(`dd_harness.testing.open_case`), so a reported failure becomes a failing test, which is how a case
reaches the conformance report and the only way it does ([Evaluation and conformance](evaluation.md)).

Out of scope here: the admin service's download and a person's own download from the app (#1576),
the service journal and content written as digests (TODO(#1581)), and the workbench's import of a
case (#15).

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
   digests of its runs. Its own digest, which the export prints, names the whole case.
4. **A case is checked, not trusted.** `case verify` checks:
   - every file against `case.json`;
   - every envelope against the contract;
   - the input hash on each run's root span against the hash of its stored request's input;
   - the grounding linter over each run's stored trace against the report the run stored.
     The linter reads `withheld.json` where there is one, since that was what it linted.

   It does not fetch a source outside the case again, and its report says so. Opening a case
   writes nothing to it.
5. **`CASE.md` and `timeline.jsonl` are derived.** `CASE.md` lists the runs that did not succeed
   first, with what to open for each. `timeline.jsonl` merges project events, stage records and
   run completions by time, each naming its file. Neither is authoritative; the stores are.
6. **Exporting is a security event**, `case.exported`, naming who exported which scope
   ([Security baseline](security.md)).
7. **A zip depends on its content alone**: fixed entry times, entries in path order.

## Boundaries and contracts

- **Privacy.** A case holds research content and personal data: messages, answers, names,
  drafts, and the output a check withheld from the researcher ([Storage](storage.md),
  invariant 5). There is no redaction pass ([Security baseline](security.md), rejected
  alternatives). Secrets never reach a record, so none reaches a case, and the span-scrub
  sentinel checks a case too. A case travels **out of band**: the operator hands it to the
  developer privately, and a public issue names only its scope, identifier and `case.json` digest.
- **Who may export.** Today only someone with the deployment's command line and its stores, who can
  already read every record. A profile key decides who may export once another surface does
  (#1576).
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
  invariant 2, and would hide what a developer needs to see.

## Non-functional requirements

- Exporting a conversation reads its runs through the store's conversation filter. A project or a
  run outside any conversation may scan the run index once, which is acceptable for an operator
  command.

## Open questions

- TODO(#1581): the service journal lines that name a case's runs, and content written as digests
  for a case that must leave the institution.
