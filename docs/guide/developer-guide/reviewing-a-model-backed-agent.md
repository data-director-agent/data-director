# Reviewing a model-backed agent

Use this checklist when you review a pull request that adds or changes an advisor that calls a
language model, from its first model-backed alpha onwards. That includes a pull request that
changes only a prompt: a prompt is code.

The rules themselves are in the [Agents](../../specs/agents.md) specification: invariant 14 for the
model-backed alpha state, and [Model-backed personas](../../specs/agents.md#model-backed-personas)
for how every such advisor is built. Each item below is a check against one of those rules, not a
restatement of it; where the two disagree, the specification wins and this page should be fixed.
`agents/advisor-standards/` is the worked example of the `template` default (`factory.py`,
`explain.py`), and `agents/advisor-documentation/` of the declared model and structured output
(`factory.py`, `prose.py`).

## The alpha state

Invariant 14 in [Agents](../../specs/agents.md#invariants).

- [ ] The package has a pre-release version (for example `0.1.0a1`), and its `README.md` and its
      row in the table in [`agents/README.md`](../../../agents/README.md) say it is alpha.
- [ ] Its grounding mode is `input_only`.
- [ ] Its description does not begin "Mock.", and the agent's own tests check that.
- [ ] It has a `template` writer, which calls no model, and it is the default unless the
      specification says otherwise (only `advisor-documentation` defaults to `model`). With the
      `template` writer and no key set, the agent runs, and its whole suite passes with no key.
- [ ] `AgentSpec.models` declares a `dd_sdk.agent.ModelUse` only when a model is configured, as
      `advisor-documentation`'s `factory.py` does; the template path declares none.
- [ ] The payload's `limitations` says what the advisor still does not do.
- [ ] Its tests are marked only with the project's own contract requirements (`DD-*`), not with a
      Blueprint requirement: an alpha substantiates none.

## The conventions

### 1. Deterministic shell, model core

- [ ] Input checks, abstentions, scores and anything exact (checksums, licence identifiers, the
      shape of a schema) are in code, not asked of the model.
- [ ] A content problem the shell finds ends as an outcome with a reason code before any model is
      called, not as an exception and not as a model call.
- [ ] A failed or rejected model reply falls back to the rule output rather than failing the run.

### 2. Structured output

- [ ] The model replies against a schema derived from the payload class, not free text that is
      parsed after the fact.
- [ ] A checker validates every reply before any of it is used.
- [ ] The checker records what it dropped and why, and that record reaches the payload or the
      run, so a reviewer can see it.

### 3. Safety by construction

- [ ] Where a miss is harmful, the model can add to the rules' output but cannot remove from it.
      Check the code that merges the two, not just the prompt.
- [ ] Where invention is harmful, the model chooses from a closed set the code supplies, and a
      value outside the set is dropped by the checker.
- [ ] Where the researcher must write a value, the model suggests beside it and never writes it
      ([Drafting documents](../../specs/drafting.md)).

### 4. Provenance per value

- [ ] Each payload field a model may write is declared in `AgentSpec.derivations` with a
      `recorded_in` sibling of type `Derivation` (invariant 8).
- [ ] That recorder is set per value, so a template fallback is shown as `template`, not `model`.
- [ ] Each model call is made with `dd_sdk.model.call`, not the provider's client directly, so
      it is recorded with `dd_sdk.prompts.ModelCallLog`; the log's `calls` and `prompts` are
      returned in the `AgentResult` ([Disclosure](../../specs/disclosure.md)).

### 5. Prompts are code

- [ ] The system prompt is `system_prompt.md` beside the module that sends it, not a string in
      the code or a file elsewhere.
- [ ] A change to a prompt is reviewed as a change to behaviour: the pull request says what is
      meant to change, and the tests or the evaluation show it.

### 6. Tests use a fake model

- [ ] The suite exercises the model path, including a rejected or malformed reply, with
      `dd_sdk.testing.FakeModel` or a fake kept in the agent's own `testing` module or tests.
- [ ] Nothing in the suite needs a key or the network; CI runs it as it is.

### 7. An evaluation before alpha ends

- [ ] A pull request that takes an advisor out of alpha (an ordinary version) brings an evaluation
      set that includes false-negative cases: the flags, discrepancies or options it must not miss
      ([Evaluation and conformance](../../specs/evaluation.md)).
- [ ] Until then, nothing claims the advisor is validated: not its `README.md`, its description or
      its test markers.

### 8. Tools after the first retrieval

- [ ] Tools follow [Tools: MCP servers and Agent Skills](../../specs/agents.md#tools-mcp-servers-and-agent-skills):
      the shell retrieves before the model is called; tools are read-only and limited per run;
      each record a tool returns is retrieved by the agent, with its `retrieval` span, before it
      may be cited; tool results reach the model as untrusted data in the user turn.
- [ ] A model's claim about a record stands only on something code checks, such as a quote found
      in that record, and its tests include a fabricated quote and an instruction planted in a
      record.
- [ ] Until the harness's tool gateway exists (TODO(#875)), a tool reaches its registry from the
      agent, as `advisor.policy`'s do (`advise.py`).

## Per advisor

The roster review in [Agents](../../specs/agents.md#the-roster) chose which advisors take a model
next and how. Check a pull request for one of them against its row as well.

- **Ethics (`advisor.ethics`) and DMP (`advisor.dmp`).** The model reads language where the rules
  are weak, and adds to the rules' flags; it never removes one from what the person reviewing
  sees. The DMP checker's model may merge two flags into one (a `missing` and an `unplanned`
  output it reads as one renamed output become one `renamed` flag, still for review), or move a
  flag to the payload's `reconciled` list with its reason (two names for one licence or
  repository); both stay in front of the reviewer. The ethics adviser flags sensitive
  data and stops there: deciding how such data are handled
  (`governance.sensitive-data-handle`) is a person's decision.
- **Rights (`advisor.rights`).** The model chooses from a closed set of licences or terms that the
  code supplies; it never writes a licence identifier of its own. In the alpha the set is the
  rows of `licences.yaml`: every licence offered is built from a row, an id the model names from
  outside is dropped and listed in `dropped`, and a licence that fits the reuse it read is never
  left out (`advisor-rights/interpret.py`, `check`). Its tests include a reply naming licences
  outside the table.
- **Metadata (`advisor.metadata`).** The model suggests beside a value the researcher must give;
  it never fills or overwrites the value.
- **FAIRness (`advisor.fairness`).** The model writes the recommendations only. Assessments and
  scores stay in code.
- **Policy (`advisor.policy`).** The model may add policies it found with its tools and
  obligations it read, each with a quote the agent finds in the cited record; it never removes a
  policy the rules matched or weakens an obligation read by rule, and it never names an actor
  whose name was ambiguous.

These stay deterministic, so a pull request that puts a model behind any of them needs the
specification changed first: `advisor.quality`, `advisor.linking`, `advisor.files`,
`orchestrator.stub` and `example.hello`.

## Before approving

- [ ] The agent's tests pass with no key: `uv run pytest agents/<name>`.
- [ ] `uv run python scripts/check_todos.py` passes.
- [ ] `uv run --only-group docs mkdocs build --strict` passes if documentation changed.
- [ ] If the agent keeps a `CHANGELOG.md`, it has an entry, and a prompt change is listed there
      as a change in behaviour.
