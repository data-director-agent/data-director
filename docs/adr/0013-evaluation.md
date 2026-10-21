# ADR-0013: Evaluation on Inspect AI, starting with seeded defects

**Status:** Accepted
**Date:** 2026-09-25

## Context

The tests are example-based (MVP plan §3). Each one shows that one path through an agent works,
and `CONFORMANCE.md` says plainly that "substantiated" is not an evaluation result. Nothing
measured how well an agent does across many inputs, or whether a change made it worse. The MVP
plan defers this to D4: "Inspect AI over the stratified ORDA corpus, seeded-defect pack,
Exercise 4 materials". The delivery plan it derives from (§7A.4) adopts Inspect AI because the
evaluation runner then becomes "mostly Inspect tasks and scorers rather than bespoke code". It
also counts `abstained`, `referred` and `suspended` as success states, scored apart from `failed`
(delivery plan §5.2). That plan is not in this repository.

No labelled corpus exists. The Blueprint says that no community benchmark exists either (§10,
C15). A seeded defect needs no labeller: start from a known-good input, break it in one named
way, and what the agent should do follows from the defect. The EnviSmart result cited in the
delivery plan (a producing role caught none of four seeded errors; an auditing role caught all
four) is the case for this design.

"Inspect AI" is always written in full here, because the viewer also has a page called Inspect.

## Decision

1. **Inspect AI runs evaluations.** A case is an Inspect `Sample`, and an agent's evaluation is
   an Inspect `Task`. The log (`.eval`) is the result, and `inspect view` browses it.
2. **Every case goes through the conductor.** The solver `workbench.evaluation.invoke_agent`
   builds an `InvocationRequest` and calls `Conductor.invoke`. The policy gate, the input check
   and the grounding linter run as they do for any invocation. By default the agent is served in
   memory over A2A; given an `agents.yaml`, the task reaches the deployed services instead. No
   model is called (`--model none`).
3. **What is common lives in the workbench; what an agent should recommend lives with the
   agent.** `workbench.evaluation` holds the solver, the scorers that apply to every agent
   (`outcome_matches`, `stopped_correctly`, `grounding_passed`) and the run comparison. An
   agent's own cases, defects and scorers are in its package (for R3, `dd_agent_r3.evals`),
   which imports the workbench lazily, as `dd_agent_r3.testing` does. `src/workbench/` still
   imports no agent.
4. **Stopping is scored as its own answer.** `stopped_correctly` asks whether the agent stopped
   exactly when the case expects it to. Stopping when it should have answered and answering when
   it should have stopped are counted separately. A `failed` run is neither.
5. **Scores stay separate.** There is no blended figure. For R3, recall of the expected
   recommendations and "no wrong recommendation" are two scores: a missed standard and a
   confidently wrong one are different failures. A scorer that does not apply to a case returns
   NOANSWER, and `mean_applicable` leaves that case out. Inspect's own `mean` would count it as
   zero, contrary to the rule that a missing input is `None`, never `0.0`.
6. **A defect is registered and never changes.** Defects are named functions in a registry
   (`dd_agent_r3.evals.defects.DEFECTS`), under the rule `CANONICALISATIONS` follows. A new
   mutation is a new name.
7. **A run records what produced it.** `AgentSpec.version` is set by hand and does not change
   when ranking rules, a snapshot or an explainer change. The task's `metadata["identity"]`
   records the git revision, the agent's configuration variables, and the hashes of the ranking
   rules, the snapshot and the case file.
8. **A committed baseline gates regressions.** Each evaluated agent commits a `baseline.json`
   (per-case scores and the run's identity). A pytest test runs the evaluation and fails if any
   case scores lower, or higher, or if the identity hashes differ. So the existing CI test job
   enforces it, and any change in behaviour shows up in review. The baseline is rewritten
   (`workbench/scripts/eval_compare.py --write-baseline`) in a commit of its own that says why.
9. **Evaluation is not conformance.** Evaluation tests carry no requirement marker, and
   evaluation results do not appear in `CONFORMANCE.md`.
10. **Cases publish identifiers, not records.** A case names FAIRsharing records by identifier
    only. The snapshot is CC BY-SA 4.0, and publishing record content in a case would carry that
    licence onto the case file.

## Dependencies introduced

| Dependency | Tier | Fallback if this dependency is abandoned |
|---|---|---|
| `inspect-ai` (the workbench `eval` extra) | Evaluation/CI path | A loop over the case file that calls `Conductor.invoke` and applies the scorers as plain functions. The scorers read only the envelope and the linter report in the sample's metadata, and the comparison reads only per-case floats, so both port directly. |

## Consequences

- An agent change that makes any seeded case worse fails CI. So does one that makes a case
  better without rewriting the baseline. Either way the change in behaviour is visible in review.
- The labels in R3's case file are provisional. They follow the Metadata Librarian's guidance in
  Uzwyshyn, *The Research Data Director* v0.8.2, and no domain expert has reviewed them. The
  labelled ORDA corpus is to replace them
  ([#22](https://github.com/data-director-agent/data-director/issues/22)). It plugs in as a
  second dataset for the same task.
- Seeded defects show only whether an agent responds to faults we introduced ourselves. They say
  nothing about performance on real deposits. The corpus is still needed.
- Inspect AI leaves one of its own memory streams unclosed. The evaluation test modules ignore
  that single `ResourceWarning` and force garbage collection at teardown, so that the warning
  does not fail an unrelated later test.
- A conductor must be built on the thread that uses it: one used across threads leaks its
  in-memory A2A streams. `invoke_agent` therefore runs every case on one worker thread and calls
  the conductor factory there.
- Do not add a requirement marker to an evaluation test. Do not change what a registered
  defect does. Do not blend scores into one figure.
- TODO: Exercise 4 workshop materials ("Should it have stopped?") can build on
  `stopped_correctly`. They are not written.
