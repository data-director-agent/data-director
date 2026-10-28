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

## Code style and testing

The Python packages use Python 3.14 and [uv](https://docs.astral.sh/uv/); `app/web` uses Node 22
and npm. `uv run scripts/dev.py setup` installs both sides and `uv run scripts/dev.py doctor`
says what is wrong with a setup (README, "Quick start"). Follow the conventions of the surrounding
code, and describe how you tested your change in the pull request description.

Every pull request runs `.github/workflows/ci.yml`, which ends in one check, **CI passed**, that
passes only when every other job has. Each job can be run locally from the repository root:

| Job | Locally |
|---|---|
| Ruff (lint + format) | `uv run ruff check . && uv run ruff format --check .` |
| mypy | `uv run mypy` |
| pytest | `uv run pytest --json-report --json-report-file=.report.json` |
| CONFORMANCE.md is current | `uv run python scripts/conformance_report.py --check` (after pytest, which writes `.report.json`) |
| Generated schemas up to date | `uv run dd-gen-schema && git diff --exit-code -- sdk/src/dd_sdk/schema/generated/` |
| Packages build and install alone | `uv build --all-packages -o dist && uv run python scripts/check_wheels.py dist` |
| Agents as services (smoke) | `uv run python scripts/smoke_agents.py` |
| Workbench viewer in a browser | `uv run playwright install chromium && uv run pytest workbench/browser_tests` |
| App shell | in `app/web`: `npm ci && npm run lint && npm run typecheck && npm test && npm run build && npm run e2e` |
| Links and citation file | `lychee --offline --include-fragments '**/*.md'`, `uvx cffconvert --validate` and `uv run scripts/check_citation.py` |
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

```sh
python3 scripts/check_names.py --title "feat(app): history tab" --branch "$(git branch --show-current)"
```

## Keeping `uv.lock` current

`uv.lock` records every workspace package's version and dependencies, so any branch that changes
a `pyproject.toml` changes it too, and two such branches conflict. The `uv-lock` pre-commit hook
re-locks whenever a `pyproject.toml` changes, so the lock never lags behind and CI's locked check
never fails for that reason. Install it once:

```sh
uv tool install pre-commit && pre-commit install
```

Never resolve a `uv.lock` conflict by hand. Take the base branch's file and lock again:

```sh
git checkout origin/main -- uv.lock && uv lock && git add uv.lock
```

then continue the rebase or merge. Release pull requests are re-locked by `release-please.yml`.

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
the citation file. Bots and AI assistants are not cited. Run it locally in a full clone:

```sh
uv run scripts/check_citation.py
```
