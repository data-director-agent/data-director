# Experiments

This directory holds prototype and exploratory work — not the reference implementation.

## Purpose

The [project charter](../docs/CHARTER.md) commits this repository to a reference implementation
of the RDA Data Director Agentic AI Blueprint, but the stack, architecture, and structure for that
implementation have not yet been decided by the maintainer group. `experiments/` is where that
groundwork happens: trying out languages, frameworks, and designs for individual Blueprint
components before proposing any of it as the project's direction.

## Rules

- **Nothing here is authoritative.** Code, structure, and conventions in `experiments/` do not
  represent a decision by the maintainers and should not be relied on or built against.
- **Each experiment gets its own subdirectory**, named for what it's exploring (e.g.
  `experiments/blueprint-orchestrator-python/`), with its own short `README.md` explaining what
  it's testing and its status.
- **Promoting an experiment** to the reference implementation (or a part of it) goes through the
  normal RFC / lazy consensus process in [GOVERNANCE.md](../GOVERNANCE.md) — moving code out of
  `experiments/` is a project decision, not a unilateral edit.
- **Prune freely.** Abandoned or superseded experiments should be deleted rather than left to rot;
  git history preserves them if needed later.
