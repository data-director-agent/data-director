# ADR-0032: An agent may serve a step of the process flow, not only a requirement

**Status:** Proposed
**Date:** 2026-10-29

Amends [ADR-0028](0028-entry-points-and-serves.md) (decisions 2 and 3).

## Context

ADR-0028 places an agent in the process flow by the Blueprint requirements it serves: a step's
agents are those whose manifest entry serves one of the step's requirements. Many steps in §8.2
name no requirement. Phase 2, governance and constraints, names one (R8) in four steps, and
Phase 3's first step, *check whether the funder, journal or institution mandates a repository*,
names none. An agent written for such a step could declare nothing that places it there, so
both orchestrators and the phase tracker would report "no agent yet" for a step an agent serves.

Claiming the nearest requirement does not work either. A policy check could claim R1, whose
description includes flagging conflicts between funder, journal and institutional requirements.
But R1 is applied at Phase 3's repository recommendation, so the agent would be listed there and
not at the Phase 2 step it was written for.

## Decision

1. **Every step has a stable id.** `dd_sdk.process_flow.Step.id` is `<phase>.<step>`, for
   example `governance.policies`, and all the steps of a phase share the prefix. The ids are this
   repository's labels for the Blueprint's steps, not the Blueprint's own, and `STEPS` holds them.
   A test keeps them unique and distinct from requirement IDs.
2. **An agent may serve a step by its id** (amends ADR-0028 decision 2). `AgentSpec.serves`
   names functional requirements, step ids or both. Anything else is a `SpecError`. Serving a
   requirement remains the way to claim a Blueprint capability; serving a step claims only that
   the agent helps at that point in the flow.
3. **A step's agents are the agents serving its id or one of its requirements** (amends
   ADR-0028 decision 3). `plan` and the app shell's `servingStep` make the same join.
4. **The orchestrator sees step ids but does not show them.** `describe_flow()` prints each
   step's id, and a tool's description lists the requirements and the steps its agent serves
   separately. The system prompt tells the model not to show ids to the researcher.

The contract version is unchanged: `serves` is still a list of strings on the manifest entry, and
a description written before this decision is read as before.

## Dependencies introduced

None.

## Consequences

- An agent can be placed at any step, including the many with no requirement. Phase 2's policy
  check is the first (`policy.advisor`).
- A step id is a published name once an agent serves it. Renaming one breaks every agent that
  serves it, as an unknown id is refused. Treat a rename as a breaking change to the SDK.
- Checking the steps against Figures 1 to 6 (TODO(#245)) may add steps or split them. New ids are
  harmless; a split needs the same care as a rename.
- Serving a step makes no conformance claim. The conformance report still counts only
  requirements.
