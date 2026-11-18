# Policy and identity

## Intent and scope

Data Director acts under rules that an institution sets and on behalf of a person who can be
named. This spec covers four things that make that true:

- the **institutional profile**, a declarative YAML file that says which agents may run, the
  action class each is assigned and which classes need a human's approval (Blueprint C12, C13);
- the **principal**, the human every invocation acts for, named by the authentication boundary
  and recorded beside the agent (Blueprint §5.4, P5);
- **signing in**, by which a person establishes who they are through OpenID Connect, with ORCID
  as the first provider and an institution's sign-in reached through the same protocol (C1);
- **model credentials**: where an API key for a hosted model lives, and what may never carry it
  (C1, C2). A person's own model account, held by the model broker rather than by an agent, is in
  [A person's own model account](model-accounts.md).

It does not cover who may see or continue a project or a conversation ([Projects](projects.md)),
the app's process boundary ([The app](app.md)), or how a delegation grant is issued
([Orchestration](orchestration.md)). Roles beyond "a signed-in person is a researcher" are not
settled; see Open questions. The profile's keys and how to edit them are described for stewards in
[`workbench/profiles/README.md`](../../workbench/profiles/README.md); where each setting and key
file lives is in the [operations guide](../guide/operations/configuration.md) and
[AI models](../guide/operations/ai-models.md).

A governing rule runs through all four: **the party being governed does not state the facts the
governance rests on.** The conductor fills identifiers, timestamps and lineage; by the same rule
it applies the deployment's profile, assigns the action class the profile gives, and records the
principal the authentication boundary names. Neither a request nor an agent can choose any of
them.

## Invariants

1. **One profile per deployment.** The operator names the profile file when the conductor is
   built. Every invocation, including every delegated child, is gated by it. A missing or
   malformed profile stops start-up, never a request (`harness/tests/test_harness.py`).
2. **A request cannot name a profile or a principal.** The request model and its generated JSON
   Schema are closed, so a request carrying `policy_bundle_ref` or `acting_for` fails validation
   and nothing runs (`workbench/tests/test_transport.py`, `sdk/tests/test_contract.py`).
3. **The profile assigns each agent its action class.** An agent not listed fails with
   `agent-not-permitted`; an agent whose card declares a class other than the one assigned fails
   with `action-class-mismatch`. In both cases the agent is not called. The gate matches the
   *assigned* class against the classes requiring approval; the card's class is checked, never
   trusted (`harness/tests/test_harness.py`).
4. **A profile holds only keys something enforces.** Any other key is refused at load, so a
   steward never sees a rule that looks in force but is not (`test_a_profile_key_nothing_enforces_is_refused`).
5. **The orchestrator a profile names is an agent it enables.** Otherwise the profile is refused
   at load. Neither the harness nor the shell holds a fallback orchestrator identifier, and the app
   picks no substitute when the named one is unavailable or does not declare `delegation`
   grounding ([The app](app.md)).
6. **Every envelope records the rules it was held to**: the profile's identifier and version, and
   the SHA-256 of the profile file's bytes, so a stored run names its rules exactly after the file
   changes (`test_the_envelope_records_the_profile_the_conductor_applied`).
7. **Every envelope names the human it acted for**, on every path, including policy refusals and
   agent errors: a refused action was still attempted on someone's behalf. The crate's
   `CreateAction` names that human as its `agent` and the agent as its `instrument`.
8. **The conductor holds no principal.** The principal is a required argument of each
   invocation. An invocation without one is a type error, not an anonymous run.
9. **A delegated child acts for its parent's principal**, carried on the grant, whoever sends the
   callback (`test_a_child_acts_for_its_parent_whoever_sends_the_callback`).
10. **An agent is not told whom it acts for.** Neither the run context nor the A2A request to an
    agent carries the principal. A model grant names only a pseudonym sealed to the broker, which
    the agent cannot read
    ([A person's own model account](model-accounts.md), invariants 3–4).
11. **No anonymous fallback.** With neither a provider nor an operator principal configured, the
    CLI, the servers and the evaluation refuse to start (`harness/tests/test_identity.py`,
    `harness/tests/test_server.py`, `app/tests/test_app.py`).
12. **A caller who cannot be authenticated is refused, never given a default.** On a server with
    a provider configured, no HTTP caller is ever given the operator's principal. A provider
    configured beside an operator principal stops start-up (`harness/tests/test_bearer_tokens.py`).
    The app answers an API request with no valid session `401` with the `unauthenticated` problem
    document, and stores nothing (`app/tests/test_sign_in.py`).
13. **The assurance says how the principal was known.** `asserted` means nobody checked;
    `authenticated` means an identity provider vouched and the harness verified its signed
    statement. `vouched_by`, the issuer's IRI, is present exactly when the assurance is
    `authenticated`, enforced by rules in the contract (`sdk/tests/test_contract.py`).
14. **The browser holds an opaque session cookie, never a token.** The cookie is random,
    `HttpOnly`, `Secure` and `SameSite=Lax`; the server keeps only a hash of it. No ID, access or
    refresh token is kept once verified, in the session, the run store or the browser
    (`test_no_token_reaches_the_run_store`, `test_the_session_cookie_is_opaque_and_kept_from_script`).
    `SameSite=Lax` does not stop a same-site, cross-origin form, so a `POST`, `PUT`, `PATCH` or
    `DELETE` to `/api` is refused with `415` unless it declares `application/json`, body or not,
    which a cross-origin page cannot send without a CORS preflight the app never answers
    (`test_every_state_changing_api_route_refuses_a_body_that_is_not_json`).
15. **Only the `openid` scope is requested**, so no email address is asked for or held
    (`test_the_app_asks_for_openid_alone_and_authenticates_with_its_secret`).
16. **A principal is keyed on its issuer and subject, and two routes are two principals.** The
    identifier is derived from the ID token's `iss` and `sub` alone, never from an email address or
    a name, which an issuer may reassign. Accounts are never linked by matching email addresses or
    names.
17. **Only the calling agent's process holds the deployment's model key, and only the model broker
    holds a person's own.** When the profile turns own accounts on, the broker holds the
    deployment's key as well, and agents hold only a broker credential. The app, the harness and the conductor never hold one, and no A2A
    message, grant, envelope, span, evidence item, crate or export carries one
    (`agents/advisor-standards/tests/test_key_not_stored.py`,
    `agents/orchestrator-model/tests/test_orchestrator_key_not_stored.py`,
    which run against a cassette with a sentinel key, the orchestrator's also against an
    OpenAI-compatible endpoint played by a mock transport). The broker keeps a person's key out of
    its answers, logs and records (`broker/tests/test_broker_key_not_leaked.py`), and an agent's
    broker credential and model grant reach no record
    (`agents/advisor-documentation/tests/test_grant_not_stored.py`,
    [A person's own model account](model-accounts.md), invariants 1 and 6).
18. **A model client is always given its key explicitly**, read once when the agent's factory
    builds it (`sdk/src/dd_sdk/credentials.py`). The provider SDK's own credential chain, such as
    a saved command-line login, is never searched, and no key is read during a run. A model grant
    is not a key: it is minted by the conductor for one invocation of one agent, allows only the
    models that agent declares, and expires with the run
    ([A person's own model account](model-accounts.md), invariant 4).
19. **A credential misconfiguration stops the agent at start-up**, in one line that names the
    variable or path and never the value, before any port opens; the agent's unit does not
    restart on that exit status (`sdk/tests/test_credentials.py`, `deploy/systemd/`).
20. **Each agent is given only the shared agent settings and its own**, never the app's or another
    agent's, so a key in one agent's settings reaches no other.
21. **Tests and CI never need a real key.** Model calls are replayed from cassettes with the
    network blocked, and recorded cassettes have credential headers removed (root `conftest.py`).
22. **A profile sets only the options an agent's card offers.** An agent's card may declare
    settings, each with its choices and a default. The profile's `agent_settings` sets them per
    agent, as strings. At load, a profile that sets options for an agent it does not enable is
    refused. At invocation, the gate refuses an agent whose card does not declare a setting the
    profile gives it, or does not accept the value, with `setting-not-declared`, and the agent is
    not run. Otherwise the conductor sends the agent its card's defaults overlaid by the profile,
    and nothing else (`test_a_setting_the_card_does_not_offer_fails_and_the_agent_is_not_run`,
    `test_an_agent_is_sent_its_card_defaults_overlaid_by_the_profile`).

## Boundaries and contracts

**The policy gate** answers three questions and nothing else: may this agent run, with which of
its declared settings, and does the class the profile assigns it require approval? It runs before the input check. An action class needing
approval yields `referred(policy_requires_approval)` to `data_steward`, and the agent is not run.
Nothing yet resumes a referred run; see Open questions. The gate decides whether the harness calls
an agent; it cannot stop an agent's own service doing something it did not declare. That is why no
agent holds write credentials (Blueprint P4): an agent proposes, and a person approves
([Projects](projects.md)). When an agent would change something outside a project, it is to
propose the change in its payload and the conductor is to perform it after approval
(TODO(#72)).

**The profile vocabulary** is the identifier, version, description, the agent-to-class mapping,
the classes requiring approval, the optional orchestrator, `hosted_models`, `model_accounts`
(whether people may or must use their own model account, whether the deployment pays for someone
who has none, and which providers and base URLs their account may use;
[A person's own model account](model-accounts.md)) and `agent_settings` (the options each agent's
card offers, such as whether it reads a source live; invariant 22) and `model_footprint` (the
prices and per-token energy factors the conductor estimates each run's model footprint from, with
their source and date; [Disclosure](disclosure.md), invariant 8). A setting is the agent's own
option, chosen by the steward: the conductor checks it against the card and sends it, and the agent
applies it. It is not a way to grant an agent anything the other keys withhold. A change to which orchestrator is
named raises the profile's version. Approved repositories (R1), persistent identifier systems
(R7) and registry access return as keys only together with the agent or check that enforces them.
`hosted_models` lists the classes of project content (`inventory`, `documentation`,
`researcher`, `decisions`) that may go to an agent whose card declares a `hosted` model; without
it `inventory` and `decisions` may ([Projects](projects.md), invariant 8). Researcher facts the profile does not list
are left out of such an agent's input rather than refused. It covers project content the conductor gives, not what a
caller or a person sends, such as a conversation's text (TODO(#40)). The rights and licensing part of a profile is to be expressed in ODRL
when repository selection or deposit needs it.

Two keys arrive with the harness's tool gateway, which is what enforces them
([Agents](agents.md#tools-mcp-servers-and-agent-skills), TODO(#875)): a grant of MCP servers per
agent, without which the gateway refuses the agent's calls; and the classes of project content
that may go to an agent granted a `remote` server, mirroring `hosted_models`. Without the second,
no `researcher` facts go to such an agent. A server is `local` or `remote` by the same rule as a
model's endpoint.

**The authentication boundary** is one interface: from the headers of a caller's HTTP request
(or none, for a caller with no request) to a principal. Three implementations sit behind it:

- the operator's assertion: the one principal configured, whoever calls, recorded `asserted`. It
  serves callers with no request (the CLI, the evaluation, tests) and development servers, which
  have no provider configured. The app says on every page of a development server that it is not
  signing anyone in.
- the session authenticator of a way in that signs people in (the app, and a deployed
  workbench), which returns the principal of the request's session.
- the harness server's bearer authenticator, which verifies an ID token sent as
  `Authorization: Bearer` on every request.

Each sign-in callback and the bearer authenticator verify a token with the one function in
`dd_harness.identity`, so every way in agrees on what a valid token is.

**Admins.** A deployed workbench admits only the ORCID iDs its deployment lists
(`DD_WORKBENCH_ADMINS`). The flow refuses anyone else after verifying their token and before
opening a session, and every request is checked against the list, so an admin taken off it is
refused at once. Once more than one issuer is accepted, the list holds principal identifiers,
not only iDs (TODO(#936)). TODO(#154): the list stands in for an administrator role until people
have roles.

**The admin service.** The admin service (`admin/`) shows an operator every person's runs and
projects, and the deployment's settings with secret values hidden. It has no sign-in of its own:
it listens on the VM's loopback only, NGINX does not serve it, and it refuses a request whose
`Host` is not a loopback name. Whoever can open an SSH session to the VM can reach it, through a
tunnel, and could read the same stores and files there already; SSH access is its credential. It
reads and never writes, and acts for nobody: it starts no run. TODO(#154): when people have roles,
decide whether the administrator role signs in to it.

**Signing in.** The app is the relying party and a confidential client running the
authorisation-code flow. The flow and the sessions are the harness's (`dd_harness.signin`,
`dd_harness.sessions`), so any way in that signs people in runs the same checks; the way in serves
the routes and names its own cookies. The code names no provider; a provider is configuration (issuer, client
identifier, client secret). The first version accepts one issuer, ORCID (`https://orcid.org`;
the sandbox issuer in development and CI); a deployment is to accept several, each configured the
same way, with the sign-in page letting the person choose (TODO(#936)). The flow sends a fresh `state` and `nonce` per sign-in
and checks both; binds `state` to the browser that started it, so a callback carried to another
browser opens no session; and verifies the ID token's signature against the issuer's published
keys (RS256 only, so a token cannot choose a weaker algorithm), its issuer, audience, expiry and
nonce. PKCE is to be added if ORCID advertises it; a confidential client checking `state` and
`nonce` does not depend on it. Sign-in calls no ORCID API, so a free public API client suffices.

**Other providers.** Every provider Data Director talks to speaks OpenID Connect. An institution's
single sign-on that offers OpenID Connect is configured directly. One that offers only SAML, and
federated sign-in through the UK Access Management Federation or eduGAIN, is reached through a
broker run by the deployment or the institution (Keycloak or SATOSA, for example) that speaks
SAML to the identity providers and OpenID Connect to Data Director. To Data Director the broker is
the issuer: it is what `vouched_by` records and whose keys verify the token. What is ORCID's
choice today becomes each provider's configuration, read from its discovery document and checked:
the signing algorithms (asymmetric only; `none` and shared-secret algorithms are always refused)
and the client authentication method. Only `openid` is requested from any provider. Groups,
affiliation or entitlement claims an institutional provider may assert are not acted on until
people have roles (TODO(#154)). The implementation is TODO(#936).

**A person's public ORCID record** is read only when that person asks, from ORCID's public API,
which needs no credential and returns only what the holder made public, and only for their own
iD: the one ORCID vouched for at sign-in, or on a development server the operator's asserted iD
URL (`dd_harness.orcid.issuer_of`). What they keep of it in a project, and how it reaches agents,
is in [Projects](projects.md), invariant 27. An email address is never read from it.

**The principal.** Its identifier is an absolute IRI. For ORCID it is the iD URL, whose path is
the token's `sub`. For any other issuer it is a URN made from the issuer and the subject alone,
`urn:data-director:oidc:<iss>:<sub>`, each part percent-encoded (RFC 3986) so that a colon in
either cannot be mistaken for the separator and the pair can be read back. The `sub` is the
issuer's stable identifier for the person; an issuer that offers a pairwise subject gives a
different principal at another relying party, which is intended. A `mailto:` IRI is used only for
a principal the operator asserts or an accountable role, never one derived from a token. Its kind is `person` or `accountable_role`, the latter
covering §5.4's case of acting for an institution. Its name is a label for a reader (ORCID's
`name`, else given and family names, else the iD itself) and nothing decides anything by it. An
ORCID holder may make their name private.

**Sessions** have an idle timeout and an absolute lifetime set by the deployment. Asking when a
session ends does not keep it going. The shell warns before an idle session ends and offers to
keep it (WCAG 2.2.1). Sign-out deletes the server-side session; the person stays signed in at
ORCID, which offers relying parties no sign-out, and the sign-out page says so. A run still going
when its session ends finishes and acts for whoever started it. The shell answers a `401` by
showing the sign-in page and decides nothing about identity itself.

**Model credentials.** A key is supplied one way in development (the key in a variable) and one
way in deployment (a path to a file, resolved against systemd's credentials directory when
relative); both set, neither set, or an empty or unreadable file is a configuration error. On the
VM, each agent's credentials drop-in is written from the files present in its directory under
`/etc/data-director/credentials/` (`deploy/credentials.sh`, put there by `deploy/secret.sh`):
a file `<secret>` is loaded as a credential of that name, and the agent is told its name in
`<SECRET>_FILE`. systemd does not start a unit whose credential file is missing, and an
agent whose model is optional must start without one, so a drop-in never names a file that is not
there.

**Model providers.** An agent names its provider in `DD_MODEL_PROVIDER` (`anthropic` by default,
`openai`, `gemini`, or `openai-compatible` with `DD_MODEL_BASE_URL`), and holds that provider's key
alone, under the provider's own variable (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`,
`DD_MODEL_API_KEY`) and by the rule above. A key set for any other provider is a configuration
error, so no key lies unused where an agent can read it. The key is given to the provider's
client explicitly, and nothing the client would read from the environment for itself (a key, a
base URL, an organisation or extra headers) reaches the endpoint. Only an `openai-compatible`
endpoint that is local may be called without a key; for it, leaving both variables unset is the
deliberate choice of no key, and a hosted endpoint without one is a configuration error
(`dd_sdk.model_provider`).

Each agent's manifest declares each
model it sends data to (provider, model, `hosted` or `local`) and names no credential
([Agents](agents.md)); the app's agent directory shows the list. The declaration is the deployment's
configuration as the agent reports it, not proof. Hosting is worked out, never stated by the
operator: a model is `local` only when its endpoint's host is `localhost` or a loopback, private or
link-local address written as an IP literal, and `hosted` otherwise, including every named
provider and any host name, which is not resolved. A mistake in this rule can only call a local
model hosted, which withholds more from it under the profile's `hosted_models`. For
`openai-compatible` the declared provider is the endpoint's host and port. Rotating a key means replacing the credential
file and restarting that agent's service; nothing else changes. When a profile lets people use
their own account, an agent's model calls go to the model broker instead, with the agent's own
broker credential and the run's grant; the deployment's key, if the profile keeps it as the
fallback, is then the broker's, not the agent's
([A person's own model account](model-accounts.md), invariant 14). An agent calls through the
broker when `DD_MODEL_BROKER_URL` is set, and then holds no provider key
(`dd_sdk.credentials.model_endpoint`). The broker serves every provider in its own format, below
its own path, so the declared provider is still the agent's own. Through the broker, an
`openai-compatible` model is declared `openai-compatible` and `hosted`: the broker, not the agent,
decides which endpoint serves it, and a person's endpoint is not known at start-up.

## Rationale

- **YAML, not a policy language.** The policy's owners are data stewards, not engineers. A small
  fixed vocabulary they can read and, with review, edit is worth more than expressiveness nobody
  yet needs. Every new gate question is a vocabulary addition and a few lines in the gate.
- **The profile is the deployment's.** A2A and AG-UI endpoints accept requests from anyone who
  can reach them; if a request named its profile, a caller could choose permissive rules or point
  at any file on the host. If the agent's declared class were trusted, an agent declaring `advise`
  would never be referred whatever it did. Running two policies therefore means running two
  instances. An agent that changes its declared class stops running until a steward updates the
  profile: a change in what an agent does is a policy decision.
- **The principal comes from the boundary.** A request field would let any caller name anyone. A
  stub that honestly records `asserted` was preferred to no record, and the place where real
  authentication enters was built first so that adding it changed nothing else.
- **The agent is not told** because no agent needs to know whom it acts for to do its work, and
  personal data goes only where the record needs it. Researcher facts a person keeps in a project
  ([Projects](projects.md), invariant 27) do not tell it: they are the project's researchers, the
  same for every run in it, and the record needs them as its creators.
- **The record says who vouched**, so a reader can weigh an identity claim by who made it. No
  published vocabulary has a term meaning exactly this, so the contract mints `dd:vouched_by` and
  the crate carries it as `vouchedBy`, referencing an `Organization` entity for the issuer.
- **A broker for SAML and federations**, rather than SAML in Data Director: a SAML service
  provider, its metadata handling and federation membership are mature plumbing that Keycloak and
  SATOSA already provide, and one protocol keeps one verification function for every way in. The
  cost is that the record names the broker, not the institution behind it, as the party that
  vouched; the broker is the party Data Director trusts and checks, so that is the honest record.
- **The subject, not the email address, is the key**, because an issuer may reassign an address
  to another person while its `sub` for a person never changes. Deriving the identifier from
  `iss` and `sub` alone also keeps the `openid`-only scope, so no address is asked for.
- **ORCID first** because the Blueprint prefers persistent identifiers for people (P5) and ORCID
  publishes a standard OpenID Connect configuration. Only `openid` is requested, which is all ORCID
  offers and keeps email addresses out (C2).
- **A server-side session with an opaque cookie** means nothing is signed into the cookie, so the
  deployment needs no session secret, and a leaked store cannot be replayed as cookies. `Lax`
  rather than `Strict` because the provider redirects back across sites.
- **The key stays with the agent**, read once and passed explicitly, so the configuration alone
  says which credential a run used, a missing key fails start-up rather than every run, and a key
  in one agent's settings reaches no other agent and never the process that serves the web page.
  A person's own key cannot follow that rule, since it is chosen per run, so it stays with one
  service built to hold it, and the run records whose account paid
  ([A person's own model account](model-accounts.md), Rationale).

## Rejected alternatives

- **A policy engine (Open Policy Agent's Rego, Cedar)** as the source of policy: a second
  language every contributor must learn and stewards cannot read. If genuinely conditional logic
  appears (a rule depending on the dataset, the requester or another rule), the YAML is to be
  compiled to Rego, not replaced by it, so the steward-readable file stays authoritative. That the
  gate cannot express a condition is the trip-wire for revisiting this.
- **A profile chosen per request**, or a way for a request or an agent to select or relax the
  profile applied to it.
- **Profile keys nothing enforces**, kept as placeholders: they told stewards a rule was in force
  when it was not.
- **A principal field on the request**, a principal set by an agent, or a default principal on
  the conductor.
- **The operator's principal for an unauthenticated HTTP caller** on a server with a provider.
- **Linking accounts by matching email addresses or names**: anyone who controls a matching
  address at another provider would become the same principal.
- **SAML implemented in Data Director**, beside OpenID Connect: a second protocol, a second
  verification path and federation metadata to keep, all of which a broker already does.
- **A `mailto:` principal from a token's `email` claim**: an address can be reassigned, and
  asking for it breaks the `openid`-only scope.
- **The `<issuer>/<sub>` form for every issuer**: it reads as a URL the issuer serves, which only
  ORCID's iD URLs are.
- **Keeping tokens** in the browser, the session or the run store, and **scopes beyond `openid`**.
- **Letting the provider SDK find a key for itself**, including a command-line login: nobody could
  say from the configuration which credential a run used.
- **One shared settings file for every agent**, which gave every agent every key.
- **Migrating runs stored before sign-in**: a deployment that turns sign-in on starts from an empty
  run store, so no `asserted` run sits beside `authenticated` ones.

## Non-functional requirements

- **Security.** Sign-in requires HTTPS. A server with a provider configured fails closed: no
  credential, no run. A token-verification failure message never contains the credential, and a
  credential error never contains the key. An issuer's keys are re-fetched when a token names an
  unknown key, but no more than once a minute, so a run of such tokens cannot become a run of
  requests to the issuer. All agents run as one operating-system user, so key separation in
  deployment depends on each agent service's key arriving as a systemd credential readable only by
  that service.
- **Key hygiene.** A deployment may give several agents one key, but should give each its own, so
  one can be revoked alone and the provider's usage reports show each agent. A spending limit is
  set on the provider's side per workspace, not per key.
- **Privacy.** Sign-in holds nothing beyond the iD and a display name. The only other personal
  data held about a person is what they choose to keep in a project from their own public ORCID
  record, which they may withdraw from agents but which stays in the project's log
  ([Projects](projects.md), invariant 27). Retention of personal data the app holds about its
  users is TODO(#156).
- **Availability.** Sessions are held in the app's memory, which suits one server process:
  restarting the app signs everyone out.
- **Accessibility.** The session time-out warning meets WCAG 2.2.1.
- **Development and tests** need no ORCID client and no model key: tests act for the ORCID
  documentation's example researcher, so no stored test run names a real person, and use a fake
  identity provider.

## Open questions

- TODO(#16, #72, #73): the approval half of the gate: suspend a referred run, record an approval
  bound to the input hash and the profile digest, and resume it as a new invocation; and an
  action-level review gate in the app.
- TODO(#372, #373): escalation to a data steward as a record the harness keeps, routed by the
  profile, and what a steward may do in a researcher's project.
- TODO(#154): roles (researcher, steward, administrator), and per-user or per-group profiles.
- TODO(#936): accepting several issuers, and the principal form above for those that are not
  ORCID.
- TODO(#937): an explicit act of linking a person's principals from two providers, with both
  sign-ins completed in one session; the principal who signed in stays the one recorded, and the
  link is a record of its own. Until then invariant 16 holds without exception.
- TODO(#17): whether an ID token is the right credential for a program calling the harness, or
  whether that waits for machine-to-machine authentication. Until then the harness's A2A
  transport refuses an unauthenticated caller inside the task, with the `unauthenticated` problem
  document, rather than answering the HTTP request `401` with `WWW-Authenticate: Bearer`.
- TODO(#800): an accountable role is a `prov:Agent` typed `dd:AccountableRole`, never a person
  ([Provenance](provenance.md), invariant 4), but the Process Run Crate still records it as a
  `Person` whose description states its kind.
- TODO(#40): enforcing a manifest's model declarations beyond project content
  ([Projects](projects.md), invariant 8), such as which models may receive a conversation's text.
- TODO(#37): the threat model this spec's controls answer to. Their baseline against C1 is
  [Security baseline](security.md).
