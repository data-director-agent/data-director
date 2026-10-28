# ADR-0029: A person signs in with ORCID through OpenID Connect, and the record says who vouched

**Status:** Proposed
**Date:** 2026-10-22

Settles the TODO that [ADR-0018](0018-acting-for.md) left for real authentication (#150).

## Context

ADR-0018 made every invocation record the human it acted for, and put the place where the
principal enters at one boundary: `Authenticator.principal_for(headers)` in `dd_harness.identity`.
The only authenticator is the stub `OperatorAssertion`. It returns the one principal the operator
configured, whoever calls, and records `assurance: asserted`. The public deployment puts a shared
NGINX password in front of the app, and every run there is recorded as the operator's
(`deploy/README.md`).

The Blueprint asks for more. Under §5.4, "all agent actions must be executed on behalf of a named,
identified human user". C1 asks for access to be "role-based, token-verified and auditable". P5
prefers persistent identifiers such as ORCID for people. #149 tracks the move to several people,
each signing in as themselves. This ADR settles how a person is established and how that is
recorded. Roles (#154), ownership of conversations and runs (#153) and personal data (#156) have
their own issues.

ORCID publishes an OpenID Connect discovery document at
`https://orcid.org/.well-known/openid-configuration`, and the sandbox publishes one at
`https://sandbox.orcid.org/...`. At the time of writing it advertises the following:

- the issuer `https://orcid.org`, and ID tokens signed with RS256 against `https://orcid.org/oauth/jwks`;
- the scope `openid`, and no other;
- the claims `sub` (the bare iD), `name`, `given_name`, `family_name`, `auth_time` and `iss`, with no email address;
- the response type `code`, with the client authenticating by `client_secret_post` only;
- no `code_challenge_methods_supported`, so it does not advertise PKCE.

The registered client may be a free public API client. The Member API is a paid tier for writing
to ORCID records, and nothing here writes to one.

## Decision

- **OpenID Connect, with ORCID as the one provider in the first version.** The code names no
  provider. A provider is configuration: issuer, client ID and client secret. The first version
  accepts one issuer, `https://orcid.org`, and development and CI use the sandbox issuer. TODO: a
  second provider, such as an institution's single sign-on, so that staff without an iD can sign
  in. It is configuration, not a change of design, but it raises the question of linking
  accounts (below).
- **The app is the relying party, and it is a confidential client.** The app's server runs the
  authorisation-code flow:
  - It authenticates to the token endpoint with `client_secret_post`.
  - It sends a fresh `state` and `nonce` with each sign-in and checks both on return.
  - It verifies the ID token's signature against the issuer's published keys, together with its
    issuer, audience, expiry and nonce. The verifier is a function of `dd_harness.identity`
    (#151), so that the app and the harness's own server verify a token the same way.
  - PKCE is added if ORCID advertises it. A confidential client that checks `state` and `nonce`
    does not depend on it.
- **The browser holds a session cookie, never a token.** After the callback the app keeps a
  server-side session that holds the `Principal` and the session's times, and nothing else.
  - The cookie is an opaque, random session identifier, marked `HttpOnly`, `Secure` and
    `SameSite=Lax`. `Lax` is needed because the provider redirects back across sites.
  - Neither the ID token nor any access or refresh token is kept once it has been verified.
    Nothing calls ORCID's API.
- **The principal is the iD URL.** For ORCID, `principal_id` is `https://orcid.org/` followed by
  the token's `sub`, `principal_kind` is `person`, and `name` is taken from these claims, in
  order:
  1. the `name` claim;
  2. `given_name` and `family_name` together;
  3. failing both, the iD itself.

  An ORCID holder may make their name private, so the name is a label for a reader. Nothing
  decides anything by it. Another provider's principal is a `mailto:` IRI or a URN, as ADR-0018
  allows.
- **Two routes are two principals.** One person who signs in by two providers is two principals.
  Accounts are never linked by matching email addresses or names. TODO: an explicit act of
  linking, when a second provider arrives.
- **The record names the issuer that vouched.** The LinkML contract changes, and its version
  rises by a minor step:
  - `Assurance` gains `authenticated`: an identity provider vouched for the principal, and the
    harness verified its signed statement.
  - `Principal` gains `vouched_by`, the issuer's IRI (for example `https://orcid.org`). It is
    required when `assurance` is `authenticated` and absent when it is `asserted`. A reader can
    then weigh the claim by who made it.
  - The slot's IRI is `dd:vouched_by` (`https://w3id.org/data-director/vouched_by`). No
    published vocabulary has a term that means exactly this, so none is borrowed. The contract
    states the rule as LinkML rules on `Principal`, and the JSON Schema enforces it.
  - The crate's `Person` carries it as `vouchedBy`, a term the crate adds to its `@context`
    with that IRI. Its value references a context entity of type `Organization` for the issuer,
    whose `@id` is the issuer's IRI.
- **The `Authenticator` interface does not change.** `principal_for(headers)` still maps a
  caller's request headers to a `Principal`. Two kinds of caller use it:
  - The app's authenticator reads the session cookie and returns the session's principal.
  - The harness's own server (`dd-harness serve`, ADR-0022) has no browser session. A
    non-browser caller sends `Authorization: Bearer` with an ID token from the configured issuer,
    and the server verifies it per request. TODO: whether an ID token is the right credential for
    a program that calls the harness, or whether that waits for machine-to-machine
    authentication (#17).
- **A caller who cannot be authenticated is refused, never given a default.** An API request with
  no session, an expired one, or a bad token is answered `401`.
  - The body is a problem document (ADR-0004) of type
    `https://w3id.org/data-director/problems/unauthenticated`. A bearer caller also gets
    `WWW-Authenticate: Bearer`.
  - The shell answers a `401` by showing the sign-in page. It decides nothing about identity
    itself (ADR-0024).
  - No request is ever given the operator's principal.
- **The operator's assertion stays where there is no request.** The CLI, the evaluation and the
  tests have no request (`principal_for(None)`). They keep `OperatorAssertion` and record
  `asserted`, as now.
  - A server whose configuration names a provider uses only the provider's authenticator for
    HTTP callers. If a provider and an operator principal are both configured for a server, it
    refuses to start.
  - A server with no provider configured is a development server. It records `asserted` as
    now, and the app says on every page that it is not signing anyone in (#152).
- **Sessions expire, and sign-out ends them on the server.**
  - A session has an idle timeout and an absolute lifetime, both set by the deployment. The
    proposed defaults are an idle timeout of 8 hours and a lifetime of 7 days. TODO: confirm
    these against the hosting institution's policy.
  - Sign-out deletes the server-side session. ORCID offers no sign-out for a relying party, so
    the person stays signed in at ORCID, and the sign-out page says so.
  - A run that is still going when its session ends finishes and acts for whoever started it.
    `acting_for` is fixed when the conductor is invoked.
- **Only `openid` is requested.** That yields the subject and the claims about the name. No email
  address is asked for or held (C2, #156).
- **Runs stored before sign-in are deleted, not migrated.** No deployment holds runs that need
  keeping. A deployment that turns on sign-in starts from an empty run store, so no stored run
  is recorded as `asserted` beside the `authenticated` ones.
- **The site password goes.** Once sign-in works, the deployment removes the NGINX basic
  authentication. Sign-in requires HTTPS, so HTTPS becomes required (#155). Who may do what once
  signed in is #154's question. A person who signs in with an iD and nothing more is a
  researcher.

## Dependencies introduced

| Dependency | Tier | Fallback if this dependency is abandoned |
|---|---|---|
| `joserfc`, the JOSE library that verifies ID tokens in the harness (#151). Chosen over `authlib` because it is that project's JOSE core alone, typed, with no web framework. | Runtime path | Another JOSE library, or verifying RS256 with `cryptography` directly. Token verification sits behind one function in `dd_harness.identity`, and the sign-in flow behind the app's sign-in routes, so a replacement is local to each. |

## Consequences

- An envelope or crate from a deployment with sign-in names a person whom ORCID vouched for, and
  says so. Records from development servers still say `asserted`.
- Every deployment registers its own ORCID client and redirect URI, and keeps a client secret
  and a session secret. Development and CI need a sandbox client.
- People without an ORCID iD cannot sign in until a second provider is configured.
- The browser API gains a `401` that every route can return, and the shell must handle it.
- Nothing about an agent changes. An agent is still not told who it acts for (ADR-0018).
- A future contributor must not do any of the following without revisiting this decision:
  - give an HTTP caller the operator's principal on a server that has a provider configured;
  - keep a provider's tokens in the browser or the run store;
  - link two principals by matching email addresses or names;
  - request a scope beyond `openid`.
