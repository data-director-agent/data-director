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
   mode, derivations, models, steps served and title come from its card, never from the
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
   works out a payload's presentation from its schema and the derivations.
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
    advisors serve the same step. That last rule is not yet checked by a test.
13. A mock advisor's description begins "Mock.", its grounding mode is `none`, and its payload
    says in `limitations` what it does not yet do. Each mock's own tests check the prefix. A mock
    substantiates no Blueprint requirement; its tests may be marked only with the project's own
    contract requirements (`DD-*`) that the harness enforces on every agent.

## Boundaries and contracts

**What an agent owns.** Its domain logic, its input and payload classes
([Contract](contract.md)), its grounding mode ([Evidence and grounding](grounding.md)), its own
configuration (read from its own `DD_<AGENT>_*` variables, never from the harness's settings), its
model credentials ([Policy and identity](policy-and-identity.md)), and its system prompt as a file
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
load, so an agent started after the harness is found without a restart. Reloading a changed
configuration and checking the health of registered agents while running are not built yet:
TODO(#251).

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

Some steps are deliberately served by no agent, and the orchestrators name them as steps with no
agent:

- deciding how sensitive data are handled (`governance.sensitive-data-handle`) is a person's
  decision (C2). The ethics adviser flags sensitive data and stops there;
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

What a persona that drafts project documents may infer, ask and write is in
[Drafting documents](drafting.md).

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

## Non-functional requirements

- **Security.** Calls between the harness and its agents are not authenticated yet:
  TODO(#17). Until they are, agent ports must not be exposed beyond the host or a private
  network. The linter checks what an agent reports about its spans, and that report now crosses a
  network ([Evidence and grounding](grounding.md)).
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
