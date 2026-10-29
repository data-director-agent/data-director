# AI models

Most of Data Director runs without a model. Two agents can call a hosted AI model, and an operator
decides whether they do, which model they call, and whose key pays for it. This page covers those
decisions. [ADR-0026](../../adr/0026-model-credentials.md) records why the key is handled as it is.

## Which agents call a model

| Agent | Calls a model | Default model | Needs a key |
|---|---|---|---|
| `orchestrator.model` | Always. It writes the replies in the app's conversation. | `claude-sonnet-5-5` | Yes: it does not start without one. |
| `standards.advisor` | Only with `DD_STANDARDS_EXPLAINER=anthropic`. The default, `template`, is deterministic. | `claude-sonnet-5-5` | Only in that mode. |
| `hello.world`, `quality.reviewer`, `director.stub` | Never. | none | No. |

The reference profile names `director.stub` as the agent a researcher converses with, so a
default installation sends nothing to a model provider. It becomes model-backed when you choose,
below.

The only provider supported today is Anthropic, and its models are hosted. A manifest can also
declare a `local` model, but no agent in the repository uses one.

## What a provider receives

A model call sends the provider text from the user's session. It is worth stating to the data
steward, and to the institution's data protection officer, before turning either agent on.

- **The orchestrator** sends the model the latest turns of the conversation (20 by default,
  `DD_ORCHESTRATOR_HISTORY`), the description of each agent the profile permits, and the result of
  each agent it delegates to: that agent's status, statement and payload. What a user types into
  the conversation, and what a delegated agent returns about their data, reaches the provider.
- **The standards advisor's explainer** sends the dataset profile's title, description, keywords,
  themes and field names and types, and the candidate standards' names, descriptions and
  subjects. It never sends data values.

The provider's retention terms govern what happens next. Some models require the provider to keep
data, and an organisation under a zero-data-retention agreement gets an error on every turn from
such a model. Check the chosen model against the institution's agreement, not only against its
price.

Each agent declares the models it sends data to in its manifest (`models`: provider, model and
hosting). The app's **About** tab for the agent shows the list, or says that it calls no model.
This is what the deployment configured, declared by the agent itself; it is not proof of what
left the host. A profile rule that refuses an agent's models by class of data is not built yet
(#40).

## Choose a model

`DD_MODEL_ID`, in the agent's own settings file, selects the model. Both agents default to
`claude-sonnet-5-5`, which balances the quality of routing and wording against cost and latency.

| If you want | Do |
|---|---|
| Lower cost or faster replies | Set `DD_MODEL_ID` to a smaller model. It may route ambiguous requests less reliably. |
| More reliable routing | Set `DD_MODEL_ID` to a more capable model. |
| Fewer tokens per turn | Lower `DD_ORCHESTRATOR_HISTORY`. `0` sends only the current message. |
| Less or more reasoning per turn | Set `DD_ORCHESTRATOR_EFFORT`: `low`, `medium`, `high` (the default), `xhigh` or `max`. |
| A cap on tool calls a turn | Set `DD_ORCHESTRATOR_MAX_DELEGATIONS` (default 4). |

Each model call is recorded as a `chat` span with its token counts, in the stored run, so a
change of model or settings can be judged from the runs themselves. The full list of settings,
and what an unknown value does, is in the agents' readmes:
[orchestrator](../../../agents/orchestrator/README.md) and
[standards advisor](../../../agents/standards/src/dd_agent_standards/README.md).

A model identifier is the provider's, and the services do not check it at start-up: a mistyped
identifier shows as a failed run, not a failed start. After changing it, run one conversation turn
and read the agent's About tab.

## Supply a key

An agent that calls a model holds its key itself. The app, the harness and the conductor never
do, and the key never appears in a run, a trace, a manifest or an export.

| | Development | A server |
|---|---|---|
| Variable | `ANTHROPIC_API_KEY_FILE`, relative to `config/local/credentials/` | `ANTHROPIC_API_KEY_FILE` |
| Put it in | A file under `config/local/credentials/`, named in `config/local/agents/<name>.env`, which only that agent reads | A root-only file under `/etc/data-director/credentials/<name>/`, loaded as a systemd credential |

`ANTHROPIC_API_KEY` itself also works in an agent's own file. Set one variable or the other, never both. A command-line login on the host, such as
`ant auth login`, is never used. Never put a key in `app.env` or `agents.env`, in
`config/local/` or `/etc/data-director/`: every agent reads `agents.env`.

**Give each agent its own key.** One key can then be revoked without disturbing the other, and
the provider's usage reports show each agent separately. A spending limit is set on the provider's
side, for the Console workspace a key belongs to, not per key. An institution that wants a limit
per agent needs a workspace per agent.

## Turn on the standards advisor's explainer

1. Put the key where only root can read it. The unit loads it as a credential, so no other agent
   can read it, although every agent runs as `datadirector`.

   ```bash
   sudo install -d -m 0700 /etc/data-director/credentials/standards
   sudo install -m 0600 /dev/stdin /etc/data-director/credentials/standards/anthropic-api-key
   # paste the key, then Ctrl-D
   ```

2. Configure the advisor in `/etc/data-director/agents/standards.env`:

   ```bash
   DD_STANDARDS_EXPLAINER=anthropic
   # DD_MODEL_ID=<another model, if you do not want the default>
   ```

3. Restart it: `sudo systemctl restart data-director-agent@standards.service`.

The app runs no agent in its own process, so there is nothing to change in the app (ADR-0027).

## Turn on the model-backed orchestrator

`orchestrator.model` is not part of `data-director.target`, because it cannot start without a
key. Until the profile names it, the app converses with the rule-based `director.stub`.

1. Install its key as above, under `/etc/data-director/credentials/orchestrator/`
   (`anthropic-api-key`). Its optional settings go in `/etc/data-director/agents/orchestrator.env`.
2. Start it, and have it start with the rest:

   ```bash
   sudo systemctl enable --now data-director-agent@orchestrator.service
   ```

3. Add `8107` to `DD_WAIT_PORTS` in a drop-in for `data-director-app.service`, so the app waits
   for it.
4. In the deployment's profile, set `orchestrator: orchestrator.model` and raise `version`.
   List the agent under `agents` too. Then restart the app.

To go back, set `orchestrator: director.stub` in the profile, raise `version` and restart the
app. The orchestrator can then be stopped.

## Check it works

1. In the app, open the agent directory and the agent's About tab. It should name Anthropic and
   the model you chose.
2. Have a short conversation on the home page. If the named agent is not running, is not
   permitted by the profile, or does not delegate, the page says so; it does not fall back to
   another agent.
3. Read the agent's journal:

   ```bash
   journalctl -u data-director-agent@orchestrator -n 50
   ```

## Rotate or revoke a key

Replace the credential file and restart that agent's unit. No other component changes. To revoke
a key at once, delete it at the provider; the agent's runs then fail until the new key is in
place.

## Start-up errors

A configuration error stops the agent before any port opens, with one line in its journal that
names the variable or path and never the key. The unit is not restarted on that exit status
(`RestartPreventExitStatus=2`), so fix the setting and start it again.

| Message begins | Cause |
|---|---|
| `set ANTHROPIC_API_KEY or ANTHROPIC_API_KEY_FILE, not both` | Both variables are set. |
| `no model key` | Neither variable is set. |
| `ANTHROPIC_API_KEY_FILE=… is relative and CREDENTIALS_DIRECTORY is not set` | A relative path outside a systemd unit that loads the credential. |
| `ANTHROPIC_API_KEY_FILE: cannot read …` / `… is empty` | The file is missing, unreadable or empty. |
| `DD_ORCHESTRATOR_EFFORT=…`, or an unknown `DD_STANDARDS_*` value | An unrecognised setting. |

If the credential file is missing, systemd refuses to start the unit at all, since the unit
declares `LoadCredential=`. That is why the orchestrator's unit is enabled only once its key is
in place.
