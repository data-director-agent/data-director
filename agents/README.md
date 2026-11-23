# Agents

[![CI](https://github.com/data-director-agent/data-director/actions/workflows/ci.yml/badge.svg)](https://github.com/data-director-agent/data-director/actions/workflows/ci.yml) [![Coverage](https://codecov.io/gh/data-director-agent/data-director/graph/badge.svg?flag=agents)](https://codecov.io/gh/data-director-agent/data-director?flags[0]=agents)

Each directory here is one agent: its own package, its own tests, and its own service. The
harness does not import any of them. Its conductor reaches each agent over A2A at the URL listed
in a registry file: `app/config/agents.yaml` for the app and `workbench/agents.yaml` for the
workbench ([Agents](../docs/specs/agents.md)). The rules for working here are in
[`AGENTS.md`](AGENTS.md).

An agent is an `AgentSpec` plus one method, `run(request, ctx) -> AgentResult`
(`dd_sdk.agent`). `dd_sdk.serve` puts it behind A2A: it publishes the agent card with the spec,
runs the agent under a tracer parented to the conductor's span, and returns the result with the
spans the agent recorded. The harness's conductor then holds the agent to its spec:

- it refuses an input of a class the agent did not declare, or one its class schema rejects;
- it rejects a payload of a class other than the one declared, or one its class schema rejects;
- it records the declared grounding mode on the envelope;
- it runs the grounding linter's rules for that mode over the returned spans.

An agent never sets identifiers, timestamps, telemetry or its grounding mode.

An agent owns its input and payload classes
([Contract](../docs/specs/contract.md)). It declares
them in a LinkML file of its own, which imports the core contract, and its card carries each
class's JSON Schema pinned by a digest. The conductor checks inputs and payloads against those
schemas, so it needs no copy of an agent's classes, and adding one needs no SDK release. What
every agent shares is the core, `sdk/src/dd_sdk/schema/data_director.yaml`: the request, the
envelope, outcomes, grounding, evidence, delegation, the principal, and the chat classes
`Message` and `Reply`. Its `version` is the contract version each card declares; the harness's
registry lists an agent built against an incompatible one as **incompatible**.

| Package | Agent id | Accepts | Mode | Payload | Serve | Status |
|---|---|---|---|---|---|---|
| `advisor-quality/` | `advisor.quality` | `MetadataRecord` | `input_only` | `QualityReview` | `dd-advisor-quality`, port 8102 | Demonstration, the Metadata Reviewer: weighted completeness from `checks.yaml`, with a summary beside the findings by a model (on by default; `DD_QUALITY_SUMMARISER=template` turns it off) (`advisor-quality/README.md`). |
| `example-hello/` | `example.hello` | `Salutation` | `none` | `Greeting` | `dd-example-hello`, port 8101 | **Template.** The Friendly Greeter: greets whoever the input names; the worked example of every step below (`example-hello/README.md`). |
| `orchestrator-stub/` | `orchestrator.stub` | `Message` | `delegation` | `Reply` | `dd-orchestrator-stub`, port 8106 | Rule-based stand-in for the orchestrator: routes each message by `routing.yaml` or an @mention and delegates through the conductor, or lists the steps from the researcher's Blueprint entry point and delegates the step they choose ([Orchestration](../docs/specs/orchestration.md), `orchestrator-stub/README.md`). |
| `orchestrator-model/` | `orchestrator.model` | `Message` | `delegation` | `Reply` | `dd-orchestrator-model`, port 8107 | The model-backed orchestrator (#21): Claude decides which agents to ask, from the manifest the harness publishes, and writes the reply. Besides those delegations it has only its own conversation tools (asking questions, naming the project, setting the entry point): no MCP server, web search or Skills ([Orchestration](../docs/specs/orchestration.md)). Needs a model key (`orchestrator-model/README.md`). |
| `advisor-standards/` | `advisor.standards` | `DatasetProfile` | `retrieval` | `Recommendations` | `dd-advisor-standards`, port 8105 | **Alpha.** The Standards Librarian: recommends vocabularies, ontologies and formats from FAIRsharing, before collection as well as after (committed snapshot, or live with the snapshot as fallback). Ranking rules choose first; a model (on by default) explains each pick, notes doubts and adds records it found with its own searches, each checked by the agent, never removing a rule pick. Configured by `DD_STANDARDS_*` (`advisor-standards/README.md`). |
| `advisor-policy/` | `advisor.policy` | `PolicyContext` | `retrieval` | `PolicyChecks` | `dd-advisor-policy`, port 8108 | **Alpha.** Phase 2: checks what funder, journal and institutional data and open access policies ask, from FAIRsharing's and Jisc Open Policy Finder's records, with a model (on by default) that searches for more and quotes each obligation from its record, and flags where they differ; also names any repository they require for Phase 3 (`advisor-policy/README.md`). |
| `advisor-repository/` | `advisor.repository` | `RepositoryNeeds` | `retrieval` | `RepositoryOptions` | `dd-advisor-repository`, port 8109 | **Alpha.** Phase 3: recommends repositories from the whole of re3data (a pinned monthly export), or describes the mandated ones, with PIDs, access, costs and certification as re3data and FAIRsharing record them (`advisor-repository/README.md`). |
| `advisor-ethics/` | `advisor.ethics` | `SensitivityContext` | `input_only` | `SensitivityFlags` | `dd-advisor-ethics`, port 8111 | **Alpha.** Flags field names that suggest sensitive data, by keyword and, by default (`DD_ETHICS_READER=template` turns it off), a model that may add flags but never remove one; asks what must be confirmed about consent and embargo; never decides how the data are treated (`advisor-ethics/README.md`). |
| `advisor-storage/` | `advisor.storage` | `StorageNeeds` | `retrieval` | `StorageAdvice` | `dd-advisor-storage`, port 8118 | **Alpha.** The Storage Adviser (`setup.storage`): recommends where to keep a project's data while it runs from the storage services the institution's profile names (`institution_storage`), leaving out those not approved for personal data when the data involve them, with each one's concerns and the questions a storage and backup plan answers. Its model, on by default (`DD_STORAGE_SUMMARISER=template` turns it off), writes a summary beside the advice and changes none (`advisor-storage/README.md`). |
| `advisor-files/` | `advisor.files` | `FileInventory` | `input_only` | `FormatAssessment` | `dd-advisor-files`, port 8110 | **Alpha.** Lists each file of a project's inventory with the format its media type or extension suggests and whether that format is open, and the files whose names, size or digest call for a person to look before deposit, without reading any file. Its model, on by default (`DD_FILES_SUMMARISER=template` turns it off), writes a summary beside those findings and changes none. |
| `advisor-dmp/` | `advisor.dmp` | `DmpCommitments`, `DmpReviewRequest` | `input_only` | `DmpDiscrepancies` | `dd-advisor-dmp`, port 8112 | **Alpha.** With a model, reviews an attached plan against Science Europe's core requirements, UKRI and UK Data Service good practice and the decisions made in the project (`setup.dmp-review`): each requirement covered, vague or missing as the model reads it, with a quote checked against the plan; without a model it abstains. Compares what a data management plan committed to share with what is planned at publication, and flags each difference for human review without enforcing it. Its matcher model, on by default (`DD_DMP_MATCHER=template` turns it off), reads only what the rules leave over: it may merge a missing and an unplanned output into one renamed flag, or reconcile two names for one licence or repository, each shown with its reason. With the model it also reads an attached free-text plan and proposes its commitments for the researcher to confirm (#962); reading a machine-actionable plan is #701. |
| `advisor-fairness/` | `advisor.fairness` | `PublishedRecord`, `ProjectMetadataDraft` | `input_only` | `FairnessReport` | `dd-advisor-fairness`, port 8117 | **Alpha.** Checks a published dataset's metadata, or at any time the project's draft metadata record, against a short list of FAIR-related presence checks, without retrieving anything or giving a FAIRness evaluation. It says what is already met first, tallies the checks for each of F, A, I and R, names the next steps and, for a draft, what is newly met since the version approved. Its writer model, on by default (`DD_FAIRNESS_WRITER=template` turns it off), tailors each recommendation to the record; whether a check is met stays by rule (`advisor-fairness/README.md`). Resolving the record and running F-UJI is #704; discovering related datasets is #954. |
| `advisor-metadata/` | `advisor.metadata` | `DraftRequest` | `input_only` | `Document` | `dd-advisor-metadata`, port 8113 | **Alpha.** The drafter of the metadata record (#200): a DataCite record with every property the chosen repository asks for, filling only the resource type, the formats and sizes the inventory gives, what researchers kept from their ORCID records and the answers they recorded, with a question for every value left null. Its suggester model, on by default (`DD_METADATA_SUGGESTER=template` turns it off), suggests a title, description, keywords and language beside the questions, never in the record. |
| `advisor-documentation/` | `advisor.documentation` | `DraftRequest` | `input_only` | `Document` | `dd-advisor-documentation`, port 8114 | **Alpha.** The Documentation Editor: drafts a Data Management Plan to Science Europe's core requirements from the decisions made and the researcher's answers, with no inventory (`setup.dmp-create`), and the README and the data dictionary ([Drafting documents](../docs/specs/drafting.md)): copies the inventory's files and fields and the approved metadata record's title, creators, abstract and licence, marks each dictionary value as inferred, supplied or unknown, fills missing value codes the inventory's summary found, marked inferred, and leaves the methods, definitions, units and any other codes as marked gaps, each asked as a question. Its model, on by default (`DD_DOCUMENTATION_WRITER=template` turns it off), writes the README's prose from those facts alone and suggests answers beside some questions, never in the draft; a plan's storage question is offered the institution's storage services from the profile (`advisor-documentation/README.md`). |
| `advisor-rights/` | `advisor.rights` | `RightsContext` | `input_only` | `RightsOptions` | `dd-advisor-rights`, port 8115 | **Alpha.** Lists data licences from a short fixed table that fit the reuse wanted, and access levels with when each applies, for the researcher to choose from; never chooses. Its interpreter model, on by default (`DD_RIGHTS_INTERPRETER=template` turns it off), reads a reuse wish in the researcher's own words and tailors questions about third-party content or a mandate, choosing only from the table (`advisor-rights/README.md`). Licences from SPDX through the tool gateway are #877. |
| `advisor-linking/` | `advisor.linking` | `LinkCandidates` | `retrieval` | `RelatedIdentifiers` | `dd-advisor-linking`, port 8116 | **Alpha.** Recognises DOIs, ORCID iDs, ROR IDs and grant numbers by form, checks ORCID checksums, gives canonical https forms and suggests how to record each link; looks DOIs, ORCID iDs and ROR IDs up through the tool gateway where one is granted. Its model, on by default (`DD_LINKING_SUMMARISER=template` turns it off), writes a summary beside those findings and changes none. |

Start every agent with `scripts/run-agents.sh` from the repository root, or one agent with
`uv run dd-example-hello serve --port 8101`. The script restarts an agent when a file in its package
changes, its `system_prompt.md` included, unless `scripts/dd.py start` is given `--no-reload`;
`serve --reload` does the same for one agent.

An agent id is `<group>.<name>`. The groups are `orchestrator` (agents a person converses with,
which delegate to others), `advisor` (agents that answer one kind of question, each a persona from
the roster in [Agents](../docs/specs/agents.md) with a `title` that people see) and
`example` (templates). A directory, package and serve command spell the id with hyphens or underscores:
`advisor.policy` is `advisor-policy/`, `dd_agent_advisor_policy` and `dd-advisor-policy`.

## Start with `dd.py new-agent`

```sh
uv run scripts/dd.py new-agent advisor-foo
uv sync --all-packages --all-extras
```

writes `advisor-foo/`: the package `dd_agent_advisor_foo`, with agent id `advisor.foo`, served
by `dd-advisor-foo` on the port after the highest the app lists. The name is lower-case words
joined by hyphens; the first hyphen is the dot in the agent id. The new agent is a working mock
(grounding mode `none`) with:

- its own input class and its own payload class, and their generated schemas;
- its payload fields' derivations, and a `limitations` slot saying what it does not yet do;
- a console script;
- tests through a conductor, with their sample input.

It is written on the agent kit in `dd_sdk.agent`, which every agent uses rather than its own
copy:

- `abstain(reason, statement)` returns an abstention, with no payload or evidence.
- `input_ref(ctx)` and `input_evidence(ctx)` return the grounding reference and the evidence item
  that cite the invocation's input, which is all a `none` or `input_only` agent may cite.

The command also does steps 5 to 7 below. It lists the agent wherever `example-hello` is listed:

- the root `pyproject.toml`, then `uv lock`;
- `compose.yaml`, `docker/compose.image.yaml` and `docker/agents.yaml`;
- `app/config/agents.yaml`, `workbench/agents.yaml` and `deploy/agents/<name>.env`;
- the three profiles;
- the docs navigation in `mkdocs.yml`;
- the Mock row of the roster table in [Agents](../docs/specs/agents.md).

The new agent passes `uv run pytest`, `uv run mypy`, `uv run lint-imports`,
`scripts/check_boundaries.py` and `scripts/check_members.py` as written. Then:

1. Replace its placeholder advice.
2. Add its row to the table above.
3. Move it in the roster table when it is no longer a mock.

`example-hello/` stays the worked example. `example-hello/src/dd_agent_example_hello/agent.py`
walks the whole of the recipe below with no domain logic in the way, and is commented against
the numbered steps. It is also the check on the claim in the last line of this file.
`example.hello` has no reason to fail other than the harness. If adding an agent ever needs an
edit to the conductor, linter, CLI, transports or viewer, this agent will show it.

## Build for reuse

An agent is the contract-bound layer over work that should stand without it. Before writing
domain logic into an agent, decide which part is reusable by anyone, and build that part as its
own asset ([System and boundaries](../docs/specs/system.md)):

| The work is | Build it as | Repository |
|---|---|---|
| A lookup of or action on an external service or dataset | An MCP server, or a plain Python library | `mcp-<name>`, or a descriptive name |
| Know-how, a checklist or a procedure a model follows | An Agent Skill (`SKILL.md` with optional scripts and references) | `skills` |
| A formal artefact (vocabulary snapshot, profile, schema, evaluation set) | Versioned data with its own licence and provenance | descriptive name |
| Answering a question under the contract, with grounding and evidence | An A2A agent | `agent-<name>`, or here |

The agent then calls the library or MCP server, loads the skill's instructions into its prompt,
and adds the contract: its classes, its grounding mode and the evidence for what it retrieved.
Rules that keep this true:

- Agent logic that needs no `dd_sdk` import sits in a module, or a separate package, that does
  not import it, so the agent file stays thin. `advisor-standards/` is the nearest example: its
  `fairsharing/` subpackage is a client that almost never imports `dd_sdk`, though it is still
  inside the agent's package rather than published on its own (TODO(#280)).
- An agent may use MCP servers and Agent Skills; it must still hash what it retrieved through
  them and cite it (step 3 below), so a tool's answer is evidence like any other. An orchestrator
  has no such tools of its own ([Orchestration](../docs/specs/orchestration.md)).
- Use open standards for every interface: A2A, MCP, Agent Skills, JSON Schema, LinkML. Do not add
  an agent-only protocol or a private config format where one of these serves.
- Keep an agent to one question. Compose agents by delegation, not by one agent absorbing
  another's logic.
- An agent imports no other agent and nothing outside `sdk/` among workspace members, and reads
  no path outside its directory, so that it can move to its own repository by copying it.
- Give the package a README that says what it does, what it depends on, its licence and its
  version, and say in it which parts are reusable without the contract.

## Adding an agent

1. **Declare what it reads and returns.** A conversational agent can use the core's `Message`
   and `Reply`. Any other class belongs to the agent. `example-hello/` is the worked example:
   - `src/dd_agent_<name>/schema/<name>.yaml` declares the classes in LinkML. It imports
     `linkml:types` and `data_director` (the core), and has its own `id` and prefix. An input
     class carries the slot `schema_class`; a payload class carries `schema_class` and
     `mixins: [Grounded]`.
   - `uv run dd-gen-schema agents/<name>/src/dd_agent_<name>/schema/<name>.yaml` writes, for
     each class, its JSON Schema, its SHACL shapes and its JSON-LD context to `generated/` beside
     it. Commit them; never edit them by hand. The card carries all three, and the harness keeps
     a SHACL Validation Report of each payload beside the run.
   - `src/dd_agent_<name>/classes.py` holds a Pydantic model per class, subclassing
     `dd_sdk.contract.models.Frozen` (input) or `Grounded` (payload), with
     `schema_class: Literal["<Class>"]`.
   - The spec names each class as `ClassSchema.of(Model)`. It reads the generated schema from
     the model's package and refuses a model whose fields differ from it.

   A test calls `dd_sdk.schema.gen.stale(<path to the LinkML file>)` and expects `[]`, so a
   stale generated schema fails the agent's own suite. Two agents may define classes of the same
   name; the digest, not the name, identifies a class in a stored run.

   Say which steps of the Blueprint's process flow the agent helps with, by their ids in
   `dd_sdk.process_flow`: `serves=("setup.vocabularies", "setup.formats", "preparation.formats")`. The
   orchestrators name it at those steps and no others ([Orchestration](../docs/specs/orchestration.md)). Name steps, not
   requirements: the requirements it bears on follow from the steps, and whether it meets them is
   for the [requirements register](../docs/requirements.yaml).
2. **Decide its grounding mode** ([Evidence and grounding](../docs/specs/grounding.md)).
   - `retrieval` if it consults external records. Emit one
     `dd_sdk.tracing.retrieval_span(ctx.tracer, source_id, content_hash)` per record consulted,
     before any model call. Put a `GroundingRef` for each record the payload rests on in
     `grounded_on`.
   - `input_only` if it works over the input and may call a model.
   - `none` if it is deterministic.
   - `delegation` if it answers by handing work to other agents (an orchestrator). Call
     `ctx.delegate(agent_id, input)`, never another agent directly; the conductor runs the child
     and returns a `Delegated` whose `ref` and `evidence` are what the payload cites for it
     ([Orchestration](../docs/specs/orchestration.md)). `ctx.delegate` is `None` when no grant was issued (for example under
     `workbench invoke`); handle that as an outcome. `orchestrator-stub/` is the worked example.

   In `input_only` and `none`, `grounded_on` and `evidence` cite the input and nothing else:
   `input_ref(ctx)` and `input_evidence(ctx)` from `dd_sdk.agent`. Always use `ctx.tracer`. A span started some other way is
   outside the invocation's trace, and the linter's G0 rule withholds the output.
3. **Hash what you retrieved** with a registered canonicalisation from `dd_sdk.evidence`
   ([Evidence and grounding](../docs/specs/grounding.md)). Register a new name there if none fits; never invent one in the agent.
4. **Write the package.** `dd.py new-agent` writes it (above). You need:
   - `pyproject.toml` depending on `data-director-sdk`, with a console script
     `dd-<name> = "dd_agent_<name>.agent:main"`;
   - a class with `spec = AgentSpec(...)` and `run`;
   - a module-level `build() -> Agent` and `main() -> int` that returns `serve.main(build)`.

   Read the agent's own `DD_<AGENT>_*` environment variables in `build`. They are for how the
   agent works, such as an endpoint or a path; what the deployment allows is set in its
   institutional profile, not in a variable ([Policy and identity](../docs/specs/policy-and-identity.md)).
   A content problem is an outcome (`abstain(reason, statement)` from `dd_sdk.agent`), not an
   exception.

   A source copy too large to commit is built where it is used, from something the package pins.
   Declare it as a `dd_sdk.sources.BuiltSource` (its name, pin, what is wrong with the built copy,
   and how to build it into a given cache) and register it in `pyproject.toml` under
   `[project.entry-points."dd.sources"]`; mark its entry in each `sources.yaml` `built: true`.
   `uv run dd-sources prepare` then builds it wherever the others are built, and nothing outside
   the agent needs its build command. `advisor-repository/` is the example (`registry.SOURCE`).

   An agent that calls a model keeps its system prompt in `system_prompt.md` beside the module
   that sends it, and reads it with `Path(__file__).with_name("system_prompt.md")`, so the prompt
   can be read and reviewed as prose. A second prompt is `<purpose>_prompt.md` beside it
   (`orchestrator-model/`'s `title_prompt.md`). CI treats these files as the agent's code, not as
   prose.
   It records each call with a `dd_sdk.prompts.ModelCallLog`, where it opens the call's `chat`
   span, with the system prompt, messages and tools it sent and the model the response names, and
   returns the log's `calls` and `prompts` in its `AgentResult`. The harness keeps the prompts
   beside the run, and a project's disclosure names the model and the prompt's digest
   ([Disclosure](../docs/specs/disclosure.md)). `orchestrator-model/` and `advisor-standards/`
   are the examples.

   An agent that is exploratory — not yet validated, likely to change shape — ships with a
   pre-release version (`version = "0.1.0a1"`, PEP 440) instead of the usual `0.1.0`, and its
   `README.md` and its row in the table above say plainly that it is alpha. There is no separate
   prototype tree for this: an experimental agent is a normal package under `agents/`, just marked
   by its version. Bump it to an ordinary `0.1.0`-style version once it is no longer experimental.

   An advisor moving from a mock to a model (a model-backed alpha) declares `input_only`, drops
   the "Mock." prefix and defaults to its model, with a `template` writer that calls no model for an
   operator to select; add its setting to `MODEL_BY_DEFAULT` in `scripts/ddtool/common.py`, which
   `scripts/tests/test_dev_script.py` checks. The barebones start is `dd_sdk.summary`: a model's
   summary beside the rules' findings (`advisor-quality/`). Build it to the
   conventions in [Model-backed personas](../docs/specs/agents.md#model-backed-personas): a
   deterministic shell around the model, checked structured output, a recorder for each value a
   model may write, a fake client in its tests, and an evaluation set before it leaves alpha.
   Reviewers check it against
   [Reviewing a model-backed agent](../docs/guide/developer-guide/reviewing-a-model-backed-agent.md).
5. **Add it to the workspace.** `dd.py new-agent` has done this. It adds the distribution to
   the `dependencies` and `[tool.uv.sources]` of the root `pyproject.toml`, and the package to
   every other list there that `scripts/check_members.py` checks, then runs `uv lock`. Run
   `uv sync --all-packages --all-extras`. A package that lives outside this repository skips this
   step; it only has to be served.
6. **Register it.** `dd.py new-agent` has done this. It adds one entry with a name and the URL it
   is served at to each registry file (`app/config/agents.yaml`, `workbench/agents.yaml` and
   `docker/agents.yaml`). It adds a service to `compose.yaml` and `docker/compose.image.yaml`, and
   writes `deploy/agents/<name>.env`. `scripts/run-agents.sh` reads the app's list.
7. **Enable it** in the profiles that should run it (`app/config/profile.yaml.example`,
   `workbench/profiles/default.yaml` and the harness's test profile
   `harness/src/dd_harness/testing/profiles/test-permissive.yaml`). `dd.py new-agent` enables it
   in all three; take it out of any that should not run it. Registration is not permission.
8. **Ship a sample input and declare the payload's derivations.**
   - Put a sample input, with `schema_class` set, in `workbench/samples/`. The viewer builds its
     input form from the class schema in the agent's card.
   - If the agent has a payload, declare in `spec.derivations` how it produces each field that
     it does not copy from input or evidence, for example
     `{"rationale": Derived(Derivation.MODEL, recorded_in="rationale_derivation")}`. A field a
     model may write names the sibling that records, per value, how it actually came about. The
     spec refuses a path or a sibling that the payload class does not have. Ship no presentation:
     the viewer lays the payload out from its schema, in LinkML slot order ([Agents](../docs/specs/agents.md)).
9. **Test it** in `<name>/tests/`, with a test module name no other package uses. Test the
   agent through a conductor with `dd_harness.testing.make_conductor(runs_dir, YourAgent())`,
   which serves it in memory over A2A exactly as a deployed conductor calls it. Mark each test with the
   requirement identifiers it actually exercises (`docs/requirements.yaml`). Do not
   claim a Blueprint `R` a demonstration does not meet.
10. **Optionally, evaluate it** ([Evaluation and conformance](../docs/specs/evaluation.md)). Put an Inspect AI task in `<package>/evals/`, built
    on `workbench.evaluation.invoke_agent` and its generic scorers, with the agent's own cases
    and scorers beside it and a committed `baseline.json`. `dd_agent_advisor_standards.evals` is the worked
    example.

Nothing in the SDK, conductor, linter, CLI, transports or viewer is edited.
