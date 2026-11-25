---
name: debug-case
description: Read a Data Director case file (a directory or zip holding case.json, CASE.md, timeline.jsonl, runs/ and projects/) to find why a run, conversation or project failed, and reproduce the failure as a test. Use when someone hands over a case, names a case.json digest, or asks to debug a run exported with `dd-harness case export` or the admin service's "Download case".
---

# Debugging a case

A case is a filtered copy of a deployment's run and project stores, exported so that a failure can
be reproduced off the deployment ([`docs/specs/casefile.md`](../../../docs/specs/casefile.md)).
`runs/` is a valid `DD_RUNS_DIR` and `projects/` a valid `DD_PROJECTS_DIR`, so every reader of the
stores opens it unchanged.

## A case holds personal data

It holds research content and personal data: messages, answers, names, drafts, and what the
checks withheld from the researcher. Therefore:

- **Never commit a case**, or any file copied from one, and never paste its content into an
  issue, pull request, commit message or log. Name a case only by its scope, identifier and
  `case.json` digest.
- Keep it outside the repository (for example in a scratch directory) while you work.
- A test that reproduces the failure uses a minimal synthetic fixture that has the same shape,
  never the case itself.

## 1. Check it before reading it

```bash
uv run dd-harness case verify path/to/case.zip
```

This checks every file against `case.json`, every envelope against the contract, each run's input
hash against its stored request, and the grounding linter over each stored trace against the
report the run stored. Note the `case.json sha256:` line: it names the case. A failed check is a
finding in itself: a record that does not match what the deployment says it did.

If `case.json` says `"content": "named"`, every text is an RFC 6920 `ni:` digest and the project's
files are left out; only the files are checked. Debug from structure: identifiers, statuses,
reason codes, stages, check reports and the order of events.

## 2. Read in this order

1. `CASE.md`: the scope, the build (harness and contract versions), and the runs that did not
   succeed first, each with what to open.
2. For each run that did not succeed, under `runs/<invocation_id>/`:
   - `envelope.json`: the outcome, reason code, problem and delegations;
   - `stages.jsonl`: what the person saw, step by step, with the check reports and tool calls;
   - `spans.jsonl`: the trace (the conductor's spans and the agent's, after secrets were dropped);
   - `grounding.txt` and `sources.txt`: what the grounding linter and source check found;
   - `withheld.json`, if present: what the agent returned before a check or the project withheld
     it. This is never shown to the researcher; do not quote it anywhere.
   - `request.json` and `prompts.json`: what the agent was given and what its model was sent.
3. `timeline.jsonl`: project events, stages, run completions and, if present, `journal.jsonl`
   lines, merged by time. Read it around the failure to see what came just before.
4. `projects/<project_id>/events.jsonl`: the project's log, if the case holds one.

To browse it, serve the admin view over it:

```bash
DD_RUNS_DIR=path/to/case/runs DD_PROJECTS_DIR=path/to/case/projects uv run dd-admin serve
```

## 3. Reproduce it as a test

Open the case as stores with the test kit, and confirm the failure there first:

```python
from dd_harness.testing import open_case

with open_case(Path("path/to/case.zip")) as (runs, projects):
    envelope = runs.get(invocation_id)
    request = runs.get_request(invocation_id)
```

Then write the failing test in the package whose job it is (the root `AGENTS.md`, "Where code
goes"): replay the request through the conductor with the test kit's doubles, or call the agent or
check directly with the input that failed. Rebuild that input as a small synthetic fixture that has
the same shape; do not load the case in the committed test. Assert on structure (status, reason
code, which check failed), not on wording.

## 4. Report

In the issue or pull request, name the case by its scope, identifier and `case.json` digest, and
describe the cause in terms of code and structure. Quote nothing from the case.
