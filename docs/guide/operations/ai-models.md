# AI models

Data Director's advisors and its model-backed orchestrator can call an AI model, and most do by
default. An operator decides whether they do, which provider and model they call, and whose key
pays for it. This page covers those decisions.
[Policy and identity](../../specs/policy-and-identity.md) records why the key is handled as it is.

## Which agents call a model

Every advisor except three calls a model unless its setting says `template`. The orchestrator calls
one only while `deployment.yaml` names it.

| Agent | Setting | What the model does | Default model |
|---|---|---|---|
| `orchestrator.model` | `orchestrator: model` in `deployment.yaml` (off: `stub`) | Writes the replies in the app's conversation and routes to the advisors. Names each new conversation with a second, smaller model. | `claude-sonnet-5-5`, and `claude-haiku-5-5` for the name |
| `advisor.standards` | `DD_STANDARDS_EXPLAINER` | Explains each standard its ranking picked, notes doubts about a pick, and adds standards it finds by searching FAIRsharing, each checked by the agent. Its model must support tool calls. | `claude-sonnet-5-5` |
| `advisor.policy` | `DD_POLICY_ADVISOR` (older name `DD_POLICY_EXPLAINER`) | Reads the policy records found, searches Open Policy Finder, Crossref and FAIRsharing for more, and states each obligation with a quote from its record. Its model must support tool calls. | `claude-sonnet-5-5` |
| `advisor.repository` | `DD_REPOSITORY_EXPLAINER` | Writes the rationale for each repository its rules ranked. | `claude-sonnet-5-5` |
| `advisor.documentation` | `DD_DOCUMENTATION_WRITER` | Writes a README's prose and suggests answers to a draft's questions. | `claude-sonnet-5-5` |
| `advisor.dmp` | `DD_DMP_MATCHER` | Reads what its rules leave over, to pair renamed outputs and reconcile two names for one licence or repository, and reads an attached plan's commitments for the researcher to confirm. | `claude-sonnet-5-5` |
| `advisor.rights` | `DD_RIGHTS_INTERPRETER` | Reads a reuse wish in the researcher's own words as the licence table's reuse values, and tailors questions about third-party content or a mandate. It chooses only from its own table. | `claude-sonnet-5-5` |
| `advisor.fairness` | `DD_FAIRNESS_WRITER` | Tailors the retrofit recommendation for each check a published record does not meet, from the record's metadata as given. Whether a check is met stays by rule. | `claude-sonnet-5-5` |
| `advisor.ethics` | `DD_ETHICS_READER` | Reads a dataset's field names for sensitive data the keyword table missed. It can add flags and questions, never remove a keyword flag. | `claude-sonnet-5-5` |
| `advisor.metadata` | `DD_METADATA_SUGGESTER` | Suggests values beside a metadata record's questions. It never writes a value into the record. | `claude-sonnet-5-5` |
| `advisor.files` | `DD_FILES_SUMMARISER` | Writes a short summary beside the rules' findings about a file inventory. It cannot add, remove or change a finding. | `claude-sonnet-5-5` |
| `advisor.linking` | `DD_LINKING_SUMMARISER` | Writes a short summary beside the rules' findings about the identifiers given. It cannot add, remove or change a finding. | `claude-sonnet-5-5` |
| `advisor.quality` | `DD_QUALITY_SUMMARISER` | Writes a short summary beside the rules' completeness findings about a metadata record. It cannot add, remove or change a finding. | `claude-sonnet-5-5` |
| `example.hello`, `orchestrator.stub` | none | Never calls a model; neither is a sub-agent. | none |

For each advisor in the table, the setting is `model` unless you set it to `template`. `template`
needs no key, calls no model and sends nothing to a provider. Whichever you choose, the agent's rules
decide what is exact, and a model's reply is checked before it is used.

A model-backed agent does not start without a model key, unless it calls through the
[model broker](model-broker.md) or its endpoint is local. With no key, start-up stops with
`no model key … (DD_POLICY_ADVISOR is model by default: set DD_POLICY_ADVISOR=template to run
without a model)`, naming that advisor's own setting.

A default installation therefore sends a project's facts to a model provider as soon as each advisor
has a key. What each one sends is under [What a provider receives](#what-a-provider-receives). To send
nothing from an advisor, set its setting to `template` in the agent's own settings file, for example
`DD_STANDARDS_EXPLAINER=template` in `/etc/data-director/agents/advisor-standards.env`. The
`deployment.yaml` of a new installation names `orchestrator: stub`, the agent a researcher converses
with, so the orchestrator is the one model you turn on yourself,
[below](#turn-on-the-model-backed-orchestrator).

`anthropic`, the older value of these settings, still works and means `model` with the
Anthropic provider. The default model applies to Anthropic only; with any other provider,
`DD_MODEL_ID` must name one.

## Choose a provider

The orchestrator and the advisors above that call a model can call any provider below, set in the
agent's own settings file with no code change.

| `DD_MODEL_PROVIDER` | What it calls | Sends to | Key | Declared as |
|---|---|---|---|---|
| `anthropic` (default) | Claude, through the Messages API | Anthropic | `ANTHROPIC_API_KEY` | `anthropic`, `hosted` |
| `openai` | OpenAI's Chat Completions API | OpenAI | `OPENAI_API_KEY` | `openai`, `hosted` |
| `gemini` | Gemini, through Google's OpenAI-compatible endpoint | Google | `GEMINI_API_KEY` | `gemini`, `hosted` |
| `openai-compatible` | Any server that speaks the OpenAI Chat Completions API, at `DD_MODEL_BASE_URL`: Ollama, vLLM, llama.cpp, LM Studio, or a gateway such as [LiteLLM](../../../deploy/llm-gateway/README.md) | Whoever runs that server | `DD_MODEL_API_KEY`, which a local server may go without | the server's host and port, `local` or `hosted` |

Each key variable also has its `_FILE` form, as below. An agent holds only its own provider's key:
a key set for another provider stops it at start-up.

**Through the model broker.** Any provider above can be called through the
[model broker](model-broker.md), which then holds the key: set `DD_MODEL_BROKER_URL` and the
agent's broker credential in place of the key, and keep `DD_MODEL_PROVIDER` and `DD_MODEL_ID`. The
broker decides where an `openai-compatible` call goes, so `DD_MODEL_BASE_URL` is not set, and the
model is declared `openai-compatible`, `hosted`. If the broker sends the deployment's calls through
the [LiteLLM gateway](../../../deploy/llm-gateway/README.md#model-names), `DD_MODEL_ID` stays the
provider's own model ID: the gateway serves Claude models by name and OpenAI (`gpt-…`) and Gemini
(`gemini-…`) models by pattern.

**The orchestrator on another provider.** The orchestrator delegates by calling tools, so its model
must support tool calling (function calling) through the provider's API. Every provider above
accepts tools; whether a given model uses them well is another matter, and
[#833](https://github.com/data-director-agent/data-director/issues/833) records which provider and
model combinations have been checked. An endpoint that refuses tools fails each turn with its own
answer, which the run records as an agent error; a model that sends a tool call the orchestrator
cannot read is told so, and the call counts against the turn's limit of delegations.

- `DD_ORCHESTRATOR_EFFORT` is `low`, `medium`, `high`, `xhigh` or `max` for Claude (default
  `high`). Any other provider takes `low`, `medium` or `high`, sent as `reasoning_effort`; unset,
  it is sent none, and the provider's default applies. A model that does not reason may ignore it,
  and a local server may refuse it.
- The conversation title is written by `DD_TITLE_MODEL_ID` from the same provider: Claude Haiku
  5.5 by default with Anthropic, and the orchestrator's own model with any other.

**Local or hosted.** Whether a model is `local` is worked out from `DD_MODEL_BASE_URL`, not
configured. It is `local` only when the host is `localhost` or an IP address that is loopback
(`127.0.0.1`, `::1`), private (`10.x`, `172.16–31.x`, `192.168.x`, `fd…`) or link-local.
Anything else is `hosted`, including a host name on the institution's own network, because a
name is not looked up. A `hosted` model is subject to the profile's `hosted_models` rules below,
so a server on the institution's network that you want treated as local must be named by its IP
address. A model the agent reaches on loopback runs on the same host, and no project content
leaves it.

For example, an advisor on a local Ollama server:

```bash
DD_STANDARDS_EXPLAINER=model
DD_MODEL_PROVIDER=openai-compatible
DD_MODEL_BASE_URL=http://127.0.0.1:11434/v1
DD_MODEL_ID=llama3.3
```

or on OpenAI:

```bash
DD_STANDARDS_EXPLAINER=model
DD_MODEL_PROVIDER=openai
DD_MODEL_ID=<an OpenAI model>
```

with its key given by `sudo data-director secret set advisor-standards openai-api-key`.

The quality of an advisor's text depends on the model. Which provider and model
combinations have been evaluated is not yet recorded (#833); after changing provider, read a few
runs' output before relying on it.

## What a provider receives

A model call sends the provider text from the user's session. It is worth stating to the data
steward, and to the institution's data protection officer, before turning any of these agents on.

- **The orchestrator** sends the model the latest turns of the conversation (20 by default,
  `DD_ORCHESTRATOR_HISTORY`), the description of each agent the profile permits, and the result of
  each agent it delegates to: that agent's status, statement and payload. What a user types into
  the conversation, and what a delegated agent returns about their data, reaches the provider.
  On a conversation's first turn it also sends the first message, and nothing else, to a second
  model (`DD_TITLE_MODEL_ID`) that writes the title the app lists the conversation by.
  `DD_TITLE_MODEL=none` turns that call off, and the app then names the conversation by the
  start of its first message.
- **The standards advisor** sends the dataset profile's title, description, keywords, themes,
  media types and field names and types, and the FAIRsharing records found: their names, types,
  statuses, subjects and descriptions. FAIRsharing receives the words its model searches for. It
  never sends data values.
- **The policy advisor** sends the project's funders, journals, disciplines and kinds of data, and
  the policy records found. Open Policy Finder, Crossref and FAIRsharing receive the words its model
  searches for.
- **The documentation advisor** sends the facts a README is written from: each file's path, format
  and size, each table's field names, types and formats, the counts and total size, the metadata
  record's title, creators, funders, abstract, licence and publication year, and the chosen
  repository's name and licences. It never sends the data, a field's description, the researcher's
  answers or an earlier version.
- **The repository advisor** sends registry text and the researcher's stated needs, never research
  data.
- **The metadata advisor** sends the chosen repository's name and requirements and the inventory's
  structure: each file's path, media type and size, and its fields' names, types and formats. It
  never sends the data, a description a person wrote, the researchers' ORCID records, an answer or
  an earlier version.
- **The DMP advisor** sends only what its rules left over: the outputs missing from or unplanned in
  the plan, and the values that differ. Nothing it matched exactly is sent. It also sends an attached
  plan's text, to read its commitments for the researcher to confirm.
- **The rights advisor** sends the researcher's words for the reuse wanted (only when its rules did
  not understand them), a mandated licence, whether there is third-party content, and its licence
  table. It never sends whether the data are sensitive.
- **The fairness advisor** sends the published record's metadata as the researcher gave it:
  identifier, title, description, licence, keywords, creators and their identifiers, formats,
  related identifiers and access protocol.
- **The ethics advisor** sends the dataset's field names and whether it involves people. Field names
  of a sensitive dataset can themselves say something about the people in it, and the profile's
  `hosted_models` rule does not yet cover this input (TODO(#40)). Set `DD_ETHICS_READER=template`,
  or use a local model, if a hosted provider must not see them.
- **The files, linking and quality advisors** each send what their rules found beside the input
  they were given: each file's path, format and check, each identifier with what was found for it,
  or a metadata record with its completeness findings. The model writes one summary and cannot
  change a finding.

The provider's retention terms govern what happens next. Some models require the provider to keep
data, and an organisation under a zero-data-retention agreement gets an error on every turn from
such a model. Check the chosen model against the institution's agreement, not only against its
price.

Each agent declares the models it sends data to in its manifest (`models`: provider, model and
hosting). The app's **About** tab for the agent shows the list, or says that it calls no model.
This is what the deployment configured, declared by the agent itself; it is not proof of what
left the host. The profile's `hosted_models` says which classes of project content (`inventory`,
`documentation`, `researcher`, `decisions`) an agent with a hosted model may be given; the shipped
profile allows all but `researcher`, so that the documentation advisor can write a project's
documents. `decisions` are the facts people decided about a project, such as its funder or which
files go in; they hold no one's own words. Remove `decisions` to keep them from the provider; a
drafter's or orchestrator's runs in a project that holds any then fail with
`project-content-withheld`. Remove
`documentation` to keep metadata records, drafts and answers from the provider; the advisor's runs
in a project then fail with `project-content-withheld`. Add `researcher` to let such an agent be
given the facts researchers kept from their ORCID records, such as their affiliations and works;
without it those facts are left out of its input and the run goes ahead. A rule for other data, such as a conversation's text, is not
built yet (#40).

## Choose a model

`DD_MODEL_ID`, in the agent's own settings file, selects the model. With Anthropic, every model-backed agent defaults to
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
[standards advisor](../../../agents/advisor-standards/README.md).

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

Another provider's key works the same way under its own name: `openai-api-key`
(`OPENAI_API_KEY_FILE`), `gemini-api-key` (`GEMINI_API_KEY_FILE`) or `dd-model-api-key`
(`DD_MODEL_API_KEY_FILE`). `ANTHROPIC_API_KEY` itself also works in an agent's own file. Set one variable or the other, never both. A command-line login on the host, such as
`ant auth login`, is never used, nor anything a provider's library would read from the
environment for itself, such as `OPENAI_BASE_URL` or `OPENAI_CUSTOM_HEADERS`. Never put a key in `app.env` or `agents.env`, in
`config/local/` or `/etc/data-director/`: every agent reads `agents.env`.

**Give each agent its own key.** One key can then be revoked without disturbing the other, and
the provider's usage reports show each agent separately. A spending limit is set on the provider's
side, for the Console workspace a key belongs to, not per key. An institution that wants a limit
per agent needs a workspace per agent.

**People's own accounts.** Each person may use their own Anthropic, OpenAI, Gemini or
OpenAI-compatible account, so that their calls are paid for by them rather than by the
deployment, where the profile allows it and the [model broker](model-broker.md) runs
([A person's own model account](../../specs/model-accounts.md)). An agent is served only by the
provider it is configured for: a person's account with another provider counts as none for its
calls. The shipped profiles keep own accounts off, so every model call uses the keys described
here.

## Give the advisors their keys

Each advisor's model is on by default, so each needs a key, a broker credential or `template`.
`sudo data-director apply` refuses to turn on an advisor that has none of the three, and says which
command fixes it. `sudo data-director doctor` reports the same.

1. Optionally, configure an advisor in its own file, `/etc/data-director/agents/<name>.env`
   (for example `advisor-standards.env`):

   ```bash
   # DD_STANDARDS_MAX_LOOKUPS=<the most searches its model may make in one run; 4 by default>
   # DD_MODEL_ID=<another model, if you do not want the default>
   # DD_MODEL_PROVIDER=<another provider; see "Choose a provider">
   ```

   An advisor needs no setting to use its model. To run one without a model, set its switch from
   [the table](#which-agents-call-a-model) to `template` here, for example
   `DD_ETHICS_READER=template`.

2. Give each advisor that calls a model its own key, from your clone of the repository:

   ```bash
   sudo data-director secret set advisor-standards anthropic-api-key
   # paste the key at the prompt, which does not show it, then Enter
   ```

   The command keeps the key in a file only root can read, has systemd hand it to this agent
   alone (every agent runs as `datadirector`), and restarts the advisor. Repeat it for each of
   `advisor-standards`, `advisor-policy`, `advisor-repository`, `advisor-documentation`,
   `advisor-dmp`, `advisor-rights`, `advisor-fairness`, `advisor-ethics` and `advisor-metadata`
   that you have not set to `template`.

3. Apply and check:

   ```bash
   sudo data-director apply
   sudo data-director doctor
   ```

**Through the model broker instead.** If the [model broker](model-broker.md) pays for the calls, an
advisor holds a broker credential in place of a key. In each advisor's own file set
`DD_MODEL_BROKER_URL=http://127.0.0.1:8300`, leave out any provider key, and make the credentials
for every advisor that calls a model, in one command:

```bash
sudo deploy/broker-credentials.sh advisor-standards advisor-policy advisor-repository advisor-documentation advisor-dmp advisor-rights advisor-fairness advisor-ethics advisor-metadata orchestrator-model
```

Name every agent that calls through the broker each time (leave out `orchestrator-model` if you
run the stub orchestrator): a run replaces the whole list, and an agent left out loses its access.
Then restart the broker, as [its guide](model-broker.md#on-a-vm) says, and run
`sudo data-director apply`.

The policy advisor's `DD_POLICY_MAX_LOOKUPS` limits the searches its model may make in one run (6
by default). It also searches Jisc Open Policy Finder when given a free key:
`sudo data-director secret set advisor-policy open-policy-finder-api-key`. Without it, a run that
finds no policy for a funder or journal reports that it could not search, and
`sudo data-director doctor` notes the key as not set. The app runs no agent
in its own process, so there is nothing to change in the app ([The app](../../specs/app.md)).

## Turn on the model-backed orchestrator

`deployment.yaml` names the orchestrator the home page converses with:
- on a server, `/etc/data-director/deployment.yaml`;
- in development, `config/local/deployment.yaml`.

`orchestrator: stub` is the rule-based `orchestrator.stub`, and `model` is `orchestrator.model`.
The model-backed orchestrator runs only while it is the orchestrator, because it cannot start
without a model to call.

1. Give it its key. Its optional settings, such as another provider
   ([Choose a provider](#choose-a-provider)), go in
   `/etc/data-director/agents/orchestrator-model.env`.

   ```bash
   sudo data-director secret set orchestrator-model anthropic-api-key
   ```

2. Set `orchestrator: model` in `/etc/data-director/deployment.yaml` and apply it:

   ```bash
   sudo data-director edit
   ```

   It saves the file once it is valid and asks whether to apply it. Applying:
   - writes the profile with `orchestrator.model` and a raised `version`;
   - starts the agent with the rest;
   - makes the app wait for it;
   - restarts the services.

   It refuses if the key is not in place, and says which command gives it.

In development:
1. `uv run scripts/dd.py setup` asks for the key and offers to make this change.
2. `uv run scripts/dd.py start` applies `config/local/deployment.yaml` each time.

To go back, run `sudo data-director edit` again and set `orchestrator: stub`. The model-backed orchestrator is then
stopped.

## Check it works

On a VM, `sudo data-director doctor` reports an agent turned on without its key, a unit that
is not running, and the orchestrator the app converses with ([Deploying to a VM](../../../deploy/README.md), "Day to day").
In development, `uv run scripts/dd.py doctor` does the same for `config/local/`.

1. In the app, open the agent directory and the agent's page. It should name the provider and
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
| `no model key` | Neither variable is set. For an advisor left on its default, the message ends with the setting that runs it without a model (`DD_…=template`). |
| `ANTHROPIC_API_KEY_FILE=… is relative and CREDENTIALS_DIRECTORY is not set` | A relative path outside a systemd unit that loads the credential. |
| `ANTHROPIC_API_KEY_FILE: cannot read …` / `… is empty` | The file is missing, unreadable or empty. |
| `no model key` on the VM, after a key was put in place by hand | `data-director apply` (or `install.sh`) left the key out of the drop-in because it is not a non-empty regular file (a directory, say), and said so. `sudo data-director secret list` shows it as a `PROBLEM`. |
| `DD_TITLE_MODEL=…`, or an unknown `DD_STANDARDS_*` value | An unrecognised setting. |
| `DD_…=anthropic but DD_MODEL_PROVIDER is not` | The older value names Anthropic; set `model` to use another provider. |
| `DD_MODEL_PROVIDER=…: expected one of …` | An unknown provider. |
| `DD_MODEL_ID is required with DD_MODEL_PROVIDER=…` | Only Anthropic has a default model. |
| `… is set but DD_MODEL_PROVIDER is …` | A key for a provider other than the configured one. Remove it. |
| `DD_MODEL_BASE_URL is required …`, `… is for DD_MODEL_PROVIDER=openai-compatible only`, `… is not an http or https URL` | The base URL is missing, set for a named provider, or malformed. |
| `no model key: … only a local DD_MODEL_BASE_URL may have none` | An `openai-compatible` endpoint that is not local, with no `DD_MODEL_API_KEY`. |
| `DD_ORCHESTRATOR_EFFORT=…: DD_MODEL_PROVIDER=… accepts …` | An effort the provider does not name, such as `max` for a provider other than Anthropic. |
| `set DD_MODEL_BROKER_URL or ANTHROPIC_API_KEY, not both` (or another provider's key) | The agent calls through the [model broker](model-broker.md), which holds the key, so it may hold none itself. |
| `set DD_MODEL_BROKER_URL or DD_MODEL_BASE_URL, not both` | Through the broker, the broker decides where an `openai-compatible` call goes. |
| `no model broker credential` | `DD_MODEL_BROKER_URL` is set without `DD_MODEL_BROKER_CREDENTIAL` or `DD_MODEL_BROKER_CREDENTIAL_FILE`. |
| A run fails with problem `model-broker-bypassed` | The profile lets people's own accounts pay, and the agent's entry in `app/config/agents.yaml` does not say `model_broker: true`. Set the agent to call through the [model broker](model-broker.md#the-agents-calling-through-the-broker), then mark it. |

If the credential file is missing, systemd refuses to start the unit at all, since the unit
declares `LoadCredential=`. That is why the orchestrator's unit is enabled only once its key is
in place.
