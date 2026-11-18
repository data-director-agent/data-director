# The model broker

The model broker lets a person's own AI provider account pay for model calls in place of the
deployment's. It is a separate service that holds each person's key, sealed, and makes model calls
for agents. No agent, and neither the app nor the harness, ever holds a person's key. The design
is in [A person's own model account](../../specs/model-accounts.md).

!!! warning "Alpha, and off by default"
    The shipped profiles set `model_accounts: {own: off}`, so every grant says the deployment pays
    and every call is paid for by the deployment, as before. Turning the broker on with that
    profile only moves the deployment's key from the agents to the broker. People's own accounts
    pay only once the steward turns them on in the profile
    ([Institutional profiles](../../../workbench/profiles/README.md)).

## What it does

For each call an agent makes, the broker:

- checks the agent's own broker credential and the model grant the harness signed for that run;
- refuses a model the grant does not allow;
- pays for the call from the person's own account, or from the deployment's, as the grant says,
  and reports which on its answer;
- counts tokens per person and day, by a pseudonym, never by name or ORCID iD;
- keeps no prompt and no reply;
- reduces every refusal and provider error to a reason code, so a provider's error text, which
  might quote a key, never leaves it.

A rejected or rate-limited own key ends the run with `model-account-rejected` or
`model-account-limit`. A person with no account, when the profile requires one or lets the
deployment pay for no one, ends it with `model-account-missing`. None of these is ever quietly
paid for by the deployment instead.

## On a VM

`deploy/install.sh` prepares the broker but does not start it:

- the user `data-director-broker`, which no other service shares;
- `/etc/data-director/credentials/model-broker/`, readable by root alone;
- `/etc/data-director/model-broker.env`, for its settings;
- the unit `data-director-model-broker.service`, which keeps its store in
  `/var/lib/data-director-model-broker/`, readable by the broker's user alone.

To turn it on, write its three secrets as root:

```bash
cd /etc/data-director/credentials/model-broker
```

```bash
openssl rand -base64 32 > key-encryption-key
```

```bash
openssl ecparam -name prime256v1 -genkey -noout | openssl pkcs8 -topk8 -nocrypt > subject-key
```

The third, `agent-credentials`, is how the broker recognises an agent. Each agent that may call
through the broker has a *broker credential*, a random password only that agent holds. The broker
keeps only its SHA-256 digest, a fingerprint it can compare but not reverse, so a copy of the file
does not reveal any agent's credential. The file maps each agent's id (its name with a dot,
`advisor.standards`) to that digest:

```json
{"advisor.standards": "<sha256 hex of the agent's broker credential>"}
```

One script does it for every agent you name. Run it as root from the clone, naming each
model-backed agent as in `app/config/agents.yaml`:

```bash
sudo deploy/broker-credentials.sh advisor-documentation advisor-policy advisor-repository advisor-standards orchestrator-model
```

For each agent it makes a credential, stores it as the agent's `dd-model-broker-credential` secret
(restarting the agent if it is running; see [The agents](#the-agents-calling-through-the-broker)),
and writes the credential's digest into `agent-credentials`, readable by root alone. Then restart
the broker so it reads the file:

```bash
sudo systemctl restart data-director-model-broker.service
```

A run replaces the whole file and makes new credentials for the agents it names, so name every
agent that calls through the broker each time, and an agent left out loses its access.

??? note "By hand"
    Make a credential with `openssl rand -hex 32` and its digest with `printf %s "$credential" |
    sha256sum`. Write the digest into `agent-credentials`, and give the agent the credential
    itself as its `dd-model-broker-credential` secret (below). The agent holds the credential and
    the broker holds only the digest.

`install.sh` sets `DD_BROKER_HARNESS_JWKS_URL` in `model-broker.env` to the harness's published
keys (below) on the app's loopback address, and leaves a value you set there alone. Start the
broker:

```bash
sudo systemctl enable --now data-director-model-broker.service
```

The broker listens on `127.0.0.1:8300`. Like the agents' ports, it must not be reachable from
beyond the host or a private network (TODO(#17)).

If it fails with `status=203/EXEC` and `Permission denied`, the broker's user cannot reach the
release's Python: the VM was installed before uv's Python moved to `/opt/data-director/python/`.
Run `install.sh` again, which rebuilds the live release against it
([deploy/README.md](../../../deploy/README.md#the-model-broker)). `sudo data-director doctor`
reports this.

### The harness: signing grants

The process that runs the conductor, normally the app, signs a model grant for each invocation of
an agent whose card declares models. It needs three secrets, each as `NAME` in development or as
`NAME_FILE`, a systemd credential, in deployment:

- `DD_MODEL_GRANT_SIGNING_KEY`: the harness's private signing key, for example
  `openssl ecparam -name prime256v1 -genkey -noout | openssl pkcs8 -topk8 -nocrypt`;
- `DD_MODEL_BROKER_SUBJECT_KEY`: the broker's public subject key,
  `openssl ec -in subject-key -pubout`;
- `DD_PSEUDONYM_SECRET`: at least 32 random bytes, such as `openssl rand -hex 32`. Changing it
  changes every person's pseudonym, so the broker no longer finds their enrolled keys.

On a VM, write each as a file in `/etc/data-director/credentials/app/`, readable by root alone,
under the names `model-grant-signing-key`, `model-broker-subject-key` and `pseudonym-secret`:

```bash
cd /etc/data-director/credentials/app
```

```bash
(umask 077 && openssl ecparam -name prime256v1 -genkey -noout | openssl pkcs8 -topk8 -nocrypt > model-grant-signing-key)
```

```bash
(umask 077 && openssl ec -in ../model-broker/subject-key -pubout > model-broker-subject-key)
```

```bash
(umask 077 && openssl rand -hex 32 > pseudonym-secret)
```

Then run `sudo data-director apply`. It writes the app's drop-in,
`data-director-app.service.d/model-grants.conf`, which loads those of the three files that exist
as systemd credentials and sets the matching `_FILE` variables (`deploy/credentials.sh`). In
development, set the three variables themselves in `config/local/app.env`.

With all three set, the app publishes the public half of the signing key at
`/.well-known/jwks.json`. Point the broker's `DD_BROKER_HARNESS_JWKS_URL` there, or copy that
JSON to a file and name it with `DD_BROKER_HARNESS_JWKS_FILE`. With none set, no grant is minted.
With only some set, the app stops at start-up.

### The profile: turning own accounts on

The steward decides, in the profile's `model_accounts`, whether people may or must use their own
account and whether the deployment pays for someone who has none
([Institutional profiles](../../../workbench/profiles/README.md)). A profile that turns own
accounts on stops the app at start-up unless the three secrets above are set, since without grants
nothing would carry that decision to the broker.

On a VM, write `model_accounts` in `/etc/data-director/deployment.yaml` (see
[`config/examples/deployment.yaml`](../../../config/examples/deployment.yaml)) and run
`sudo data-director apply`, which copies it into the generated profile and raises the profile's
`version`. Do not edit the generated `profile.yaml`: `apply` rewrites it.

Every model-backed agent must then call through the broker (below).

A steward can also map a model an agent declares to one that a person's own provider serves, in
the profile's model map. A mapped call is paid for only by the person's own account, never by the
deployment's: without one it is refused, `model-account-missing`. An agent that calls through
the broker asks it, once per run, which provider and model serve each model it declares, so a
person whose account is with the mapped provider is served by the mapped model. The run records
both the model that served each call and the one the agent declared.

### The Settings page: adding one's own key

A person adds, replaces or removes their key on the Settings page. The browser sends the key to the
broker, not to the app, on the app's own site: NGINX passes `/broker/enrolment/` on to the broker
on `127.0.0.1:8300`, and nothing else of the broker's
([`deploy/nginx/data-director.conf`](../../../deploy/nginx/data-director.conf)). To turn the page's
account section on, turn own accounts on in the profile, set the three harness secrets above and,
in `/etc/data-director/app.env`:

```bash
DD_APP_MODEL_BROKER_URL=/broker
```

Each request from the page carries a ticket the app issued for the person signed in, good for one
request and two minutes. The broker checks a new key with one free call to the provider, listing
one model, and stores it only if the provider accepts it.

### The agents: calling through the broker

An agent calls through the broker when its environment sets:

- `DD_MODEL_BROKER_URL`, such as `http://127.0.0.1:8300`;
- `DD_MODEL_BROKER_CREDENTIAL_FILE`, a systemd credential holding the agent's broker credential
  (`DD_MODEL_BROKER_CREDENTIAL` in development).

On a VM, `DD_MODEL_BROKER_URL` goes in the agent's `/etc/data-director/agents/<agent>.env`. Give it
the credential as a secret named `dd-model-broker-credential`. `deploy/broker-credentials.sh`
(above) does this for you; to do it by hand for one agent, whose credential you made yourself:

```bash
sudo data-director secret set advisor-standards dd-model-broker-credential
```

The secret's name becomes the variable, so only that name gives `DD_MODEL_BROKER_CREDENTIAL_FILE`.
A secret named `model-broker-credential` would give `MODEL_BROKER_CREDENTIAL_FILE`, which no agent
reads, and the agent would refuse to start without its credential.

Then run `sudo data-director apply` (`dd.py start` applies it in development). It writes the
app's agent list, `agents.yaml` beside `deployment.yaml`, and names it with `DD_AGENTS_CONFIG` in
`app.env`: the release's `app/config/agents.yaml`, with `model_broker: true` on each agent whose
settings set `DD_MODEL_BROKER_URL`. The harness reads that statement from the list alone, which the
agent cannot write:

```yaml
  - name: orchestrator-model
    url: http://127.0.0.1:8107
    timeout_s: 300
    model_broker: true
```

Do not edit the generated list: `apply` rewrites it. `deploy.sh` does not run `apply`, so a release
that adds an agent or moves one to another port reaches the app at the next
`sudo data-director apply`; `sudo data-director doctor` reports a list that no longer matches the
live release.

While own accounts are on, the harness runs no model-backed agent without `model_broker: true`:
its runs fail with problem `model-broker-bypassed` and the agent is not called, since an agent
holding its own provider key would ignore the grant and the deployment would pay without the run
saying so. The harness logs each such agent when it starts. `apply` refuses to turn on an agent
that calls a model without the broker while `model_accounts` lets people's own accounts pay, and
`doctor` reports one.

Remove its provider key (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` or
`DD_MODEL_API_KEY`, and their `_FILE` forms): an agent that calls through the broker holds no
provider key, and refuses to start with one. It also refuses to start without its credential.
`sudo data-director doctor` and `sudo data-director apply` check both on a VM: they report an
agent with `DD_MODEL_BROKER_URL`, in its own settings or in `agents.env`, that still holds a
provider key or lacks its broker credential, and do not ask such an agent for a provider key.
Keep its `DD_MODEL_PROVIDER` and `DD_MODEL_ID`; for `openai-compatible`, remove
`DD_MODEL_BASE_URL`, since the broker decides where the call goes. The broker serves each provider
in its own format, below its own path (`/anthropic`, `/openai`, `/gemini`,
`/openai-compatible`), and never serves a call with a provider other than the one the agent asked
for. Each of the model-backed agents (`advisor.documentation`, `advisor.policy`,
`advisor.repository`, `advisor.standards` and `orchestrator.model`) reads the same two settings.

### The deployment's own calls

When own accounts are on, the broker also pays for the calls the deployment pays for, so that one
service, not each agent, decides who pays. Give it the deployment's key for each provider its
agents use, read from the variable an agent would use: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` or
`GEMINI_API_KEY`. A call for a provider with no key is refused with
`deployment-account-unavailable`. For Anthropic, with a drop-in:

```bash
sudo systemctl edit data-director-model-broker.service
```

```ini
[Service]
LoadCredential=anthropic-api-key:/etc/data-director/credentials/model-broker/anthropic-api-key
Environment=ANTHROPIC_API_KEY_FILE=anthropic-api-key
```

Other providers take the same two lines, with `openai-api-key` and `OPENAI_API_KEY_FILE`, or
`gemini-api-key` and `GEMINI_API_KEY_FILE`.

If the deployment runs the [LiteLLM gateway](../../../deploy/llm-gateway/README.md), use a gateway
key in place of each provider key. Then set `DD_BROKER_DEPLOYMENT_BASE_URL=http://127.0.0.1:4000` in
`model-broker.env`. On a VM, `sudo deploy/install.sh --domain … --gateway` does both, and runs the
gateway too ([deploy/README.md](../../../deploy/README.md#the-litellm-gateway)). The deployment's calls then go through the gateway, whose budgets and spend
reports still apply: Anthropic's to its `/v1/messages`, and every other provider's to its
`/v1/chat/completions`. The deployment pays for an `openai-compatible` call only through the
gateway, with the gateway key in `DD_MODEL_API_KEY`. A call on a person's own key goes straight to
their provider, never through the gateway. The broker forwards the agent's model ID unchanged, so
the gateway must serve it: its `config.yaml` serves Claude models by name and OpenAI and Gemini
models by pattern ([Model names](../../../deploy/llm-gateway/README.md#model-names)).

### Custom endpoints

A person's own `openai-compatible` account names its endpoint's base URL when they add it, under
one of the origins the profile's `providers` lists for it; the Settings page offers no other. The
broker checks
the key there, and later sends calls there, only if the origin is `https` and on
`DD_BROKER_ALLOWED_BASE_URLS`; for a call, the profile's `model_accounts` (carried in the grant)
must list it as well. It refuses one that
resolves to a private, loopback or link-local address, unless that origin is also in
`DD_BROKER_PRIVATE_BASE_URLS`. It checks the address after resolving the name and connects to the
address it checked.

## Backups

The broker's store holds sealed keys and token counts. `data-director backup` copies it every night
while the broker runs, and `data-director restore` puts it back owned by the broker's user alone
([Backups](../../../deploy/README.md#backups)). A backup also holds the key-encryption key, in
`config.tar.gz`, so whoever holds a copy can unseal every enrolled key: guard the backups as well
as the VM. After a copy is lost, stop the broker, replace the key-encryption key and move
`broker.sqlite3` aside, since a key sealed under the old one no longer opens and a call on it
fails. Start the broker again; people enrol their keys again. Ask them to revoke the old keys with
their providers.

Restoring starts nothing, and whether the broker was enabled is not in the backup: if it was on,
run `sudo systemctl enable --now data-director-model-broker.service` after the restore.

## In development

```bash
uv run dd-model-broker serve
```

It reads the settings listed in `dd_broker.settings`. Docker Compose runs it with the
`model-broker` profile. Its secrets are files in `config/local/credentials/model-broker/`, and its
settings are in `config/local/model-broker.env`. The Vite dev server passes `/broker/enrolment/`
on to it (`DD_BROKER_URL`, by default `http://127.0.0.1:8300`), so the Settings page works there
once `config/local/app.env` sets `DD_APP_MODEL_BROKER_URL=/broker`.
