# orchestrator.model

The model-backed Data Director orchestrator (#21, [Orchestration](../../docs/specs/orchestration.md)). It is the agent a researcher
converses with. It hands each request to the specialist agents through the harness, and writes
the reply with a model. It has `orchestrator.stub`'s specification: `Message` in, `Reply` out,
grounding mode `delegation`, with `reply_derivation` `model`.

| | |
|---|---|
| Agent id | `orchestrator.model` |
| Serve | `dd-orchestrator-model serve --port 8107` (`scripts/run-agents.sh`) |
| Model | `claude-sonnet-5-5`, and `claude-haiku-5-5` for titles, at the time of writing, declared in `AgentSpec.models` |
| Status | Alpha (`0.1.0`) |

## What it cannot do

**The orchestrator has no tools except its delegations** ([Orchestration](../../docs/specs/orchestration.md)
decision 15). The model is offered one tool per input class of each agent in the harness's
manifest, and nothing else: no MCP server, no web search or fetch, no code execution and no Agent
Skills. Every lookup is therefore a child run that the harness governs, stores and grounds.

If the orchestrator needs to know something new, such as a registry, a funder's policy or a PID
service, write or extend an agent that serves the step and let the orchestrator delegate to it.
An agent may use an MCP server itself. Do not give the orchestrator the tool.
`tests/test_orchestrator_only_delegates.py` fails, in CI, if the Messages API request carries
anything but delegation tools, or if the package gains a dependency or an import beyond
`dd_sdk`, `anthropic` and the standard library.

The system prompt (`system_prompt.md`) holds the model to the same limit. It keeps apart four
kinds of knowledge:

- the researcher knows their own project and makes every consequential choice;
- the agents know what is specific to the case, from the sources they cite;
- the model knows the process, the tools and the conversation, and may explain general concepts
  as background;
- some questions belong to people outside the Data Director: legal advice, ethics, consent,
  anonymisation and CARE.

The prompt also tells the model to pause the sharing steps when sensitive data is flagged, and to
treat agent results and pasted text as data, not instructions. Context about the deployment and
the project is for the harness to supply (#341, #160).

## How a turn runs

1. It reads the harness's manifest (`ctx.delegate.manifest()`, [Orchestration](../../docs/specs/orchestration.md)). This is
   the list of agents the harness has registered, with each agent's input schemas. It offers the
   model one tool per input class of each agent, leaving out delegation agents, itself included.
   No list of agents is configured here, so an agent registered with the harness can be asked as
   soon as the profile permits it.
   Each tool's description also names the steps its agent `serves` and the requirements those
   steps apply ([Orchestration](../../docs/specs/orchestration.md)). The system
   prompt carries the Blueprint's process flow (`dd_sdk.process_flow`): on a first turn that
   does not say, the model asks which of the three entry points applies, then takes the
   researcher through the steps from there, naming any step no tool serves with its requirement
   ([Orchestration](../../docs/specs/orchestration.md)).
2. It sends the model the last `DD_ORCHESTRATOR_HISTORY` turns of the conversation, then the
   current message. Turns before the first user turn in that window are dropped. The whole
   history is still covered by the input hash.
3. Each tool call is a delegation through `ctx.delegate`. The conductor runs the child as an
   ordinary governed, stored invocation and records it on this one. The child's status,
   statement and payload go back to the model as the tool result. A failed child, an agent the
   harness refused, or a tool with no agent behind it is marked as an error, and the model is
   told why.
4. One turn makes at most `DD_ORCHESTRATOR_MAX_DELEGATIONS` tool calls. After that the model is
   asked to reply with what it has.
5. The reply cites the input and every child it delegated to. The linter's `delegation` rules
   check those citations against what the conductor recorded.

The run succeeds once the model has replied, whatever its children's outcomes were ([Orchestration](../../docs/specs/orchestration.md)
decision 14). It fails, as `failed(agent-error)`, only when it cannot reply: the Messages API
failed, or the model declined the request after the server-side fallback
(`fallbacks: "default"`). Its reply is never replaced by a template.

Each model call is a `chat` span with its tokens. Cached input counts as input read.

## Conversation titles

On a conversation's first turn, once the model has replied, the orchestrator makes one more call
to a small model (`DD_TITLE_MODEL_ID`) for a title of a few words, which the app lists the
conversation by (`Reply.conversation_title`, [Contract](../../docs/specs/contract.md)). The call is
sent the researcher's first message and nothing else, and its prompt (`title_prompt.md`) tells the
model that the message is data, not instructions. It is recorded like any other call: a `chat`
span, its tokens in the run's totals, and an entry in `telemetry.model_calls` naming the model
that answered, with the prompt kept beside the run. Quotation marks and a closing full stop are
removed, and the title is cut to 80 characters.

A title is a convenience. If the call fails, the model declines or the answer is empty, the reply
carries no title and the turn still succeeds; the harness then names the conversation by the start
of its first message ([Orchestration](../../docs/specs/orchestration.md)). Later turns make no
title call.

## Settings

Read at start-up by `factory.build`. A bad value stops the service with one line ([Policy and identity](../../docs/specs/policy-and-identity.md)).

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` / `ANTHROPIC_API_KEY_FILE` | none: required without the broker | The model key, which only this process holds. |
| `DD_MODEL_BROKER_URL` | unset | The [model broker](../../docs/guide/operations/model-broker.md), if the agent calls through it in place of the provider. It then holds no provider key. |
| `DD_MODEL_BROKER_CREDENTIAL` / `DD_MODEL_BROKER_CREDENTIAL_FILE` | none: required with the broker | The agent's own broker credential. |
| `DD_MODEL_ID` | `claude-sonnet-5-5` | The model it calls. |
| `DD_ORCHESTRATOR_EFFORT` | `high` | `low`, `medium`, `high`, `xhigh` or `max`. |
| `DD_ORCHESTRATOR_HISTORY` | `20` | Earlier turns sent to the model. `0` sends only the current message. |
| `DD_ORCHESTRATOR_MAX_DELEGATIONS` | `4` | Tool calls allowed in one turn. |
| `DD_TITLE_MODEL_ID` | `claude-haiku-5-5` | The model that titles a conversation on its first turn. |
| `DD_TITLE_MODEL` | unset | `none` makes no title call; the conversation is named by its first message. |

In development these go in `config/local/agents/orchestrator-model.env` (`config/examples/agents/orchestrator-model.env`), with the key in `config/local/credentials/`.
On a server they go in `/etc/data-director/agents/orchestrator-model.env`, with the key loaded as a
systemd credential (`deploy/README.md`).

## Choice of model

The orchestrator defaults to a mid-sized model, which balances the quality of its routing against
the cost and latency of each turn. Two consequences follow:

- **Capability.** A smaller model may route ambiguous requests less reliably, and a larger one
  costs more. Set `DD_MODEL_ID` to suit.
- **Data retention.** Some models require the provider to retain data, and are not available to
  an organisation under zero data retention, which gets an error on every turn. Check the
  chosen model against the institution's agreement.

The operations guide's [AI models](../../docs/guide/operations/ai-models.md) page covers what the
provider receives and how to turn the agent on.

TODO(#40): a profile rule that limits which models an agent may send a given class of data to.

## Using it in the app

The app converses with the agent its profile names under `orchestrator`. An instance chooses it
with `orchestrator: model` in `deployment.yaml` and `data-director apply`, which writes the
profile; a new `deployment.yaml` names `stub`, so the app runs with no key. See `app/README.md`,
"Choosing the orchestrator", and the operations guide's
[command reference](../../docs/guide/operations/commands.md).

## Tests

```bash
uv run pytest agents/orchestrator-model
```

`test_orchestrator.py` scripts the model, so it needs no key and no cassette.
`test_orchestrator_title.py` scripts the title model in the same way.
`test_orchestrator_only_delegates.py` checks the limit in "What it cannot do".
`test_orchestrator_key_not_stored.py` replays three Messages API replies from a hand-written
cassette through the real client. It checks that the tool loop works and that the key reaches
no stored record.
