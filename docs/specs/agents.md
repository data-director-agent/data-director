# Agents

## Intent and scope

An agent is the part of Data Director that knows something about research data: which
vocabularies fit, what a funder's policy asks, which repository suits a dataset. The harness
governs agents but holds no such knowledge, and an agent holds no governance. This spec covers
what an agent is as a deployable thing, how the harness comes to know about it, what an agent says
about itself, and which agents there should be.

It does not cover what crosses the wire ([Transport and tracing](transport.md)), the classes an
agent reads and returns ([Contract](contract.md)), its grounding rules
([Evidence and grounding](grounding.md)), how agents are placed in the process flow and delegate
to one another ([Orchestration](orchestration.md)), or whether a deployment lets an agent run
([Policy and identity](policy-and-identity.md)). How to write an agent is in
[`agents/README.md`](../../agents/README.md); how the registry behaves at start-up and on failure
is in [`harness/docs/registry.md`](../../harness/docs/registry.md).

## Invariants

1. Each agent is its own workspace package and its own A2A service under `agents/<name>/`. No
   other package imports an agent: not the harness, the workbench, the app or another agent.
   Enforced by `harness/tests/test_harness_boundary.py` and `app/tests/test_app_boundary.py`.
2. The harness reaches every agent over A2A, including in tests, where the test kit serves the
   agent on an in-memory transport and calls it through the same card and messages as a deployed
   one (`dd_harness.testing.in_process`). There is no second, in-process way to run an agent.
3. An agent describes itself in exactly one manifest, `describe(spec)`, carried on its A2A card.
   Every consumer (the harness's own card, `workbench agents`, `GET /agents`, the workbench viewer
   and the app shell) reads that manifest and nothing else about the agent. A spec rebuilt from a
   card equals the agent's own description: `harness/tests/test_registry.py`.
4. The registry's configuration holds addresses only. An agent's identity, classes, grounding
   mode, derivations, models, steps served, title and settings come from its card, never from the
   configuration. The `agent_id` is the card's, not the configured name.
5. A card that lacks the Data Director extension, names a class it carries no schema for, carries
   a schema that does not match its digest, or declares an ungrounded payload class makes its
   agent unavailable; a card built against a contract version the harness cannot govern makes it
   incompatible. Either way the agent is listed with the reason and the others still load. A
   duplicate `agent_id` or a malformed configuration stops start-up. Enforced by
   `harness/tests/test_registry.py`.
6. Registration is not permission. A registered agent runs only if the profile in force assigns
   it ([Policy and identity](policy-and-identity.md)).
7. The manifest declares derivations and carries no presentation: no uiSchema fragment, widget
   name, layout hint or field order. `workbench/tests/test_viewer.py` checks that the viewer
   works out a payload's presentation from its schema and the derivations. A persona's title and
   icon are its identity, not presentation in this sense.
8. A derivation names a payload field path the payload class has, and its `recorded_in`, when
   given, names a sibling field of type `Derivation`. An agent with no payload declares no
   derivations. The spec refuses anything else when it is built, both in the agent and when the
   harness rebuilds it from a card: `sdk/tests/test_agent_spec.py`.
9. A generated class schema lists its properties in LinkML induced-slot order (own slots, then
   mixins), so source order is reading order: `sdk/tests/test_contract.py`.
10. Adding, removing or replacing an agent edits no code in the SDK, the harness, the workbench's
    CLI, transports or viewer, or the app shell. It changes only the agent's package, the
    workspace members, the registry configuration and the profiles. `agents/example-hello/` is
    the standing check: it has no reason to need anything else.
11. Every in-tree agent is listed in the app's reference registry configuration and enabled by
    its reference profile: `app/tests/test_app.py`.
12. Every advisor is a persona: it has a title, and it serves only steps of the process flow
    (`dd_sdk.process_flow`). `AgentSpec` refuses a step id that is not in the flow. No two
    advisors serve the same step. That last rule is not yet checked by a test. A persona may also
    have an `icon`, one emoji, which the app shows beside its title; `AgentSpec` refuses an icon
    that is not one (`sdk/tests/test_agent_spec.py`). A card without an icon gets the client's
    default (`DEFAULT_AGENT_ICON` in `@data-director/agent-view`). An agent that reads the text
    of the documents a researcher attaches says what for in `reads_attached`, a phrase completing
    "<title> reads its text …"; `AgentSpec` refuses it from an agent no accepted class of which
    is given `project_documents` ([Projects](projects.md)). Being given the text is not reading
    it, so the card says so and the schema does not: the app's document dialog and the
    orchestrator's note name the agents that read an attachment, and say that the others cannot
    use it, before anyone relies on them doing so (#1326).
13. A mock advisor's description begins "Mock.", its grounding mode is `none`, and its payload
    says in `limitations` what it does not yet do; a payload of the core `Document` class, which
    has no such slot, says it in the outcome statement instead. A mock declares no model and
    substantiates no Blueprint requirement; its tests may be marked only with the project's own
    contract requirements (`DD-*`) that the harness enforces on every agent. No in-tree agent is
    a mock now: `advisor.files`, the last, is a model-backed alpha.
14. A model-backed alpha advisor sits between a mock and a persona. It has a pre-release version,
    its grounding mode is `input_only`, or `retrieval` where it reads outside records (the Policy
    Adviser), and its description does not begin "Mock.". It has a `template` writer, which
    calls no model, so its tests pass with no key; an operator can select it, but the model is
    its default (Model-backed personas). Its `factory` module names the setting that chooses the writer
    (`SWITCH`). It declares a model in `AgentSpec.models`
    only when one is configured. Its payload says what it still does not do, as a mock's does.
    Like a mock, it substantiates no Blueprint requirement until it leaves alpha.

    `scripts/tests/test_roster.py` checks invariants 13 and 14 across the roster, from the cards:
    it reads each in-tree agent's state from the table in [The roster](#the-roster), and fails on
    an agent with none. Each rule's known gaps are listed in the test, each with its issue, and
    the list only shrinks. Whether an outcome statement states a `Document` payload's limitations
    is prose and is not checked.

## Boundaries and contracts

**What an agent owns.** Its domain logic, its input and payload classes
([Contract](contract.md)), its grounding mode ([Evidence and grounding](grounding.md)), its own
configuration (read from its own `DD_<AGENT>_*` variables, never from the harness's settings), its
model credentials ([Policy and identity](policy-and-identity.md)), or its own model broker
credential when a person's own account pays ([A person's own model account](model-accounts.md)), and its system prompt as a file
beside the code that sends it. It decides an outcome, a payload and the evidence it rests on.

**What an agent never does.** It does not fill identifiers, timestamps, telemetry, the grounding
mode on the envelope or the input hash; the conductor builds the envelope. It does not call
another agent directly; it delegates through the harness
([Orchestration](orchestration.md)). It ships no presentation.

**What the SDK gives both sides.** `data-director-sdk` holds the agent interface, the manifest
and its inverse, the core contract, evidence canonicalisations, span helpers and the A2A server
an agent runs behind. It is the only package an agent and the harness share
([System and boundaries](system.md)).

**The registry.** The harness builds its registry from a configuration file of base URLs, one per
deployment: `workbench/agents.yaml` for development and `app/config/agents.yaml` for the app,
either overridden by `DD_AGENTS_CONFIG`. It reads each card once at start-up. When a request names
an agent that is not registered, the conductor asks the registry to retry the agents it could not
load, so an agent started after the harness is found without a restart. An entry may also say
`model_broker: true`: the operator's statement that the agent calls its models through the model
broker, which the conductor requires of every model-backed agent while the profile lets people's
own model accounts pay ([A person's own model account](model-accounts.md), invariant 14). It is
read from the configuration alone, never from the agent's card. On a deployment, `dd.py apply`
writes the configuration from the release's list and marks each agent whose settings, which the
operator writes, set `DD_MODEL_BROKER_URL` (`scripts/ddtool/agent_list.py`). Reloading a changed
configuration and checking the health of registered agents while running are not built yet:
TODO(#251).

**Settings.** An agent may offer options, each a name with its choices, a default and a
description, such as whether it reads a source live. The manifest carries them; a profile sets
them in `agent_settings`; the conductor refuses a value the card does not offer and sends the
agent the values that apply, which it reads with `dd_sdk.agent.setting`
([Policy and identity](policy-and-identity.md), invariant 22). A setting is not configuration
that differs per machine, such as a key or an address: those stay in the agent's own settings
file.

**Derivations.** For each payload field the agent produces rather than copies, the manifest
says how (`model`, `template`, a rule, and so on, from the contract's `Derivation`). An unlisted
field is copied from input or evidence, and the viewer shows it as verified. Where the method can
vary per value (a model with a template fallback), the field names a sibling that records, per
value, how that value actually came about, so a fallback is shown as what it was. The workbench
viewer and the app shell ([The app](app.md)) each lay a payload out from its class's JSON Schema
plus these derivations. The workbench viewer hides `schema_class`, the payload's own `grounded_on` and every recorder field,
put an item's `grounded_on` first and resolve it through evidence, badge each derived field, and
otherwise keep schema order. The envelope-level layout belongs to the viewer, not to any agent.

**Agent ids.** An id is `<group>.<name>`: `orchestrator` for agents a person converses with and
that delegate to others, `advisor` for personas, `example` for templates. An exploratory agent is
an ordinary package marked alpha by a pre-release version, not a separate tree
([`agents/README.md`](../../agents/README.md)).

## The roster

Advisors follow one principle: **one persona per kind of expertise**, named as a role a research
office would recognise (Standards Librarian, Research Ethics Adviser, FAIR Assessor). Each serves
a fixed set of process-flow steps and no others. The current roster is the set of `advisor-*`
packages in `agents/`, and each one's steps are its `serves`. The orchestrators delegate to the
personas and are not personas themselves.

A new advisor is justified when there is a kind of expertise no current persona covers, with its
own sources, failure modes and evaluation, and steps no persona serves. Work that fits an existing
persona's expertise extends that persona instead. A new persona takes its steps from no other.

A persona may also be asked for advice outside its steps, at any point in the work, through an
input class of its own: the orchestrators offer every class an agent accepts, whatever step it
serves. Such advice takes no step from another persona and marks none done. The FAIR Assessor
gives feedback on the project's draft metadata record this way (#430, #432): the Metadata Librarian
drafts it (`preparation.metadata`) and the Metadata Reviewer checks it is complete enough to
deposit (`deposit.validate`), while the assessor says what it already meets against FAIR-related
checks, what is newly met since the version approved, and what to do next, so that each
improvement is visible. It changes nothing; the researcher edits or approves the draft. The
assessor also serves `deposit.fairness`, our addition to Figure 5, with the same input class, so
that the check comes before submission as well as after publication (`post.fairness`). That step
is advice: it gates nothing and marks no other step done.

The Data Management Planner (`advisor.dmp`) is the persona for the project's plan: it describes the
project before its data are collected (`setup.project`, our addition to Figure 1), reviews an
attached plan (`setup.dmp-review`) and checks sharing at publication against the plan's commitments
(`governance.dmp`). Each reads the researcher's own planning documents, a proposal, an award
letter or a plan, and proposes what it reads as project facts that count only once a person
confirms them, quoting the passage each rests on; its failure mode is a misreading, which the
quote lets a person check. Describing the project was a step no persona served, and the Blueprint's
Planning Agent is the role it fills. Writing a plan stays with the Documentation Editor, since a
written plan is a project document (`Document`) and an agent returns one payload class.
What it describes reaches the other personas as decided facts: the Standards Librarian, for one,
searches on the decided field of study when its input names no subject (#1529).

The Storage Adviser (`advisor.storage`) is the persona for where a project's data live while it
runs: its own sources (the deployment's `institution_storage`, which no registry holds), its own
failure modes (offering storage not approved for personal data) and its own step,
`setup.storage`, our addition to Figure 1. No other persona covered it: the Documentation Editor
drafts a plan's storage section from what the researcher says, and the Data Management Planner
reviews it, but neither knows the institution's services. It flags what the profile does
not vouch for and leaves how sensitive data are protected to the person who decides it.

Some steps are deliberately served by no agent, and the orchestrators name them as steps with no
agent:

- deciding how sensitive data are handled (`governance.sensitive-data-handle`) is a person's
  decision (C2). The ethics adviser flags sensitive data and stops there. The step is marked
  `person_decides`, so `AgentSpec` refuses an agent that serves it and the policy page shows it
  as never delegated;
- the steps that act in a repository or an institutional system: reviewing the deposit link,
  uploading, finalising, the institutional record, monitoring and embargo release. Whether a
  deposit persona should take any of them on is undecided: TODO(#362).

Provenance (R10) is not a persona. It is the harness's work on every run, and the Blueprint's
Provenance Agent maps to the run store.

A persona may start as a mock: an ordinary alpha package with its own classes, steps, title and
card, whose `run` is deterministic and driven by a small rule table. It lets the orchestrators and
the phase tracker show the whole intended design before each persona is built. A mock's classes
are a sketch, not a published format; its real implementation is its own piece of work and may
replace them. The orchestrators tell the researcher when a result came from a mock.

A mock may next become a model-backed alpha (invariant 14): a basic agent with a system prompt,
built to the conventions in [Model-backed personas](#model-backed-personas), before it becomes a
fully designed persona. Not every mock should. A model helps where the task is reading language or
judgement; where the work is exact, the next step is retrieval, not a model. The review of the
roster for #353 found:

| Agent | Next step |
|---|---|
| `advisor.ethics`, `advisor.dmp` | Model-backed alpha first: the rules are the weak point and the task is reading language. |
| `advisor.rights`, `advisor.metadata` | Model-backed alpha, choosing from a closed set (rights) or suggesting beside a value (metadata). |
| `advisor.fairness` | Model-backed alpha for its recommendations only; little gain until it retrieves. Also gives constructive feedback on the project's draft metadata record at any time (`GivenProjectMetadataRecord`, #432). |
| `advisor.quality` | Stays rule-based in its findings; it overlaps the FAIR Assessor (#18). Since every advisor became model-backed by default, a model writes a summary beside them (`dd_sdk.summary`). |
| `advisor.linking`, `advisor.files` | Identifier syntax, checksums and format lookup are exact and stay in rules. Their next step is retrieval (#360, #354); `advisor.linking` has taken it for DOIs, ORCID iDs and ROR ids, through the tool gateway and the PID resolver (`mcp-pid/`), the first MCP server in this repository, and suggests a DOI's DataCite relation from the type of work its record names. Since every advisor became model-backed by default, each is a model-backed alpha whose model only writes a summary beside the rules' findings (`dd_sdk.summary`). |
| `orchestrator.stub`, `example.hello` | Stay deterministic by design. |

Each in-tree agent's state now. This table is the one place a state is written down:
`scripts/tests/test_roster.py` reads it, and fails on an agent missing from it.

| State | Agents |
|---|---|
| Mock (invariant 13) | none |
| Model-backed alpha (invariant 14) | `advisor.dmp`, `advisor.documentation`, `advisor.ethics`, `advisor.fairness`, `advisor.files`, `advisor.linking`, `advisor.metadata`, `advisor.policy`, `advisor.rights`, `advisor.storage` |
| Persona | `advisor.quality`, `advisor.repository`, `advisor.standards` |
| Deterministic by design, or not an advisor | `example.hello`, `orchestrator.model`, `orchestrator.stub` |

What a persona that drafts project documents may infer, ask and write is in
[Drafting documents](drafting.md).

## Model-backed personas

Every advisor that calls a model, from its alpha onwards, is built the same way, so that adding
tools or an evaluation later changes the agent without rewriting it. `advisor-standards/` is the
worked example of the `template` path (`factory.py`, `explain.py`), and
`advisor-documentation/` of the declared model and of structured output (`factory.py`,
`prose.py`), and `advisor-policy/` and `advisor-standards/` of a model that calls tools
(`advise.py`). Every model-backed advisor has a `template` path an operator can select, and its
model is on by default (`dd_sdk.model_provider.optional_model(..., default="model")`): an advisor
without a key, a broker credential or `template` does not start, and says which setting runs it
without a model. A model can be on by default because it is only ever added to a deterministic
result, never trusted in place of one:

- The Documentation Editor's model only adds prose and suggestions beside a draft made by rule.
- The Policy Adviser's only adds to what its rules found, and each obligation it adds stands only
  on a quote that code finds in the cited record.
- The Standards Librarian's never removes a pick its ranking rules made, and each standard it adds
  is a record retrieved in the run that code checks against the dataset profile.
- The Repository Adviser's only writes the rationale for a ranking its rules made, and a rationale
  that names an identifier it was not given is replaced by the template's.
- The Ethics Adviser's only adds flags and questions to the keyword table's, never removing one.
- The Rights Adviser's chooses only from its own licence table, and the Data Management Planner's, the FAIR
  Assessor's and the Metadata Librarian's only pair, tailor or suggest beside what their rules
  decided, checked before use.

1. **Deterministic shell, model core.** Input checks, abstentions, scores and anything exact
   (checksums, licence ids, the shape of a schema) stay in code; the model does judgement and
   language. A content problem the shell finds is an outcome with a reason code, before any
   model is called.
2. **Structured output.** The model replies against a schema derived from the payload class. A
   checker validates every reply before it is used, and records what it dropped and why.
3. **Safety by construction.** Where a miss is harmful, the model may add to the rules' output
   but not remove from it; merging two flags into one, or moving a flag to a list shown beside
   the others with the model's reason, is not removing it (`advisor-dmp/`). Where invention is
   harmful, it chooses from a closed set the code supplies, or states a claim only with a quote that code finds, word for word, in the record it cites (`advisor-policy/`, `verify.py`), or in the attached document it
   cites (`advisor-dmp/`, `read_plan.py`, which proposes a plan's sharing commitments as project
   facts for the researcher to decide, [Projects](projects.md), invariant 28). Where the researcher must write a value, it suggests beside that value and never
   writes it ([Drafting documents](drafting.md)).
4. **Provenance per value.** Each field a model may write names a `Derivation` recorder in
   `recorded_in` (invariant 8), so a template fallback is shown as what it was. Each call is
   made with `dd_sdk.model.call`, which opens the `chat` span, records the call's tokens and
   records it with `dd_sdk.prompts.ModelCallLog`; the card declares the model as a
   `dd_sdk.agent.ModelUse` made from the model itself (`dd_sdk.model.declared`), never written
   beside it. The provider is an adapter behind `dd_sdk.model.Model`
   (`dd_sdk.model_anthropic.AnthropicModel` for Claude, `dd_sdk.model_openai.OpenAIModel` for
   any OpenAI-compatible endpoint), built from the agent's settings by
   `dd_sdk.model_provider.configured_model`, or `optional_model` where a `template` path
   stands in for it; so an agent imports no provider's SDK and runs on any provider the SDK
   supports with no code change ([Policy and identity](policy-and-identity.md)). An agent whose
   model calls tools passes them to `call` as `dd_sdk.model.ToolSpec`s and keeps its
   conversation in the seam's neutral types (`AssistantMessage`, `ToolResults`); content a
   provider requires back unchanged travels in `AssistantMessage.replay`
   ([Orchestration](orchestration.md), invariant 8). A model the agent relies on to call tools
   is declared so on the card (`ModelUse.tools`, from `configured_model(..., tool_use=True)`),
   so that a profile's model map never routes it to a model that does not serve them
   ([A person's own model account](model-accounts.md), The model map).
5. **Prompts are code.** The system prompt is `system_prompt.md` beside the module that sends it.
   A change to a prompt is a change to the agent's behaviour and is reviewed as one.
6. **Tests use a fake model.** An agent's suite exercises the model path with
   `dd_sdk.testing.FakeModel`, or a fake of its own in its `testing` module; CI never needs a
   key.
7. **An evaluation before alpha ends.** An advisor leaves alpha only with an evaluation set that
   includes false-negative cases: the flags, discrepancies or options it must not miss
   ([Evaluation and conformance](evaluation.md)).
8. **Sources through the harness, procedures in the prompt.** A persona reads an outside source
   through an MCP server that the harness reaches for it, and loads procedural know-how as an
   Agent Skill in its system prompt. Both are declared on its card. See
   [Tools: MCP servers and Agent Skills](#tools-mcp-servers-and-agent-skills).

## Tools: MCP servers and Agent Skills

Most personas need sources: licence lists, vocabularies, identifier resolvers, policy records.
Several personas need the same source, and some procedures (reading a machine-actionable DMP,
choosing a licence) are the same whichever agent follows them. A source is shared as an MCP
server, and a procedure as an Agent Skill. Both are framework-neutral resources
([System and boundaries](system.md)), and a persona consumes them under the harness's
governance as follows. Skills are loaded by `dd_sdk.skills`; MCP servers are reached through the
harness's tool gateway (`dd_harness.gateway`), which an agent calls through `ctx.tools`
(`dd_sdk.tools`).

Two advisors predate the gateway. `advisor.policy` offers its model read-only tools that reach
FAIRsharing, Jisc Open Policy Finder and Crossref from the agent itself, and `advisor.standards`
one that searches FAIRsharing's standards. Each follows items 5 to 7
below: its shell makes the first retrieval; the tools are limited per run
(`DD_POLICY_MAX_LOOKUPS`, `DD_STANDARDS_MAX_LOOKUPS`); each record a tool returns is retrieved by the agent, with its
`retrieval` span, before it may be cited; tool results reach the model as numbered, untrusted
records in the user turn; and the model cites records only by those numbers. Their tools move
behind the gateway, TODO(#1143).

**MCP servers for sources.**

1. The deployment lists the MCP servers it runs, as it lists agents, in the file
   `DD_TOOLS_CONFIG` names (`dd_harness.gateway.config`): each server's name and address, and
   the source it serves: which field identifies a record, the registered canonicalisation its
   records are hashed under, and the pinned copy, if there is one
   ([Evidence and grounding](grounding.md)). A server is `local` or `remote`, worked out from its
   address as a model's endpoint is ([Policy and identity](policy-and-identity.md)). Without the
   file there is no gateway, and no agent is sent a tools grant.
2. The deployment pins each server's tool definitions by digest (`tools_sha256`, the
   `dd-mcp-tools-v1` digest of each tool's name, description, input schema and output schema).
   At start-up the harness lists each server's tools; a server whose list has changed, or that
   cannot be reached, is unavailable until an operator reviews the new list and pins it
   (`dd-harness tools pins`), so a changed tool description cannot reach a prompt unreviewed.
3. A persona reaches a server only through the harness's **tool gateway**, under its
   invocation's grant, as an orchestrator reaches its children. It never connects to a server
   itself. Its card declares the servers and tools it uses (`AgentSpec.tools`), and the profile
   grants servers per agent (`tool_servers`). The conductor sends a grant only for servers both
   name that are available: the gateway's address and a token, in the A2A metadata
   (`dd.tools_url`, `dd.tools_token`), which `dd_sdk.serve` binds to `ctx.tools`. The gateway is
   one MCP endpoint at `/mcp` beside the delegation callback, speaking the stateless revision of
   the streamable HTTP transport, and lists each tool as `<server>.<tool>`. It refuses a call to
   a tool the grant does not cover, and a token whose invocation has ended.
4. The conductor records each record a tool returns, so a retrieval through the gateway is the
   harness's observation, not the agent's account ([Evidence and grounding](grounding.md)). The
   envelope lists them in `tool_retrievals` ([Contract](contract.md), invariant 27), each call is
   an `execute_tool` span under the invocation's root, and the gateway tells the agent what it
   recorded in the result's `_meta`, so the agent cites exactly that (`dd_sdk.tools.ToolRecord`).
5. Only a structured result grounds anything: `structuredContent` that the tool's pinned output
   schema admits, either one record or a list of them under `records`, each with its identifier.
   A record's source id is `tool:<server>/<record id>`. Free text from a tool is never
   evidence.
6. The deterministic shell makes the first retrieval, so the model is never called before a
   retrieval has ended (G1). It may then offer the model the granted, read-only tools as
   `dd_sdk.model.ToolSpec`s for follow-up lookups, with a limit per turn. Those calls also pass
   through the gateway and are recorded.
7. Tool results are untrusted content. They reach the model as quoted data in the user turn,
   never in the system prompt. Where invention is harmful, the model chooses identifiers only
   from the records the shell retrieved (Model-backed personas, item 3), and G2 checks every
   identifier the payload cites.

**Agent Skills for procedures.**

1. A persona loads a Skill as text in its system prompt. Code chooses which Skills a step needs,
   with `dd_sdk.skills.load_skills`, and adds their text with `with_skills`; the model gets no
   filesystem tool and does not choose Skills for itself. A Skill's references follow its
   `SKILL.md` in the prompt, since the model cannot follow a link to a file.
2. A Skill is vendored into the agent's package from the `skills` repository at a pinned
   release, under `skills/<name>/` beside `system_prompt.md`, and reviewed as a prompt change is
   (item 5). `skills/pins.json` records each Skill's version, the release it came from and its
   SHA-256, and `dd-vendor-skill` is the one way to change a vendored copy: it vendors a
   release already on disk and writes the pin. The digest, `dd-skill-files-v1`, is SHA-256 over
   one `<SHA-256 of the file>  <relative path>` line per file, sorted by path, as `sha256sum`
   prints them; like the prompt digest it is not an evidence canonicalisation. A Skill whose
   files do not hash to its pin is refused when the agent loads it. The card declares each
   Skill's name, version and SHA-256 (`AgentSpec.skills`, the manifest's `skills`), taken from
   the loaded Skill so that the two cannot disagree. The prompt digest already covers its text
   ([Disclosure](disclosure.md)).
3. A Skill a persona loads is text only: `SKILL.md` and Markdown or plain-text files under
   `references/`. Scripts, assets, executable files and links are refused, when vendored and
   when loaded. An exact procedure becomes code in the deterministic shell, or a tool on an MCP
   server.
4. A Skill cannot widen what a persona may do. Its tools, grounding mode and grants come from its
   card and the profile, never from prompt text; the loader reads only its front matter's `name`.

**Delegation versus tools.** A persona never delegates: it declares one grounding mode, and only
a `delegation` agent delegates ([Orchestration](orchestration.md)). A persona calls a tool when
it needs a record from a source or an exact lookup. When the need is another kind of expertise's
judgement, an outcome that may be `referred` or an abstention, or a different step, the
orchestrator asks the persona that serves it. Two personas that need the same source each use
its server; neither calls the other. Shared know-how is a Skill, not a persona.

**Worked example: `advisor.rights`** (partly built). It builds on the model-backed
alpha (`advisor-rights/interpret.py`, #697), whose model already chooses only from a closed set,
and has moved from `input_only` to `retrieval`. The shell builds the candidate licences from the
input and retrieves each through the gateway (`advisor-rights/retrieval.py`) before any model is
called; the closed set is the licences the gateway returned, and the payload cites the records the
conductor recorded (`tool:spdx/<id>`), hashed under the registered `dd-spdx-licence-v1` where the
deployment names it for the server. A failed retrieval leaves the licence out and says so in
`limitations`. Because a card declares one mode, an adviser granted no `spdx` server reads its
packaged table under one `retrieval` span and says so. The local MCP server is `mcp-spdx`, serving a
pinned SPDX release; no deployment runs it yet (TODO(#1478)). Still to build: the
`licence-choice` Skill loaded into the model's prompt (TODO(#280)).

## Rationale

- **Separate services.** An agent can be written, versioned, deployed, scaled and restarted apart
  from the harness, and its dependencies (a retrieval index, a model client) are not the
  harness's. The harness needs only an agent's inputs, outputs and the spans showing what it did;
  none of its governance depends on where the agent's code runs.
- **Discovery is configuration.** A deployment chooses its agents by listing addresses; an agent
  outside this repository is registered the same way as one inside it.
- **One manifest.** Every view of an agent agrees with every other because all are rendered from
  the same description.
- **Derivations, not presentation.** Which fields a model, a template or a rule produces is a
  claim about the agent's method, which is provenance and belongs in its manifest as data. Rules
  such as hiding `schema_class` follow from the schema, and field order from the LinkML source,
  so neither needs declaring. A declared derivation is checked against the payload class; a free
  presentation fragment was not, and a mistyped field was silently ignored.
- **Personas.** A role a person recognises is easier for a researcher to trust and for a data
  steward to assess. A narrow role keeps each agent's sources, failure modes and evaluation
  separate. Naming steps that no agent serves makes the whole intended design visible.
- **An emoji icon.** An icon lets a researcher tell a conversation's agents apart at a glance. An
  emoji names no icon library, so any client shows it as text, with no sprite or dependency, and
  a card stays meaningful wherever it is read.
- **A model-backed alpha.** It shows a persona's model-backed design to researchers early without
  claiming it is validated. The `template` path keeps CI and deployments without a key
  working once an operator selects it, and keeping exact work in a deterministic shell keeps it testable and lets a failed
  or rejected model reply fall back to rule output.
- **Tools through the harness.** A retrieval an agent makes itself is only its own account of
  what it read, so the linter can check only that the account agrees with itself
  ([Evidence and grounding](grounding.md)). A retrieval through the gateway is recorded by the
  conductor, as a delegation is. The gateway is also the only place a per-agent grant or an
  egress rule can be enforced, and a profile holds only keys something enforces.
- **Skills as pinned prompt text.** Text in the system prompt works on every provider and on a
  local model, needs no code-execution container, and is already named by the prompt digest. A
  procedure shared as a Skill is written once and reviewed once, whichever persona loads it.

## Rejected alternatives

- **Agents in the harness's process, found through Python entry points.** The harness and the
  agents were one program and could not be deployed apart. Keeping entry points as a second mode
  beside A2A was also rejected: two ways to reach an agent are two behaviours to keep conformant.
- **A central module listing every agent.** Every author edits one file, and it cannot list an
  agent from another distribution.
- **Discovery from the institutional profile.** The profile is policy. Letting it discover agents
  would let a profile edit add code paths.
- **A uiSchema (RJSF) fragment in the manifest.** It carried presentation to every consumer when
  only the viewer reads it, repeated rules that follow from the schema, and was never checked
  against the payload class.
- **Presentation fragments in the viewer, keyed by payload class.** The derivation claims
  describe an agent's method, not its class; two agents may produce the same class differently.
- **LinkML annotations as rendering hints.** They move presentation into the fixed contract,
  where each hint would be a contract change.
- **Inferring a recorder field by naming convention** (`<field>_derivation`). Existing classes do
  not follow it, and renaming them is a contract change for no gain.
- **The Blueprint's six broad agents** (§9.4, Table 7: Planning, Linking, Metadata, Repository,
  Provenance, Validation). Each mixes kinds of expertise, so its sources and failure modes could
  not be evaluated apart. Provenance in particular is the harness's job, not an agent's.
- **Each agent its own MCP client.** It is quicker to build, but the conductor sees no retrieval,
  the profile cannot grant or refuse a server, and nothing stops content leaving for a remote
  server.
- **Retrieval code private to each agent.** Two personas needing one source would each build and
  maintain it, and no other framework could use it ([System and boundaries](system.md)).
- **The model choosing Skills, or Skills with scripts.** A model reading Skills on demand needs a
  filesystem tool, and what it loaded would differ from run to run. Scripts need a
  code-execution container, which adds egress, does not carry over to a local model, and moves
  exact work out of the tested shell.
- **A persona asking another persona directly.** It would make the persona a delegating agent
  with a second grounding mode, and hide a step from the orchestrator and the researcher.

## Non-functional requirements

- **Security.** Calls between the harness and its agents are not authenticated yet:
  TODO(#17). Until they are, agent ports must not be exposed beyond the host or a private
  network. The linter checks what an agent reports about its spans, and that report now crosses a
  network ([Evidence and grounding](grounding.md)).
- **Egress.** A persona granted a `remote` MCP server receives only the classes of project content
  the profile allows for such servers ([Policy and identity](policy-and-identity.md)), so it never
  holds content it may not send there. Personal data go only to `local` servers, after detection
  (TODO(#39)). Red-team cases for injected tool results are TODO(#40).
- **Availability.** An unreachable agent is reported as unavailable and the rest carry on; a call
  that fails ends the run `failed` with the envelope stored as usual.
- **Portability.** Production container images and a Compose stack for the agents are not built
  yet: TODO(#223, #224).

## Open questions

- Whether agents declare example inputs in their manifest, instead of samples kept by the
  workbench: TODO(#108).
- Whether one persona may produce at a step while another checks the draft (a draft-and-critique
  loop): TODO(#309).
- Whether personas that read the same facts about a dataset, such as its fields, should share a
  project record rather than each declaring its own input class: TODO(#160).
- Whether an item's `grounded_on` column takes a per-class title. If it does, that is a
  schema-level `title`, not an agent-level hint: TODO(#70).
