# Software Management Plan

This plan follows the [FAIR4RS Software Lifecycle Planning](https://fair2-for-research-software.github.io/Software_Lifecycle_Planning/SMP_for_research.html)
approach. It is a living document, updated as the project matures — items marked `TODO` are not
yet decided.

## Purpose and scope

`data-director` is a reference implementation of the RDA Data Director Agentic AI Blueprint,
officially adopted by the RDA and published at <https://doi.org/10.15497/RDA00157>. See
the [project charter](https://github.com/data-director-agent/.github/blob/main/CHARTER.md) for the project's mission and scope.

## Development approach

- **Language / stack**: Python, `uv` workspace. Exploratory approaches are trialled as
  alpha-versioned agents in [`agents/`](../agents/) (see `agents/README.md`) rather than in a
  separate prototype tree.
- **Repository**: Git, hosted at `TODO: repository URL`.
- **Branching and release strategy**: `TODO` — to be defined once initial development begins.
- **Versioning**: [Semantic Versioning](https://semver.org/) once releases begin.

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
- Further user- and developer-facing documentation: `TODO`, to be added as the implementation
  takes shape.

## Testing and quality assurance

`TODO` — no code or tooling exists yet. A testing strategy (frameworks, coverage expectations, CI)
will be defined once implementation starts, and this section updated accordingly.

## Citation

See [CITATION.cff](../CITATION.cff) for how to cite this software.
