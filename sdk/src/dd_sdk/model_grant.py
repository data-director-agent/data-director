"""The model grant's format (docs/specs/model-accounts.md, The grant).

A model grant lets one invocation of one agent call models through the model broker, paid for by
the account the conductor chose. The harness signs it as a JWT. The broker verifies it. The agent
only forwards it, as an opaque value, and never parses it.

This module holds only what the harness, the broker and the agent's adapter must agree on: the
claim names, the account values, the algorithms, the metadata key and the HTTP headers. Minting is
the conductor's job (`dd_harness.model_grants`). Verifying is the broker's own code
(`dd_broker.grants`), because checking a grant is governance
([Dependencies](../../../docs/specs/dependencies.md)).

`ModelGrantClaims.from_claims` checks that a verified claim set has the shape below. It does not
check a signature, an audience or a time; the broker does that before calling it.

The enrolment ticket (docs/specs/model-accounts.md, Enrolment) is the grant's sibling: a token the
harness signs with the same key, for the browser to present to the broker when a person reads, adds
or removes their own account. It names the person only by their pseudonym, sealed to the broker as
in a grant, and carries a `jti` so that the broker accepts it once. Its JOSE `typ` and its
`dd_purpose` claim keep a ticket from passing as a grant, and a grant from passing as a ticket.
`EnrolmentTicketClaims.from_claims` checks its shape.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit

from dd_sdk.contract.models import ModelAccount

# Where the conductor puts the grant in the A2A request's metadata, beside `dd.input_ref` and
# `traceparent` (dd_sdk.wire re-exports it). It is never written to the envelope, a span or a
# store (invariant 6).
META_MODEL_GRANT = "dd.model_grant"

# The `aud` of every model grant: the broker, and nothing else, accepts it.
BROKER_AUDIENCE = "urn:data-director:model-broker"

# The harness signs grants with an asymmetric key and publishes the public half as a JWKS. No
# other algorithm is accepted, so a grant cannot choose a weaker one.
SIGNING_ALGORITHMS = ("RS256", "ES256")

# The pseudonym is sealed to the broker as a compact JWE nested in the signed grant, so an agent
# cannot read it and each grant carries a different value (invariant 4). The broker's key is an
# EC P-256 key; only these algorithms are accepted.
SUBJECT_KEY_ALGORITHM = "ECDH-ES+A256KW"
SUBJECT_ENCRYPTION = "A256GCM"

# Claim names. `aud`, `iat` and `exp` are the registered JWT claims (RFC 7519).
CLAIM_AUDIENCE = "aud"
CLAIM_ISSUED_AT = "iat"
CLAIM_EXPIRES = "exp"
CLAIM_AGENT = "dd_agent"
CLAIM_INVOCATION = "dd_invocation"
CLAIM_MODELS = "dd_models"
CLAIM_ACCOUNT = "dd_account"
CLAIM_SUBJECT = "dd_subject"
# Only in a grant that may use a person's own account: the providers that account may be with, and
# the origins (scheme, host and port) it may name as a base URL. The profile's `model_accounts`
# decides both, and the broker refuses an own account outside them.
CLAIM_PROVIDERS = "dd_providers"
CLAIM_BASE_URLS = "dd_base_urls"
CLAIM_TICKET_ID = "jti"
CLAIM_PURPOSE = "dd_purpose"

# The enrolment ticket's JOSE `typ` header and `dd_purpose` value. A grant's `typ` is `JWT`.
TICKET_TYPE = "dd-enrolment+jwt"
TICKET_PURPOSE = "enrolment"
# A ticket is good for one request to the broker, sent within this many seconds of its issue.
TICKET_LIFETIME_S = 120
# Claims that only a grant carries; a ticket that has any of them is refused.
_GRANT_ONLY_CLAIMS = (
    CLAIM_AGENT,
    CLAIM_INVOCATION,
    CLAIM_MODELS,
    CLAIM_ACCOUNT,
    CLAIM_PROVIDERS,
    CLAIM_BASE_URLS,
)

# HTTP headers between an agent's adapter and the broker. The agent's own broker credential
# travels where its provider client already sends an API key (`x-api-key` or
# `Authorization: Bearer`), so an adapter changes only its base URL and its credential.
HEADER_GRANT = "X-DD-Model-Grant"
# On the broker's answer: who paid (`own` or `deployment`), which provider served the call, and,
# when the broker refused or the provider failed, a reason code.
HEADER_ACCOUNT = "X-DD-Model-Account"
HEADER_PROVIDER = "X-DD-Model-Provider"
HEADER_REASON = "X-DD-Reason"


class Account(StrEnum):
    """Which account a grant lets the broker use (docs/specs/model-accounts.md, The profile)."""

    OWN = "own"
    OWN_OR_DEPLOYMENT = "own-or-deployment"
    DEPLOYMENT = "deployment"


# Whose account paid for one call, as the broker reports it and a run records it
# (`ModelCall.model_account`). One enumeration, so the header and the record cannot disagree.
Payer = ModelAccount


def origin(url: str) -> str:
    """A base URL's origin as a grant's `dd_base_urls` and the broker's allow-list name it:
    `https://host[:port]`, lower case, with the default port left out. Raises `ValueError` for
    anything that is not a plain `https` URL; the message never quotes the URL."""
    parts = urlsplit(url.strip())
    if parts.scheme != "https":
        raise ValueError("a base URL must use https")
    if not parts.hostname:
        raise ValueError("a base URL must name a host")
    if parts.username is not None or parts.password is not None:
        raise ValueError("a base URL must not carry user information")
    if parts.query or parts.fragment:
        raise ValueError("a base URL must not carry a query or a fragment")
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("a base URL's port is not a number") from exc
    host = parts.hostname.lower()
    shown = f"[{host}]" if ":" in host else host
    return f"https://{shown}" if port in (None, 443) else f"https://{shown}:{port}"


class ModelGrantError(ValueError):
    """A claim set does not have the model grant's (or the enrolment ticket's) shape. The message
    names the claim, never a claim's value."""


def _text(claims: Mapping[str, Any], name: str, token: str) -> str:
    value = claims.get(name)
    if not isinstance(value, str) or not value:
        raise ModelGrantError(f"the {token}'s {name} is missing or not a string")
    return value


def _texts(claims: Mapping[str, Any], name: str, *, empty: bool) -> tuple[str, ...]:
    value = claims.get(name)
    if (
        not isinstance(value, list)
        or (not value and not empty)
        or not all(isinstance(v, str) and v for v in value)
    ):
        raise ModelGrantError(f"the grant's {name} is not a list of strings")
    return tuple(value)


def _number(claims: Mapping[str, Any], name: str, token: str) -> int:
    value = claims.get(name)
    # bool is an int in Python; a time is never true or false.
    if not isinstance(value, int) or isinstance(value, bool):
        raise ModelGrantError(f"the {token}'s {name} is missing or not an integer")
    return value


@dataclass(frozen=True)
class ModelGrantClaims:
    """The claims of a model grant whose signature has been checked."""

    audience: str
    agent: str
    invocation: str
    models: tuple[str, ...]
    account: Account
    subject: str
    issued_at: int
    expires_at: int
    # The providers and base URL origins a person's own account may use; empty for a grant the
    # deployment pays for.
    providers: tuple[str, ...] = ()
    base_urls: tuple[str, ...] = ()

    @classmethod
    def from_claims(cls, claims: Mapping[str, Any]) -> ModelGrantClaims:
        def text(name: str) -> str:
            return _text(claims, name, "grant")

        def number(name: str) -> int:
            return _number(claims, name, "grant")

        if CLAIM_PURPOSE in claims:
            raise ModelGrantError(f"a grant carries no {CLAIM_PURPOSE}")
        models = claims.get(CLAIM_MODELS)
        if (
            not isinstance(models, list)
            or not models
            or not all(isinstance(m, str) and m for m in models)
        ):
            raise ModelGrantError(f"the grant's {CLAIM_MODELS} is not a list of model identifiers")
        try:
            account = Account(text(CLAIM_ACCOUNT))
        except ValueError as exc:
            raise ModelGrantError(f"the grant's {CLAIM_ACCOUNT} is not a known account") from exc
        providers: tuple[str, ...] = ()
        base_urls: tuple[str, ...] = ()
        if account is Account.DEPLOYMENT:
            # A grant the deployment pays for says nothing about a person's own account.
            for name in (CLAIM_PROVIDERS, CLAIM_BASE_URLS):
                if name in claims:
                    raise ModelGrantError(f"a grant the deployment pays for carries no {name}")
        else:
            providers = _texts(claims, CLAIM_PROVIDERS, empty=False)
            if CLAIM_BASE_URLS in claims:
                base_urls = _texts(claims, CLAIM_BASE_URLS, empty=True)
        issued_at, expires_at = number(CLAIM_ISSUED_AT), number(CLAIM_EXPIRES)
        if expires_at <= issued_at:
            raise ModelGrantError("the grant expires before it is issued")
        return cls(
            audience=text(CLAIM_AUDIENCE),
            agent=text(CLAIM_AGENT),
            invocation=text(CLAIM_INVOCATION),
            models=tuple(models),
            account=account,
            subject=text(CLAIM_SUBJECT),
            issued_at=issued_at,
            expires_at=expires_at,
            providers=providers,
            base_urls=base_urls,
        )


@dataclass(frozen=True)
class EnrolmentTicketClaims:
    """The claims of an enrolment ticket whose signature has been checked."""

    audience: str
    ticket_id: str
    subject: str
    issued_at: int
    expires_at: int

    @classmethod
    def from_claims(cls, claims: Mapping[str, Any]) -> EnrolmentTicketClaims:
        if claims.get(CLAIM_PURPOSE) != TICKET_PURPOSE:
            raise ModelGrantError(f"the ticket's {CLAIM_PURPOSE} is not {TICKET_PURPOSE}")
        for name in _GRANT_ONLY_CLAIMS:
            if name in claims:
                raise ModelGrantError(f"a ticket carries no {name}")
        issued_at = _number(claims, CLAIM_ISSUED_AT, "ticket")
        expires_at = _number(claims, CLAIM_EXPIRES, "ticket")
        if expires_at <= issued_at:
            raise ModelGrantError("the ticket expires before it is issued")
        return cls(
            audience=_text(claims, CLAIM_AUDIENCE, "ticket"),
            ticket_id=_text(claims, CLAIM_TICKET_ID, "ticket"),
            subject=_text(claims, CLAIM_SUBJECT, "ticket"),
            issued_at=issued_at,
            expires_at=expires_at,
        )
