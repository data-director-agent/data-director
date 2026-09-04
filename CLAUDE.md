# Data Director

## Purpose

A reference implementation of the RDA [Data Director Agentic AI Blueprint](https://www.rd-alliance.org/groups/data-director-agentic-ai-blueprint/outputs/data-director-agentic-ai-tool-blueprint/).

## Working here

- Prototype work belongs in `experiments/<name>/`, which is explicitly non-authoritative — see
  `experiments/README.md`. Promoting anything out of `experiments/` requires an RFC.
- `docs/BLUEPRINT.md` is the Blueprint reproduced verbatim (RDA, CC BY 4.0). It is **~540KB — never
  read it whole; grep for the requirement or section you need.** Requirements are cited by ID (`R3`,
  `R3.1`, …) throughout the repo. Treat it as read-only external material, not project prose to
  improve.

## Committing

Every commit must be signed off under the Developer Certificate of Origin — `git commit -s`.
Unsigned commits are rejected at review.

## Writing conventions

British English (`organisation`, `behaviour`, `licence` as noun). Declarative prose for a mixed
audience of researchers and engineers; no hype. Mark undecided matters with an explicit `TODO`
rather than filling in a plausible guess.
