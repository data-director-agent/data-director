# Software Management Plan

This plan follows the [FAIR4RS Software Lifecycle Planning](https://fair2-for-research-software.github.io/Software_Lifecycle_Planning/SMP_for_research.html)
approach. It is a living document, updated as the project matures.

## Purpose and scope

`data-director` is a reference implementation of the RDA Data Director Agentic AI Blueprint,
officially adopted by the RDA and published at <https://doi.org/10.15497/RDA00157>. See
the [project charter](https://github.com/data-director-agent/.github/blob/main/CHARTER.md) for the project's mission and scope.

## Development approach

- **Language / stack**: Python, `uv` workspace. Exploratory approaches are trialled as
  alpha-versioned agents in [`agents/`](../agents/) (see `agents/README.md`) rather than in a
  separate prototype tree.
- **Repository**: Git, hosted at <https://github.com/data-director-agent/data-director>.
- **Branching and release strategy**: work happens on short-lived branches, merged into `main`
  by squashed pull requests whose titles are Conventional Commits (`AGENTS.md`). release-please
  reads those titles to propose each package's next version and changelog.
- **Versioning**: [Semantic Versioning](https://semver.org/), per package. Every package is
  released as an alpha pre-release for now.

## Licensing

MIT License (see [LICENSE](../LICENSE)).

## Governance and sustainability

The project follows the lightweight governance model in [GOVERNANCE.md](https://github.com/data-director-agent/.github/blob/main/GOVERNANCE.md),
including the trigger for forming a Technical Steering Committee as the contributor community
grows. The project's mission and scope are set out in the [project charter](https://github.com/data-director-agent/.github/blob/main/CHARTER.md).

## Contribution process

See the organisation-wide [contribution guide](https://github.com/data-director-agent/.github/blob/main/CONTRIBUTING.md) for how to propose changes, the Developer Certificate of
Origin sign-off requirement, and the pull request workflow.

## Documentation plan

- `README.md` — project overview.
- `CONTRIBUTING.md` — repository-specific contribution notes.
- Charter, governance, contribution guide and code of conduct — organisation-wide, in
  [`data-director-agent/.github`](https://github.com/data-director-agent/.github).
- `docs/SOFTWARE_MANAGEMENT_PLAN.md` — this document.
- `docs/architecture.md` — the system overview; `docs/adr/` — the architecture decisions.
- `docs/guide/` — the user and developer guides. The documentation site publishes them with
  the documents above and each package's own, from where they are kept (`mkdocs.yml`).

## Testing and quality assurance

Python is tested with pytest and type-checked with mypy; the app's browser shell is tested with
Vitest and Playwright. Every pull request runs these in the CI pipeline
(`.github/workflows/ci.yml`), with linting, link checks, workflow checks, a check that every
open question marked in the source names its issue, and the DCO sign-off. Coverage is reported to Codecov. A test that
substantiates a Blueprint requirement carries its marker, and `CONFORMANCE.md` is generated from
those tests.

## Citation

See [CITATION.cff](../CITATION.cff) for how to cite this software.
