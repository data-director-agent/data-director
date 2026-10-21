# ADR-0018: Every invocation records the human it acted for, named by the authentication boundary

**Status:** Accepted
**Date:** 2026-09-25

## Context

Blueprint §5.4: "All agent actions must be executed on behalf of a named, identified human user,
and both the agent identity and the human it acts for must form part of the provenance record.
Where an agent acts on behalf of an institution rather than an individual, a designated
accountable human role must be defined and documented." P5 adds that human identifiers use
persistent identifiers such as ORCID.

The envelope already named the agent (`agent_id@agent_version`). Nothing named the human.
`InvocationRequest` and `Envelope` had no field for one, the Process Run Crate's `CreateAction`
had no `agent`, and the A2A and AG-UI endpoints do no authentication. A reference implementation
of the Blueprint therefore contradicted the text it implements.

There is no authentication yet. The same rule that governs policy (ADR-0017) applies here: the
caller does not state a fact the governance rests on. A field on the request would let any
caller that can reach the endpoint name anyone. The workbench should build the place where the
principal enters, fill it with an honest stub, and record the stub for what it is.

## Decision

- **The envelope names the human.** `Envelope` gains `acting_for`, a required `Principal`, with
  `slot_uri` `prov:actedOnBehalfOf`:
  - `principal_id` is an absolute IRI. An ORCID iD is preferred for a person; `mailto:` or a URN
    is accepted for staff without one and for roles.
  - `name` is the display name.
  - `principal_kind` is `person` or `accountable_role`. The second value covers §5.4's
    institutional case.
  - `assurance` says how the workbench came to know the principal.
  - The conductor fills `acting_for` on every path, including policy refusals and agent errors:
    a refused action was still attempted on someone's behalf.
- **The request cannot name one.** `InvocationRequest` has no such field. The model forbids
  extra keys, and every transport parses the request with the model, so a request that carries
  `acting_for` fails and nothing runs.
- **The authentication boundary names the principal.** `workbench.identity.Authenticator` maps
  the headers of a caller's HTTP request (or `None`, for the CLI and the evaluation) to a
  `Principal`. The A2A and AG-UI transports call it for each request and pass the result to
  `Conductor.invoke(request, *, acting_for=...)`.
- **The conductor holds no principal.** `acting_for` is a required argument of `invoke`, not a
  field of `Conductor`. The principal can differ per request once there is authentication, and
  an invocation without one is a type error, not an anonymous run.
- **A delegated child acts for its parent's principal.** The delegation grant (ADR-0012) carries
  the parent's principal, and `invoke_delegated` uses it. It ignores whoever sent the callback.
  On that path the caller is an agent, and the human is still the parent's. This is the one place
  where the caller and the principal differ.
- **The agent is not told.** `RunContext` and the A2A request to the agent are unchanged. No
  agent needs to know who it acts for to do its work, and personal data goes only where the
  record needs it.
- **The crate names both.** The Process Run Crate's `CreateAction` keeps the agent as its
  `instrument` and gains an `agent` that references a `Person` entity for the principal.
- **The stub asserts; it does not authenticate.** `OperatorAssertion` returns the one principal
  the operator configured, whoever calls:
  - It is configured by `DD_PRINCIPAL_ID`, `DD_PRINCIPAL_NAME` and `DD_PRINCIPAL_KIND`
    (default `person`), or by `--acting-for-id` and `--acting-for-name` on `workbench invoke`
    and `workbench serve`.
  - `assurance` has one value, `asserted`: nobody checked the identity. On a shared
    `workbench serve`, every run is recorded as the operator's, whoever started it. `asserted`
    exists so that no record claims otherwise.
- **An unset principal stops start-up.** If no principal is configured, `workbench invoke`,
  `workbench serve` and the R3 evaluation refuse to start (`IdentityError`). There is no
  anonymous fallback. Tests act for `workbench.testing.TEST_PRINCIPAL`, the ORCID documentation's
  example researcher, so the suite needs no configuration and no stored test run names a real
  person.

## Dependencies introduced

None.

## Consequences

- Every stored run, crate and viewer page names a human beside the agent.
- Real authentication (an OIDC bearer token resolved to an ORCID iD, for example) replaces
  `OperatorAssertion` behind `Authenticator`. It adds `authenticated` to `Assurance`, which is a
  schema change and needs its own ADR. Nothing else changes. TODO: that ADR, together with the
  HTTP status for a caller who cannot be authenticated.
- Envelopes stored before this change have no `acting_for` and do not validate against the new
  schema. The viewer shows no principal for them.
- Every call to `Conductor.invoke` names a principal. An agent's own tests pass
  `acting_for=TEST_PRINCIPAL`.
- TODO: once there is more than one principal, bind a `conversation_id` to the principal that
  started it, so that one person cannot continue another's conversation.
- TODO: Process Run Crate has no convention for an accountable role. Until one is settled, a role
  is recorded as a `Person` whose description states its kind.
- TODO: the generated request schema's root is open (`additionalProperties: true`), so a
  consumer that validates a request with the JSON Schema alone would accept `acting_for`. Only
  the model refuses it. Closing the root needs a change to `gen_schema.py`, and it affects
  ADR-0017's `policy_bundle_ref` in the same way.
- A future contributor must not read `acting_for` from a request body, set it in an agent, or
  give the conductor a default principal without revisiting this decision.
