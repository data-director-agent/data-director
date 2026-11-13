"""Model grants: the conductor's authority for one invocation of one agent to call models through
the model broker (docs/specs/model-accounts.md, The grant).

`GrantMinter.mint` signs a grant as a JWT with the harness's private key. It names the person the
run acts for only by a pseudonym, a keyed hash of their identifier, sealed to the broker as a JWE
so that the agent that forwards the grant cannot read it, and each grant carries a different
sealed value. The claim names and algorithms are those `dd_sdk.model_grant` fixes, and the broker
verifies them (`dd_broker.grants`). `GrantMinter.jwks` is the public half of the signing key, which
the harness publishes for the broker.

`GrantMinter.enrolment_ticket` signs the grant's sibling with the same key: a single-use ticket
that lets the browser read, add or remove the signed-in person's own model account at the broker
(docs/specs/model-accounts.md, Enrolment). It names the person by the same sealed pseudonym, and
nothing else.

A grant holds no key, no principal and no project content. The conductor passes it to the agent in
the A2A request's metadata and nowhere else (invariant 6).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import secrets
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from joserfc import jwe, jwt
from joserfc.errors import JoseError
from joserfc.jwk import ECKey, KeySet, RSAKey
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from dd_sdk.contract.models import Principal
from dd_sdk.model_grant import (
    BROKER_AUDIENCE,
    CLAIM_ACCOUNT,
    CLAIM_AGENT,
    CLAIM_AUDIENCE,
    CLAIM_BASE_URLS,
    CLAIM_EXPIRES,
    CLAIM_INVOCATION,
    CLAIM_ISSUED_AT,
    CLAIM_MODELS,
    CLAIM_PROVIDERS,
    CLAIM_PURPOSE,
    CLAIM_SUBJECT,
    CLAIM_TICKET_ID,
    SUBJECT_ENCRYPTION,
    SUBJECT_KEY_ALGORITHM,
    TICKET_LIFETIME_S,
    TICKET_PURPOSE,
    TICKET_TYPE,
    Account,
)

# Where the harness publishes its public signing keys: the broker's `DD_BROKER_HARNESS_JWKS_URL`.
JWKS_PATH = "/.well-known/jwks.json"

# A shorter secret would make the pseudonym guessable from the identifiers it hides.
MIN_PSEUDONYM_SECRET_BYTES = 32


class GrantKeyError(ValueError):
    """A grant key or secret is unusable. The message names what is wrong, never the material."""


def signing_key(material: str) -> RSAKey | ECKey:
    """The harness's private signing key, from a JWK (JSON) or a PEM: an RSA key (RS256) or an
    EC P-256 key (ES256). A key without a `kid` is given its RFC 7638 thumbprint."""
    key = _import(material, "the model grant signing key")
    if not key.is_private:
        raise GrantKeyError("the model grant signing key is not a private key")
    if isinstance(key, ECKey) and key.curve_name != "P-256":
        raise GrantKeyError("the model grant signing key is an EC key not on P-256")
    if not key.kid:
        key = type(key).import_key(key.as_dict(private=True), {"kid": key.thumbprint()})
    return key


def broker_subject_key(material: str) -> ECKey:
    """The broker's public P-256 key, to which every pseudonym is sealed, from a JWK or a PEM.
    The harness needs only the public half, so a private key is refused."""
    key = _import(material, "the broker's subject key")
    if not isinstance(key, ECKey) or key.curve_name != "P-256":
        raise GrantKeyError("the broker's subject key is not an EC P-256 key")
    if key.is_private:
        raise GrantKeyError(
            "the broker's subject key is a private key; give the harness only its public half"
        )
    return key


def _import(material: str, what: str) -> RSAKey | ECKey:
    text = material.strip()
    if text.startswith("{"):
        try:
            data: Mapping[str, Any] | str = json.loads(text)
        except ValueError as exc:
            raise GrantKeyError(f"{what} is not valid JSON") from exc
        kty = data.get("kty") if isinstance(data, Mapping) else None
        kinds: tuple[type[RSAKey] | type[ECKey], ...] = (
            (RSAKey,) if kty == "RSA" else (ECKey,) if kty == "EC" else ()
        )
    else:
        data, kinds = text, (RSAKey, ECKey)
    for kind in kinds:
        try:
            return kind.import_key(data)  # type: ignore[arg-type]
        except JoseError, ValueError, TypeError:
            continue
    raise GrantKeyError(f"{what} is not an RSA or EC key as a JWK or PEM")


@dataclass(frozen=True)
class GrantMinter:
    """Mints the model grants the conductor sends to model-backed agents."""

    signing_key: RSAKey | ECKey
    subject_key: ECKey
    pseudonym_secret: bytes = field(repr=False)
    clock: Callable[[], float] = time.time

    def __post_init__(self) -> None:
        if len(self.pseudonym_secret) < MIN_PSEUDONYM_SECRET_BYTES:
            raise GrantKeyError(
                f"the pseudonym secret is shorter than {MIN_PSEUDONYM_SECRET_BYTES} bytes"
            )

    @classmethod
    def from_material(cls, signing: str, subject: str, secret: str) -> GrantMinter:
        """A minter from the three settings as text, as the harness reads them at start-up."""
        return cls(signing_key(signing), broker_subject_key(subject), secret.encode("utf-8"))

    @property
    def algorithm(self) -> str:
        return "RS256" if isinstance(self.signing_key, RSAKey) else "ES256"

    def pseudonym(self, principal: Principal) -> str:
        """The person's pseudonym: a keyed hash of their identifier, the same in every run, from
        which nobody without the secret can recover or test an identifier."""
        digest = hmac.new(
            self.pseudonym_secret, principal.principal_id.encode("utf-8"), hashlib.sha256
        )
        return digest.hexdigest()

    def mint(
        self,
        *,
        agent_id: str,
        invocation_id: str,
        models: Iterable[str],
        account: Account,
        acting_for: Principal,
        lifetime_s: float,
        providers: Iterable[str] = (),
        base_urls: Iterable[str] = (),
    ) -> str:
        """A grant for one invocation of `agent_id` to call `models`, paid for as `account` says,
        for `acting_for`. It expires `lifetime_s` from now, rounded down: no later than the
        invocation's timeout. A grant that may use a person's own account names the `providers`
        and `base_urls` (origins) the profile lets that account use; one the deployment pays for
        names neither."""
        allowed = list(dict.fromkeys(models))
        if not allowed:
            raise ValueError("a model grant needs at least one model")
        own_providers = list(dict.fromkeys(providers))
        own_base_urls = list(dict.fromkeys(base_urls))
        if account is Account.DEPLOYMENT and (own_providers or own_base_urls):
            raise ValueError("a grant the deployment pays for names no own account's provider")
        if account is not Account.DEPLOYMENT and not own_providers:
            raise ValueError("a grant that may use a person's own account needs a provider")
        issued_at = int(self.clock())
        lifetime = max(1, math.floor(lifetime_s))
        claims = {
            CLAIM_AUDIENCE: BROKER_AUDIENCE,
            CLAIM_ISSUED_AT: issued_at,
            CLAIM_EXPIRES: issued_at + lifetime,
            CLAIM_AGENT: agent_id,
            CLAIM_INVOCATION: invocation_id,
            CLAIM_MODELS: allowed,
            CLAIM_ACCOUNT: account.value,
            CLAIM_SUBJECT: self._seal(self.pseudonym(acting_for)),
        }
        if account is not Account.DEPLOYMENT:
            claims[CLAIM_PROVIDERS] = own_providers
            claims[CLAIM_BASE_URLS] = own_base_urls
        return jwt.encode(
            {"alg": self.algorithm, "kid": self.signing_key.kid, "typ": "JWT"},
            claims,
            self.signing_key,
        )

    def enrolment_ticket(
        self, *, acting_for: Principal, lifetime_s: float = TICKET_LIFETIME_S
    ) -> tuple[str, int]:
        """A single-use ticket for `acting_for` to make one request to the broker's enrolment
        interface, and the time it expires. It names them only by their sealed pseudonym."""
        issued_at = int(self.clock())
        expires_at = issued_at + max(1, math.floor(lifetime_s))
        claims = {
            CLAIM_AUDIENCE: BROKER_AUDIENCE,
            CLAIM_ISSUED_AT: issued_at,
            CLAIM_EXPIRES: expires_at,
            CLAIM_TICKET_ID: secrets.token_urlsafe(16),
            CLAIM_PURPOSE: TICKET_PURPOSE,
            CLAIM_SUBJECT: self._seal(self.pseudonym(acting_for)),
        }
        token = jwt.encode(
            {"alg": self.algorithm, "kid": self.signing_key.kid, "typ": TICKET_TYPE},
            claims,
            self.signing_key,
        )
        return token, expires_at

    def _seal(self, pseudonym: str) -> str:
        # A fresh ephemeral key and IV each time, so no two grants carry the same value.
        return jwe.encrypt_compact(
            {"alg": SUBJECT_KEY_ALGORITHM, "enc": SUBJECT_ENCRYPTION},
            pseudonym.encode("utf-8"),
            self.subject_key,
            algorithms=[SUBJECT_KEY_ALGORITHM, SUBJECT_ENCRYPTION],
        )

    def jwks(self) -> dict[str, Any]:
        """The public signing key as a JWK set, for the broker. Never the private half."""
        public = dict(self.signing_key.as_dict(private=False))
        public.update({"use": "sig", "alg": self.algorithm})
        return dict(KeySet.import_key_set({"keys": [public]}).as_dict(private=False))


def jwks_routes(minter: GrantMinter | None) -> list[BaseRoute]:
    """`GET /.well-known/jwks.json`, the public keys the broker verifies grants with. None when
    the harness mints no grants."""
    if minter is None:
        return []
    keys = minter.jwks()

    async def jwks(_request: Request) -> JSONResponse:
        return JSONResponse(keys, headers={"Cache-Control": "max-age=300"})

    return [Route(JWKS_PATH, jwks, methods=["GET"])]
