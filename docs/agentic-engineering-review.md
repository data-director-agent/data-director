# Agentic engineering review

This review compares Data Director with current practice in agentic AI engineering and proposes
improvements that stay within the [Blueprint](https://doi.org/10.15497/RDA00157). It was written
in November 2026 against `main` at `ecc1c6c`. The practice it summarises is that of 2024 to 2026,
and much of it is still changing. Each claim about outside practice links to its source in
[References](#references). A claim marked *(unverified)* could not be confirmed against a primary
source.

It complements the [Architecture review](architecture-review.md), which looks at complexity inside
packages. This review looks at the shape of the agent system as a whole.

## Summary

Data Director already follows most of what the field now agrees on. Several of its choices are
ahead of common practice: the single governed path, the deterministic shell around each model,
tool definitions pinned by digest, and state derived from an append-only log. The gaps are not in
its paradigm. They are in four capabilities the specs already name and that are not yet built:

1. **Durable pause and resume.** Elsewhere, human approval is a pause and a resume. Here the
   approval half of the policy gate does not exist yet (#16, #72, #73).
2. **Recovery and reuse of runs.** A run cannot be resumed after a crash, and a result cannot be
   reused for an identical request (C8, C17).
3. **Context and tool scaling in the orchestrator.** The orchestrator keeps a fixed window of 20
   turns and offers one tool for each input class of every registered agent.
4. **Evaluation of the model paths and of the orchestrator's choices.** Most committed baselines
   measure only the template paths.

None of these needs an agent framework. The project's reasons for rejecting LangGraph still hold
and are stronger now, but four of LangGraph's ideas are worth adopting in the project's own terms:
interrupts, checkpoints, idempotent steps and tool selection.

## 1. What current practice says

### 1.1 Workflows, agents and harnesses

- **Workflows and agents.** Anthropic's taxonomy is still the reference [1]. A *workflow* runs
  models and tools along code paths fixed in advance. An *agent* is a model that directs its own
  process. Between the two sit five patterns: prompt chaining, routing, parallelisation,
  orchestrator-workers and evaluator-optimiser.
  - The advice is to use the simplest system that works.
  - Design tools with the same care as a user interface.
  - Understand any framework before relying on it.
- **The harness.** "Harness" has become the industry's name for the code around the model: the
  loop, tools, context management and checkpoints [2][3][4].
  - Anthropic's 2026 harness post makes the point that matters most here [3]. Each component of a
    harness "encodes an assumption about what the model can't do on its own". As models improve,
    those assumptions go stale and should be removed.
  - LangChain reports a large benchmark gain from changing only the harness, with the model held
    fixed [4].
- **Owning the loop.** HumanLayer's *12-factor agents* is the framework-free position [6]:
  - own your prompts, your context window and your control flow;
  - treat tools as structured output;
  - launch, pause and resume through simple APIs;
  - contact humans through tool calls;
  - keep agents small and focused;
  - make the agent a stateless reducer over its state.
- **Loop and graph combined.** Practitioners no longer choose between a model-in-a-loop and an
  explicit graph; they combine them. LangChain's own guide lists subagents-as-tools, handoffs,
  skills, routers and custom workflows, and says the patterns compose [7].

### 1.2 One agent or many

This is still the main open dispute.

- Cognition argued for single-threaded agents, because multi-agent systems lose context between
  agents and make conflicting implicit decisions [8].
- Anthropic's research system showed that parallel subagents pay off on breadth-first work, at
  about 15 times the tokens of a chat [9].
- Cognition's 2026 follow-up settles on a middle position [10]. These work:
  - reviewer agents with a clean context;
  - read-only search subagents;
  - manager-to-child delegation.

  These do not:
  - parallel writers;
  - unstructured swarms.

  The rule is "keep writes single-threaded": extra agents should add intelligence, not actions.

### 1.3 LangGraph 1.x

LangGraph and LangChain 1.0 shipped in October 2025 [11][12]. The current practice has six parts:

- **Agent construction.** `create_agent` with middleware, including human-in-the-loop,
  summarisation, PII redaction and tool selection. `langgraph-supervisor` is in maintenance, in
  favour of subagents as tools [13].
- **Typed state.** State has reducers per channel and separate input, output and private schemas.
  `Command` combines an update with a route, and `Send` fans out to workers [15].
- **Checkpoints.** A checkpoint is written at every super-step, keyed by thread. Durability can
  be `exit`, `async` or `sync`, and PostgreSQL savers are used in production [16][17].
- **Interrupts.** `interrupt()` pauses a node and `Command(resume=…)` resumes it. The node re-runs
  from its start, so code before the interrupt must be idempotent [19].
- **Time travel.** A run can be replayed from a checkpoint, or forked with `update_state` [17].
- **Deep Agents.** A "batteries included" harness: planning, a virtual filesystem, subagents with
  isolated context, skills and memory [5].

### 1.4 Context engineering, tools, Skills and MCP

- **Context engineering.** Context is a limited attention budget: recall falls as the token count
  grows ("context rot") [21]. The remedies:
  - the smallest set of high-signal tokens;
  - minimal tool sets that do not overlap;
  - retrieval just in time;
  - compaction, or clearing old tool results;
  - structured notes kept outside the window;
  - subagents that return condensed results.

  The 2026 harness post adds context *resets* with a structured handoff as an alternative to
  compaction [3].
- **Tools for agents.** Build tools around tasks, not one per endpoint [22]. Namespace them,
  return meaningful fields, truncate with sensible defaults, and write error messages that tell
  the agent how to fix its call. Improve them against evaluations.
- **Agent Skills.** Now an open standard [23]. It discloses progressively: the name and
  description first, then the body, then references when needed.
- **Code execution with MCP.** Present MCP servers as code APIs to a sandboxed agent [24]. This
  cuts tokens sharply, but needs a sandbox and egress controls.
- **MCP security.** The known attacks are:
  - tool poisoning, rug pulls and shadowing [25];
  - token passthrough and confused-deputy attacks [26];
  - the "lethal trifecta" of private data, untrusted content and a way to send data out [27].

  The consensus is that classifiers are not a security boundary. The design itself must keep
  untrusted input away from consequential actions.

### 1.5 Durable execution

Long-running agents are now built as durable workflows: Temporal with the OpenAI Agents SDK
[28], DBOS checkpoints in PostgreSQL [29], or LangGraph's checkpointer.

- Model and tool calls are recorded steps.
- Orchestration code is deterministic, so it can be replayed.
- Every side effect is idempotent, because a step may be retried.
- A failed run resumes where it failed instead of starting again [9].

### 1.6 Protocols

- **A2A** reached 1.0 in March 2026 and is now hosted by the Linux Foundation's Agentic AI
  Foundation (AAIF) [30][31][32]. It adds signed agent cards, `securitySchemes`, the
  `INPUT_REQUIRED` and `AUTH_REQUIRED` task states, extensions declared by URI and negotiated
  through `A2A-Extensions`, and version negotiation through `A2A-Version`.
- **MCP's current revision is 2026-07-28** [34][35]. It is stateless: there is no `initialize`
  step and no session ID. It also changes:
  - an `input_required` result replaces server-initiated sampling and elicitation;
  - Tasks become an extension;
  - `tools/list` should list tools in a deterministic order, so that prompts cache;
  - trace context travels in `_meta`;
  - Client ID Metadata Documents replace Dynamic Client Registration.

  One source calls this revision a release candidate *(unverified as final)*.
- **AG-UI** streams lifecycle, message, tool-call, state and subagent events. Its interrupt and
  resume for human approval is still a draft [38].

### 1.7 Evaluation and observability

- **Evals.** Anthropic's 2026 guidance on evaluating agents [39]:
  - use code, model and human graders;
  - grade what the agent produced before the path it took;
  - report pass@k or pass^k to suit the case;
  - calibrate model judges against human experts, and give them an "Unknown" option;
  - promote capability evaluations into regression suites;
  - read the transcripts.

  The emerging practice is to grade outcomes by default and add targeted assertions on the
  trajectory for actions that are required or forbidden.
- **OpenTelemetry.** The `gen_ai.*` semantic conventions have moved to their own repository and
  are all still at Development status [40][41]. The first standalone release renames the agent
  and tool spans [42], so a mapping to them should be kept in one place.

### 1.8 Governance and safety

- **Structural defences against prompt injection.** The 2025 design-patterns paper [43] gives six:
  action-selector, plan-then-execute, LLM map-reduce, dual LLM, code-then-execute and
  context-minimisation. Its principle: once an agent has read untrusted input, constrain it so
  that the input cannot trigger a consequential action.
- **CaMeL** [44] goes further. A privileged model plans from the trusted query, a quarantined
  model reads the untrusted data, and an interpreter enforces data-flow policy.
- **Threat catalogues and standards.**
  - The OWASP Top 10 for Agentic Applications (December 2025) catalogues the threats [46].
  - NIST's AI Agent Standards Initiative works on agent identity and authorisation, with OAuth,
    SPIFFE and MCP [47].
  - Under the EU Digital Omnibus, the high-risk obligations of the AI Act move to December 2027
    [48][49].

## 2. Where Data Director stands

### 2.1 A note on the word "harness"

Here, the *harness* is the governance around every run: the conductor, policy gate, checks,
stores and provenance. Elsewhere, a harness usually means the agent's runtime loop. In Data
Director that loop lives inside each agent, on the `dd_sdk.model` seam. This review uses
"governance harness" and "agent loop" to keep the two apart. The distinction matters, because
most outside advice about harnesses applies to the agent loops, not to the conductor.

### 2.2 Paradigm by paradigm

| Practice | Data Director | Assessment |
|---|---|---|
| Workflows before agents; simplest system first [1] | Every advisor is a "deterministic shell, model core": rules decide and the model adds judgement and language ([Agents](specs/agents.md#model-backed-personas)). Every model path has a `template` path behind it. | Strong. It is prompt chaining with programmatic gates, as [1] recommends. |
| Routing; orchestrator-workers [1][7] | `orchestrator.stub` routes by rules. `orchestrator.model` delegates to specialists offered as tools, one level deep ([Orchestration](specs/orchestration.md)). | Matches the "subagents as tools" pattern that LangChain now recommends over supervisors [13]. |
| Parallelisation [1][9] | Delegations within a turn run one after another (`orchestrator-model/agent.py`). | Gap: independent read-only children could run concurrently (C10). |
| Evaluator-optimiser; reviewer with a clean context [1][10] | `advisor.quality` exists but runs only when the orchestrator chooses it. The SHACL validation is deterministic and comes at the deposit step. | Partial: C15 asks for checks on the system's own outputs before a person sees them. |
| Own the loop and the control flow (12-factor) [6] | No framework. Each agent's loop is explicit and bounded (`MAX_TOKENS`, `DEFAULT_MAX_DELEGATIONS = 4`, lookup limits per run). | Strong, and well argued ([Dependencies](specs/dependencies.md#rejected-alternatives)). |
| Single writer; extra agents add intelligence, not actions [10] | No agent holds write credentials. Agents propose; the conductor writes to the project log; a person approves. | Strong: a stricter form of Cognition's rule. |
| Unify execution state and business state; stateless reducer [6] | Progress, entry point and decisions are derived from the project log on every read. Nothing keeps a cursor. | Strong: event sourcing achieves what LangGraph's typed state and reducers achieve, with no store of a second copy. |
| Pause and resume; human approval as an interrupt [6][19][32] | The `suspended` outcome is in the contract. A class that needs approval is *referred*, and nothing resumes it (#16, #72, #73). Questions are non-blocking turns (invariant 16). | **Main gap.** P4 and C13 are met by refusing, not by waiting. |
| Durable execution; resume after failure [9][16][28][29] | Every run is recorded, and children survive a failed parent. A crashed run is not resumed, and a run has no journal of its steps. | Gap against C8 ("recover automatically") and C10 (asynchronous bulk work). |
| Context engineering [21] | Notes derived from the project record by the harness, and a stable system prompt that caches. History is the last 20 turns (`DEFAULT_HISTORY_TURNS`). | Good structured state. The fixed window and the tool list that grows with every agent will not scale. |
| Tool design [22] | One tool for each input class of every registered agent, plus a few tools of the orchestrator's own. Tool names come from the manifest. | Workable at about 16 agents. It is the overlap and "too many tools" pattern that [21][22] warn against as the roster grows. |
| Agent Skills [23] | Skills are vendored and pinned by digest. They are text only and code chooses them, with no scripts. | Conservative and defensible. It gives up progressive disclosure to keep governance. |
| MCP security [25][26][27] | Tool gateway; tool definitions pinned by digest (stops rug pulls); a grant per invocation; no token passthrough; only `structuredContent` grounds; tool results quoted as untrusted data. | Ahead of common practice. Poisoning on first listing relies on the operator's review when pinning. |
| Lethal trifecta [27] | Private data: the project. Untrusted content: documents, registry records. Outward channel: links in replies, which are kept only if the address was already seen. No agent writes outside the project. | Mitigated by construction. Undocumented until the threat model (#37) exists. |
| Prompt-injection design patterns [43][44] | Closed sets of identifiers (action-selector); quotes found word for word by code (data attribution); the orchestrator has no tools beyond delegation (context-minimisation); grounding checks by the harness. | Strong, but the patterns are not named, so reviewers cannot check them. |
| A2A [32] | `a2a-sdk` 1.x; card extensions; harness-mediated callbacks under a grant. Calls between the harness and agents are unauthenticated and rely on loopback (#17). | Gap: A2A 1.0 gives `securitySchemes` and signed cards. |
| MCP revision [34] | The gateway speaks the stateless streamable HTTP transport, `mcp` 2.3. | Aligned in direction. Deterministic tool order and Tasks are worth checking. |
| AG-UI [38] | Used from harness to browser. Streaming replies not built (#159). | Gap against C10 (visible progress). |
| Evaluation [39] | Inspect AI, seeded defects, false negatives first, evaluation kept apart from conformance. Six agents evaluated, mostly on template paths. No evaluation of the orchestrator. | Excellent method, thin coverage of the model paths. |
| OpenTelemetry [40][42] | `dd.*` attributes are fixed and `gen_ai.*` added beside them. Spans: `invoke_agent`, `execute_tool`, `chat`. | Right choice. One deprecated attribute (`gen_ai.system`) is still written. |

### 2.3 Why not LangGraph (or another framework)

The rejection in [Dependencies](specs/dependencies.md#rejected-alternatives) still holds, and
current practice strengthens it:

- **The field has moved toward owning the loop.** LangChain itself now presents `create_agent` as
  a minimal harness with middleware [4][12]. Anthropic says every harness component should be
  revisited as models change [3]. Neither favours a heavy runtime that hides steps.
- **LangGraph's main gifts are already here, in auditable form.** Its checkpointer and reducers
  correspond to the run store and the project log. Its replay corresponds to the stored request
  and input hash. Its `Command` handoffs correspond to the conductor's delegation under a grant.
- **The Blueprint rules out a hosted platform.** P10 (Data Sovereignty), P11 (Deploy Anywhere)
  and P13 (Built to Last) rule out LangSmith Deployment and its equivalents. The
  framework-specific supervisor and swarm libraries have already gone into maintenance or become
  dated [13]. That is the churn P13 warns against.
- **Governance must sit outside the loop.** Framework guardrails cover the first and last agent,
  and handoffs bypass them [45]. A conductor that every run must pass through has no such hole.

## 3. Improvements within the Blueprint

The improvements are in order of value. Each names the Blueprint clauses it serves and the
constraint that bounds it. All keep the fixed formats unchanged, except where a spec change is
named; [Rule 1](../AGENTS.md#rules) then applies.

### 3.1 Build the approval half of the gate as a durable interrupt (P4, C8, C13, C14)

This is the issue the specs already name (#16, #72, #73). Current practice gives it a tested
design: LangGraph's `interrupt` [19], A2A's `INPUT_REQUIRED` [32], and the interrupt outcome in
AG-UI [38].

- **Suspend and record.** The gate returns `suspended`, not `referred`. The contract already
  provides the outcome and its resumption condition. The conductor records an approval request
  bound to the input hash, the agent version and the profile digest.
- **Resume as a new invocation.** It is linked to the suspended one by lineage, so provenance
  shows the approval as an `AssessAction` between the two (P5). LangGraph re-runs the interrupted
  node from its start [19]. Here nothing runs before the gate, so a resume has no partial work to
  repeat. Keep it that way: an approval comes before the agent, never in the middle of it.
- **Approve proposed effects.** For actions outside a project (#72), the agent proposes the
  effect in its payload. The conductor performs it only after approval, under an idempotency key
  derived from the invocation and the effect. That is the durable-execution rule that side
  effects be idempotent [28][29]. An effect a person confirmed as irreversible is logged and
  disclosed, as C8 requires.
- **Map it to the protocols.** On the A2A way in, map a suspended run to the `INPUT_REQUIRED`
  task state. In the app, offer it as an AG-UI interrupt only once that part of AG-UI is stable;
  until then keep the project page as the place a person decides.

**Bound:** questions stay non-blocking, as orchestration invariant 16 decides. Only approvals
suspend.

### 3.2 A step journal for recovery and reuse (C7, C8, C10, C17, P14)

The run store already holds requests and envelopes. Two small additions give most of what
durable-execution engines give, without adopting one.

- **Reuse of identical runs (C17, P14).** Before running a child, the conductor looks for a
  succeeded run with the same agent, agent version, input hash, profile digest and source pins.
  If one exists, it returns that run's envelope, recorded as reused, with a provenance link to
  the original rather than a fresh run.
  - Live sources (`*:live:<date>`) and model paths without a pinned model are excluded by
    default. A profile key could allow them, since this is a deployment's choice about cost.
  - This is C17's requirement that agents "must not duplicate work".
- **Resuming a turn after a crash.** If an orchestrator run dies after some of its children
  succeeded, a retried turn reuses those children through the rule above, instead of running and
  billing them again. That is replay with results restored, as in DBOS [29] and LangGraph's
  functional API [18], expressed in the store the project already has.
  - The turn lock and "a turn follows the latest" already provide the idempotency key.
- **Asynchronous bulk work (C10).** Run bulk operations, such as retrofitting many records (R9),
  as queued invocations in the PostgreSQL backend, and notify on completion. Consider DBOS or a
  plain outbox table behind a `RunQueue` protocol with a file-backend fallback. Do not adopt
  Temporal, which adds a cluster to run.

**Bound:** a new canonicalisation is needed for the reuse key. Register it in
`dd_sdk.evidence.CANONICALISATIONS` and change [Storage](specs/storage.md) and
[Provenance](specs/provenance.md) in the same pull request.

### 3.3 Context engineering for the orchestrator (C10, C17, P14)

- **Replace the fixed window with derived state and a recorded summary.** The harness notes
  (repository, decisions, drafts, progress) already carry most of what matters. For long
  conversations, add a summary of earlier turns as a compaction [21]. Make the summary a run of
  its own, stored and linked, so it is traceable (P5) and explainable (P8). It is never an
  unrecorded rewrite of the history. The input hash goes on covering the whole history.
- **Scope the tools to the step.** Offer the model only the agents that serve steps open in the
  current and next phase, from `dd_harness.progress`, plus a fixed `other_steps` escape that
  lists the rest. This is LangChain's tool-selection middleware [12] and Anthropic's minimal tool
  sets [21], done by code and not by a model, so it stays deterministic and auditable.
  - Keep tool order deterministic, so the prompt caches, as MCP 2026-07-28 now asks of
    `tools/list` [34].
- **Condensed child results.** Give the orchestrator each child's result in a short form fixed by
  the payload class (its decisions, concerns and cited sources), with the full payload in the
  store. This is the subagent pattern of [9] and [21]. It needs no new format if the condensed
  view is generated from the payload class.

### 3.4 A bounded reviewer after drafting (C15, P4)

C15 asks that the system check its own outputs and flag low-quality ones before a person reviews
them. Cognition reports that reviewers with a clean context are among the multi-agent patterns
that work [10].

- After a drafting child returns a `Document`, run `advisor.quality` on it automatically, as a
  child of the same turn and once only.
- Show its findings beside the draft.
- The reviewer never edits; the drafter is not re-run automatically. The person decides, under
  P4.
- Whether this runs is a profile key, as a deployment's policy choices must be.

This is evaluator-optimiser [1] with the optimising step left to a person.

### 3.5 Parallel read-only delegation (C10)

When the model asks for several delegations in one turn and all are advisory (no `Document`
payload), run them concurrently. Keep drafting children sequential: "keep writes single-threaded"
[10]. The conductor already runs parents and children side by side across conversations. The
change is inside one orchestrator turn, and so is local to `orchestrator-model`.

### 3.6 Evaluate what the models do, and what the orchestrator chooses (C14, C15, C16)

- **Model-path baselines.** Make model-path baselines part of each advisor's evaluation, run
  against a pinned model with recorded responses (`pytest-recording` is already adopted), so CI
  needs no key. This closes #415 and the like.
- **Orchestrator evaluation.** Cases are researcher turns with labelled expectations:
  - which agent should be delegated to;
  - which steps must not be offered (out of scope, or a skipped governance step);
  - that no claim is made without a cited child.

  Score the outcome and the evidence first, with a few assertions on the trajectory for forbidden
  actions, as [39] advises.
- **pass^k for safety flags.** Report pass^k, not pass@k, for flags that must not be missed, such
  as personal data (C2) and consent.
- **Calibrated judges.** Use a model judge only for prose quality. Calibrate it against a data
  steward's labels and give it an "Unknown" option. Keep its scores out of conformance, as
  [Evaluation and conformance](specs/evaluation.md) already requires.
- **Cases from real use (C16).** Turn steward escalations and case exports (`dd-harness case
  export`) into evaluation cases, with consent and pseudonymisation.

### 3.7 Write the threat model from the design patterns (C1, C13, #37)

The mitigations exist; what is missing is the document that says which threat each one answers.
Write #37 around:

- the lethal trifecta [27];
- the six design patterns of [43];
- the OWASP agentic Top 10 [46].

Map each to the existing control: closed sets, quote verification, tool pinning, link filtering,
the orchestrator having no tools, and the grant per invocation. That makes the structural
defences reviewable, and shows where none exists. Two gaps already show:

- **Agent authentication (#17).** Use A2A 1.0's `securitySchemes`, with mTLS or workload
  identity (SPIFFE, as NIST's concept paper proposes [47]) between the harness and agents. Use
  signed agent cards so that the registry can verify the card it pins.
- **First-listing tool poisoning.** Tool pinning catches a change after review, not a poisoned
  first listing [25]. Add a review checklist to `dd-harness tools pins` that shows each tool's
  full description and schema before it is pinned.

### 3.8 Separate governance from scaffolding

Anthropic's point that harness components encode assumptions about model weakness [3] applies to
the agent loops, not to the governance harness. Make the difference explicit, so that one is
never relaxed in the name of the other.

- **Governance invariants** come from the Blueprint and never relax as models improve: the policy
  gate, grounding, source checks, single writer, human approval and provenance.
- **Capability scaffolds** are there because of today's models and are tuned by evaluation:
  history length, delegation limits, lookup limits, the rules a model may only add to, and the
  template fallbacks.

Record each scaffold's reason beside its constant, and revisit it when the model changes, with
the evaluations of 3.6 as the test. Where `advisor.policy`, `advisor.standards` and
`orchestrator-model` each write a bounded tool loop, consider one loop on the `dd_sdk.model` seam
(the [Architecture review](architecture-review.md) notes copying between agents), provided it
stays free of contract concepts.

### 3.9 Track the protocols (C5, P6, P13)

- **MCP 2026-07-28.** Confirm that the gateway lists tools in a deterministic order and accepts
  trace context in `_meta`. Consider the Tasks extension for slow lookups. Refuse Sampling, now
  deprecated, as the gateway already refuses anything not granted.
- **A2A 1.0.** Send and check `A2A-Version`. Declare Data Director's card extensions with
  `required` where the harness depends on them, so that a client lacking one fails clearly.
- **OpenTelemetry.** Keep `dd.*` primary and the `gen_ai.*` mapping in one module. Drop
  `gen_ai.system`, which `gen_ai.provider.name` replaces, and follow the span renames of [42]
  once they are released.
- **AG-UI.** Stream replies and progress events (#159) for C10.

## 4. What not to adopt

| Option | Why not |
|---|---|
| LangGraph, CrewAI or a similar runtime | See 2.3: the governance must sit outside the loop, and P13 warns against framework churn. Adopt the ideas: interrupts, checkpoints, idempotent steps and tool selection. |
| A hosted agent platform (LangSmith Deployment, cloud agent engines) | P10 and P11. |
| Code execution with MCP [24] | It needs a sandbox and egress, does not carry over to a local model, and its generated code is harder to ground. The token saving matters little at this tool count. |
| Parallel writers or swarms | Cognition's evidence [10], and the single-writer rule that P4 implies. |
| Model-chosen Skills or Skills with scripts | They would widen what a persona may do outside its card and the profile ([Agents](specs/agents.md#tools-mcp-servers-and-agent-skills)). |
| Guardrail classifiers as a security boundary | They are probabilistic [27]. Use them, if at all, as a signal that refers a run to a steward, never as the control. |
| Delegation more than one level deep | Nothing in R1 to R12 needs it, and each level multiplies tokens [9] and loses context [8]. |

## 5. Proposed issues

These are candidates to file. None has been filed with this review.

1. Approval as `suspended`, with resume as a linked invocation and A2A `INPUT_REQUIRED` (extends
   #16, #72, #73).
2. Reuse of identical runs by a registered reuse key, and resumption of a crashed turn (C8, C17).
3. Queued invocations for bulk operations, with notification (C10).
4. Tool scoping by phase, and condensed child results, in `orchestrator-model`.
5. A recorded summary of earlier turns in place of the fixed history window.
6. An automatic `advisor.quality` review after drafting, as a profile key (C15).
7. Concurrent advisory delegations within a turn.
8. Model-path baselines and an orchestrator evaluation, with pass^k for safety flags.
9. A threat model mapped to the trifecta, the design patterns and the OWASP agentic Top 10 (#37).
10. Authentication between harness and agents with A2A 1.0 security schemes and signed cards
    (#17).
11. Protocol tracking: MCP 2026-07-28, `A2A-Version`, and the OpenTelemetry GenAI renames.

## References

1. Anthropic, [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents), December 2024.
2. Anthropic, [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents), November 2025.
3. Anthropic, [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps), March 2026.
4. LangChain, [How middleware lets you customise your agent harness](https://blog.langchain.com/how-middleware-lets-you-customize-your-agent-harness); [Improving Deep Agents with harness engineering](https://blog.langchain.com/improving-deep-agents-with-harness-engineering).
5. LangChain, [Deep Agents](https://docs.langchain.com/oss/python/deepagents/index).
6. HumanLayer, [12-factor agents](https://github.com/humanlayer/12-factor-agents).
7. LangChain, [Multi-agent](https://docs.langchain.com/oss/python/langchain/multi-agent).
8. Cognition, [Don't build multi-agents](https://cognition.com/blog/dont-build-multi-agents), June 2025.
9. Anthropic, [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system), June 2025.
10. Cognition, [Multi-agents: what's actually working](https://cognition.com/blog/multi-agents-working), April 2026.
11. LangChain, [LangChain and LangGraph 1.0](https://blog.langchain.com/langchain-langgraph-1dot0), October 2025.
12. LangChain, [LangGraph v1 release notes](https://docs.langchain.com/oss/python/releases/langgraph-v1); [Agent middleware](https://www.langchain.com/blog/agent-middleware).
13. LangChain, [Migrating from langgraph-supervisor](https://docs.langchain.com/oss/python/migrate/langgraph-supervisor).
14. LangChain, [LangGraph Platform renamed](https://changelog.langchain.com/announcements/ann_NXVDQVGqbwBqW).
15. LangChain, [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api).
16. LangChain, [Durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution).
17. LangChain, [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers).
18. LangChain, [Functional API](https://docs.langchain.com/oss/python/langgraph/functional-api).
19. LangChain, [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts).
20. LangChain, [Deep Agents harness](https://docs.langchain.com/oss/javascript/deepagents/harness).
21. Anthropic, [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents), September 2025.
22. Anthropic, [Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents), September 2025.
23. [Agent Skills specification](https://agentskills.io/).
24. Anthropic, [Code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp), November 2025.
25. Invariant Labs, [MCP security notification: tool poisoning attacks](https://invariantlabs.ai/blog/mcp-security-notification); [arXiv 2506.01333](https://arxiv.org/pdf/2506.01333).
26. Model Context Protocol, [Security best practices (2026-07-28)](https://modelcontextprotocol.io/specification/2026-07-28/basic/security_best_practices).
27. S. Willison, [The lethal trifecta for AI agents](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/), June 2025.
28. Temporal, [OpenAI Agents SDK integration](https://docs.temporal.io/develop/python/integrations/openai-agents-sdk).
29. Pydantic, [Durable execution with DBOS](https://pydantic.dev/docs/ai/integrations/durable_execution/dbos/).
30. AAIF, [A2A joins the Agentic AI Foundation](https://aaif.io/blog/a2a-joins-aaif).
31. Linux Foundation, [A2A in its first year](https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year).
32. [A2A specification](https://a2a-protocol.org/latest/specification/).
33. Linux Foundation, [Formation of the Agentic AI Foundation](https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation).
34. Model Context Protocol, [Changelog, 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/changelog).
35. AAIF, [MCP 2026-07-28: what's changing and how to migrate](https://aaif.io/blog/mcp-2026-07-28-whats-changing-and-how-to-migrate).
36. Model Context Protocol, [Changelog, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/changelog).
37. [AG-UI protocol](https://github.com/ag-ui-protocol/ag-ui).
38. AG-UI, [Events](https://docs.ag-ui.com/concepts/events).
39. Anthropic, [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), January 2026.
40. OpenTelemetry, [GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/); [semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai).
41. Dash0, [OpenTelemetry GenAI semantic conventions explained](https://www.dash0.com/knowledge/opentelemetry-genai-semantic-conventions-explained).
42. OpenTelemetry, [semantic-conventions-genai changelog](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/CHANGELOG.md).
43. Beurer-Kellner, Tramèr et al., [Design patterns for securing LLM agents against prompt injections](https://arxiv.org/abs/2506.08837), June 2025.
44. Debenedetti et al., [Defeating prompt injections by design (CaMeL)](https://arxiv.org/abs/2503.18813).
45. OpenAI, [Agents SDK guardrails](https://openai.github.io/openai-agents-python/guardrails/).
46. OWASP, [Top 10 for Agentic Applications](https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agent), December 2025.
47. NIST, [AI Agent Standards Initiative](https://www.nist.gov/caisi/ai-agent-standards-initiative), February 2026.
48. Orrick, [EU AI Act update: Digital Omnibus](https://www.orrick.com/zh-CN/Insights/2026/07/EU-AI-Act-Update-Digital-Omnibus-Finalizes-8-Compliance-Changes), July 2026.
49. Pinsent Masons, [Rules on high-risk AI delayed under EU omnibus deal](https://www.pinsentmasons.com/out-law/news/rules-high-risk-ai-delayed-under-eu-omnibus-deal).
