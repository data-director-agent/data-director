# A person's own model account

## Intent and scope

Today the deployment pays for every model call: each model-backed agent holds one provider key,
read once at start-up ([Policy and identity](policy-and-identity.md), Model credentials). This spec
lets a person use their own AI provider account instead, so that:

- an institution can offer Data Director without a central model budget;
- a researcher can use a provider or model their institution already approves;
- each person sees their own usage and spending in their own provider account.

It covers four parts:

- **the model broker**, a separate service that holds people's keys and makes model calls on
  their behalf;
- **enrolment**, by which a person gives the broker a key without the app or the harness
  receiving it;
- **the model grant**, a short-lived capability the conductor gives one invocation of one agent,
  which lets that agent's model calls be paid for by the account of the person the run acts for;
- **recording**, so that a run says whose account paid for each call without naming a credential
  or a person.

The first version supports two kinds of account: Anthropic, and OpenAI or an
OpenAI-compatible endpoint the operator has allowed. The second depends on the providers in #348.

It does not cover:

- which models an agent may call, or how an agent calls a model ([Agents](agents.md), Model-backed
  personas);
- the deployment's own keys, which stay as [Policy and identity](policy-and-identity.md) describes;
- spending limits, which a person sets with their provider, and the deployment's own spend
  ([`deploy/llm-gateway`](../../deploy/llm-gateway/README.md)).

The broker is built (`broker/`), with the grant's format in the SDK (`dd_sdk.model_grant`). The
harness mints grants and publishes its keys (`dd_harness.model_grants`), and every model-backed
agent can call through the broker (`dd_sdk.credentials.model_endpoint`,
`dd_sdk.model_anthropic.anthropic_client`). Enrolment is built: the harness signs the ticket
(`GrantMinter.enrolment_ticket`), the app issues it, the broker serves the browser
(`dd_broker.enrolment`), and the Profile page holds the form. The profile key is built: the
conductor reads `model_accounts` when it mints a grant (`dd_harness.policy.ModelAccounts`), and the
broker enforces what the grant says. Recording whose account paid and the reason codes are built:
the SDK reads the broker's answer (`dd_sdk.model_account`), and a refused account ends the run as
an outcome. OpenAI-compatible accounts TODO(#811). The shipped profiles turn own accounts off, so
every grant says the deployment pays, and every model call is paid for by the deployment, as it is
today.

The governing rule is the one in [Policy and identity](policy-and-identity.md): **the party being
governed does not state the facts the governance rests on.** Neither an agent nor a request chooses
whose account pays. The conductor decides that from the profile and from whom the run acts for, and
the broker checks that decision.

## Invariants

1. **Only the broker holds a person's key.** The browser sends the key once, to the broker. The
   app, the harness, the conductor and every agent never receive it, and no A2A message, grant,
   envelope, span, evidence item, crate, export, log line or error message carries it. A sentinel
   key enrolled with a ticket the app issued, then a run, appears in nothing the app is sent or
   answers, in no log line and in no file the app or the harness keeps
   (`app/tests/test_model_account.py`). The broker's part is tested: a sentinel key, which the
   provider's answers quote back when it is called and when it is enrolled, appears in no answer,
   log line or record of the broker's (`broker/tests/test_broker_key_not_leaked.py`).
2. **A key is sealed at rest.** The broker encrypts each key with authenticated encryption under a
   key-encryption key that only the broker's process can read, supplied as a systemd credential. The
   record's pseudonym is bound to the ciphertext as associated data, so a sealed key moved to
   another person's record does not open (`dd_broker.seal`, `broker/tests/test_broker_seal.py`).
3. **The broker knows a person only by a pseudonym.** The pseudonym is a keyed hash of the
   principal's identifier under a secret the harness holds. The broker never receives an ORCID iD,
   a name or a session: a grant and an enrolment ticket name the person only by the pseudonym,
   sealed to the broker (`harness/tests/test_model_grants.py`, `app/tests/test_model_account.py`).
4. **A grant is not a key.** A model grant authorises one invocation of one agent to call the
   models that agent's card declares and the profile allows, for the person the run acts for. It
   expires no later than that invocation's timeout. It is useless to any other agent, for any
   other run, and after it expires. It names the person only by their pseudonym, sealed to the
   broker, so an agent cannot read the pseudonym or link two grants to one person
   (`harness/tests/test_model_grants.py`).
5. **The conductor mints every grant; nothing else does.** Each invocation of an agent whose card
   declares `models` gets its own grant, delegated children included. A request cannot carry a
   grant, and an agent cannot mint one or pass its grant to a child: the harness reads no grant
   from a request's metadata (`harness/tests/test_model_grants.py`).
6. **A grant is never stored.** It travels only in the A2A request's metadata, as the delegation
   grant does, and never enters the envelope, a span, the run store, the crate or an export. A
   task is forgotten once it ends ([Transport and tracing](transport.md), invariant 20), so no
   caller can read a grant back (`harness/tests/test_model_grants.py`,
   `agents/advisor-documentation/tests/test_grant_not_stored.py`).
7. **The broker checks every call.** It refuses a call unless the grant's signature is the
   harness's, the grant is addressed to the broker and has not expired, the calling agent proves
   it is the agent the grant names using its own credential, and the model asked for is one the
   grant allows (`dd_broker.grants`, `broker/tests/test_broker_grants.py`,
   `broker/tests/test_broker_calls.py`).
8. **The agent's own credential is read once, at start-up.** An agent that calls through the
   broker holds a broker credential of its own, supplied like any key
   ([Policy and identity](policy-and-identity.md), invariants 18–19). A missing or malformed
   credential stops the agent at start-up in one line (`dd_sdk.credentials.model_endpoint`,
   `sdk/tests/test_model_broker.py`).
9. **Whose account paid is recorded, never whose key.** Every model call records `own` or
   `deployment` (`ModelCall.model_account`, and `dd.model_account` on its `chat` span), and the
   provider and model that served it as the broker reports them. The client the SDK builds for
   the broker reads `X-DD-Model-Account` from each answer, so an agent that calls its client
   directly records it too; a call that did not go through the broker was paid for by the
   deployment. The Process Run Crate gives each call's `CreateAction` the same value as a
   `PropertyValue` named `model_account`. The credential, its label and the pseudonym never enter
   the record (`dd_sdk.model_account`, `sdk/tests/test_whose_account_paid.py`,
   `harness/tests/test_model_grants.py`, `app/tests/test_model_account.py`).
10. **A missing or failing account is an outcome.** If the profile requires a person's own account
    and they have none, the run ends `abstained` with reason code `model_account_missing`. If the
    provider refuses the key, it ends with `model_account_rejected`. If the provider reports a
    quota or rate limit, it ends with `model_account_limit`. The broker sends each as the same
    name in kebab case in `X-DD-Reason`; the SDK's agent server, and the conductor for an agent it
    runs in process, find it on the exception the agent raised and end the run with the calls made
    before it (`dd_sdk.model_account.accounted`). None of these is an exception, and none silently
    changes who pays. Adding these reason codes raised the contract version to 0.10.0
    ([Contract](contract.md); `sdk/tests/test_whose_account_paid.py`,
    `harness/tests/test_model_grants.py`).
11. **The profile decides; the default changes nothing.** Whether people may use their own
    account, whether they must, and whether the deployment's key is the fallback are profile
    settings that the conductor and the broker enforce. The shipped profiles turn own accounts off
    (`harness/tests/test_harness.py`, `harness/tests/test_model_grants.py`). A profile that turns
    them on is refused unless the harness mints grants, and the app offers a person no account of
    their own unless the profile lets one pay (`app/tests/test_model_account.py`).
12. **A provider is never substituted silently.** A call is served by the provider and model the
    grant allows, or it is refused. Choosing a different model for a person's account is a
    profile mapping the run records, never a guess the broker makes (TODO(#811)).
13. **Tests and CI never need a real key**, a real provider or a real broker key-encryption key.
    Provider calls are replayed from cassettes, as everywhere else
    ([Policy and identity](policy-and-identity.md), invariant 21).
14. **Only the broker decides who pays.** When the profile turns own accounts on, every model call
    goes through the broker, which then holds the deployment's provider keys as well as people's
    own. Only the broker applies the grant's account setting; an agent never chooses who pays and
    holds no provider key of its own. The broker applies the account setting
    (`broker/tests/test_broker_calls.py`). An agent configured to call through the broker refuses
    to start with a provider key beside its broker credential (`sdk/tests/test_model_broker.py`).
    The conductor cannot yet tell whether an agent calls through the broker, so which agents do is
    the operator's choice (TODO(#819)).

## Boundaries and contracts

**The model broker** is its own service and its own process. In deployment it runs as its own
operating-system user, which no agent's or the app's service shares. It depends on the SDK for the
grant's format and on nothing in the harness. It holds:

- the sealed keys and their labels, by pseudonym;
- each person's token counts, by pseudonym and day;
- its key-encryption key and its own credential list for agents;
- the deployment's provider keys, when the profile allows own accounts, each read once at start-up
  from a systemd credential as an agent's key is today
  ([Policy and identity](policy-and-identity.md), invariants 18–19).

It keeps no prompt and no reply. It exposes two interfaces: enrolment, for the browser, and model
calls, for agents. Each speaks the provider's own request format: the Anthropic Messages API and
the OpenAI chat completions API. Agents therefore keep their adapters, with a different base URL
and credential. Provider HTTP is plumbing ([Dependencies](dependencies.md)): the broker uses the
provider SDKs or an OpenAI-compatible client, and may send the deployment's own calls through the
LiteLLM gateway. Checking the grant is governance and is the broker's own code.

**The broker's interface for agents.** An agent's provider client points at the broker in place of
the provider. For the Anthropic Messages API that is `POST /anthropic/v1/messages`. The client
sends the agent's own broker credential where it would send an API key (`x-api-key` or
`Authorization: Bearer`), and the grant as `X-DD-Model-Grant`. The broker does these checks and
steps in order:

1. It authenticates the agent.
2. It verifies the grant for that agent.
3. It refuses a model the grant does not allow, and a streamed request.
4. It chooses the account from the grant alone:

   | The grant's account | The person has an account | The person has none |
   |---|---|---|
   | `own` | Their key | Refused, `model-account-missing` |
   | `own-or-deployment` | Their key | The deployment's key |
   | `deployment` | The deployment's key | The deployment's key |

5. It forwards the request body unchanged.

The broker returns the provider's answer unchanged, with `X-DD-Model-Account` (`own` or
`deployment`) and `X-DD-Model-Provider`. The model that served the call is in the answer itself.
A refusal or a provider error is reduced to a status and a reason code, which the broker sends in
`X-DD-Reason` and in an error body of the provider's shape:

| What happened | The status | The reason code |
|---|---|---|
| The provider refuses a person's own key | 403 | `model-account-rejected` |
| The provider reports a quota or rate limit on it | 429 | `model-account-limit` |

Neither falls back to the deployment's key. The header names, claim names and account values are
in `dd_sdk.model_grant`; the reason codes are in `dd_broker.reasons`. The run records the three
`model-account-*` codes as the `ReasonCode` values of the same names in snake case (invariant 10).

The deployment's own calls go to `DD_BROKER_DEPLOYMENT_BASE_URL` when it is set, normally the
[LiteLLM gateway](../../deploy/llm-gateway/README.md), with a gateway key in place of the provider
key. The gateway's budgets and spend reports then cover them as before. A call on a person's own
key never passes through the gateway, which would otherwise see the key.

**Enrolment.** A signed-in person adds, replaces or removes their account on the Profile page.
The steps are:

1. The app asks the harness for an enrolment ticket (`POST /api/model-account/ticket`, for the
   person signed in). The ticket is short-lived, single-use, signed by the harness and addressed to
   the broker, and it names the pseudonym.
2. The browser sends the key, and for an OpenAI-compatible account the base URL, to the broker
   together with the ticket. The key never passes through the app.
3. The broker checks the key with one inexpensive call to the provider. If the key works, the
   broker seals it and returns a label: the provider, the account's name if the provider gives
   one, and the last four characters of the key.

The page shows the label and the person's token use, and nothing else. Removing the account erases
the sealed record at once. A run in progress makes no further calls on that account: its next
call ends the run with `model_account_missing`, or is paid for by the deployment only if the grant
allows `own-or-deployment`, and the run records that it was (invariants 9–10).

The ticket is the grant's sibling, signed with the same key and checked against the same published
keys (`dd_sdk.model_grant`):

- **Header:** `typ` is `dd-enrolment+jwt`, where a grant's is `JWT`, so neither passes for the
  other.
- **Claims:** `aud` (the broker's, as in a grant), `iat`, `exp`, `jti`, `dd_purpose` (`enrolment`)
  and `dd_subject` (the pseudonym, sealed to the broker as in a grant). It carries none of a
  grant's other claims.
- **Lifetime:** 120 seconds. The broker accepts each `jti` once, and remembers it until the ticket
  has expired.

The page asks for a fresh ticket for each request it makes of the broker. The broker's enrolment
interface is `/enrolment/account`, with the ticket as `Authorization: Bearer`:

| Request | What the broker does | Its answer |
|---|---|---|
| `GET` | Reads the account's label and the person's token use for the last 30 days. | `{account, usage}`; `account` is `null` if they have none. |
| `PUT` `{provider, key}` | Checks the key by listing one model, which costs no tokens, and stores it only if the provider accepts it. | `{account, usage}`, or a status and `{reason}`. |
| `DELETE` | Erases the sealed record. | `204`. |

A key that fails is answered `422` with `model-account-rejected`, `429` with `model-account-limit`,
or `502` with `provider-unreachable` or `provider-error`, and is not stored. A ticket that is
missing, invalid, expired or used is answered `401` with `ticket-missing`, `ticket-invalid`,
`ticket-expired` or `ticket-used`. Every answer is `Cache-Control: no-store`. The page puts each
reason in plain words.

The browser reaches the broker on the app's own origin: the reverse proxy passes
`/broker/enrolment/` on to the broker's `/enrolment/`, and nothing else of the broker's
([`deploy/nginx/data-director.conf`](../../deploy/nginx/data-director.conf)). So the broker needs
no cross-origin rules, and its interface for agents stays on the host's private network. The app's
`DD_APP_MODEL_BROKER_URL` names that path, and must be a path. Without it, or without the harness
minting grants, the app issues no ticket and the page offers no account.

**The grant.** A JWT signed by the harness with an asymmetric key, which the broker verifies
against the harness's published keys. Its claims are:

- the audience (the broker);
- the pseudonym, encrypted to the broker (a JWE nested in the signed grant), so the value an
  agent forwards is one it cannot read and that differs in every grant;
- the agent's identifier;
- the invocation's identifier;
- the models allowed: the card's `models` that the profile permits, and only those;
- which account to use (`own`, `own-or-deployment` or `deployment`);
- for a grant that may use a person's own account, the providers and the base URL origins the
  profile lets that account use;
- issue and expiry times.

`dd_sdk.model_grant` fixes the format:

- **Signature:** RS256 or ES256, and no other algorithm.
- **Audience:** `urn:data-director:model-broker`.
- **Claims:** `dd_agent`, `dd_invocation`, `dd_models`, `dd_account` and `dd_subject`, beside
  `aud`, `iat` and `exp`. A grant whose `dd_account` is `own` or `own-or-deployment` also carries
  `dd_providers`, a non-empty list of provider names, and `dd_base_urls`, a list of origins
  (`https://host[:port]`, lower case, default port left out, as `dd_sdk.model_grant.origin` writes
  them); a grant the deployment pays for carries neither. The broker refuses a person's own
  account whose provider is not in `dd_providers` (`account-unsupported`), and one whose base URL's
  origin is not in `dd_base_urls` (`base-url-refused`), and does not fall back to the deployment's
  key for either.
- **The sealed pseudonym:** a compact JWE in `dd_subject`, made with `ECDH-ES+A256KW` and
  `A256GCM` to the broker's P-256 key.

The broker allows 30 seconds of clock skew. The grant expires the agent's transport timeout after
it is issued, rounded down to the second.

The harness mints grants when three settings are given, each as `NAME` or as `NAME_FILE` for a
systemd credential:

- `DD_MODEL_GRANT_SIGNING_KEY`: its private signing key, an RSA or EC P-256 key as a JWK or a PEM;
- `DD_MODEL_BROKER_SUBJECT_KEY`: the broker's public P-256 key, to which pseudonyms are sealed;
- `DD_PSEUDONYM_SECRET`: at least 32 bytes, the secret under which the pseudonym is a keyed hash
  (HMAC-SHA256) of the principal's identifier.

With none of them, the harness mints no grant. With some but not all, or one it cannot use, it
stops at start-up in one line that names the setting and never its value. When it mints grants,
every way in that serves HTTP, the app included, publishes the public signing key as a JWK set at
`/.well-known/jwks.json`, which the broker's `DD_BROKER_HARNESS_JWKS_URL` names. The broker can read
the same set from a file instead.

It holds no key, no principal and no project content. The conductor passes it as `dd.model_grant`
in the A2A request's metadata, beside `dd.input_ref` and `traceparent`. The SDK exposes it to the
agent as an opaque value on the run context (`RunContext.model_grant`), and binds it to the run
while the agent works. Every Claude client the SDK builds
(`dd_sdk.model_anthropic.anthropic_client`, which `AnthropicModel` behind the model seam uses too)
sends the bound grant as `X-DD-Model-Grant` with each call to the broker, so no agent's own code
handles it. An agent never parses it.

An agent calls through the broker when `DD_MODEL_BROKER_URL` is set. It then reads its broker
credential, `DD_MODEL_BROKER_CREDENTIAL` or `DD_MODEL_BROKER_CREDENTIAL_FILE`, once at start-up, and
refuses to start if a provider key is set beside it (`dd_sdk.credentials.model_endpoint`).

**The profile.** One key, `model_accounts`, with three settings:

- `own`: `off`, `allowed` or `required`; `off` when the key is absent;
- `fallback`: `deployment` or `none`, required unless `own` is `off`;
- `providers`: the providers, and the allow-listed base URLs, that a person's own account may use,
  required unless `own` is `off`. Each entry names a `provider` (`anthropic` until TODO(#811)) and
  may list `base_urls`, each a `url` and an optional `local: true`.

```yaml
model_accounts:
  own: allowed
  fallback: deployment
  providers:
    - provider: anthropic
      base_urls:
        - url: https://llm.example.ac.uk
          local: true
```

The conductor turns the first two into the grant's account setting:

| `own` | `fallback` | The grant's account | A person with no account of their own |
|---|---|---|---|
| `off` | either | `deployment` | Not applicable. |
| `allowed` | `deployment` | `own-or-deployment` | The deployment pays. |
| `allowed` | `none` | `own` | The run ends with `model_account_missing`. |
| `required` | `none` | `own` | The run ends with `model_account_missing`. |

`required` with `fallback: deployment` contradicts itself, so a profile that combines them is
refused when it is loaded. So is a `fallback` or `providers` beside `own: off`, a provider the
broker cannot serve, a base URL that is not a plain `https` URL, and any other key: each would tell
a steward a rule is in force when nothing enforces it ([Policy and identity](policy-and-identity.md),
invariant 4). A profile that turns own accounts on stops the harness at start-up unless it mints
grants, since nothing else would carry the decision to the broker.

It sits beside `hosted_models` ([Policy and identity](policy-and-identity.md), The profile
vocabulary), which still governs what project content may go to a `hosted` model. A person's own
endpoint counts as `hosted` unless the profile declares its base URL `local`. The conductor cannot
know in advance which endpoint a person's account will use, so while own accounts are on, every
model-backed agent's models count as `hosted` unless every endpoint the profile allows is declared
local. A provider's own endpoint, used by an entry without `base_urls`, is never local. The
operator's broker allow-list (`DD_BROKER_ALLOWED_BASE_URLS`) must also name an origin before the
broker sends a key there.

**What the person sees.** The agent page for a model-backed agent shows the models its card
declares, as before. Where the profile lets people use their own accounts, it also shows the
signed-in person the label of their own account, read from the broker with their own ticket, or
points them to the Profile page if they have none. A stored run's "About this run" shows each
model call and whether the person's own account or the deployment's paid for it
([Disclosure](disclosure.md)). Only the person whose account it is sees the label.

## Rationale

- **A broker, not the agent, holds a person's key.** Every model-backed agent would otherwise hold
  every person's key in memory during their runs, and every agent would become a place a key could
  leak. With a broker, each agent still holds one credential read at start-up, but it is a broker
  credential in place of a provider key, and it is worth nothing without a grant. A compromised
  agent can spend only the grants it is given while it runs. The broker holds the deployment's keys
  too when own accounts are on, so that one service, not each agent, decides who pays.
- **A grant rather than a key on the wire.** A grant is bound to one agent, one invocation and a
  list of models, and it expires with the run. A stolen grant is worth one run's calls to the
  models the run was already allowed. A stolen key is worth everything the account can do until
  someone notices.
- **The conductor mints the grant** because it already knows whom the run acts for, which agent it
  calls, the agent's declared models and the profile. Those are the facts that decide who pays, and
  no agent or request may state them.
- **A pseudonym, not the principal.** The broker needs to find one person's key and nothing about
  who they are. A keyed hash keeps the broker's records useless for identifying anyone without the
  harness's secret. It also keeps invariant 10 of Policy and identity, that an agent is not told
  whom it acts for, true in substance: the pseudonym in the grant an agent forwards is sealed to
  the broker, so the agent can neither read it nor correlate two runs of one person.
- **Enrolment goes straight to the broker** so that the app, the one process that serves web
  pages, stays a process that has never held a model key
  ([The app](app.md), Boundaries and contracts).
- **Own accounts are off by default** so that turning the feature on is a steward's decision,
  recorded in the profile and in the version of every run held to it.
- **Provider-native APIs at the broker** let agents keep the adapters they already have behind the
  model seam. Only a base URL and a credential change.

## Rejected alternatives

- **A key store each agent reads.** Every model-backed agent would hold people's keys during
  their runs, and a key would be read during a run, which Policy and identity forbids for good
  reason: nobody could say from an agent's configuration which credential it used.
- **A key held in the browser and sent with each turn.** Nothing would be stored on the server, but
  the key would cross the app, the harness and the A2A request on every turn. Every hop would have
  to be kept from logging it.
- **LiteLLM virtual keys as the person's credential.** Each person would hold a long-lived bearer
  secret of their own, and nothing could tie a call to one run of one agent. The gateway stays
  useful for the deployment's own spend.
- **OAuth with the provider.** No supported provider offers delegated API access through OAuth for
  this use today. If one does, enrolment is the only part that changes.
- **Choosing a substitute model when a person's provider does not serve the one declared.** The run
  would then not say what was sent where. A mapping is a steward's decision in the profile, or the
  run ends with an outcome.
- **Recording the account's label or pseudonym in the run.** A run is shared with a project's
  members and exported. `own` or `deployment` is what a reader needs to know; whose account it was
  is the person's business.

## Non-functional requirements

- **Security.** The threat model:

  | Threat | Answer |
  |---|---|
  | The broker is compromised. | Keys are sealed under a key-encryption key in a systemd credential that only the broker's user can read. A database copy without that credential opens no key. The broker's process can still use every key, so it runs alone, holds nothing else, and exposes only its two interfaces to the host's private network. |
  | A grant is stolen from an agent's memory or the network. | It works for one agent's credential, one invocation, the declared models, and until the run's timeout. |
  | A grant is replayed by a different agent. | The broker checks the calling agent's own credential against the agent the grant names. |
  | The broker spends the deployment's key. | With own accounts on, the broker holds the deployment's provider keys and sends the deployment's calls through the LiteLLM gateway, whose spending limits still apply ([`deploy/llm-gateway`](../../deploy/llm-gateway/README.md)). |
  | An attacker sends the broker an SSRF base URL. | A custom base URL must be on the operator's allow-list. Private, loopback and link-local addresses are refused unless the operator listed them, and the address is checked after resolving the name, not only as text. |
  | A key reaches logs. | Errors from the provider are reduced to a status and a reason code before they leave the broker. No request body is logged. |

  Agent ports must still not be exposed beyond the host or a private network, as transport
  requires, TODO(#17).
- **Privacy.** A person's key, label and token counts are personal data the broker holds about
  them. They are erased when the person removes their account. Their retention otherwise is part of
  TODO(#156). The broker's records name only pseudonyms.
- **Availability.** If the broker is unreachable, a call that needs it ends the run as an agent
  error. The broker does not fall back to the deployment's key unless the grant allows it.
- **Accessibility.** The Profile page's account section follows the app's accessibility
  requirements ([The app](app.md)).
- **Portability.** The broker runs on the VM under systemd like every other service, and in Compose
  for development. It needs no cloud service (Blueprint P11).

## Open questions

- TODO(#40): whether a profile may refuse a person's own provider for a given class of data, such
  as a conversation's text, beyond `hosted_models` for project content.
- TODO(#154): whether a steward may require own accounts for some people or groups and not
  others.
- TODO(#811): how a profile maps a declared model to one a person's provider serves, and whether an
  agent that relies on tool calls refuses an endpoint that does not support them.
- TODO(#43, #37): where the broker's key-encryption key and its rotation fit the security baseline
  and the threat model.
