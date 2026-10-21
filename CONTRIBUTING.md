# Contribution guide

Thank you for your interest in contributing to `data-director`, a reference implementation of the
Research Data Alliance's Data Director Agentic AI Blueprint.

The organisation-wide [contribution guide](https://github.com/data-director-agent/.github/blob/main/CONTRIBUTING.md)
applies here: when to open an RFC, the Developer Certificate of Origin sign-off (`git commit -s`)
and the pull request workflow. [Governance](https://github.com/data-director-agent/.github/blob/main/GOVERNANCE.md)
and the [code of conduct](https://github.com/data-director-agent/.github/blob/main/CODE_OF_CONDUCT.md)
are also organisation-wide. This file covers what is specific to this repository.

## Repository structure

This repository is organised as follow:

* `docs/` contains what governs every package: the Blueprint, the decision records (`docs/adr/`),
  the contract, the glossary, the requirements register and the review record. A package's own
  documents are in its own `docs/` (`harness/docs/`, `workbench/docs/`)
* `app/` contains the Data Director app that people use (alpha); its browser shell in `app/web`
  needs Node 22 or later and npm (`app/README.md`)
* `sdk/` contains what agents and the harness share: the contract, evidence and the agent server
* `harness/` contains the governance every agent invocation goes through (ADR-0022)
* `workbench/` contains the development environment for building and testing sub-agents
* `agents/` contains one package per agent, including alpha-versioned experimental ones
  (`agents/README.md`)

## Developer quick-start

You need [uv](https://docs.astral.sh/uv/) (it installs Python 3.14), Node 22 or later with npm, and
git. From a clone of the repository:

```
uv sync --all-packages --all-extras      # Python environment for every workspace package
uv tool install pre-commit && pre-commit install
(cd app/web && npm ci)                 # the shell's dependencies
```

Check the setup with `uv run pytest`, which is offline and needs no credentials.

### Run the app with hot reload

The app has two parts: a Python server (`dd_app`) that serves `/api`, and the React shell in
`app/web`. Run both, in two terminals:

```
# Terminal 1, repository root: the API on http://127.0.0.1:7860
export DD_PRINCIPAL_ID=https://orcid.org/...  DD_PRINCIPAL_NAME="..."
(cd app/web && npm run build)          # once: the server refuses to start without app/web/dist
uv run data-director

# Terminal 2, in app/web: the shell with hot module replacement
npm run dev
```

Open the address Vite prints (usually <http://localhost:5173>), not port 7860. Port 7860 serves
the built `app/web/dist`, which is stale until `npm run build`. Vite proxies `/api` to the server;
set `DD_APP_URL` if the server is elsewhere. The Python server does not reload on change: restart
it after editing `app/src`, `harness/` or `sdk/`. `app/README.md` describes the configuration.

### Develop and test an agent

`workbench/` is the development way in for agent authors: `uv run workbench agents` lists the
registered agents, `uv run workbench invoke --agent <id> --input <file>` runs one, and
`uv run workbench serve` opens the Inspect and Chat pages at <http://127.0.0.1:8000/viewer/>
(`workbench/README.md`). Read `workbench/AGENTS.md` before changing `workbench/` or `harness/`.

## Code style and testing

The Python packages use Python 3.14 and [uv](https://docs.astral.sh/uv/); `app/web` uses Node 22
and npm. Follow the conventions of the surrounding code, and describe how you tested your change
in the pull request description.

Every pull request runs `.github/workflows/ci.yml`, which ends in one check, **CI passed**, that
passes only when every other job has. Each job can be run locally from the repository root:

| Job | Locally |
|---|---|
| Ruff (lint + format) | `uv run ruff check . && uv run ruff format --check .` |
| mypy | `uv run mypy` |
| pytest and CONFORMANCE.md | `uv run pytest --json-report --json-report-file=.report.json && uv run python scripts/conformance_report.py --check` |
| Generated schemas up to date | `uv run dd-gen-schema && git diff --exit-code -- sdk/src/dd_sdk/schema/generated/` |
| Packages build and install alone | `uv build --all-packages -o dist && uv run python scripts/check_wheels.py dist` |
| Agents as services (smoke) | `uv run python scripts/smoke_agents.py` |
| Workbench viewer in a browser | `uv run playwright install chromium && uv run pytest workbench/browser_tests` |
| App shell | in `app/web`: `npm ci && npm run lint && npm run typecheck && npm test && npm run build && npm run e2e` |
| Links and citation file | `lychee --offline --include-fragments --exclude-path docs/BLUEPRINT.md '**/*.md'` and `uvx cffconvert --validate` |
| Workflows | `uvx zizmor .github` and [actionlint](https://github.com/rhysd/actionlint) |
| Developer Certificate of Origin | every commit signed off by its author: `git commit -s` |
| Dependency review | a new dependency with a known advisory of moderate severity or worse is refused |

The pytest suite blocks the network and needs no credentials. `CONFORMANCE.md` is generated;
regenerate it with the same two commands without `--check`. CodeQL (`codeql.yml`) analyses the
Python, JavaScript and TypeScript code and the workflows, and `audit.yml` checks every locked
dependency against the advisory databases each day. Dependabot proposes updates weekly.

## Pull request titles and branch names

A pull request is squash-merged, so its title becomes the commit subject on `main`, and
release-please reads that subject as a [Conventional Commit](https://www.conventionalcommits.org/)
to decide each package's next version and its changelog. `names.yml` checks every pull request
and runs again when the title is edited:

* the title is `type(scope)!: summary`. `type` is one of `build`, `chore`, `ci`, `docs`, `feat`,
  `fix`, `perf`, `refactor`, `revert`, `style` or `test`; `(scope)`, usually the package
  (`app`, `harness`, `sdk`), and `!`, for a breaking change, are optional. The summary starts in
  lower case unless its first word is a name or acronym, has no closing full stop, and the whole
  title is at most 90 characters: `feat(app): register every in-tree agent`
* the branch is lower-case words joined by hyphens, optionally grouped with slashes, in at most
  60 characters: `ci-faster`, `harness/run-store`

Dependabot's and release-please's pull requests are exempt. Check a title and branch locally:

```
python3 scripts/check_names.py --title "feat(app): history tab" --branch "$(git branch --show-current)"
```

## Keeping `uv.lock` current

`uv.lock` records every workspace package's version and dependencies, so any branch that changes
a `pyproject.toml` changes it too, and two such branches conflict. The `uv-lock` pre-commit hook
re-locks whenever a `pyproject.toml` changes, so the lock never lags behind and CI's locked check
never fails for that reason. Install it once:

```
uv tool install pre-commit && pre-commit install
```

Never resolve a `uv.lock` conflict by hand. Take the base branch's file and lock again:

```
git checkout origin/main -- uv.lock && uv lock && git add uv.lock
```

then continue the rebase or merge. Release pull requests are re-locked by `release-please.yml`.

## Credit

Please add your details to the [citation file](./CITATION.cff) to be acknowledged as a contributor.
