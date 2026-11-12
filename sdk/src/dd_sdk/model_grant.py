"""The model grant's format (docs/specs/model-accounts.md, The grant).

A model grant lets one invocation of one agent call models through the model broker, paid for by
the account the conductor chose. The harness signs it as a JWT. The broker verifies it. The agent
only forwards it, as an opaque value, and never parses it.

This module holds only what the harness, the broker and the agent's adapter must agree on: the
claim names, the account values, the algorithms, the metadata key and the HTTP headers. Minting is
the conductor's job (TODO(#808)). Verifying is the broker's own code (`dd_broker.grants`), because
checking a grant is governance ([Dependencies](../../../docs/specs/dependencies.md)).

`ModelGrantClaims.from_claims` checks that a verified claim set has the shape below. It does not
check a signature, an audience or a time; the broker does that before calling it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

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


class Payer(StrEnum):
    """Whose account paid for one call, as the broker reports it and a run records it."""

    OWN = "own"
    DEPLOYMENT = "deployment"


class ModelGrantError(ValueError):
    """A claim set does not have the model grant's shape. The message names the claim, never a
    claim's value."""


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

    @classmethod
    def from_claims(cls, claims: Mapping[str, Any]) -> ModelGrantClaims:
        def text(name: str) -> str:
            value = claims.get(name)
            if not isinstance(value, str) or not value:
                raise ModelGrantError(f"the grant's {name} is missing or not a string")
            return value

        def number(name: str) -> int:
            value = claims.get(name)
            # bool is an int in Python; a time is never true or false.
            if not isinstance(value, int) or isinstance(value, bool):
                raise ModelGrantError(f"the grant's {name} is missing or not an integer")
            return value

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
        )
