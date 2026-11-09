# Contract

## Intent and scope

The contract is the fixed format the harness governs every agent invocation by: the request an
agent receives, the envelope it returns, the outcome vocabulary and its problem reports, and the
grounding slots every payload carries. It is small on purpose. It says what any governed run must
look like, and leaves what a particular agent reads and returns to that agent.

This spec covers the core contract, how agents own their input and payload classes, LinkML as the
source and JSON Schema as what runtime checks, identifiers, outcomes and problem reports, the
dataset profile, the validation report format and the place of RO-Crate. The field-level
description of the request and envelope is in [the contract reference](../contract.md). Evidence,
grounding modes and canonicalisations are in [Evidence and grounding](grounding.md); the A2A card
that carries an agent's schemas is in [Transport and tracing](transport.md) and
[Agents](agents.md); the principal an invocation acts for is in
[Policy and identity](policy-and-identity.md); conversations and delegation are in
[Orchestration](orchestration.md); the deposit package is in [Deposit](deposit.md).

## Invariants

1. The core contract holds only what the harness itself reads: the request and the envelope, the
   outcome and problem details, grounding and evidence, telemetry, delegation and the principal,
   and the few classes the harness, the project record or the deposit package read without
   knowing the agent (conversation turns, `Message` with the `InventorySummary` the conductor fills
   in and a `ChoiceAnswer`, `Reply` with a `ChoiceQuestion`, `Document` with its
   `DocumentQuestion`s, `FileInventory`, `RequirementSet`, the drafters' `DraftRequest` with
   `CurrentVersion`, `DraftAnswer` and `RepositoryRequirements`, and the
   enums they use). No agent's own input or payload class is added to it.
2. In the core, an input is any object with a `schema_class`, and a payload is any object with a
   `schema_class` that mixes in `Grounded`. The core checks nothing else about either
   (`sdk/tests/test_contract.py`, the "open but name their class" and "any class" tests).
3. Every input and payload class carries `schema_class`, a required type designator whose value
   is the class name, and every payload class, and every item class within a payload that asserts
   an identity, mixes in `Grounded`. A card whose payload schema does not require `schema_class`
   and `grounded_on` is refused (`dd_sdk/contract/classes.py`, `sdk/tests/test_agent_spec.py`).
4. No closed registry of class names exists in the SDK, the harness, the workbench or the app.
   The harness knows a class only from the schema an agent's card carries; its own test doubles
   use classes of their own for that reason (`harness/tests/test_harness.py`,
   `test_the_doubles_classes_are_generated_from_their_own_linkml`).
5. A card carries the contract version its agent was built against and, for each class it accepts
   or returns, the class's JSON Schema with its digest (sha256 in the `dd-json-document-v1`
   canonicalisation). A card whose digest does not match its schema, or that names a class it
   carries no schema for, is refused (`harness/tests/test_registry.py`). Beside the schema, a
   class may carry `shapes`: its SHACL shapes as Turtle text, the JSON-LD context that reads its
   documents as RDF, and their digest (of `{"shacl", "context"}` in the same canonicalisation;
   neither holds a number, so the digest survives A2A). Shapes that do not match their digest are
   refused like a schema; a class without them is governed all the same
   (`harness/tests/test_payload_shapes.py`).
6. An agent is governed only when its contract version has the harness's major version and, while
   the major version is 0, its minor version too (the caret rule). Any other agent is recorded as
   **incompatible**, naming both versions, and never as unavailable (`dd_sdk/contract/version.py`,
   `harness/tests/test_registry.py`).
7. The conductor refuses, before the agent runs, an input whose `schema_class` the agent does not
   accept or which fails that class's schema: the outcome is `failed` with problem type
   `input-not-accepted` (HTTP 422). A payload of another class than the declared one, or one its
   class schema rejects, becomes `failed` with `agent-error` (`harness/tests/test_harness.py`).
   A payload the envelope still carries once every check has run is then checked against its
   class's shapes, when the class has any, and the SHACL Validation Report is kept beside the run
   as `validation-report.jsonld` and in its Process Run Crate. The shape check reports only: the
   outcome, payload and problem are the same whatever the report says
   (`harness/tests/test_payload_shapes.py`).
8. A stored envelope names the contract version it was governed under, the digest of the input
   class schema it was checked against (when the class was accepted) and the digest of the
   payload class schema exactly when there is a payload. The run store keeps each schema once,
   by digest, so a stored run is rendered with the schema it was checked against, whatever the
   agent's card says later.
9. Within a stored run, a class is identified by its schema digest, not its name: two agents may
   each define a class of the same name.
10. The input hash is taken over the validated input document as the agent is given it, with
    null values removed: as it was received, except for the project's facts the conductor puts
    into a `Message`, a `DraftRequest` or a `FileInventory` in a project, and a `Message`'s
    `project_inventory`, `project_entry` and `project_progress`, which it removes outside one ([Projects](projects.md), invariant 6). No
    model defaults are added before hashing.
11. `project_id`, on the request and the envelope, is set only by the conductor, from the
    conversation a request is a turn of or a child's grant. A caller's request that carries it is
    refused, and the agent is never sent it (`harness/tests/test_project_runs.py`).
12. `invocation_id` is a UUIDv7 (RFC 9562); the schema pins the version nibble in a pattern
    (`test_request_validates_and_rejects_bad_id`). Identifiers carry no information about the
    dataset.
13. The outcome status is one of `succeeded`, `abstained`, `referred`, `failed`, `suspended`, and
    `validate.py` enforces what JSON Schema cannot: `succeeded` carries a payload and no other
    status does; `failed` and `suspended`, and only they, carry a `problem`; `abstained` and
    `referred` carry a `reason_code`; `referred` also names `referred_to`
    (`sdk/tests/test_contract.py`).
14. A `problem` is an RFC 9457 Problem Details object, used verbatim, with a type URI under
    `https://w3id.org/data-director/problems/`. The resumption condition of a `suspended` run is
    in the two extension members `resume_condition` and `resume_after`.
15. `requires_human_review` is the constant `true` in the generated schema, so no envelope, from
    any language, can claim otherwise (C13, C15; `test_human_review_cannot_be_false`).
16. The LinkML source is the contract. `schema/generated/` is never edited by hand: it must equal
    a fresh `dd-gen-schema` run, for the core (`test_generated_schemas_are_current`, and the
    `git diff --exit-code` step in `.github/workflows/ci.yml`) and for each agent's classes (each
    agent's `gen.stale(SCHEMA)` test).
17. Generator gaps are repaired only in `sdk/src/dd_sdk/schema/gen.py`, whose `_repair` docstring
    names each repair. Rules JSON Schema cannot state are written as prose in the LinkML source
    and enforced in `dd_sdk/contract/validate.py`, the single runtime call site for validation.
18. Runtime code never imports `linkml` or `linkml_runtime`. LinkML is a development dependency of
    the root workspace, needed to regenerate a schema, never to load or check a document.
19. An agent's Pydantic model for a class has exactly the fields of the class's generated schema;
    `ClassSchema.of` refuses one that differs
    (`test_a_model_that_disagrees_with_its_generated_schema_is_refused`).
20. No agent builds, sends or parses an RO-Crate as part of a call, and nothing in the harness
    reads a crate back to make a decision. `dd_harness/provenance.py` is the only importer of
    `rocrate`.
21. An envelope records each model call an agent reports in `telemetry.model_calls`, and names
    the call's prompt by its `dd-prompt-json-v1` digest only. The prompt itself never enters the
    envelope, the trace or the crate; the run store keeps it ([Disclosure](disclosure.md)).
22. A `Reply` may carry `conversation_title`, one line of at most 80 characters that a person can
    tell the conversation apart by. A model writes it from the researcher's first message, on a
    conversation's first turn only; an agent that sets it declares it model-derived, and a later
    turn, or a rule-based agent, leaves it out. The harness reads it to name the conversation
    ([Orchestration](orchestration.md)) and checks nothing else about it.
23. A `Reply` may carry one `ChoiceQuestion` (`reply_question`): a prompt and 2 to 12 options,
    each a string value with a label and optional help, whether several may be chosen, and whether
    the researcher may answer in their own words. Option values are unique within the question and
    are strings, because A2A carries numbers as doubles. A `Message` may carry a `ChoiceAnswer`
    (`choice_answer`) naming the invocation whose reply asked, the values chosen and any answer in
    the researcher's own words; `message_text` says the same in words. The option bounds are in
    the Pydantic model, not the schema: a card carries class schemas over A2A, which would turn the
    bounds into doubles and break the schema digest (#333). The harness checks an answer against
    its question before the turn runs (`dd_harness.conversations.answer_problem`,
    `sdk/tests/test_contract.py`, `harness/tests/test_conversations.py`). The project intake asks
    its questions as `ChoiceQuestion`s too, outside any reply; its answers go to the project, not
    a turn, so they carry no `ChoiceAnswer` and the core schema does not change for them
    ([Orchestration](orchestration.md), invariant 20).
24. A `Document` may carry `document_questions`, one `DocumentQuestion` for each gap the version
    leaves: an identifier unique within the document (`q-` and 16 hexadecimal digits, derived
    from the gap), the text put to the person, and a target that is either a README section or a
    data dictionary cell named by file, field and column, and optionally a suggested answer with
    how it was derived (`suggested_answer` and `suggestion_derivation`, both or neither). A
    `DraftRequest` may carry `draft_answers`, each a `DraftAnswer` naming the question it answers
    and the text, which the drafter places as given ([Drafting documents](drafting.md), `sdk/tests/test_contract.py`).

## Boundaries and contracts

**The core and the agents.** The SDK owns the core schema and its `version`, which is the
contract version. Changing the core, the outcome vocabulary or the reason codes is a change to a
fixed format and changes this spec. An agent owns its input and payload classes: it declares
them in its own LinkML file, which imports the core and uses its own `id` and prefix, generates
one self-contained, closed JSON Schema per class into its own package, and keeps its Pydantic
model beside it. An agent's classes follow the agent's own version. Adding an agent with new
classes therefore touches nothing central: no SDK release and no harness redeploy.
`agents/README.md` is the recipe.

**Languages other than Python.** The JSON Schema is the published contract for an agent in any
language. The Pydantic models in the SDK are a convenience for Python, written by hand to mirror
the source; the tests validate instances of them against the generated schema, but do not catch a
slot present in the source and missing from a core mirror.

**The outcome vocabulary.** The Blueprint defines no outcome vocabulary; this one is the
project's contribution. `abstained` and `referred` are not problems. They are outcomes of equal
standing with `succeeded`, each with a reason from the `ReasonCode` enumeration. Only `failed`
and `suspended` are problems. Problem types the harness emits are in
`dd_sdk/contract/problem.py`.

**The dataset profile.** `DatasetProfile` is the standards advisor's input class, owned by that
agent, not a core class. It is deliberately minimal: it describes only what the standards advisor
reads, so that no agent is tempted to read the dataset itself through it. Each of its slots maps
to Dublin Core Terms or DCAT by `slot_uri`, so a repository that speaks DCAT fills it without a
mapping table. A new slot names the agent that reads it and its external term. Tabular fields are
the core's `TableField`, which mirrors a Frictionless Table Schema field descriptor; Frictionless
publishes no RDF namespace, so those slots carry `see_also` to its specification rather than
invented URIs.

**Vocabularies.** A slot or class that means a term of an existing vocabulary (Dublin Core, DCAT,
schema.org, PROV) says so with `slot_uri` or `class_uri`. A slot without an external term carries
`see_also` to its specification. No Data Director term is invented where an external one exists.

**Validation reports.** Structured validation output (C15) uses the W3C SHACL Validation Report
vocabulary (`sh:ValidationReport`, `sh:ValidationResult`), with a Frictionless validation report
for tabular data. No bespoke report type is defined. The harness writes a report in two places.
When it validates a project for deposit, the shapes are generated from the chosen repository's
requirements ([Deposit](deposit.md)). When an agent returns a payload, the shapes are its class's
own: `dd-gen-schema` writes, beside each class's JSON Schema, the class's SHACL shapes
(`<Class>.shacl.ttl`, the class's node shape and every shape it reaches) and a JSON-LD context
(`<Class>.context.jsonld`), and the card carries both. The harness reads the payload as RDF
through the context, naming each object's class with `@type` from the class schema
(`dd_sdk.contract.rdf`), and runs pySHACL (`dd_harness.shacl`). The report names the
invocation, the payload class and the digests of its schema and shapes.

The shape check does not change the outcome. The class's JSON Schema, which a payload must
pass, already decides what is structurally valid, and the shapes are generated from the same
LinkML source; what the shapes add is a reading of the payload in its vocabularies, which a
reviewer reads beside the run. A violation is a finding for the agent's author, not a content
problem for the researcher.

**RO-Crate.** RO-Crate is a record written after a run, not a message format. Callers, the
harness and agents exchange `InvocationRequest` and `Envelope` over A2A, validated against the
contract. Once the checks are done, the conductor writes a Process Run Crate into the run's
folder (R10): one `CreateAction` with the agent as instrument, the human it acted for as agent,
the request as object and the envelope and trace as result. The crate is derived; the envelope
stays authoritative, and turning crate writing off changes no outcome. The deposit package is
itself an RO-Crate of the dataset, written by the harness, never returned by an agent as a
payload; see [Deposit](deposit.md).

## Rationale

The harness governs agents it was not built with, written by other people, perhaps in other
languages, and deployed separately. A central schema of every class forced every agent to change
in lockstep with one file and one SDK release, and it put demonstration classes into the fixed
format. Everything the harness checks is structural (a `schema_class`, a `grounded_on`, a class
schema), so it does not need to know a class in advance. Carrying the schemas, pinned by digest,
in the card lets one fetch give the harness everything it checks, and lets a stored run name the
exact schema it was held to.

A discriminator is required because input classes have only optional slots: without one, `{}`
would match any class, and a JSON Schema `anyOf` could match several. The `Grounded` mixin lets
the grounding linter find what any payload rests on without knowing its class; an unfamiliar
shape is then a violation, never a silent pass.

An explicit contract version turns a mismatch into a named incompatibility rather than an agent
listed unavailable for a reason that does not say why.

LinkML is the source because the contract must be language-neutral, legible to researchers and
engineers, and bound to existing vocabularies, and because SHACL shapes are needed alongside
JSON Schema. One YAML source yields both, with slot URIs and descriptions a reader needs.
Keeping LinkML out of the runtime keeps a deployed instance independent of it: if LinkML were
abandoned, the committed JSON Schema would become the hand-maintained source.

UUIDv7 sorts by time, so an append-only run store and any index sort invocations by identifier
alone. RFC 9457 is understood by existing software, so a consumer that handles Problem Details
needs nothing new for failures.

A crate carries a root dataset and a JSON-LD graph that the governance checks do not need, and
it is read later by a person or an archive, not immediately by the next agent. Keeping it out of
the message path lets it change shape, or be replaced by another provenance format, without
touching the contract, the agents or the checks.

## Rejected alternatives

- **Every class in the core, or in a separate central file.** A new class would still need an SDK
  release and a harness redeploy, and agents would change in lockstep.
- **Serving class schemas beside the card, by URL and digest.** More fetches and more ways to
  fail, for a card that stays small in practice.
- **Generating class schemas from the Pydantic models, or Pydantic as the source.** That makes
  Python the definition of a language-neutral contract and loses slot URIs and descriptions.
- **Hand-written JSON Schema as the source.** No vocabulary URIs, and SHACL kept in step by hand.
  It remains the fallback if LinkML is abandoned.
- **SHACL or OWL as the source.** Harder for engineers to read and write, and neither yields a
  JSON Schema conventional tooling validates against.
- **A bare `grounded_on` convention without the mixin.** Nothing would enforce it.
- **Per-class adapters registered with the linter.** An unregistered class reintroduces the
  silent pass, and the linter would change with every agent.
- **A fixed `DatasetProfile` with a free-form `context` map instead of polymorphic input.** Weaker
  typing, and every agent would pretend to read a dataset profile.
- **A rich dataset profile, or a Data Director vocabulary for its slots.** The first invites
  agents to read the input directly; the second adds a mapping problem for every repository that
  already speaks DCAT.
- **A bespoke `ValidationReport` type.** A second thing to maintain where a W3C vocabulary exists.
- **A SHACL violation in a payload downgrades the outcome, as a linter violation does.** The
  shapes come from the same source as the JSON Schema that already gates the payload, so a
  violation is a disagreement between two readings of one class, which the agent's author
  resolves; withholding a researcher's result for it would be out of proportion.
- **The payload's report in the envelope.** The envelope is closed, and a report is a record of a
  check, like the linter's summary, not part of the agent's answer; it is kept beside the run.
- **Shapes for the whole core and every agent in one file, as `gen-shacl` writes them.** A card
  would carry shapes for classes the agent never returns; per-class shapes are as self-contained
  as the class schemas.
- **Treating `abstained` or `referred` as problems.** Declining or handing to a person is a valid
  answer, not an error.
- **RO-Crate as the message between agents.** The checks run on the request, envelope and trace;
  a crate adds what they do not need and would make provenance a governance input.

## Non-functional requirements

- **Portability.** Validation needs only a Draft 7 JSON Schema validator; the generated schemas
  declare Draft 7, and the workbench viewer validates against the same files. The shape check
  needs a SHACL processor, and only reports, so a consumer without one loses no check that
  decides an outcome.
- **Auditability.** A stored run can be rechecked and rendered from its own record: contract
  version, schema digests and the schemas themselves are kept with it.
- **Privacy.** An identifier carries nothing about the dataset, and a problem report never
  carries the caller's credential.

## Open questions

- Problem type URIs and agent identifiers use the w3id namespace, which is not yet registered.
  TODO(#3)
- `TableField` slots carry `see_also` until Frictionless publishes term IRIs. TODO(#20)
- The Process Run Crate names the harness's own files as object and result rather than the
  records the agent read or the metadata it changed; it does not link a delegated run to its
  parent, names an accountable role as a `Person`, records the outcome as an unreferenced
  `PropertyValue`, does not name the schema digests, and is not checked against the profile with
  `rocrate-validator` or aligned with PROV-O (R10). TODO(#26)
- Envelopes stored under an older contract lack the contract version and schema digests and do not
  validate against the current schema; they are shown as raw JSON until migrated. TODO(#247)
- Why the core models are hand-written mirrors rather than LinkML's `gen-pydantic` output is not
  recorded. TODO(#249)
