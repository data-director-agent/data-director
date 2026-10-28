"""A fake OpenID Connect provider (ADR-0029).

`FakeIdentityProvider` stands in for an OpenID Connect provider such as ORCID: a local signing
key, its published keys, and ID tokens built to order, so that a test of sign-in needs no network
and no real account.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey

from dd_harness.identity import BearerTokenAuthenticator, IssuerKeys, OidcProvider

# RSA modulus size for the fake provider's key: the smallest that RS256 verifiers accept.
FAKE_KEY_BITS = 2048
FAKE_TOKEN_LIFETIME_S = 600


def _signing_key(kid: str) -> RSAKey:
    return RSAKey.generate_key(FAKE_KEY_BITS, parameters={"kid": kid, "use": "sig", "alg": "RS256"})


@dataclass
class FakeIdentityProvider:
    """An OpenID Connect provider in memory: it signs ID tokens with a local key and publishes
    that key, as ORCID does at its `jwks_uri`. The issuer defaults to ORCID's sandbox, so the
    principals it yields have the form a development deployment records."""

    issuer: str = "https://sandbox.orcid.org"
    client_id: str = "APP-TESTCLIENT0000"
    key: RSAKey = field(default_factory=lambda: _signing_key("fake-1"))
    fetches: int = 0

    @property
    def provider(self) -> OidcProvider:
        return OidcProvider(issuer=self.issuer, client_id=self.client_id)

    def jwks(self, issuer: str = "") -> dict[str, Any]:
        """The published keys: what `IssuerKeys` would fetch from the issuer."""
        self.fetches += 1
        return dict(KeySet([self.key]).as_dict(private=False))

    def keys(self) -> IssuerKeys:
        return IssuerKeys(self.issuer, fetch=self.jwks)

    def authenticator(self) -> BearerTokenAuthenticator:
        return BearerTokenAuthenticator(self.provider, self.keys())

    def rotate(self, kid: str) -> None:
        """Sign with a new key from now on, as a provider rotating its keys does."""
        self.key = _signing_key(kid)

    def id_token(
        self,
        sub: str = "0000-0002-1825-0097",
        *,
        name: str | None = "Josiah Carberry",
        nonce: str | None = None,
        issued_at: int | None = None,
        lifetime_s: int = FAKE_TOKEN_LIFETIME_S,
        audience: str | list[str] | None = None,
        issuer: str | None = None,
        key: RSAKey | None = None,
        **claims: Any,
    ) -> str:
        """An ID token as the provider would issue it; each argument changes one claim, so a
        test can build the token it means to refuse."""
        iat = int(time.time()) if issued_at is None else issued_at
        body: dict[str, Any] = {
            "iss": issuer or self.issuer,
            "aud": self.client_id if audience is None else audience,
            "sub": sub,
            "iat": iat,
            "exp": iat + lifetime_s,
            "auth_time": iat,
            **({"name": name} if name is not None else {}),
            **({"nonce": nonce} if nonce is not None else {}),
            **claims,
        }
        signer = key or self.key
        return jwt.encode({"alg": "RS256", "kid": signer.kid}, body, signer)
