"""A fake OpenID Connect provider (ADR-0029).

`FakeIdentityProvider` stands in for an OpenID Connect provider such as ORCID: a local signing
key, its published keys, and ID tokens built to order, so that a test of sign-in needs no network
and no real account. Its `transport` serves the discovery document, the keys and the token
endpoint over HTTP, and `approve` plays the person who signs in at the authorisation endpoint, so
a test can run the whole authorisation-code flow.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey

from dd_harness.identity import (
    DISCOVERY,
    BearerTokenAuthenticator,
    IssuerKeys,
    OidcProvider,
)

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
    client_secret: str = "fake-client-secret"
    key: RSAKey = field(default_factory=lambda: _signing_key("fake-1"))
    fetches: int = 0
    # Each form the token endpoint was sent, so a test can see how the client authenticated.
    token_requests: list[dict[str, str]] = field(default_factory=list)
    # Codes `approve` issued that the token endpoint has not redeemed: the redirect URI each was
    # issued for, and the ID token it is redeemed for. Each is used once.
    _codes: dict[str, tuple[str, str]] = field(default_factory=dict, repr=False)

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

    def discovery(self) -> dict[str, Any]:
        """The discovery document, with ORCID's paths."""
        return {
            "issuer": self.issuer,
            "authorization_endpoint": f"{self.issuer}/oauth/authorize",
            "token_endpoint": f"{self.issuer}/oauth/token",
            "jwks_uri": f"{self.issuer}/oauth/jwks",
            "scopes_supported": ["openid"],
            "response_types_supported": ["code"],
            "token_endpoint_auth_methods_supported": ["client_secret_post"],
            "id_token_signing_alg_values_supported": ["RS256"],
        }

    def approve(self, authorize_url: str, sub: str = "0000-0002-1825-0097", **token: Any) -> str:
        """Where the provider sends the browser back once the person sent to `authorize_url`
        signs in as `sub`: the redirect URI with a one-time `code` and the `state` it was sent.
        `token` changes the ID token the code is redeemed for, as `id_token` takes it; the nonce
        is the one sent unless `token` names another. Raises `AssertionError` for a request ORCID
        would not accept."""
        query = _query(authorize_url)
        assert authorize_url.startswith(self.discovery()["authorization_endpoint"] + "?")
        assert query.get("client_id") == self.client_id, "another client"
        assert query.get("response_type") == "code", "not the authorisation-code flow"
        assert query.get("scope") == "openid", "a scope beyond openid (ADR-0029)"
        assert query.get("state") and query.get("nonce"), "no state or no nonce"
        token.setdefault("nonce", query["nonce"])
        code = secrets.token_urlsafe(16)
        self._codes[code] = (query["redirect_uri"], self.id_token(sub, **token))
        return f"{query['redirect_uri']}?{urlencode({'code': code, 'state': query['state']})}"

    def deny(self, authorize_url: str, error: str = "access_denied") -> str:
        """Where the provider sends the browser back when the person declines to sign in."""
        query = _query(authorize_url)
        return f"{query['redirect_uri']}?{urlencode({'error': error, 'state': query['state']})}"

    def transport(self) -> httpx.MockTransport:
        """The provider's HTTP endpoints: discovery, keys, and the token endpoint, which redeems a
        code from `approve` once, for this client authenticating with `client_secret_post`."""

        def answer(request: httpx.Request) -> httpx.Response:
            url = str(request.url.copy_with(query=None))
            endpoints = self.discovery()
            if request.method == "GET" and url == self.issuer.rstrip("/") + DISCOVERY:
                return httpx.Response(200, json=endpoints)
            if request.method == "GET" and url == endpoints["jwks_uri"]:
                return httpx.Response(200, json=self.jwks())
            if request.method == "POST" and url == endpoints["token_endpoint"]:
                form = {k: v[0] for k, v in parse_qs(request.content.decode("ascii")).items()}
                self.token_requests.append(form)
                return self._redeem(form)
            return httpx.Response(404)

        return httpx.MockTransport(answer)

    def _redeem(self, form: dict[str, str]) -> httpx.Response:
        # RFC 6749 §5.2 names the errors.
        if (form.get("client_id"), form.get("client_secret")) != (
            self.client_id,
            self.client_secret,
        ):
            return httpx.Response(401, json={"error": "invalid_client"})
        if form.get("grant_type") != "authorization_code":
            return httpx.Response(400, json={"error": "unsupported_grant_type"})
        issued = self._codes.pop(form.get("code", ""), None)
        if issued is None or issued[0] != form.get("redirect_uri"):
            return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(
            200,
            json={
                "access_token": secrets.token_urlsafe(16),
                "token_type": "bearer",
                "expires_in": FAKE_TOKEN_LIFETIME_S,
                "scope": "openid",
                "id_token": issued[1],
            },
        )


def _query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
