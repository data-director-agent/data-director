# orchestrator.stub

**Rule-based alpha** (`0.1.1-alpha.4`): the Data Director persona, a model-free stand-in for the
orchestrator a researcher converses with ([Orchestration](../../docs/specs/orchestration.md)). It
calls no model, routes by the rules in `routing.yaml`. A deployment's profile names which orchestrator the app
opens on.
`orchestrator.model` ([`../orchestrator-model/`](../orchestrator-model/)) is the model-backed one
with the same specification.

| Part | In this agent |
|---|---|
| Input | `Message`: `message_text`, `history`, `reply_answers`, and the `project_*` fields the conductor fills from the conversation's project. A caller never sets those. |
| Payload | `Reply`: `reply_text`, `reply_derivation` (always `template`), `reply_questions` and `grounded_on`. |
| Grounding mode | `delegation`: the reply cites the input and each child envelope it relays. |
| Steps served | None. An orchestrator places other agents in the process flow; it does not serve a step itself. |
| Outcomes | `succeeded` once it has replied, whatever a child's outcome was; `abstained` with `OUTSIDE_AGENT_SCOPE` or `CAPABILITY_NOT_IMPLEMENTED`. |

## How it decides

It reads the current message, and uses `Message.history` only to tell a first turn. In this order:

1. **A step chosen** from the "what next?" question (`reply_answers`, key `next-step`, value a step
   id). It sends the inputs `routing.yaml` gives for that step to the agent whose manifest entry
   serves the step and accepts that class, through the conductor. A step with agents but no
   template is answered with how to ask them directly (`@<agent_id> <what you need>`); a step with
   no agent is named as one no agent can help with yet; an out-of-scope step is named as such.
2. **An entry point chosen** (`reply_answers`, key `entry`, value 1, 2 or 3). It lists every step
   from that entry's phase to the last.
3. **A routing rule.** The first rule whose pattern matches the message, or the rule of the agent
   named by a leading `@<agent_id>`, delegates a fixed input document to that agent. The rules
   cover `example.hello`, `advisor.standards`, `advisor.documentation` and `advisor.quality`. A
   new agent is routable only once a rule names it. The reply names the agent and version, the
   child's outcome and statement, and the payload field the rule relays, if any.
4. **No rule matched.** A message that names an entry point (`entries` in `routing.yaml`) is
   answered with the steps from it. A message that asks what to do next, or a first turn in a
   project whose entry point is known, gets the project's steps with each marked done, started or
   skipped from `Message.project_progress`, and the suggested next step offered with a few open
   ones as a choice question. A first turn with neither asks which entry point applies, as a
   choice question. Later turns abstain with `OUTSIDE_AGENT_SCOPE` and list what it can route.

Each step in a list names the agents the manifest says serve it, by persona title and id, and says
"no agent can help with this yet" where none does. A reply names no requirement ID. Nothing is a
gate: any step may be chosen, and any rule still routes. The work and every decision stay with the
researcher.

The agent learns what it may invoke from the harness's manifest, read through its grant. A child
the profile does not enable is refused by the policy gate and recorded as such. Delegation is one
level deep.

## Configuration

`routing.yaml` holds the rules, entry-point phrases, the "what next" pattern and the step inputs.
It has no `DD_ORCHESTRATOR_STUB_*` environment variables; which agents it may delegate to comes from
the deployment's institutional profile.

## What it does not do

- It calls no model, so it understands only what the patterns in `routing.yaml` match. A request in
  other words reaches no agent, and a refused or unmatched message does not become a rule.
- It routes to four agents. Any other agent is reached only with `@<agent_id>` where a rule names
  it, or by choosing a step that has a template.
- It does not fill an agent's input from the researcher's words beyond the patterns' groups; for
  other steps it points the researcher to the agent.
- It names no project, records no entry point and suggests no setup answers; those are the model
  orchestrator's tools ([Orchestration](../../docs/specs/orchestration.md), invariants 8 and 18).
- Started without a conductor (for example `workbench invoke`), it has no way to delegate and
  abstains with `CAPABILITY_NOT_IMPLEMENTED`.

## Run it

```sh
uv run dd-orchestrator-stub serve --port 8106
uv run workbench invoke --agent orchestrator.stub --input workbench/samples/director.message.json
uv run pytest agents/orchestrator-stub
```

The sample has no conductor behind it, so the invoke shows the abstention above; use the app, or
`dd_harness.testing`'s in-process conductor, to see delegation.
