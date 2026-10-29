# orchestrator.model

The model-backed Data Director orchestrator (#21, ADR-0012). It is the agent a researcher
converses with. It hands each request to the specialist agents through the harness, and writes
the reply with a model. It has `orchestrator.stub`'s specification: `Message` in, `Reply` out,
grounding mode `delegation`, with `reply_derivation` `model`.

| | |
|---|---|
| Agent id | `orchestrator.model` |
| Serve | `dd-orchestrator-model serve --port 8107` (`scripts/run-agents.sh`) |
| Model | `claude-sonnet-5-5` at the time of writing, declared in `AgentSpec.models` |
| Status | Alpha (`0.1.0`) |

## How a turn runs

1. It reads the harness's manifest (`ctx.delegate.manifest()`, ADR-0012 decision 13). This is
   the list of agents the harness has registered, with each agent's input schemas. It offers the
   model one tool per input class of each agent, leaving out delegation agents, itself included.
   No list of agents is configured here, so an agent registered with the harness can be asked as
   soon as the profile permits it.
   Each tool's description also names the steps its agent `serves` and the requirements those
   steps apply (ADR-0032). The system
   prompt carries the Blueprint's process flow (`dd_sdk.process_flow`): on a first turn that
   does not say, the model asks which of the three entry points applies, then takes the
   researcher through the steps from there, naming any step no tool serves with its requirement
   (ADR-0028).
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

The run succeeds once the model has replied, whatever its children's outcomes were (ADR-0012
decision 14). It fails, as `failed(agent-error)`, only when it cannot reply: the Messages API
failed, or the model declined the request after the server-side fallback
(`fallbacks: "default"`). Its reply is never replaced by a template.

Each model call is a `chat` span with its tokens. Cached input counts as input read.

## Settings

Read at start-up by `factory.build`. A bad value stops the service with one line (ADR-0026).

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` / `ANTHROPIC_API_KEY_FILE` | none: required | The model key, which only this process holds. |
| `DD_MODEL_ID` | `claude-sonnet-5-5` | The model it calls. |
| `DD_ORCHESTRATOR_EFFORT` | `high` | `low`, `medium`, `high`, `xhigh` or `max`. |
| `DD_ORCHESTRATOR_HISTORY` | `20` | Earlier turns sent to the model. `0` sends only the current message. |
| `DD_ORCHESTRATOR_MAX_DELEGATIONS` | `4` | Tool calls allowed in one turn. |

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

The app converses with the agent its profile names under `orchestrator`. The reference profile
names `orchestrator.stub`, so the app runs with no key. See `app/README.md`, "Choosing the
orchestrator".

## Tests

```bash
uv run pytest agents/orchestrator-model
```

`test_orchestrator.py` scripts the model, so it needs no key and no cassette.
`test_orchestrator_key_not_stored.py` replays two Messages API replies from a hand-written
cassette through the real client. It checks that the tool loop works and that the key reaches
no stored record.
