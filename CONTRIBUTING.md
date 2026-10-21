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

## Credit

Please add your details to the [citation file](./CITATION.cff) to be acknowledged as a contributor.
