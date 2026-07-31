# Governance

This document describes how decisions are made in the `data-director` project. It favours a
lightweight process suited to an early-stage, community-driven project, and defines the trigger
for evolving into a more formal structure as the community grows.

## Core maintainer group

The project is led by a core maintainer group. Maintainers have merge
rights and are collectively responsible for the health of the project.

A new maintainer is added when an existing maintainer nominates a regular, trusted contributor and no other maintainer objects
within 5 business days. The group is capped at four; if growth beyond four is warranted, see
[Technical Steering Committee](#technical-steering-committee-tsc) below.

## Decision-making: lazy consensus

Most day-to-day decisions, including pull request merges, use **lazy consensus**:

- A change can be merged once at least one maintainer has approved it and no maintainer has
  raised an objection within 3 business days of that approval.
- Silence is treated as consent. Anyone, maintainer or not, may object; objections must include a
  rationale and should be worked towards resolution before the change proceeds.
- Trivial changes (typo fixes, documentation corrections, dependency bumps with no behavioural
  change) may be merged by any maintainer without waiting out the review window.

Lazy consensus keeps routine work moving without requiring every maintainer to weigh in on every
change.

## RFC process for spec-conformance changes

Some changes affect how `data-director` conforms to the RDA Data Director Agentic AI Blueprint
that it implements — for example, changes to interfaces, data models, or behaviours the Blueprint
specifies. These require more visibility than lazy consensus alone provides:

1. Open an issue labelled `RFC` describing the proposed change, the motivation, and its impact on
   spec conformance.
2. Allow a minimum comment period of 5 business days for community and maintainer feedback.
3. At least one maintainer must approve the RFC before an implementing pull request can be merged.
4. Once approved, the implementing pull request follows normal lazy consensus.

This process is intentionally lightweight — a GitHub issue and a waiting period, not a formal
document review board.

## Technical Steering Committee (TSC)

This project is currently maintainer-led. If the project grows to the point where **three or more
independent organisations** are contributing regularly (judged by contributor affiliation, e.g. as
declared in commit sign-offs — see [CONTRIBUTING.md](CONTRIBUTING.md)), the maintainers will
initiate the formation of a Technical Steering Committee (TSC) with representation from each
contributing organisation.

When that trigger is reached, this document will be revised to define the TSC's composition,
scope of authority, and relationship to the maintainer group.

## Scope

This governance model applies to the `data-director` reference implementation repository. The RDA
Data Director Agentic AI Blueprint itself is a separate specification stewarded by its own RDA
working group; this project aims to track and conform to it, not to govern it.

## Amendments

Changes to this document follow the same lazy consensus process as any other pull request.
