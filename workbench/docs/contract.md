# The contract

The contract defines what an agent receives and what it returns. It is written in LinkML in
[`sdk/src/dd_sdk/schema/data_director.yaml`](../../sdk/src/dd_sdk/schema/data_director.yaml),
which the workbench and every agent share through the SDK. The JSON Schema and SHACL shapes in
`generated/` beside it are produced from that file and are never edited by hand.

## The request

An agent receives an `InvocationRequest`. Its main fields are:

| Field | Meaning |
|---|---|
| `invocation_id` | A UUIDv7 identifier for this run. UUIDv7 values sort by time ([ADR-0004](adr/0004-identifiers-and-problems.md)). |
| `agent_id` | The agent to run, for example `quality.reviewer`. |
| `input` | The input document. |
| `conversation_id` | Optional. The conversation this run is a turn of (see below). |
| `parent_invocation_id` | Set only by the conductor, on a run another agent delegated. A caller that sets it is refused. |

A request does not name an institutional profile. The deployment chooses one, and a request that
carries `policy_bundle_ref` fails validation ([ADR-0017](adr/0017-policy-is-the-deployments.md)).

The input is one of several input classes: `DatasetProfile`, `MetadataRecord`, `Claim`,
`Salutation` or `Message`. Its `schema_class` field says which one it is
([ADR-0007](adr/0007-polymorphic-contract.md)).

## The envelope

An agent's response is wrapped in an `Envelope`. Every envelope contains:

| Field | Meaning |
|---|---|
| `outcome` | What happened. Its `status` is one of the five values below. |
| `payload` | The agent's result. Present only when the status is `succeeded`. |
| `evidence` | The source records the result rests on. Each item carries a content hash and names the canonicalisation used to compute it ([ADR-0009](adr/0009-evidence-canonicalisations.md)). |
| `grounding_mode` | The grounding mode the agent declared ([`grounding.md`](grounding.md)). |
| `policy_bundle_ref`, `policy_digest` | The institutional profile the conductor applied, as `profile:<id>@v<version>`, and the SHA-256 of its file ([ADR-0017](adr/0017-policy-is-the-deployments.md)). |
| `telemetry` | The trace id, the model id, token counts, and energy fields. The energy fields are always empty for now (`not_measured`). |
| `requires_human_review` | Always `true`. The schema fixes it as a constant, so no envelope can claim otherwise. |
| `problem` | Details of the problem, when the status is `failed` or `suspended`. |
| `conversation_id`, `parent_invocation_id` | Copied from the request, when present. |
| `delegations` | For an agent in grounding mode `delegation`: each run it delegated, with that run's agent, version, status and envelope hash. Omitted when empty. |

The envelope also carries the invocation id, the agent id and version, and the completion time.
The [conductor](conductor.md) fills these in, not the agent.

## Outcomes

The Blueprint does not define a set of outcomes. This vocabulary is the workbench's own
proposal.

| Status | Meaning | Also carries |
|---|---|---|
| `succeeded` | The agent produced a result it stands behind. | A `payload`. |
| `abstained` | The agent declined to give a result. This is a valid answer, not an error. | A `reason_code`, such as `no_candidates_retrieved`. |
| `referred` | The agent passed the decision to a named person or role. | A `reason_code` and `referred_to`. |
| `failed` | The agent or the workbench could not complete the run. | A `problem` in RFC 9457 Problem Details format. |
| `suspended` | The run is waiting for something outside the workbench. | A `problem` that says what must happen before it can resume. |

## Payloads

Each payload class is specific to an agent: `Recommendations`, `QualityReview`, `FactCheck`,
`Greeting` or `Reply`. Every payload class includes the `Grounded` mixin, which adds a `grounded_on` list.
Each entry in that list names a source by its identifier and content hash. This is the only
place a payload may assert which sources it relies on. The grounding linter checks each entry.

## Conversations

A conversation is a sequence of runs that share a `conversation_id`. Each turn is one ordinary
run with its own envelope, so every check applies to it
([ADR-0012](adr/0012-conversation-and-orchestration.md)).

A conversational agent accepts `Message`: the text of this turn (`message_text`) and the
conversation so far (`history`, a list of `ConversationTurn`). Each agent turn in the history
names the agent, version and run it came from. The history is part of the input, so the input
hash covers everything the agent was shown. The agent replies with a `Reply` payload
(`reply_text`, `reply_derivation`).

The workbench keeps no separate conversation store. `GET /conversations` lists conversations and
`GET /conversations/{id}` returns one, read back from the stored runs: each turn with the runs it
delegated, the stored inputs, where an agent's version changed between turns, and the history to
send with the next `Message`.

An orchestrator hands work to other agents only through the workbench. Each hand-off is a run of
its own, stored with `parent_invocation_id`, and listed in the parent envelope's `delegations`.
[`conductor.md`](conductor.md) describes how.
