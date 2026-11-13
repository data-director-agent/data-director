# The model broker

The model broker lets a person's own AI provider account pay for model calls in place of the
deployment's. It is a separate service that holds each person's key, sealed, and makes model calls
for agents. No agent, and neither the app nor the harness, ever holds a person's key. The design
is in [A person's own model account](../../specs/model-accounts.md).

!!! warning "Alpha, and off by default"
    The broker is built, but nothing calls it yet:

    - A person cannot yet enrol a key from the Profile page (TODO(#807)).
    - The harness does not yet sign model grants or publish its keys, and agents do not yet call
      through the broker (TODO(#808)).
    - The profile has no `model_accounts` setting yet (TODO(#810)).

    Until those land, every call is paid for by the deployment, as before, and there is no reason
    to turn the broker on.

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
`model-account-limit`. It is never quietly paid for by the deployment instead.

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

The third, `agent-credentials`, lists each agent that may call through the broker, with the
SHA-256 digest of that agent's broker credential:

```json
{"advisor.standards": "<sha256 hex of the agent's broker credential>"}
```

Make a credential with `openssl rand -hex 32`, and its digest with `printf %s "$credential" |
sha256sum`. The agent holds the credential and the broker holds only the digest. Giving agents
their credentials is TODO(#808).

Set `DD_BROKER_HARNESS_JWKS_URL` in `model-broker.env`, then start the broker:

```bash
sudo systemctl enable --now data-director-model-broker.service
```

The broker listens on `127.0.0.1:8300`. Like the agents' ports, it must not be reachable from
beyond the host or a private network (TODO(#17)).

### The deployment's own calls

When own accounts are on, the broker also pays for the calls the deployment pays for, so that one
service, not each agent, decides who pays. Give it the deployment's key with a drop-in:

```bash
sudo systemctl edit data-director-model-broker.service
```

```ini
[Service]
LoadCredential=anthropic-api-key:/etc/data-director/credentials/model-broker/anthropic-api-key
Environment=ANTHROPIC_API_KEY_FILE=anthropic-api-key
```

If the deployment runs the [LiteLLM gateway](../../../deploy/llm-gateway/README.md), use a gateway
key in place of the provider key. Then set `DD_BROKER_DEPLOYMENT_BASE_URL=http://127.0.0.1:4000` in
`model-broker.env`. The deployment's calls then go through the gateway, whose budgets and spend
reports still apply. A call on a person's own key goes straight to their provider, never through
the gateway.

### Custom endpoints

A person's own account may one day name an OpenAI-compatible endpoint (TODO(#811)). The broker
sends a key only to an `https` origin listed in `DD_BROKER_ALLOWED_BASE_URLS`. It refuses one that
resolves to a private, loopback or link-local address, unless that origin is also in
`DD_BROKER_PRIVATE_BASE_URLS`. It checks the address after resolving the name and connects to the
address it checked.

## Backups

The broker's store holds sealed keys and token counts. `data-director backup` does not copy it yet
(TODO(#814)). Losing it loses only enrolments: people enrol their keys again.

## In development

```bash
uv run dd-model-broker serve
```

It reads the settings listed in `dd_broker.settings`. Docker Compose runs it with the
`model-broker` profile. Its secrets are files in `config/local/credentials/model-broker/`, and its
settings are in `config/local/model-broker.env`.
