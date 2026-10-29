# ADR-0028: The orchestrators route by the Blueprint's entry points, and an agent says what it serves

**Status:** Proposed
**Date:** 2026-10-22

Decisions 2 and 3 are amended by [ADR-0032](0032-agents-serve-process-steps.md): an agent may
also serve a step by its id.

Amends [ADR-0012](0012-conversation-and-orchestration.md) (decisions 11 and 13) and
[ADR-0011](0011-remote-agents.md) (the manifest gains `serves`).

## Context

The Blueprint describes the researcher's work as six phases (§8.2, Figures 1–6), entered at one of
three points (§8.1): Entry 1 before data collection begins (Phase 1), Entry 2 with data collected
and being prepared for sharing (Phase 2), and Entry 3 ready to deposit (Phase 3). All three
continue through the same final phases. Each step names the functional requirement (§7.1) it
applies, or none.

Both orchestrators waited for a request shaped for one agent. `director.stub` matched it against
`routing.yaml`; `orchestrator.model` offered the model one tool per agent. Neither could tell a
researcher where they were in the work, which steps from there an agent could help with, or which
steps had no agent (#134).

Two facts are needed to answer that. The process flow is the Blueprint's, the same for every
agent and every deployment. Which agent serves which step depends on the agents a harness has
registered. ADR-0012 decision 13 already made the harness's manifest the only list of agents an
orchestrator reads, so the second fact belongs there.

Governance as the entry point, which would route researchers to open, restricted or unshared
paths, is deferred by the Blueprint to v2.0 (Appendix G, comment 1) and is not decided here.

## Decision

1. **The process flow is SDK data.** `dd_sdk.process_flow` holds the three entry points and the
   six phases, each step with the requirements its figure caption names. It is shared by every
   orchestrator and names no agent. The steps are taken from the captions in §8.2; whether the
   figures show more is open, TODO(#245).
2. **An agent declares the Blueprint requirements it serves.** `AgentSpec.serves` is a tuple of
   functional requirement IDs, `R1` to `R12`; a sub-requirement such as `R3.1`, or anything else,
   is a `SpecError`. `describe` carries it as `serves`. A description without it, written before
   this decision, serves none. The contract version is unchanged, as for `models` (ADR-0026).
3. **A step's agents are the agents whose manifest entry serves one of its requirements.**
   `process_flow.plan(entry, manifest)` joins the two. No orchestrator keeps its own map.
4. **A step with no agent is named, with its requirement.** An orchestrator that takes a
   researcher through the steps says "no agent yet" and the requirement (for example R5), or
   that the Blueprint names none. It does not skip the step or do it itself.
5. **`director.stub` asks on a first turn** (amends ADR-0012 decision 11). A message a routing
   rule matches is routed as before. Otherwise, a message that names an entry point, by the
   `entries` patterns in `routing.yaml`, is answered with the steps from that entry. A first turn
   that names neither is answered with a question listing the three entry points. These replies
   are templates, delegate nothing and rest on the input alone. Any other message abstains as
   before.
6. **`orchestrator.model` is told the process flow and reads `serves` from the manifest**
   (amends ADR-0012 decision 13). Its system prompt carries `describe_flow()` and the same rules:
   ask on a first turn, follow the phases from the entry, name a step with no agent. Each tool's
   description adds the requirements its agent serves. The prompt still names no agent and is
   the same on every run, so it caches.

## Dependencies introduced

None.

## Consequences

- An agent becomes part of an entry point's plan by declaring `serves` in its spec. Neither
  orchestrator needs changing when a new agent serves a requirement, although `director.stub`
  can give an example request only for an agent a `routing.yaml` rule names.
- `serves` is a claim by the agent's author, not a check. Nothing tests that an agent serving
  `R3` meets R3; that is for the conformance report and its reviews (ADR-0014).
- Which entry point a researcher chose is not recorded beyond the conversation. The stub reads
  only the current message, so it lists the steps once and does not track progress through them.
  TODO(#203): whether an orchestrator should keep the researcher's place in the flow across turns.
- Changing the process flow changes the model's prompt, and so its behaviour: treat an edit to
  `dd_sdk/process_flow.py` as a change to both orchestrators.
