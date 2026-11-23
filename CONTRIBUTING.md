# Contribution guide

Thank you for your interest in contributing to `data-director`, a reference implementation of the
Research Data Alliance's Data Director Agentic AI Blueprint.

The organisation-wide [contribution guide](https://github.com/data-director-agent/.github/blob/main/CONTRIBUTING.md)
applies here: when to open an RFC, the Developer Certificate of Origin sign-off (`git commit -s`)
and the pull request workflow. [Governance](https://github.com/data-director-agent/.github/blob/main/GOVERNANCE.md)
and the [code of conduct](https://github.com/data-director-agent/.github/blob/main/CODE_OF_CONDUCT.md)
are also organisation-wide. This file covers what is specific to this repository. New here? Start with
[your first contribution](docs/guide/developer-guide/first-contribution.md): a table of what you
might want to do, and the steps from a fresh clone to a pull request.

## Contributing without writing code

Much of what the project needs is judgement rather than code: whether advice is right for a
discipline, whether a decision suits an institution, whether a requirement is met. Each has an
issue form, chosen when you [open an issue](https://github.com/data-director-agent/data-director/issues/new/choose):

* **Conformance review**: you examined a Blueprint requirement, such as accessibility (C6) or the
  appropriateness of standards advice (R3), and found it met or not met. A maintainer records it
  in the review record on your instruction ([the conformance report](docs/conformance.md)).
* **Spec feedback**: a question about, or objection to, how one of the
  [specifications](docs/specs/README.md) says Data Director is built.
* **Blueprint reading**: the project reads a [Blueprint](docs/blueprint/README.md) requirement
  differently from you, or misses one.
* **Feedback on advice**: an agent's advice was wrong, incomplete or unhelpful, and you can say
  what good advice would have been.

## Repository structure

The repository root is a uv workspace. Put each piece of code in the package whose job it is, not
the one you happen to have open. The workbench was the first package, and that does not make it
the default home for anything.

| What you are writing | Where it goes |
| --- | --- |
| The contract, evidence, span helpers, the agent server: anything agents and the harness share | `sdk/` (`dd_sdk`) |
| Governance: the conductor, policy gate, input check, grounding linter, source check, stores, provenance, sign-in, the A2A way in ([System and boundaries](docs/specs/system.md)) | `harness/` (`dd_harness`) |
| Test doubles and helpers that any way in or any agent can use | `harness/` (`dd_harness.testing`) |
| One agent's logic, schema, data, scripts, sample inputs, evaluation cases and tests; prototypes too, marked alpha by their version (`agents/README.md`) | `agents/<name>/` (sample inputs are still in `workbench/samples/` until TODO(#275) moves them) |
| The app people use: its server, configuration (`app/config/`) and browser shell (`app/web`, React and TypeScript, Node 22 or later; [The app](docs/specs/app.md), designed from `docs/ui/best-practices.md`) | `app/` |
| The operators' read-only view of a deployment, on loopback only ([The admin service](docs/guide/operations/admin.md)) | `admin/` |
| The model broker, which holds people's own model keys and makes their model calls ([A person's own model account](docs/specs/model-accounts.md)) | `broker/` |
| The deposit broker, which holds people's own repository tokens and makes draft deposits for them ([Deposit](docs/specs/deposit.md)) | `deposit-broker/` |
| The development client for agent authors: the `workbench` CLI, viewer and its development configuration | `workbench/` |
| `dd-inventory`, which a researcher runs where their data live to describe a dataset's files ([Projects](docs/specs/projects.md)) | `inventory/` |
| The PID resolver, an MCP server that resolves DOIs, ORCID iDs, ROR identifiers and ISSNs for agents through the tool gateway | `mcp-pid/` |
| `dd-units`, a library that turns a unit as a person writes it into a UCUM code | `units/` |
| `dd-subjects`, subject classifications (OECD Fields of R&D, ANZSRC Fields of Research) to suggest a field of study from | `subjects/` |
| `dd-formats`, file formats described from the records of a pinned PRONOM release | `formats/` |
| `dd-duo`, data use conditions from a pinned release of the GA4GH Data Use Ontology (DUO) | `duo/` |
| `dd-journals`, journals by ISSN and title, from a pinned OpenAlex snapshot built at install | `journals/` |
| `dd-dmp-template`, the core requirements of a Data Management Plan (after Science Europe's) | `dmp-template/` |
| The FAIRsharing server, an MCP server that looks up FAIRsharing records for agents through the tool gateway | `mcp-fairsharing/` |
| The SPDX server, an MCP server that looks up licences in a pinned release of the SPDX licence list for agents through the tool gateway | `mcp-spdx/` |
| The subjects server, an MCP server that lists the fields of a subject classification (ANZSRC, OECD) for agents through the tool gateway | `mcp-subjects/` |
| The DOAJ server, a client and MCP server that reads an open access journal's terms from the Directory of Open Access Journals | `mcp-doaj/` |
| Repository tooling and tests of the repository as a whole (scripts, shipped configuration, cross-package checks) | `scripts/`, `scripts/tests/` |
| What governs every package: the Blueprint, system overview, specifications, contract, glossary, requirements register, reviews | `docs/` |

A package's own documents are kept with it (`harness/docs/`, `workbench/docs/`). The workbench and
the app are both clients of the harness. Neither holds governance, and neither may be a dependency
of the harness, the SDK or an agent: if a second way in to the harness would need what you are
writing, it belongs in the harness or the SDK. The app's browser shell is drawn from each agent's
manifest and names no agent; it renders the harness's decisions and holds no policy.

Each package keeps to its own directory, so that it can later move to a repository of its own: it
imports only what it declares (tests from its own `dev` group) and reads no path outside itself
(`scripts/check_boundaries.py`). Agent Skills, MCP servers and other resources that do not use the
contract belong in their own repositories in the organisation. [System and boundaries](docs/specs/system.md)
sets out both.

## Changing the design

A [specification](docs/specs/README.md) states how one part is meant to work today, so a change to
the design changes its spec in the same pull request, edited to say what is now true rather than
amended. A change to a fixed format (the schema, the `dd.*` trace attributes, evidence
canonicalisation or the outcome vocabulary) always changes a spec. An issue that proposes one
carries the `needs spec` label. The history of the repository, its pull requests and its RFC
issues are the record of how the design got here; the spec is the result.

## Code style and testing

The Python packages use Python 3.14 and [uv](https://docs.astral.sh/uv/); `app/web` uses Node 22
and npm. `uv run scripts/dd.py setup` installs both sides and `uv run scripts/dd.py doctor`
says what is wrong with a setup (README, "Quick start"). Follow the conventions of the surrounding
code, and describe how you tested your change in the pull request description.

Every pull request runs `.github/workflows/ci.yml`, which ends in one check, **CI passed**, that
passes only when no job it waits for failed or was cancelled. A job skipped because a change does
not touch what it checks counts as passed. A stale CONFORMANCE.md only raises a warning in the coverage job.
`scripts/check_ci_gate.py` fails the Workflows job when a job is left out of the wait. Network
steps that download (browsers, images) retry through `scripts/retry.sh`. Each job can be run
locally from the repository root:

| Job | Locally |
|---|---|
| Pre-commit hooks and Ruff | `uv run ruff check . && uv run ruff format --check . && pre-commit run --all-files` |
| mypy | `uv run mypy` |
| pytest | `uv run pytest --json-report --json-report-file=.report.json` (runs on every core; `-n0` for one process, to debug; CI runs it as three shards, `--test-shard 1/3`, balanced by the durations in `scripts/test_durations.json`: when they drift apart, commit the map from the coverage job's `test-durations` artefact, or write it with `uv run --no-project --python 3.14 scripts/test_durations.py .report-*.json`) |
| Coverage and CONFORMANCE.md (a stale file warns) | `uv run python scripts/conformance_report.py --check` (after pytest, which writes `.report.json`) |
| Generated schemas up to date | `uv run dd-gen-schema && git diff --exit-code -- sdk/src/dd_sdk/schema/generated/` |
| Generated API types up to date | in `app/web`: `npm run gen:api && git diff --exit-code -- src/api/generated/` |
| Packages build and install alone | `uv build --all-packages -o dist && uv run python scripts/check_wheels.py dist` |
| Agents as services (smoke) | `uv run python scripts/smoke_agents.py` |
| PostgreSQL benchmark (`.github/workflows/bench.yml`, its own workflow, weekly and on demand; reports, never gates) | `DD_TEST_POSTGRES=postgresql://postgres@localhost/postgres uv run python harness/scripts/bench_postgres.py` (`--quick` to check it runs) |
| Container image (`.github/workflows/images.yml`, its own workflow) | `docker build -f docker/release.Dockerfile --build-arg REVISION="$(git rev-parse HEAD)" -t data-director:smoke . && python3 scripts/smoke_image.py --image data-director:smoke --revision "$(git rev-parse HEAD)"` |
| Workbench viewer in a browser | `uv run playwright install chromium && uv run pytest workbench/browser_tests` |
| App shell (three jobs: checks, Vitest, Playwright) | in `app/web`: `npm ci && npm run lint && npm run typecheck && npm run build && npm test && npm run e2e` |
| Links and citation file | `lychee --offline --include-fragments '**/*.md'`, `uvx cffconvert --validate`, `uv run scripts/check_citation.py`, `scripts/check_todos.py` and `scripts/check_boundaries.py` |
| Workflows | `uvx zizmor .github`, [actionlint](https://github.com/rhysd/actionlint) and `python3 scripts/check_ci_gate.py`; every `uses:` is pinned to a full commit SHA with the version as a trailing comment (`# v1.2.3`) |
| NGINX site | `sudo bash scripts/check_nginx.sh` (installs nginx; CI runs it on a clean runner) |
| LiteLLM gateway and model broker | in `deploy/llm-gateway`, with Docker: `scripts/testing/ci_env.sh && docker compose -f compose.yaml -f compose.test.yaml up -d --wait && scripts/smoke_test.sh && scripts/testing/broker_e2e.sh`, then `docker compose -f compose.yaml -f compose.test.yaml down -v` (a fake provider: no keys, nothing billed) |
| Developer Certificate of Origin | a person signs off, either with a `Signed-off-by` at the end of the pull request description or implicitly by opening the pull request from their own account (a notice names them), and no coding agent signs off anywhere, which may only co-author (`.github/workflows/dco.yml`, re-run when the description is edited; a problem is a warning, not a failure): `python3 scripts/check_signoff.py BASE HEAD --body-file description.md --author LOGIN` |
| Dependency review | a new dependency with a known advisory of moderate severity or worse is refused |

`.github/workflows/accessibility.yml` checks what people read and use against WCAG 2.2 AA, with
axe-core and reflow at 320 CSS pixels, and ends in its own check, **Accessibility passed**. A pull
request runs each job only when it touches what the job checks, by the rules in
`scripts/ci_changes.sh` that `ci.yml` also uses:

| Job | Locally |
|---|---|
| Documentation site | `uv run --only-group docs mkdocs build --strict && uv run --only-group docs --only-group accessibility scripts/check_site_accessibility.py site` |
| Workbench viewer | `uv run pytest workbench/browser_tests/test_viewer_accessibility.py` |

The app shell's accessibility checks run in the App shell jobs of `ci.yml`.

The pytest suite blocks the network and needs no credentials. It also keeps the JSON fixtures in
`app/web/fixtures`, which the shell's tests read, current: run locally, a test rewrites a fixture
that no longer matches what the server says, so commit what changed. In CI a stale fixture fails
the test instead. The AG-UI cassettes in `app/web/cassettes`, the event streams the harness sends
for each kind of run, are kept the same way by `app/tests/test_ui_cassettes.py`;
`uv run python scripts/record_ui_cassettes.py` rewrites them all. The shell's types for what the
server sends are generated from the app's response models: after changing one, run
`npm run gen:api` in `app/web` and commit `app/web/src/api/generated/` ([The app](docs/specs/app.md),
"API types"). [Writing tests](#writing-tests) says what a test should and should not pin down. `CONFORMANCE.md` is generated;
regenerate it with the same two commands without `--check`. CodeQL (`codeql.yml`) analyses the
Python, JavaScript and TypeScript code and the workflows (in a pull request, only the languages it
changes), and `audit.yml` checks every locked
dependency against the advisory databases each day. Dependabot proposes updates weekly.

### Mutation testing

Coverage shows which code the tests run, not which code they check. Once a week
`.github/workflows/mutation.yml` runs [mutmut](https://mutmut.readthedocs.io) over the governance
code the project owns: evidence hashing (`sdk/src/dd_sdk/evidence.py`), the policy gate
(`harness/src/dd_harness/policy.py`) and the grounding linter
(`harness/src/dd_harness/grounding.py`). The report is the job summary of the latest
[Mutation testing run](https://github.com/data-director-agent/data-director/actions/workflows/mutation.yml):
for each package, the counts, each surviving mutant (a change to the code that no test notices)
with its diff, and the functions no selected test reaches. It is information only: it does not
run on pull requests and never blocks a merge. To close a surviving mutant, add or tighten a test
that the change would fail. Which modules and which tests are set under `[tool.mutmut]` in
`sdk/pyproject.toml` and `harness/pyproject.toml`. To run it locally, from `sdk/` or `harness/`:

```bash
uv run --group mutation mutmut run
uv run --group mutation mutmut results
```

### Keeping the code in shape

The package boundaries are checked by Import Linter and `scripts/check_boundaries.py`. Import
Linter also checks inside a package: no package's modules import one another in a cycle (the
cycles that existed when the check was added are listed in its `ignore_imports`, and may only be
removed), and `dd_harness` and `dd_app` keep their layers, from the way in down to the checks the
project owns. Inside a package, these ratchets keep code from growing past what a reviewer can
follow ([Architecture review](docs/architecture-review.md)):

- **Function complexity.** Ruff applies mccabe complexity 12 and the pylint limits on branches
  (12), statements (50), arguments (7) and returns (6) to Python outside tests. ESLint applies
  complexity 18 and nesting depth 4 to `app/web`, `sdk/browser` and `inventory/browser` outside
  tests.
- **Class size.** Ruff's PLR0904 holds a Python class outside tests to 20 public methods, so that
  a class cannot grow by adding small ones.
- **Boolean parameters and silenced exceptions.** Ruff's `FBT` rules fail a boolean positional
  parameter in a definition and a `True` or `False` passed positionally in a call, in Python
  outside tests: a call such as `run(x, True, False)` cannot be read without the definition. Make
  the parameter keyword-only with `*` and name the argument. Ruff's `S110` fails
  `try`/`except Exception`/`pass` (`SIM105` already fails a narrower `except`/`pass`, asking for
  `contextlib.suppress`), and `BLE` fails a broad `except Exception` that neither re-raises nor
  logs: a content problem is an outcome, not a swallowed exception. No rule catches
  `contextlib.suppress(Exception)`; do not use it either.
- **File size.** `scripts/check_size.py` holds each Python source file to 500 lines and each
  TypeScript one to 400 (not tests or generated code). A file already over the limit is recorded in `scripts/size_baseline.toml`
  at its present size and may not grow. The pre-commit hook lowers an entry when its file shrinks;
  commit the change.
- **Copied code.** Agents may not import one another, so copying a block between them is the easy
  route. `scripts/check_duplication.py` runs [jscpd](https://github.com/kucherenko/jscpd) over the
  Python and TypeScript sources of every member (not tests or generated code) and fails on a block
  of 5 lines and 50 tokens or more that appears twice. The copies already there are recorded in
  `scripts/duplication_baseline.toml`, by pair of files, with the number of blocks and lines they
  share; a pair may not gain a block or a line, and a new pair fails. Move shared code to the
  package whose job it is, above all `dd_sdk` for what agents share, and import it. The check is a
  pre-commit hook, as it takes about a second; the first run installs the jscpd pinned in
  `scripts/jscpd/package-lock.json` with `npm ci`, so it needs Node.js. The hook lowers an entry
  when a copy is removed; commit the change. Its canary, `scripts/tests/test_check_duplication.py`,
  plants a block in two agents and expects the check to fail; it is skipped where jscpd is not
  installed, and CI's "Architecture" job installs it.
- **Unused code.** `uv run python scripts/check_unused.py` runs vulture over the Python, counting
  a use in a test or script, and fails a function, method, class or import in a member's `src/`
  that nothing calls. Code reached by a name vulture cannot see (a template, a base class that
  calls an override) is listed under `[[reached]]` in `scripts/unused_code.toml` with how it is
  reached; the unused code found when the check was added is listed under `[[unused]]` and may
  only shrink. `npm run lint` in `app/web`, `sdk/browser` and `inventory/browser` runs knip, which
  fails an unused file, export or dependency. A stale entry in either fails.
- **Member registration.** `scripts/check_members.py` checks that each workspace member, and above
  all each agent, appears in every list that names members by hand: the root `pyproject.toml`
  and the files that deploy every agent.

The code that exceeded a limit when it was introduced carries a marker: `# noqa: C901` (and the
like, `# noqa: FBT001` and `# noqa: PLR0904` among them) in Python, `// eslint-disable-next-line complexity` in TypeScript, or an entry in the size
baseline. These record debt. Remove the marker when you split the function or file; a marker that
no longer suppresses anything is itself an error (Ruff's RUF100, ESLint's unused-directive
report). Never add one to get new code past these checks: split the code by responsibility
instead, and if that is not possible in your pull request, open an issue and say so. The CI
"Architecture" job counts these markers, the baseline entries and the boundary exceptions in its
summary (`scripts/architecture_debt.py`), so the count can be seen to fall.

## Writing tests

The project is in alpha, and its wording, layout and set of agents change from week to week. A test
should fail when behaviour breaks, not when a sentence is reworded or an agent is added:

* Assert on structure: an outcome's status, a code, an identifier (`advisor.policy`, `R5`), a role
  and accessible name. Where text is the behaviour, match a short distinctive term or a regular
  expression, not the whole sentence.
* Take expected lists and counts from where they are defined (`app/config/agents.yaml`, the
  registry, the LinkML source, a fixture) rather than copying them into the test. Assert a lower
  bound or membership where the exact number does not matter.
* In the browser shell, query by role and accessible name; avoid CSS classes and DOM shape.
* Test what code does, not what its source says: no searching source files for code strings or
  pinned versions, and the public interface rather than `_private` attributes.
* Every test that substantiates a requirement carries `@pytest.mark.requirement("<ID>")`, with an
  ID from `docs/requirements.yaml` that it actually exercises. These tests feed `CONFORMANCE.md`:
  loosen what they assert, but keep them. An evaluation test carries no requirement marker
  ([Evaluation and conformance](docs/specs/evaluation.md)).
* Property tests use Hypothesis, for code the project owns outright (evidence canonicalisation,
  the contract validators, project event replay). The root `conftest.py` bounds every property
  test to 50 examples with no deadline; a slower one, such as one against a database, sets fewer
  with its own `@settings`.
* A test earns its place by catching a fault no other test catches. Test the project's own
  governance code thoroughly (see [Dependencies](docs/specs/dependencies.md)); test plumbing
  that the project has adopted at the boundary, not line by line. A rule about the repository's
  files (every agent does X) is one test that reports every file that breaks it, or a
  `scripts/check_*.py`, not one parametrised case per file. To see where the suite repeats
  itself, run `uv run python scripts/test_value.py`: it lists the tests that reach no line
  another test does not, the parametrised tests with many cases but few distinct paths, and
  the tests that run no code. Same lines are not the same check, so confirm with the weekly
  mutation run (`.github/workflows/mutation.yml`) before removing a test.
* Test module basenames are unique across the workspace. Test directories are not packages;
  shared doubles live in `dd_harness.testing` and in an agent's own `testing` module.
* The PostgreSQL storage tests (`harness/tests/test_postgres.py`, marked `postgres`) run only when
  `DD_TEST_POSTGRES` names a database. CI sets it; a local run skips them and says so at the end.
  Run them before changing storage:

  ```bash
  docker run -d --rm -p 5432:5432 -e POSTGRES_PASSWORD=dd-test postgres:17
  DD_TEST_POSTGRES=postgresql://postgres@localhost:5432/postgres PGPASSWORD=dd-test uv run pytest -m postgres
  ```

* Cassettes must not contain credentials. The root `conftest.py` filters the auth headers and the
  sign-in password; check a new cassette before committing it.

## Issues and labels

The kind of an issue is its GitHub issue type (Task, Bug or Feature), not a label; an umbrella
issue is a parent with sub-issues. Labels say where and what about:

* `area: …`: the part touched, one or more of `sdk`, `harness`, `workbench`, `app`, `agents`,
  `docs`, `ci`.
* `source: feedback form`: an issue filed from the app's feedback form, of any kind; the app
  applies it.
* Themes: `blueprint` (review or conformance against the Blueprint), `security`, `evaluation`,
  `accessibility`, `user report` (a bug filed from the app by someone using it; the app applies
  it, and triage treats it first), and `needs spec` for a change to a fixed format.
* `good first issue`, `help wanted` and `blocked` (waiting on something outside the project).

Pull requests take no labels by hand: the Conventional Commit title carries kind and scope.
`dependencies`, `python:uv`, `javascript` and `autorelease: …` are applied by Dependabot and
release-please. How issues move across the organisation's project board, and what coding agents
keep up to date on it, is in the organisation's
[planning guide](https://github.com/data-director-agent/.github/blob/main/PLANNING.md).

## Merging a pull request

Merge with **Squash and merge**. The repository allows no other method, and its ruleset on `main`
requires three checks to pass first: **CI passed**, **Accessibility passed** and **PR title and
branch name**. The squashed commit takes the pull request's title as its subject and has no body.

Squashing keeps one commit per pull request on `main`, which release-please needs. A merge commit
would put the branch's own commits on `main` beside GitHub's merge commit, whose body repeats the
pull request title, so release-please would list the change twice in the changelog and count every
`feat:` or `fix:` commit on the branch as a change of its own.

### The merge queue

`main` takes its pull requests through GitHub's merge queue. Once a pull request is approved and
its checks have passed, add it to the queue instead of merging it directly. The queue builds the
pull request on top of those queued ahead of it and runs the checks on that combined result, so
what lands on `main` is what was tested. The queue squashes in the same way as a direct merge, so
the rules above on titles and the squashed commit still apply.

The checks run differently in the queue:

* Every job in `ci.yml` and `accessibility.yml` runs, whether or not the change touches its files,
  as it does for a push to `main`. **CI passed** and **Accessibility passed** therefore test the
  combined result in full.
* **PR title and branch name** does not run. The queue has no title or branch of its own, and the
  check was made when the pull request was opened or its title edited. Its job is skipped, which
  counts as passed.
* A run in the queue is not cancelled by a later one: `ci.yml` cancels an earlier run only for a
  pull request.

release-please's release pull request, which only bumps versions (changelogs, the manifest,
`version` lines, `uv.lock`), skips the jobs that test code, since nothing it changes can break them
(`scripts/ci_changes.sh --release`). Any other change on its branch runs them as usual, and the
queue runs every job before the release reaches `main`.

If a check fails, the pull request leaves the queue. Fix it on its branch, push, wait for its
checks to pass on the pull request, and then add it to the queue again. The `merge_group` trigger
in each workflow is what starts these runs; a change to a workflow's triggers should keep it.

## Pull request titles and branch names

A pull request is squash-merged, so its title becomes the commit subject on `main`, and
release-please reads that subject as a [Conventional Commit](https://www.conventionalcommits.org/)
to decide each package's next version and its changelog. `names.yml` checks every pull request
and runs again when the title is edited:

* the title is `type(scope)!: summary`. `type` is one of `build`, `chore`, `ci`, `docs`, `feat`,
  `fix`, `perf`, `refactor`, `revert`, `style` or `test`; `(scope)`, usually the package
  (`app`, `harness`, `sdk`), and `!`, for a breaking change, are optional. The summary is a
  sentence that starts with a capital letter, has no closing full stop, and the whole title is at
  most 90 characters: `feat(app): Register every in-tree agent`. Lower case is also accepted, for
  a summary that opens with a command or package name such as `uv`
* the branch is lower-case words joined by hyphens, optionally grouped with slashes, in at most
  60 characters: `ci-faster`, `harness/run-store`

Dependabot's and release-please's pull requests are exempt. The check runs on every push and
every title edit, so a wrong title is fixed by editing it, with no new commit. Check a title and
branch locally:

```sh
python3 scripts/check_names.py --title "feat(app): history tab" --branch "$(git branch --show-current)"
```

`project-status.yml` puts a pull request on the project board when it is opened or marked ready
for review, using the repository secret `PROJECT_TOKEN`. When that secret is unset the job fails
with "To use GitHub CLI in a GitHub Actions workflow, set the GH_TOKEN environment variable". The
failure comes from repository settings, not from the change: the organisation owner sets
`PROJECT_TOKEN` as the workflow's header comment describes.

## Pre-commit hooks

`.pre-commit-config.yaml` holds the fast checks, so that they fail on your machine rather than in
CI. Install them once per clone:

```sh
uv tool install pre-commit && pre-commit install
```

Before each commit they fix trailing whitespace, final newlines and line endings; check YAML, TOML
and JSON parse, and that no merge marker, private key or file over 1 MB is committed; check file
modes against shebangs; run Ruff (lint with fixes, then format, at the version in `uv.lock`);
check each to-do marker names an issue (`scripts/check_todos.py`); hold source files to their
size and copied code to its baseline (`scripts/check_size.py`, `scripts/check_duplication.py`);
check every member is registered (`scripts/check_members.py`); re-lock `uv.lock` (below);
lint the workflows with actionlint and zizmor (offline); and refuse a commit made directly on
`main`. A `commit-msg` hook holds each commit subject to the pull request title rule
(`scripts/check_names.py`): a Conventional Commit, `type(scope): summary`. The title itself is
still checked in CI, as it is the one squash-merged onto `main`.

Run them all over the tree with `pre-commit run --all-files`. Generated and recorded files
(`uv.lock`, lock files, `schema/generated/`, test data, cassettes) and `docs/blueprint/` are left
alone. mypy, pytest, the architecture checks and the app/web npm scripts take minutes and need the
full environment, so they are not hooks: CI runs them. CI's "Pre-commit hooks" job runs the hooks
too, for anyone who has not installed them. Dependabot keeps the hook revisions current.

## Keeping `uv.lock` current

`uv.lock` records every workspace package's version and dependencies, so any branch that changes
a `pyproject.toml` changes it too, and two such branches conflict. The `uv-lock` pre-commit hook
re-locks whenever a `pyproject.toml` changes, so the lock never lags behind and CI's locked check
never fails for that reason.

Never resolve a `uv.lock` conflict by hand. Take the base branch's file and lock again:

```sh
git checkout origin/main -- uv.lock && uv lock && git add uv.lock
```

then continue the rebase or merge. Release pull requests are re-locked by `release.yaml`.

## Releases

[RELEASING.md](RELEASING.md) describes the versioning policy, how release-please makes a release
and what to do when it goes wrong. A pull request needs nothing more than a Conventional Commit
title; release-please reads it.

## Credit

Everyone who authors or co-authors a commit is cited as an author of the software. In your first
pull request, add yourself to `authors` in the [citation file](./CITATION.cff), with your ORCID
and affiliation if you have them:

```yaml
  - given-names: Ada
    family-names: Lovelace
    email: ada@example.org
    affiliation: University of Example
    orcid: 'https://orcid.org/0000-0000-0000-0000'
```

`scripts/check_citation.py` runs in the "Links and citation file" job and lists anyone missing.
It matches the email address of each commit's author, and of each `Co-authored-by:` trailer,
against `email`, or the name against `given-names` and `family-names`. If you commit under
several names or addresses, add a line to [`.mailmap`](./.mailmap) that maps them to the one in
the citation file. Bots and AI assistants are not cited; the project's [AI usage statement](https://github.com/data-director-agent/.github/blob/main/AI_USAGE.md) discloses their use instead. Run it locally in a full clone:

```sh
uv run scripts/check_citation.py
```
