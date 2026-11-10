# Orchestration

## Intent and scope

The Blueprint's Data Director is one agent a person converses with, which hands work to
specialist agents (§9.3). This spec covers how that works here: conversations made of turns, an
orchestrator that delegates to other agents only through the harness, and how an orchestrator
places agents in the researcher's work by the Blueprint's entry points (§8.1) and process flow
(§8.2). The step-by-step mechanics of a delegated run are in
[the conductor](../../harness/docs/conductor.md#delegation) and
[Architecture §4](../architecture.md#4-conversations-and-delegation).

An orchestrator is an ordinary agent whose grounding mode is `delegation`. Two exist and share one
specification (`Message` in, `Reply` out): `orchestrator.stub`, a fixed, model-free reference that
routes by rules, and `orchestrator.model`, which lets a model decide. The contract admits either
without change.

Out of scope here: the grounding mode's linter rules and the `invocation:` canonicalisation
([Evidence and grounding](grounding.md)); the grant's wire keys, the callback's envelope encoding
and the child's trace link ([Transport and tracing](transport.md)); the registry, manifest and
roster ([Agents](agents.md)); which agent the app opens on and how the browser shows a
conversation ([The app](app.md)); a conversation's project and who may see it
([Projects](projects.md)). Governance as an entry point (open, restricted or unshared paths) is
deferred by the Blueprint to v2.0 (Appendix G, comment 1). Creating, reviewing and updating a Data
Management Plan are out of scope for the initial phase. The figures' steps for them stay in the
process flow, marked out of scope, so that the flow is complete (invariant 17).

## Invariants

1. **A turn is one invocation.** A conversation is the set of top-level invocations sharing a
   `conversation_id`; a delegated child belongs to the conversation but is not a turn. Each turn
   is held to every rule any invocation is. (`harness/tests/test_conversations.py`)
2. **Conversations are derived from the run storage, never stored apart from it.** Turn order is
   the order in which the conductor stored the turns ([Storage](storage.md), invariant 3). So is
   a conversation's title: the first turn's `Reply.conversation_title` if a model wrote one,
   otherwise the start of the first message, with `title_source` saying which
   (`harness/tests/test_conversations.py`).
3. **The history is part of the input.** What an agent was shown of earlier turns travels inside
   `Message`, so the input hash covers it and every transport gives the agent the same document.
   (`agents/orchestrator-stub/tests/test_orchestrator_stub.py`,
   `test_history_is_part_of_the_input_hash`) So does what the conductor says of the
   conversation's project: a `Message`'s `project_inventory` names the inventory the project
   holds, and `orchestrator.model` opens the current message with a note of it, so it neither
   asks for the inventory again nor copies one into an agent's input ([Projects](projects.md)).
4. **A turn follows the latest.** A turn names the turn it follows, and one that does not follow
   the conversation's latest stored turn, or that arrives while another turn of the conversation
   is running, is refused before anything runs. So a message resent after a dropped connection
   never runs twice, two windows cannot fork a conversation, and each turn's history is exactly
   the conversation as it stood. The app enforces this at its turn endpoint, where it also builds
   the history from the stored turns rather than taking one from the caller. Not yet on `main`:
   TODO(#337, #390).
5. **An orchestrator reaches other agents only through the harness, under a grant.** The grant is
   live only while the orchestrator's own invocation runs; the harness refuses a callback with an
   unknown or expired grant, and a delegation to the orchestrator itself. Each child is an
   ordinary invocation: gated by the conductor's profile, input-checked, linted, stored and given
   its own trace. (`harness/tests/test_delegation.py`)
6. **Delegation is one level deep.** A child is never given a grant, and `orchestrator.model`
   offers no delegation-mode agent, itself included, as a tool.
   (`test_self_delegation_and_a_second_level_are_refused`;
   `agents/orchestrator-model/tests/test_orchestrator.py`,
   `test_delegation_agents_and_itself_are_not_tools`)
7. **Only the conductor sets lineage.** A caller's request carrying `parent_invocation_id` is
   refused. A child's conversation, project and the human it acts for come from the grant, never
   from whoever sent the callback. The parent's `delegations` is the conductor's record of the children
   it ran under that grant, kept when the parent later fails and including a child that finishes
   after the parent returns.
   (`test_a_caller_may_not_set_lineage_or_use_an_unknown_or_expired_token`,
   `test_a_child_acts_for_its_parents_principal_not_its_callers`,
   `test_delegations_are_kept_when_the_parent_fails_after_delegating`,
   `test_a_child_that_finishes_after_its_parent_is_still_recorded`)
8. **An orchestrator has no tools except its delegations, `offer_choices`, `name_project` and
   `set_entry_point`.** A
   model-backed orchestrator is offered one tool per input class of each agent in the harness's
   manifest, and `offer_choices`, which reaches nothing: called alone it ends the turn, and the
   reply carries its question as `Reply.reply_question`. In a project no person has named
   (`Message.project_title_by_researcher` false) it is also offered `name_project`, which reaches
   nothing either: the reply carries the name as `Reply.new_project_title`, which the conductor
   records as the project's title ([Projects](projects.md), invariant 21), and the turn goes on.
   In a project whose researcher has not chosen an entry point
   (`Message.project_entry_by_researcher` not true) it is also offered `set_entry_point`, which
   reaches nothing: the reply carries the entry point the model worked out from what the
   researcher said as `Reply.new_project_entry`, which the conductor records (invariant 18), and
   the turn goes on. Nothing else is offered: no MCP server, no server tool
   (web search, web fetch, code execution), no Agent Skills; its package depends on and imports
   nothing that could provide one.
   (`agents/orchestrator-model/tests/test_orchestrator_only_delegates.py`)
9. **An orchestrator learns what it may invoke from the harness's manifest**, read through its
   grant, and keeps no list of agents of its own. The manifest lists every registered agent; the
   policy gate still refuses a child the profile does not enable, and the orchestrator relays that
   refusal like any other outcome.
   (`test_a_delegation_agent_reads_what_it_may_invoke_from_the_harness_card`,
   `test_a_child_refused_by_policy_is_recorded_and_relayed`)
10. **An orchestrator succeeds once it has replied, whatever its children's outcomes.** A failed
    child stays failed on its own envelope and in the parent's `delegations`, and the reply says
    what went wrong and what to try next. The parent fails only when it cannot reply at all: for
    a model, when the API fails or the model declines.
    (`test_a_failed_or_refused_child_is_reported_and_the_parent_succeeds`,
    `test_a_declined_turn_fails_the_run`)
11. **The process flow is Blueprint data in the SDK and names no agent.** It holds the three entry
    points and six phases; each step has a stable id `<phase>.<step>` and the requirements its
    figure caption names, often none. Step ids are unique and never a requirement ID.
    (`sdk/tests/test_process_flow.py`)
12. **An agent's `serves` names process-flow steps only.** A requirement ID, or any unknown name,
    is a `SpecError`. A description without `serves` serves nothing. The requirements an agent
    bears on are derived from its steps, never declared. (`sdk/tests/test_agent_spec.py`,
    `test_serving_anything_but_a_step_is_refused`)
13. **A step's agents are exactly the agents whose manifest entry serves its id.** The SDK's
    `plan` and the app shell's phase tracker make the same join; no orchestrator or page keeps a
    map of its own. (`test_an_agent_is_planned_at_the_steps_it_names_and_no_other`;
    `app/web/src/flow/serving.test.ts`)
14. **A step with no agent is named, with its requirement** ("no agent yet", and for example R5),
    or with the note that the Blueprint names none. An orchestrator never skips such a step or
    does it itself. (`test_entry_two_lists_phases_two_to_six_with_the_agents_and_the_gaps`)
15. **On a first turn that names no task, an orchestrator asks which entry point applies**, then
    follows the phases from that entry. In a project whose entry point is already known
    (`project_entry`, from the intake of invariant 20 or the phase tracker), it does not ask
    again, and suggests the next step from that entry instead (invariant 19), TODO(#669). The stub's question and its list of steps are templates
    that delegate nothing and rest on the input alone; it asks as a choice question whose values
    are the entry numbers, and reads a `choice_answer` naming one before any rule. The model's prompt carries the whole flow
    with step ids, tells the model not to show ids to the researcher, names no agent, and is the
    same on every run so that it caches.
    (`test_the_prompt_carries_every_entry_point_and_phase_and_names_no_agent`)
16. **A choice question never holds up the conversation.** A reply that asks one ends
    `succeeded` like any other; nothing is suspended or waits for the answer. The next turn may
    answer by choosing, with a `choice_answer`, or ignore the question and say anything; either is
    a `Message`. The history writes the question as text after the reply that asked it, so the
    agent sees on a later turn what it offered, and the answer is the next turn's `message_text`.
    An answer is checked against the question the latest turn asked before the turn runs: values
    from its options, one unless several may be chosen, words only where allowed.
    (`test_a_question_shows_in_history_and_an_answer_is_checked_against_it`,
    `test_offering_choices_ends_the_turn_and_the_reply_carries_the_question`)

17. **A step the Blueprint has and this project does not yet do is in the flow, marked
    `out_of_scope`.** The Data Management Plan steps (`setup.dmp-create`, `setup.dmp-review`,
    `post.dmp-update`) are these. The phase tracker and the stub name them and say "out of scope
    for now"; the model's prompt marks them and tells the model not to offer to do them or look for
    a tool. An agent that serves one is a `SpecError`, so none can appear to cover it. Verifying a
    deposit against an existing plan (`governance.dmp`, R8) is in scope.
    (`test_the_data_management_plan_steps_are_in_the_flow_and_out_of_scope_for_now`,
    `test_serving_a_step_that_is_out_of_scope_for_now_is_refused`,
    `test_data_management_plan_steps_are_named_and_said_to_be_out_of_scope`)
18. **Where a project is in the flow is derived from its log on every read, never stored.** No
    orchestrator, page or store keeps a current step. The harness reads each step's state (open,
    started, done or skipped) from the project log (`dd_harness.progress`): an inventory shows the
    files described, a repository chosen shows one recommended, and a document's versions show its
    step started once drafted and done once approved, a README with any data dictionary drafted
    alongside it. The last validation shows `deposit.validate` done if it conforms and started if
    not, and a package built shows `deposit.finalise` done. Everything else is the researcher's own word, an `entry_chosen` or `step_marked`
    event, which they may change at any time; what the log produced outranks a skip. The one
    exception is the entry point an orchestrator's model worked out from what the researcher said,
    such as data already collected: a succeeded `Reply`'s `new_project_entry` is an
    `entry_chosen` event with `entry_source` `model`, caused by the run, so that the journey the
    app shows matches what the reply told the researcher. It is a weaker word. The researcher's own
    choice (`entry_source` `researcher`, or none on an older event) replaces it, and once they have
    chosen, the store refuses a model's and records nothing, so the model is no longer offered
    the tool (`Message.project_entry_by_researcher`). The phase tracker says when Data Director set
    the entry point. The conductor
    puts the entry point and the states into a `Message` in a project (`project_entry`,
    `project_progress`), so the input hash covers them, and the project summary carries the same
    derivation for the phase tracker. Work done out of order, or before the entry phase, counts.
    (`harness/tests/test_progress.py`,
    `test_a_message_in_a_project_is_told_its_entry_point_and_progress`,
    `test_a_reply_records_the_entry_point_a_model_worked_out`, the storage conformance kit's
    `check_a_researchers_entry_point_is_never_replaced_by_a_models` (`dd_harness.testing.storage`),
    `agents/orchestrator-model/tests/test_orchestrator_entry.py`)
19. **The next step is a suggestion, never a gate.** `suggested_next` names one step: the first
    from the entry phase that is neither done nor skipped, in scope and not optional, with a step
    begun before one not begun, whether or not an agent serves it. With no entry point recorded,
    where the researcher is is not known, so it names only a step begun, from any phase, or none:
    it never sends a researcher whose data are collected back to Phase 1. The tracker then asks
    where they started, and the model's note names no step and tells it to find out. Both orchestrators and the
    tracker use that one function; none refuses a step because it is not yet time. The stub offers
    the suggestion with a few other open steps as a choice question whose values are step ids;
    choosing one delegates the inputs `routing.yaml` gives for that step to the agent serving it,
    which the conductor fills from the project, and a step with no agent is named as having none
    (invariant 14). The model is told the states in a note from the harness, and its prompt tells
    it to suggest the next step and follow the researcher. No orchestrator records a step as done.
    (`sdk/tests/test_process_flow.py`;
    `agents/orchestrator-stub/tests/test_guides_the_loop.py`;
    `agents/orchestrator-model/tests/test_orchestrator_guides_the_loop.py`;
    `test_the_model_is_told_where_the_project_is_only_in_a_project`)
20. **A new project opens with the harness's intake, which asks the least that places it in the
    flow.** Before the first turn of a project with no entry point, the app shows the intake. Data
    Director asks first, so the researcher need not know what to type. The questions are Blueprint
    data in the SDK (`dd_sdk.intake`, beside `dd_sdk.process_flow`). They name no agent and run no
    orchestrator, so the stub and the model behave the same. Each question is a core
    `ChoiceQuestion` and is asked one at a time. Each, apart from the first, is asked only from the
    entry points that reach its step:

    | Question id | Asks | From entry | An answer of "No" marks skipped |
    |---|---|---|---|
    | `intake.entry` | Where are you with your research data? | always, first | (the answer is the entry point: `entry_chosen`) |
    | `intake.dmp` | Do you have a Data Management Plan for this project? | 1, 2 | `governance.dmp` |
    | `intake.sensitive` | Does the data include personal or otherwise sensitive information? | 1, 2 | `governance.sensitive-data-identify`, `governance.sensitive-data-handle` |
    | `intake.repository-mandated` | Has a funder, journal or institution said where the data must go? | 1, 2, 3 | `repository.mandated` |

    So the intake asks at most four questions, and two from entry 3. Every question but the first
    offers "Not sure", which records the answer and marks nothing. "Yes" also marks nothing: it
    never shows a step as done. The intake gathers nothing else. Funder, discipline, data types,
    embargo and licence are asked by the step that needs them, when the researcher reaches it.
    Answers are the researcher's own word, recorded in the project log and read like
    `step_marked` ([Projects](projects.md)). They can be changed at any time, from the phase tracker
    or by answering again. The researcher may skip a question, dismiss the intake, or type instead.
    None of these holds up the conversation (invariant 16). When the intake ends, the app says which
    phase the project starts at, by its researcher-facing name, and which step `suggested_next`
    proposes. A researcher who dismisses the intake or types instead may still say where they are
    in their own words; the model then records the entry point it worked out (invariant 18). The
    wording and the decision mapping await a Blueprint reading, TODO(#670); the
    question set, its tests and the app's card are TODO(#665, #667, #668).

## Boundaries and contracts

- The harness promises an orchestrator: a grant on every invocation run where it knows its own
  A2A address, the manifest of registered agents, and each child's stored envelope to cite. Where
  there is no address, as under `workbench invoke`, there is no grant and `orchestrator.model`
  abstains. (`test_a_delegation_agent_run_without_a_callback_gets_no_delegate`)
- The orchestrator promises the harness: a reply that cites only its input and the delegations the
  conductor recorded ([Evidence and grounding](grounding.md)), checked against the conductor's
  record, not against the `delegate` spans the agent reports.
- The harness's A2A routes in the app accept a callback under a live grant and nothing else
  ([Transport and tracing](transport.md)).
- An external source such as a registry, a PID service or an MCP server is reached by an agent the
  orchestrator delegates to, never by the orchestrator.
- Neither the harness nor a browser shell names an orchestrator in code. The deployment's profile
  names the one the app's conversations go to ([Policy and identity](policy-and-identity.md),
  [The app](app.md)).
- `serves` is the agent author's routing hint, "ask me at this step". It is not a conformance
  claim: whether an agent meets a requirement is recorded in `docs/requirements.yaml` and
  `docs/reviews.yaml` with its evidence ([Evaluation and conformance](evaluation.md)).
- A step id is a published name once an agent serves it. Renaming or splitting a step breaks the
  agents that serve it and is a breaking change to the SDK. Editing `dd_sdk/process_flow.py` also
  changes the model orchestrator's prompt, and so its behaviour: treat it as a change to both
  orchestrators.
- Cross-cutting requirements need no step. R10 (provenance) is the harness's work on every run and
  is never dispatched; R12 has its step. No requirement in §7.1 needs an agent placed outside the
  flow.

## Rationale

Governance must not thin out in conversation. The policy gate, the input check, the linter, the
store and provenance exist per invocation, so a turn is an invocation and so is every hand-off. A
reviewer can open each child on its own, and the parent names each with its agent and version.

Agents are separate services, so an orchestrator cannot reach the conductor in-process; the grant
and callback carry its hand-offs back across the network to the one place that governs them.
The linter trusts only what the harness observed, which is why lineage and `delegations` are the
conductor's and the child's acting-for comes from the grant.

Two facts place an agent in the researcher's work: the process flow, which is the Blueprint's and
the same everywhere, and which agent serves which step, which depends on what a harness has
registered. The first is SDK data; the second belongs on the manifest, which is already the only
list of agents an orchestrator reads. Agents name steps rather than requirements because
requirements are capabilities, not places: R3 applies in Phase 1 and Phase 4, so serving R3 put an
agent at both whether or not it helped there, and most steps name no requirement, so an agent
written for one had nothing true to declare. A figure step that joins two acts different agents
may do is split (sensitive data: identify, then handle), so that an agent can flag without
deciding treatment.

Real work is not linear: a researcher may arrive with a README written, pick a repository before
tidying their files, or come back weeks later in a new conversation. A cursor that moves one step
at a time would be wrong as soon as they did any of these, and would be one more record to keep
in step with the project. Deriving progress from what the project holds keeps one source of truth,
survives a new conversation and the model's history window, and lets work done in any order count.
Most steps leave nothing in the log, so the researcher's own word on them is an event too, and
the suggestion is only a suggestion so that marking, skipping and going back are always open.

An orchestrator succeeds whatever its children's outcomes because mirroring a child's failure on
the parent would lose the reply's explanation, while the failure stays visible where it occurred.

The intake (invariant 20) is the harness's, not an orchestrator's, for three reasons. Its answers
must reach the project log, and no agent writes there. It must be the same whichever orchestrator
a deployment runs. And it is Blueprint data, like the flow it places the project in. It asks only
the §8 decisions that change which steps come first, because every question asked before the
researcher has said anything is a cost. Everything else is asked by the step that uses it, when
the researcher can see why it is needed. A "No" may skip a step, but a "Yes" never marks one done,
because saying a plan exists is not the check of the deposit against it.

## Rejected alternatives

- **The orchestrator calling agents directly over A2A.** The children would be ungoverned and
  unstored, and the parent could cite anything.
- **A choice question as A2A `input-required`, or a suspended run.** The run would stay open
  until the researcher answered, which may be never, and suspend and resume are not built
  (TODO(#72, #16)). A question the researcher may ignore needs neither.
- **A choice question as a payload class of its own.** An orchestrator's payload is `Reply`, so it
  could not reply and ask in one turn.
- **Choices in the model's text, or a structured final message on every turn.** Parsing a block
  out of prose is fragile; a JSON reply on every turn would change every reply to serve a few.
  A tool the loop stops on keeps prose replies as they are.
- **Tools of the orchestrator's own: MCP servers, web search, Agent Skills.** A lookup made that
  way passes no policy gate, leaves no evidence or stored run, and meets no source check. Skills
  would also need the code-execution container, which adds egress and does not carry over to a
  local model.
- **Grounding mode `none` or `input_only` for an orchestrator.** It could cite only its input, so
  a relayed answer would be ungrounded. **Mode `retrieval`** requires a retrieval before any model
  call, but the orchestrator decides what to delegate before it delegates.
- **Checking delegations against the agent's `delegate` spans.** Those are the agent's account;
  the conductor has its own record.
- **History in AG-UI `messages` only.** A2A and the CLI would not carry it, and the input hash
  would not cover it.
- **A conversation store.** It would duplicate what the invocation store holds.
- **Routing from the orchestrator's own configuration, or an orchestrator's own map of agents to
  steps.** It drifts from the registry and duplicates it. (The stub's `routing.yaml` remains only
  as fixed example rules for a model-free reference.)
- **The manifest in the grant's metadata.** Every delegation-mode request would carry every
  agent's schemas, and the wire keys would change.
- **A current step kept by the orchestrator, the conversation or the project.** It drifts from
  what the project holds, is lost with the model's history window or a new conversation, and
  forces a linear order on work that is not linear.
- **The orchestrator recording a step as done.** A model's or a template's claim is not evidence;
  a step is done when the project holds its output, or when the researcher says so.
- **`serves` naming Blueprint requirements.** It misplaced agents at every step naming a
  requirement, left agents for the many steps that name none with nothing to declare, and merged
  a routing hint with a conformance claim that nothing checked.

- **An onboarding agent, or an intake run by each orchestrator.** An agent cannot write the
  project log, so its answers would stay in the conversation, as the entry question's do now. Two
  orchestrators would hold two copies of the questions that could drift apart. A new persona
  would take steps from no one, which the roster forbids ([Agents](agents.md)).
- **A long intake that also asks funder, discipline, data types, embargo and licence.** Asking
  these before the researcher has said anything puts people off. The answers would also be
  guesses that the steps would ask about again.
- **Intake answers as `step_marked` events.** That would lose what the researcher was asked, and
  make answering again unable to undo a skip that came from an earlier answer.

## Non-functional requirements

- Security: the grant token is a bearer capability. Agent and harness ports stay on the host or a
  private network until calls between them are authenticated, TODO(#17).
- Content an orchestrator did not write (a researcher's message, a child's reply) is data, not
  instructions; the model's prompt says so.
- Cost and latency: `orchestrator.model` caps the delegations in one turn and sends the model only
  the last turns of the history; the input hash still covers the whole history. An orchestrator's
  registry timeout must exceed those of the agents it delegates to; nothing checks this.
- Turns to one conversation run one at a time; turns to different conversations, and parents with
  their children, run side by side.
  (`test_async_callers_run_parents_side_by_side_and_their_children_never_wait_on_them`)
- Performance: the file backend finds conversations by scanning every stored envelope; the
  database backend answers with an indexed query ([Storage](storage.md)), TODO(#524).

## Open questions

- Mapping A2A `context_id` to `conversation_id`; delegation more than one level deep; delegation
  from the CLI; whether children inherit `requirement_ids`; checking a caller's history against
  the store on transports other than the app, TODO(#253).
- Which events show `deposit.validate` and `deposit.finalise` done, once the validation report
  and the package are recorded in the project log, TODO(#19, #202). Whether a run of an agent
  serving a step should show it started, which would need the delegation to name its step.
- The steps come from the figure captions in §8.2; the figures may show more, TODO(#245).
- Step ids as the vocabulary in which a deployment's policy names the steps that need a person's
  sign-off, TODO(#308); proposing the ids to the RDA working group, TODO(#310).
- The orchestrator's context about its deployment and the researcher's project beyond the
  inventory the project holds and the intake's answers (invariant 20), to be supplied by the
  harness rather than as a tool, TODO(#341, #160).
- Whether a deployment may change or extend the intake's questions in its profile, and whether
  "Yes" to sensitive data should say anything before the governance step, TODO(#670).
- A read-only check of a deposit against an existing Data Management Plan, TODO(#284).
- Streaming replies, TODO(#159).
