# orchestrator.model

The model-backed Data Director orchestrator (#21, ADR-0012). It is the agent a researcher
converses with. It hands each request to the specialist agents through the harness, and writes
the reply with a model. It has `director.stub`'s specification: `Message` in, `Reply` out,
grounding mode `delegation`, with `reply_derivation` `model`.

| | |
|---|---|
| Agent id | `orchestrator.model` |
| Serve | `dd-orchestrator serve --port 8107` (`scripts/run-agents.sh`) |
| Model | Claude Fable 5.1 (`claude-fable-5-1`) by default, declared in `AgentSpec.models` |
| Status | Alpha (`0.1.0`) |

## How a turn runs

1. It reads the harness's manifest (`ctx.delegate.manifest()`, ADR-0012 decision 13). This is
   the list of agents the harness has registered, with each agent's input schemas. It offers the
   model one tool per input class of each agent, leaving out delegation agents, itself included.
   No list of agents is configured here, so an agent registered with the harness can be asked as
   soon as the profile permits it.
   Each tool's description also names the Blueprint requirements its agent `serves`. The system
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
| `DD_MODEL_ID` | `claude-fable-5-1` | The model it calls. |
| `DD_ORCHESTRATOR_EFFORT` | `high` | `low`, `medium`, `high`, `xhigh` or `max`. |
| `DD_ORCHESTRATOR_HISTORY` | `20` | Earlier turns sent to the model. `0` sends only the current message. |
| `DD_ORCHESTRATOR_MAX_DELEGATIONS` | `4` | Tool calls allowed in one turn. |

In development these go in `workbench/agents/orchestrator.env` (`workbench/agents/env.example`).
On a server they go in `/etc/data-director/agents/orchestrator.env`, with the key loaded as a
systemd credential (`deploy/README.md`).

## Choice of model

The orchestrator weighs each request before handing it on, so it defaults to the most capable
model available, Claude Fable 5.1. Two consequences follow:

- **Cost.** Fable 5.1 costs more per token than Claude Opus 5.5. The system prompt is cached
  across turns. `DD_MODEL_ID=claude-opus-5-5` is the cheaper alternative.
- **Data retention.** Fable 5.1 requires 30-day data retention by the provider. It is not
  available to an organisation under zero data retention, which gets an error on every turn.
  Check this against the institution's agreement before choosing it.

TODO: a profile rule that limits which models an agent may send a given class of data to (#40).

## Using it in the app

The app converses with the agent its profile names under `orchestrator`. The reference profile
names `director.stub`, so the app runs with no key. See `app/README.md`, "Choosing the
orchestrator".

## Tests

```bash
uv run pytest agents/orchestrator
```

`test_orchestrator.py` scripts the model, so it needs no key and no cassette.
`test_orchestrator_key_not_stored.py` replays two Messages API replies from a hand-written
cassette through the real client. It checks that the tool loop works and that the key reaches
no stored record.
