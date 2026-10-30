# ADR-0032: An agent serves steps of the process flow, not requirements

**Status:** Proposed
**Date:** 2026-10-29

Sets what `serves` names in [ADR-0028](0028-entry-points-and-serves.md) (decisions 1 to 3, 6).
Settles #305.

## Context

An agent says where it fits in the researcher's work by what it `serves`, and the orchestrators
and the phase tracker list it at the matching steps of the Blueprint's process flow (§8.2). The
first design had agents name Blueprint functional requirements (R1 to R12), and a step's agents
were those serving one of its requirements. Three things argue against that.

- **Requirements are capabilities, not places in the flow.** R3 is applied in Phase 1
  (vocabularies) and Phase 4 (formats), R7 in Phases 3 and 5, and R2 and R6 share a step. Serving
  `R3` put an agent at every step that names R3, whether or not it helped there.
- **Most steps name no requirement.** Of the 30 steps, 13 name one. Phase 2 names only R8, at the
  Data Management Plan check, and Phase 3's first step, *check whether the funder, journal or
  institution mandates a repository*, names none. An agent written for such a step had nothing
  to declare. Claiming the nearest requirement misplaces it: a policy check could claim R1, which
  includes flagging conflicting funder and institutional requirements, but R1 is applied at
  Phase 3's repository recommendation, not at the Phase 2 policy step.
- **One field carried two claims.** "I implement R3" is a conformance claim, which needs
  evidence and review. "Ask me at this step" is a routing hint. Nothing checked either.

A second design from the same community points the same way. Uzwyshyn's persona-based Research
Data Director ([RDA P27 poster, 2026](https://rayuzwyshyn.net/rda-p27/)) assigns the Blueprint's
functions to roles. A role spans requirements (its Metadata Librarian covers R2, R3 and R6) and
often works at a step that names none: the Research Integrity and Ethics Manager at sensitive
data, the Data Curation Librarian at the mandated-repository check.

## Decision

1. **Every step has a stable id.** `dd_sdk.process_flow.Step.id` is `<phase>.<step>`, for
   example `governance.policies`, and all the steps of a phase share the prefix. The ids are this
   repository's labels for the Blueprint's steps, not the Blueprint's own, and `STEPS` holds them.
   A test keeps them unique and distinct from requirement IDs.
2. **A step is split where one figure step joins two acts that different agents may do.** Figure
   2's "identifying and handling sensitive data" is `governance.sensitive-data-identify` and
   `governance.sensitive-data-handle`, so that an agent can flag sensitive data without deciding
   how it is treated, as the persona-based design separates them.
3. **An agent's `serves` names steps only.** A requirement ID is a `SpecError`, like any other
   unknown name. Cards that declared requirements are changed, not translated: `advisor.standards`
   serves `setup.vocabularies` and `preparation.formats`, and `advisor.quality` serves
   `deposit.validate`.
4. **The requirements an agent bears on are derived from its steps.** `Step.requirements` is the
   only map from steps to requirements, and `process_flow.requirements_of(steps)` reads it. The
   orchestrator's tool descriptions give the steps an agent serves and the requirements those
   steps apply. "No agent yet (R5)" still works, because the step knows its requirement.
5. **Conformance stays in the register.** Whether an agent meets a requirement, and how well, is
   recorded in `docs/requirements.yaml` and `docs/reviews.yaml` with its evidence (ADR-0014), not
   on the agent card.
6. **A cross-cutting requirement needs no step.** R10, provenance, is the harness's work on every
   run: it records what each agent did, is never dispatched, and decides nothing, which is also
   how the persona-based design treats its Provenance Recorder. R12, FAIRness assessment, has its
   step, `post.fairness`. No requirement in §7.1 needs an agent placed outside the flow.

The contract version is unchanged: `serves` is still a list of strings on the manifest entry.

## Dependencies introduced

None.

## Consequences

- An agent can be placed at any step, including those that name no requirement. Phase 2's policy
  check (`advisor.policy`) is the first.
- An agent is listed only where it says it helps. Serving one R3 step no longer places it at the
  other.
- A step id is a published name once an agent serves it, and an unknown id is refused, so renaming
  or splitting a step breaks the agents that serve it. Treat either as a breaking change to the
  SDK. Checking the steps against Figures 1 to 6 (TODO(#245)) may add or split steps, and
  Blueprint v2.0 may restructure the flow. Neither needs versioned ids yet, as every agent is in
  this repository.
- Another implementation of the Blueprint would need the same step vocabulary to share agents.
  Proposing the ids to the RDA working group is TODO(#310).
- Step ids may also become the vocabulary in which a deployment's policy names the steps that
  need a person's sign-off, such as `repository.pid` or `deposit.licence` (ADR-0017), TODO(#308).
- The orchestrator's prompt explains one vocabulary, steps, rather than two.
