# AI models

Most of Data Director runs without a model. Four agents can call a hosted AI model, and an operator
decides whether they do, which model they call, and whose key pays for it. This page covers those
decisions. [Policy and identity](../../specs/policy-and-identity.md) records why the key is handled as it is.

## Which agents call a model

| Agent | Calls a model | Default model | Needs a key |
|---|---|---|---|
| `orchestrator.model` | Always. It writes the replies in the app's conversation, and names each new conversation. | `claude-sonnet-5-5`, and `claude-haiku-5-5` for the name | Yes: it does not start without one. |
| `advisor.standards` | Only with `DD_STANDARDS_EXPLAINER=anthropic`. The default, `template`, is deterministic. | `claude-sonnet-5-5` | Only in that mode. |
| `advisor.policy` | Only with `DD_POLICY_EXPLAINER=anthropic`. The default is `template`. | `claude-sonnet-5-5` | Only in that mode. |
| `advisor.repository` | Only with `DD_REPOSITORY_EXPLAINER=anthropic`. The default is `template`. | `claude-sonnet-5-5` | Only in that mode. |
| Every other agent, such as `example.hello` and `orchestrator.stub` | Never. | none | No. |

A new `deployment.yaml` names `orchestrator: stub`, the agent a researcher converses with, so a
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
  On a conversation's first turn it also sends the first message, and nothing else, to a second
  model (`DD_TITLE_MODEL_ID`) that writes the title the app lists the conversation by.
  `DD_TITLE_MODEL=none` turns that call off, and the app then names the conversation by the
  start of its first message.
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
left the host. The profile's `hosted_models` says which classes of project content (`inventory`,
`documentation`) an agent with a hosted model may be given; the shipped profile allows both, so
that the documentation advisor can write a project's documents. Remove `documentation` to keep
metadata records, drafts and answers from the provider; the advisor's runs in a project then fail
with `project-content-withheld`. A rule for other data, such as a conversation's text, is not
built yet (#40).

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
[orchestrator](../../../agents/orchestrator-model/README.md) and
[standards advisor](../../../agents/advisor-standards/src/dd_agent_advisor_standards/README.md).

A model identifier is the provider's, and the services do not check it at start-up: a mistyped
identifier shows as a failed run, not a failed start. After changing it, run one conversation turn
and read the agent's page in the agent directory.

## Supply a key

An agent that calls a model holds its key itself. The app, the harness and the conductor never
do, and the key never appears in a run, a trace, a manifest or an export.

| | Development | A server |
|---|---|---|
| Variable | `ANTHROPIC_API_KEY_FILE`, relative to `config/local/credentials/` | `ANTHROPIC_API_KEY_FILE` |
| Put it in | A file under `config/local/credentials/`, named in `config/local/agents/<name>.env`, which only that agent reads (`scripts/dd.py setup` does this) | `sudo data-director secret set <name> anthropic-api-key`, which keeps it in a root-only file under `/etc/data-director/credentials/<name>/` and loads it as a systemd credential |

`ANTHROPIC_API_KEY` itself also works in an agent's own file. Set one variable or the other, never both. A command-line login on the host, such as
`ant auth login`, is never used. Never put a key in `app.env` or `agents.env`, in
`config/local/` or `/etc/data-director/`: every agent reads `agents.env`.

**Give each agent its own key.** One key can then be revoked without disturbing the other, and
the provider's usage reports show each agent separately. A spending limit is set on the provider's
side, for the Console workspace a key belongs to, not per key. An institution that wants a limit
per agent needs a workspace per agent.

## Turn on the standards advisor's explainer

1. Configure the advisor in `/etc/data-director/agents/advisor-standards.env`:

   ```bash
   DD_STANDARDS_EXPLAINER=anthropic
   # DD_MODEL_ID=<another model, if you do not want the default>
   ```

2. From your clone of the repository, give it its key:

   ```bash
   sudo data-director secret set advisor-standards anthropic-api-key
   # paste the key at the prompt, which does not show it, then Enter
   ```

   The command keeps the key in a file only root can read, has systemd hand it to this agent
   alone (every agent runs as `datadirector`), and restarts the advisor.

The policy and repository advisors are turned on the same way, with `DD_POLICY_EXPLAINER` or
`DD_REPOSITORY_EXPLAINER` and their own names (`advisor-policy`, `advisor-repository`). The app
runs no agent in its own process, so there is nothing to change in the app ([The app](../../specs/app.md)).

## Turn on the model-backed orchestrator

`deployment.yaml` names the orchestrator the home page converses with:
- on a server, `/etc/data-director/deployment.yaml`;
- in development, `config/local/deployment.yaml`.

`orchestrator: stub` is the rule-based `orchestrator.stub`, and `model` is `orchestrator.model`.
The model-backed orchestrator runs only while it is the orchestrator, because it cannot start
without a key.

1. Give it its key. Its optional settings go in
   `/etc/data-director/agents/orchestrator-model.env`.

   ```bash
   sudo data-director secret set orchestrator-model anthropic-api-key
   ```

2. Set `orchestrator: model` in `/etc/data-director/deployment.yaml`.
3. Apply it:

   ```bash
   sudo data-director apply
   ```

   This:
   - writes the profile with `orchestrator.model` and a raised `version`;
   - starts the agent with the rest;
   - makes the app wait for it;
   - restarts the services.

   It refuses if the key is not in place, and says which command gives it.

In development:
1. `uv run scripts/dd.py setup` asks for the key and offers to make this change.
2. `uv run scripts/dd.py start` applies `config/local/deployment.yaml` each time.

To go back, set `orchestrator: stub` and apply again. The model-backed orchestrator is then
stopped.

## Check it works

On a VM, `sudo data-director doctor` reports an agent turned on without its key, a unit that
is not running, and the orchestrator the app converses with ([Deploying to a VM](../../../deploy/README.md), "Day to day").
In development, `uv run scripts/dd.py doctor` does the same for `config/local/`.

1. In the app, open the agent directory and the agent's page. It should name Anthropic and
   the model you chose.
2. Have a short conversation on the home page. If the named agent is not running, is not
   permitted by the profile, or does not delegate, the page says so; it does not fall back to
   another agent.
3. Read the agent's journal:

   ```bash
   journalctl -u data-director-agent@orchestrator-model -n 50
   ```

## Rotate or revoke a key

Run `sudo data-director secret set <name> anthropic-api-key` again with the new key; it replaces the
file and restarts that agent. No other component changes. To revoke a key at once, delete it at
the provider; the agent's runs then fail until the new key is in place.
`sudo data-director secret remove <name> anthropic-api-key` takes a key away, and
`sudo data-director secret list` shows which agent has which secret, by size, never by value.

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
| `no model key` on the VM, after a key was put in place by hand | `data-director apply` (or `install.sh`) left the key out of the drop-in because it is not a non-empty regular file (a directory, say), and said so. `sudo data-director secret list` shows it as a `PROBLEM`. |
| `DD_ORCHESTRATOR_EFFORT=…`, `DD_TITLE_MODEL=…`, or an unknown `DD_STANDARDS_*` value | An unrecognised setting. |

If the credential file is missing, systemd refuses to start the unit at all, since the unit
declares `LoadCredential=`. That is why the orchestrator's unit is enabled only once its key is
in place.
