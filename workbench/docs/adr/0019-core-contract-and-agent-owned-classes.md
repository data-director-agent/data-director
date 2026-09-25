# ADR-0019: A core contract, and input and payload classes owned by their agents

**Status:** Accepted
**Date:** 2026-09-25

Amends [ADR-0007](0007-polymorphic-contract.md) (decision 1 and its first consequence) and
[ADR-0011](0011-remote-agents.md) (the constraint "the contract stays central", decision 2's
"it is still one file", and the rejection in decision 5).

## Context

ADR-0011 made each agent a separate service, but it kept every input and payload class in one
LinkML schema, `sdk/src/dd_sdk/schema/data_director.yaml`. `INPUT_TYPES` and `PAYLOAD_TYPES` in
`dd_sdk.contract.models` were closed registries, and `spec_from_description` rejected a card
that named a class they lacked. So the rule "adding an agent touches nothing central" did not
hold. A new class meant editing the shared schema, regenerating it, releasing the SDK and
redeploying the workbench. Agents ran as separate services but had to change in lockstep with one
central file.

Three further problems followed from that:

- **The card carried no contract version.** When an agent and the workbench were built against
  different contracts, the only sign was the agent being listed as unavailable, with a
  class-name error that did not name the cause.
- **Demonstration classes sat in the normative contract.** `Salutation` and `Greeting` exist only
  to show how an agent is written. They were nonetheless part of the fixed format that needs an
  ADR to change, as were the classes of every other agent.
- **The workbench does not need to know a class in advance.** The G0 linter is already
  structural (ADR-0008): it needs only `schema_class` and `grounded_on`. The input and payload
  checks need a class's schema, not its Python type. The viewer renders a payload from its JSON
  Schema (ADR-0016).

## Decision

1. **The core contract is what the workbench governs.** `data_director.yaml` keeps only:
   - the request and the envelope;
   - the outcome and Problem Details;
   - grounding (`GroundingRef`, the `Grounded` mixin) and evidence;
   - telemetry, delegation and the principal;
   - the conversation classes `Message`, `Reply` and `ConversationTurn`, which the conductor's
     conversation index reads (ADR-0012);
   - the enums those classes use, including `Derivation`, which the manifest's `derivations`
     name.

   Its `version` is the **contract version**. It is the fixed format: changing it still needs an
   ADR.
2. **Input and payload are open in the core.**
   - `InvocationRequest.input` is any object with a `schema_class`.
   - `Envelope.payload` is any object with a `schema_class` that mixes in `Grounded`.

   The core schema checks nothing else about them. The class schema checks the rest.
3. **An agent owns its input and payload classes.**
   - It declares them in its own LinkML file, `agents/<name>/schema/<name>.yaml`, which imports
     the core, uses its own `id` and prefix, and mixes `Grounded` into every payload class as
     before.
   - `dd-gen-schema` generates one self-contained JSON Schema per class. Its `$defs` are pruned to
     the definitions the class reaches. The generated file is committed in the agent's package,
     under `schema/generated/<Class>.schema.json`.
   - The agent's Pydantic model for a class stays in the agent's package.
     `ClassSchema.load(model, package)` reads the generated file and refuses a model whose field
     names differ from the schema's properties, so the two cannot drift silently.
4. **The card carries the schemas.** The extension's `params` (`describe(spec)`) gain two keys:
   - `contract_version`: the core version the agent was built against;
   - `schemas`: for each class it accepts or returns, `{digest, json_schema}`.

   The `digest` is the sha256 of the schema in the registered `dd-json-document-v1`
   canonicalisation. `spec_from_description` rejects a card, with `SpecError`, when:
   - a digest does not match its schema;
   - an accepted or returned class has no schema;
   - a payload schema does not require `schema_class` and `grounded_on`.
5. **Compatibility is checked, and reported as its own state.**
   - A card is compatible when its `contract_version` has the workbench's major version and, while
     the major version is 0, its minor version as well (the caret rule).
   - An incompatible card raises `ContractVersionError`, which names both versions. The registry
     records the agent as **incompatible**, not unavailable, and the CLI, `GET /agents` and the
     conductor's unknown-agent message show it that way.
6. **The conductor checks against the card's schemas.**
   - The input check passes when the input's `schema_class` is one the agent accepts and the input
     validates against that class's schema. Otherwise the outcome is `failed(input-not-accepted)`,
     as before.
   - The payload check passes when the payload's `schema_class` is the declared one and the
     payload validates against its schema. Otherwise the outcome is `failed(agent-error)`, as
     before.
   - The linter and the source check are unchanged.
7. **A stored run names the schemas it was checked against.** `Envelope` gains three fields:
   - `contract_version`;
   - `input_schema`: the digest of the accepted input class;
   - `payload_schema`: the digest of the payload class, when there is a payload.

   The run store keeps each schema once, addressed by content, under `schemas/<digest>.json`. The
   viewer fetches it from `GET /schema/sha256/<digest>`, so a stored run renders with the schema
   it was checked against, whatever the agent's card now says.
8. **A class name is resolved per agent.** Two agents may each define a class of the same name.
   Within a stored run, the digest identifies the class, not the name.
9. **The input hash covers the input as it was sent.** The workbench no longer parses an input
   into a Python model, so the `dd-input-json-v1` hash is taken over the validated document as
   received, with null values removed. Model defaults are no longer added before hashing.
10. **The workbench's test doubles define their own classes.** `workbench.testing` has a small
    test-only schema of its own. The harness tests therefore run against classes the workbench
    does not otherwise know, which is the case this decision exists for.

Rejected:

- **Keeping the classes central but in a separate file.** This makes the normative core smaller,
  but a new class would still mean an SDK release and a workbench redeploy.
- **Serving the schemas beside the card.** The card would carry only a URL and a digest for each
  class. That means more fetches and more ways to fail, for a card that stays small in practice.
  Embedding the schemas lets one fetch give everything the workbench checks.
- **Generating the class schemas from the Pydantic models.** LinkML remains the source, as it is
  for the core. The class carries slot URIs and descriptions a reader needs, and the core and the
  agents are written the same way.

## Dependencies introduced

None. `jsonschema` is already a runtime dependency of the SDK. LinkML stays on the
evaluation/CI path (ADR-0007): it is needed to regenerate a class schema, not to load one.

## Consequences

- Adding an agent, with classes of its own, touches nothing central: no SDK release, no
  workbench redeploy. `agents/README.md` is the recipe.
- A contract change that is not backwards compatible shows up as a named incompatibility, not as
  an agent listed unavailable for a reason that does not say why.
- The normative fixed format is smaller. Agent classes follow their agent's own version.
- Envelopes stored before this change have no `contract_version`, `input_schema` or
  `payload_schema`, and do not validate against the new core schema. The viewer shows their
  payloads as raw JSON. TODO: a migration for stored envelopes, as in ADR-0015 decision 5.
- Input hashes of the same logical input can differ from those recorded before this change,
  where a model default was added before hashing.
- SHACL shapes are generated for the core only. TODO: whether an agent's classes get shapes, and
  where a SHACL validation report (ADR-0005) would find them.
- The Process Run Crate does not yet name the schema digests. TODO.
- A future contributor must not reintroduce a closed registry of class names in the SDK or the
  workbench, add an agent's class to the core schema, or accept a card whose schemas do not match
  their digests, without revisiting this decision.
