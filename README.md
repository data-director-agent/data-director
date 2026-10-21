# Data Director

[![Tests](https://github.com/data-director-agent/data-director/actions/workflows/conformance.yml/badge.svg)](https://github.com/data-director-agent/data-director/actions/workflows/conformance.yml) [![Coverage](https://codecov.io/gh/data-director-agent/data-director/graph/badge.svg)](https://codecov.io/gh/data-director-agent/data-director)

A proposed reference implementation for the [Data Director Agentic AI Blueprint](https://doi.org/10.15497/RDA00157) developed under the coordination of the [Research Data Alliance Data Director Working Group](https://www.rd-alliance.org/groups/data-director-agentic-ai-blueprint/activity/).

## Overview

[![Towards a Data Director reference implementation — video](https://cdnapisec.kaltura.com/p/2103181/sp/210318100/thumbnail/entry_id/1_f0c1kkwg/width/640)](https://digitalmedia.sheffield.ac.uk/media/Towards+a+Data+Director+reference+implementation/1_f0c1kkwg)

[Towards a Data Director reference implementation](https://digitalmedia.sheffield.ac.uk/media/Towards+a+Data+Director+reference+implementation/1_f0c1kkwg) is a recorded introduction to this project. It is also posted on the [RDA working group page](https://www.rd-alliance.org/groups/data-director-agentic-ai-blueprint/posts/towards-a-data-director-reference-implementation/).

## Contributing

This is a community-driven, open-source project. See:

- [Blueprint](docs/BLUEPRINT.md) — the Data Director Agentic AI Tool Blueprint (RDA, CC BY 4.0), reproduced here as Markdown
- [Project charter](https://github.com/data-director-agent/.github/blob/main/CHARTER.md) — the project's mission and scope
- [Governance](https://github.com/data-director-agent/.github/blob/main/GOVERNANCE.md) — how decisions are made and how the maintainer group grows
- [Contribution guide](CONTRIBUTING.md) — this repository's structure and tooling; the organisation-wide [contribution guide](https://github.com/data-director-agent/.github/blob/main/CONTRIBUTING.md) covers RFCs, sign-off and pull requests
- [Code of conduct](https://github.com/data-director-agent/.github/blob/main/CODE_OF_CONDUCT.md) — expected standards of behaviour
- [Software management plan](docs/SOFTWARE_MANAGEMENT_PLAN.md) — the software management plan
- [App](app/) — the Data Director itself (alpha): a browser shell drawn from each agent's manifest (ADR-0024)
- [Harness](harness/) — the governance every agent invocation goes through: the policy gate, input check, grounding linter, source check, run store and provenance
- [Workbench](workbench/) — development environment for building and testing sub-agents: the invocation contract (LinkML), an R3 agent over FAIRsharing, an abstaining stub, and a read-only viewer
- [Decision records](docs/adr/) — the architecture decisions that govern every package, with the requirements register and the generated [`CONFORMANCE.md`](CONFORMANCE.md)
