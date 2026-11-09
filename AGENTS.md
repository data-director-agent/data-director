# Data Director

<!-- Kept short on purpose: this file loads into every coding-agent session. Put only what an agent
cannot work out from the code, and link to the canonical document for the rest. -->

A reference implementation of the RDA [Data Director Agentic AI Blueprint](https://doi.org/10.15497/RDA00157).
Python 3.14 and `uv`; the root is a uv workspace. `harness/`, `agents/` and `workbench/` have
their own `AGENTS.md`: read the one for each package you change.

## Where code goes

Put code in the package whose job it is, not the one you have open; the full table is in
[CONTRIBUTING.md](CONTRIBUTING.md#repository-structure).

- `sdk/`: what agents and the harness share (contract, evidence, span helpers, agent server).
- `harness/`: all governance (conductor, policy gate, checks, stores, provenance, A2A way in) and
  the test kit `dd_harness.testing`. Depends only on `sdk/`.
- `agents/<name>/`: one package and A2A service per agent; prototypes too, marked alpha by version.
- `app/`: the app people use. `workbench/`: development client for agent authors. Both are
  clients of the harness, hold no governance, and nothing else depends on them; the app never
  depends on the workbench.
- `inventory/`: `dd-inventory`, depends on no other member. `scripts/`: repository tooling.
- `sdk/browser/`: `@data-director/agent-view`, the TypeScript and React library every front end
  uses to show an agent card, its extensions and its payloads. Put card and payload rendering
  there, not in one app.
- `docs/`: what governs every package (specs, contract, glossary, `requirements.yaml`,
  `reviews.yaml`). `docs/blueprint/` is the published Blueprint, generated and read-only:
  requirements are in `07-functional-specification.md` and cited by ID (`R3`, `R3.1`).
- Each member imports only what it declares and reads no path outside itself
  (`scripts/check_boundaries.py`).

## Commands

Run from the root; config for pytest, ruff and mypy is in the root `pyproject.toml`.

```bash
uv sync --all-packages --all-extras             # after adding a workspace member
uv run pytest                                   # parallel, network blocked, no credentials
uv run ruff check . && uv run ruff format .
uv run mypy
uv run dd-gen-schema [path/to/schema.yaml]      # after editing a LinkML schema (core by default)
uv run python scripts/check_boundaries.py
```

Every other CI job, with its local command, is in
[CONTRIBUTING.md](CONTRIBUTING.md#code-style-and-testing). `uv run pytest` rewrites stale
fixtures in `app/web/fixtures` and `sdk/browser/tests/fixtures`; commit them.

## Rules

1. **Formats are decided; components sit behind interfaces.** The core LinkML schema, the `dd.*`
   trace attributes, evidence canonicalisations and the outcome vocabulary are fixed; changing
   one changes a spec in the same pull request ([specs](docs/specs/README.md)).
2. **Adopt the plumbing; own the governance.** Bespoke code only for the outcome vocabulary and
   reason codes, policy gate, input check, grounding linter, evidence hashing, each agent's
   decisions and the conformance traceability rule ([Dependencies](docs/specs/dependencies.md)).

- Every `schema/generated/` is generated: edit the LinkML file beside it and run `dd-gen-schema`.
- The core schema, SDK, harness, app and workbench name no agent class ([Contract](docs/specs/contract.md)).
- Nothing but tests imports an agent; others reach agents through `RemoteAgent`.
- Only the conductor fills identifiers, timestamps, telemetry, grounding mode, input hash and lineage.
- A content problem is an outcome, not an exception; exceptions are for programmer and
  configuration errors.
- A canonicalisation is registered in `dd_sdk.evidence.CANONICALISATIONS`; an existing name's bytes
  never change.
- Evaluation is not conformance; baselines change only in their own commit
  ([Evaluation and conformance](docs/specs/evaluation.md)).
- Never write a `docs/reviews.yaml` entry yourself ([conformance](docs/conformance.md)), and never
  edit `CONFORMANCE.md` by hand (it is generated).
- Tests: assert on structure, not wording or counts; requirement markers only on tests that
  exercise that ID ([Writing tests](CONTRIBUTING.md#writing-tests)).
- Workflows: pin every `uses:` to a full commit SHA (`# v1.2.3`) and run `uvx zizmor .github`.

## Commits and pull requests

- Never sign off: no `git commit -s`, and no `Signed-off-by` line in a commit or a pull request
  description, whatever your git identity. Only a person can certify the work
  ([DCO](https://github.com/data-director-agent/.github/blob/main/DCO.md)).
- `main` is squash-merged with the pull request's title and description as the message, so commit
  trailers do not reach it. End the description with `Co-authored-by: <model> <noreply@anthropic.com>`
  as its last line, after any footer, and leave the line below it for the person you work for,
  who signs off there before merge. CI ("Developer Certificate of Origin") fails until they do.
- The pull request title is a Conventional Commit, `type(scope)!: summary`, lower case, no full
  stop, at most 90 characters, such as `feat(app): register every in-tree agent`. Check it before
  opening and after editing:
  `python3 scripts/check_names.py --title "…" --branch "$(git branch --show-current)"`.
  Keep an assigned `claude/…` branch.
- Put no labels on pull requests by hand ([labels](CONTRIBUTING.md#issues-and-labels)).
- If **Project status** fails asking for `GH_TOKEN`, that is the unset `PROJECT_TOKEN` secret, not
  your change: do not chase it; tell the user that the organisation owner must set it.

## Issues and the board

Keep the [project board](https://github.com/orgs/data-director-agent/projects/1) accurate as you
work, following [Coding agents](https://github.com/data-director-agent/.github/blob/main/PLANNING.md#coding-agents)
in the planning guide. In short: work from an issue, `Closes #n` in the pull request, assign the
person you work for (never yourself), and file follow-up work as issues. A cloud session cannot
set project fields: write `Board: move #n to <Status>` in the pull request and your final message,
and never report a board change you did not see made.

## Writing

British English (`organisation`, `behaviour`, `licence` as noun), declarative and without hype,
for researchers and engineers. Mark anything undecided `TODO(#123)` with the issue that will
resolve it, never a plausible guess; `scripts/check_todos.py` rejects a marker without one.
