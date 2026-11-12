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

None of this is built yet. The broker is TODO(#806); enrolment TODO(#807); the grant and the
agent's adapter TODO(#808); recording and the reason codes TODO(#809); the profile key TODO(#810);
OpenAI-compatible accounts TODO(#811). Until those land, every model call is paid for by the
deployment, as it is today.

The governing rule is the one in [Policy and identity](policy-and-identity.md): **the party being
governed does not state the facts the governance rests on.** Neither an agent nor a request chooses
whose account pays. The conductor decides that from the profile and from whom the run acts for, and
the broker checks that decision.

## Invariants

1. **Only the broker holds a person's key.** The browser sends the key once, to the broker. The
   app, the harness, the conductor and every agent never receive it, and no A2A message, grant,
   envelope, span, evidence item, crate, export, log line or error message carries it. Planned
   test: a sentinel key enrolled through the browser, then a run, then a search for the sentinel in
   every record and log (TODO(#806), TODO(#807)).
2. **A key is sealed at rest.** The broker encrypts each key with authenticated encryption under a
   key-encryption key that only the broker's process can read, supplied as a systemd credential. The
   record's pseudonym is bound to the ciphertext as associated data, so a sealed key moved to
   another person's record does not open (TODO(#806)).
3. **The broker knows a person only by a pseudonym.** The pseudonym is a keyed hash of the
   principal's identifier under a secret the harness holds. The broker never receives an ORCID iD,
   a name or a session (TODO(#807)).
4. **A grant is not a key.** A model grant authorises one invocation of one agent to call the
   models that agent's card declares and the profile allows, for the person the run acts for. It
   expires no later than that invocation's timeout. It is useless to any other agent, for any
   other run, and after it expires. It names the pseudonym, never the principal (TODO(#808)).
5. **The conductor mints every grant; nothing else does.** Each invocation of an agent whose card
   declares `models` gets its own grant, delegated children included. A request cannot carry a
   grant, and an agent cannot mint one or pass its grant to a child (TODO(#808)).
6. **A grant is never stored.** It travels only in the A2A request's metadata, as the delegation
   grant does, and never enters the envelope, a span, the run store, the crate or an export. A
   task is forgotten once it ends ([Transport and tracing](transport.md), invariant 20), so no
   caller can read a grant back. Planned test: a sentinel grant, then a search for it in every
   record (TODO(#808)).
7. **The broker checks every call.** It refuses a call unless the grant's signature is the
   harness's, the grant is addressed to the broker and has not expired, the calling agent proves
   it is the agent the grant names using its own credential, and the model asked for is one the
   grant allows (TODO(#806)).
8. **The agent's own credential is read once, at start-up.** An agent that calls through the
   broker holds a broker credential of its own, supplied like any key
   ([Policy and identity](policy-and-identity.md), invariants 18–19). A missing or malformed
   credential stops the agent at start-up in one line (TODO(#808)).
9. **Whose account paid is recorded, never whose key.** Every model call records `own` or
   `deployment`, and the provider and model that served it as the broker reports them. The
   credential, its label and the pseudonym never enter the record (TODO(#809)).
10. **A missing or failing account is an outcome.** If the profile requires a person's own account
    and they have none, the run ends with `model-account-missing`. If the provider refuses the key,
    it ends with `model-account-rejected`. If the provider reports a quota or rate limit, it ends
    with `model-account-limit`. None of these is an exception, and none silently changes who pays
    (TODO(#809)).
11. **The profile decides; the default changes nothing.** Whether people may use their own
    account, whether they must, and whether the deployment's key is the fallback are profile
    settings that the conductor and the broker enforce. The shipped profile turns own accounts off
    (TODO(#810)).
12. **A provider is never substituted silently.** A call is served by the provider and model the
    grant allows, or it is refused. Choosing a different model for a person's account is a
    profile mapping the run records, never a guess the broker makes (TODO(#811)).
13. **Tests and CI never need a real key**, a real provider or a real broker key-encryption key.
    Provider calls are replayed from cassettes, as everywhere else
    ([Policy and identity](policy-and-identity.md), invariant 21).

## Boundaries and contracts

**The model broker** is its own service and its own process. In deployment it runs as its own
operating-system user, which no agent's or the app's service shares. It depends on the SDK for the
grant's format and on nothing in the harness. It holds:

- the sealed keys and their labels, by pseudonym;
- each person's token counts, by pseudonym and day;
- its key-encryption key and its own credential list for agents.

It keeps no prompt and no reply. It exposes two interfaces: enrolment, for the browser, and model
calls, for agents. Each speaks the provider's own request format: the Anthropic Messages API and
the OpenAI chat completions API. Agents therefore keep their adapters, with a different base URL
and credential. Provider HTTP is plumbing ([Dependencies](dependencies.md)): the broker uses the
provider SDKs or an OpenAI-compatible client, and may send the deployment's own calls through the
LiteLLM gateway. Checking the grant is governance and is the broker's own code.

**Enrolment.** A signed-in person adds, replaces or removes their account on the Profile page.
The steps are:

1. The app asks the harness for an enrolment ticket. The ticket is short-lived, single-use, signed
   by the harness and addressed to the broker, and it names the pseudonym.
2. The browser sends the key, and for an OpenAI-compatible account the base URL, to the broker
   together with the ticket. The key never passes through the app.
3. The broker checks the key with one inexpensive call to the provider. If the key works, the
   broker seals it and returns a label: the provider, the account's name if the provider gives
   one, and the last four characters of the key.

The page shows the label and the person's token use, and nothing else. Removing the account erases
the sealed record at once. A run that has already started finishes on the grant it holds.

**The grant.** A JWT signed by the harness with an asymmetric key, which the broker verifies
against the harness's published keys. Its claims are:

- the audience (the broker);
- the pseudonym;
- the agent's identifier;
- the invocation's identifier;
- the models allowed: the card's `models` that the profile permits, and only those;
- which account to use (`own`, `own-or-deployment` or `deployment`);
- issue and expiry times.

It holds no key, no principal and no project content. The conductor passes it as `dd.model_grant`
in the A2A request's metadata, beside `dd.input_ref` and `traceparent`. The SDK exposes it to the
agent as an opaque value on the run context, and its broker adapter for the model seam
(`dd_sdk.model`) sends it with each call. An agent never parses it.

**The profile.** One key, `model_accounts`, with three settings:

- `own`: `off`, `allowed` or `required`;
- `fallback`: `deployment` or `none`;
- `providers`: the providers, and the allow-listed base URLs, that a person's own account may use.

It sits beside `hosted_models` ([Policy and identity](policy-and-identity.md), The profile
vocabulary), which still governs what project content may go to a `hosted` model. A person's own
endpoint counts as `hosted` unless the operator declares its base URL local.

**What the person sees.** The About tab for a model-backed agent shows the models its card
declares, as today. To the signed-in person it also shows the label of their own account, if the
profile lets that agent use it. A stored run shows `own` or `deployment` for each call
([Disclosure](disclosure.md)). Only the person whose account it is sees the label.

## Rationale

- **A broker, not the agent, holds a person's key.** Every model-backed agent would otherwise hold
  every person's key in memory during their runs, and every agent would become a place a key could
  leak. With a broker, the agents keep exactly the credentials they hold today: one per agent,
  read at start-up. A compromised agent can spend only the grants it is given while it runs.
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
  whom it acts for, true in substance: the grant an agent forwards names nobody it could look up.
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
