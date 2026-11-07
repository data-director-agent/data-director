# agents

Rules for working on an agent under `agents/<name>/`. The recipe for adding one is
[`README.md`](README.md), and [`example-hello/`](example-hello/) is the worked example to copy
([Agents](../docs/specs/agents.md)). The repository-wide rules in the root
[`AGENTS.md`](../AGENTS.md) apply as well.

An agent's code, data, schema, scripts, evaluation cases and tests live in its own directory. If
you find yourself writing one agent's logic, cases or data in the harness, the SDK, the app or
the workbench, stop.

## Load-bearing things

- **Adding an agent touches nothing central.** A package under `agents/` with `AgentSpec` +
  `run` + `build` + `main`, one line in each registry file, a sample, the payload's
  `derivations`, marked tests and a profile entry. If you find yourself editing the conductor,
  linter, CLI, transport, viewer or app shell to add an agent, stop.
- **An agent is a service.** Nothing outside `agents/` imports `dd_agent_*` from its `src/`; only
  tests do, to serve an agent in memory (`dd_harness.testing.in_process`).
- **An agent returns an `AgentResult` (outcome, payload, evidence) and nothing more.** If you find
  yourself setting `invocation_id` or `grounding_mode` in an agent, stop: only the conductor
  fills them.
- **An agent's classes are its own ([Contract](../docs/specs/contract.md)).** It declares its
  input and payload classes in its own LinkML file (`<name>.yaml`), and its card carries their
  schemas pinned by digest. Do not add them to the core's `data_director.yaml`.
- **An input or payload class carries `schema_class`; a payload class mixes in `Grounded`.**
  `grounded_on` is the only place identity is asserted. A payload without it fails the linter
  (G0) by design, and a card whose payload schema does not require it is refused.
- **An identity is stated once, in `grounded_on` ([Evidence and grounding](../docs/specs/grounding.md)).**
  What a reader is shown about a cited record comes from the evidence item's `content`, which E1
  re-hashes. Do not add a descriptive copy of a grounded record to a payload class; that copy
  would be unchecked.
- **The manifest says what an agent does, not how to draw it ([Agents](../docs/specs/agents.md)).**
  An agent declares how it produces each payload field in `AgentSpec.derivations`; the app and
  the viewer work out the rest of the presentation from the schema, whose property order
  `dd-gen-schema` keeps as the LinkML slot order. Do not add an RJSF fragment, widget name or
  layout hint to `AgentSpec`.
- **A content problem is an outcome, not an exception.** Empty search → `abstained`; registry
  down → `abstained(registry_unavailable)`; policy refusal → `failed` with Problem Details or
  `referred`.
- **A rule with missing inputs returns `None`, never `0.0`**
  (`advisor-standards/src/dd_agent_advisor_standards/rank.py`).
- **A demonstration agent does not substantiate a Blueprint `R` it does not meet.** Mark a test
  only with a requirement it actually exercises.
- **`advisor-standards/data/fairsharing/snapshot.jsonl` is CC BY-SA 4.0** (see its LICENCE.md).
  Rebuild it with `advisor-standards/scripts/build_snapshot.py`; do not hand-edit records.
- **An evaluation defect is registered, never edited**
  (`dd_agent_advisor_standards.evals.defects.DEFECTS`): a new mutation is a new name. An agent's
  `baseline.json` changes only in a commit of its own that says why
  ([Evaluation and conformance](../docs/specs/evaluation.md)).
- **Shared doubles for one agent's tests live in that agent's `testing` module** (for example
  `dd_agent_advisor_standards.testing`), not in another package.
