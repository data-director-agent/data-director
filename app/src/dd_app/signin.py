"""Signing a person in through OpenID Connect (ADR-0029, #152).

The app is the relying party and a confidential client. `GET /api/sign-in` sends the browser to
the provider's authorisation endpoint with a fresh `state` and `nonce`, asking for the `openid`
scope only. The provider sends it back to `GET /api/sign-in/callback` with a code. The app checks
the `state` against the one this browser was given, redeems the code at the token endpoint with
`client_secret_post`, and verifies the ID token with `dd_harness.identity.verify_id_token`, the
same function the harness's own server uses. It then keeps the principal in a server-side session
(`dd_app.sessions`) and forgets every token. Nothing calls the provider's API.

The provider is configuration: `DD_OIDC_ISSUER`, `DD_OIDC_CLIENT_ID` and `DD_OIDC_CLIENT_SECRET`
(or `DD_OIDC_CLIENT_SECRET_FILE`). With no issuer, the app is a development server: every run acts
for the operator named in `DD_PRINCIPAL_ID`, records `asserted`, and the shell says on every page
that nobody is signed in. A provider beside an operator principal stops start-up.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx

from dd_app.sessions import DEFAULT_IDLE_S, DEFAULT_LIFETIME_S, SessionAuthenticator, SessionStore
from dd_harness.identity import (
    FETCH_TIMEOUT_S,
    IssuerKeys,
    OidcProvider,
    Unauthenticated,
    checked_configuration,
    configuration_url,
    verify_id_token,
)
from dd_harness.settings import Settings, build_authenticator
from dd_sdk.contract.models import Principal
from dd_sdk.credentials import ConfigError, api_key

CALLBACK_PATH = "/api/sign-in/callback"
SECRET_VARIABLE = "DD_OIDC_CLIENT_SECRET"
PUBLIC_URL_VARIABLE = "DD_APP_PUBLIC_URL"
IDLE_VARIABLE = "DD_SESSION_IDLE_S"
LIFETIME_VARIABLE = "DD_SESSION_LIFETIME_S"


@dataclass(frozen=True)
class SignInSettings:
    provider: OidcProvider
    client_secret: str = field(repr=False)
    # Where people reach the app, which the provider sends them back to. It must be the redirect
    # URI registered with the provider, less `CALLBACK_PATH`.
    public_url: str
    idle_s: int = DEFAULT_IDLE_S
    lifetime_s: int = DEFAULT_LIFETIME_S

    @property
    def redirect_uri(self) -> str:
        return self.public_url.rstrip("/") + CALLBACK_PATH

    @classmethod
    def from_env(
        cls, env: Mapping[str, str], settings: Settings, base_url: str
    ) -> SignInSettings | None:
        """The provider the environment configures, or None for a development server. Raises
        `IdentityError` or `ConfigError` for a configuration that cannot be served."""
        if settings.oidc_issuer is None:
            return None
        # The harness's rules: no operator principal beside a provider, and a client ID.
        build_authenticator(settings)
        assert settings.oidc_client_id is not None
        if not (env.get(SECRET_VARIABLE) or env.get(f"{SECRET_VARIABLE}_FILE")):
            raise ConfigError(
                f"{SECRET_VARIABLE} unset: DD_OIDC_ISSUER needs the client secret "
                f"(set {SECRET_VARIABLE}_FILE in deployment)"
            )
        return cls(
            provider=OidcProvider(settings.oidc_issuer, settings.oidc_client_id),
            client_secret=api_key(env, SECRET_VARIABLE),
            public_url=env.get(PUBLIC_URL_VARIABLE) or base_url,
            idle_s=_seconds(env, IDLE_VARIABLE, DEFAULT_IDLE_S),
            lifetime_s=_seconds(env, LIFETIME_VARIABLE, DEFAULT_LIFETIME_S),
        )


def _seconds(env: Mapping[str, str], name: str, default: int) -> int:
    value = env.get(name)
    if not value:
        return default
    try:
        seconds = int(value)
    except ValueError:
        seconds = 0
    if seconds <= 0:
        raise ConfigError(f"{name}={value!r} is not a whole number of seconds above nought")
    return seconds


def safe_return_to(value: str | None) -> str:
    """A page of this app to come back to after signing in: a path, never another site's URL."""
    if not value or not value.startswith("/") or value.startswith(("//", "/\\", "/api/")):
        return "/"
    return value


class SignIn:
    """The authorisation-code flow against one provider, and the sessions it opens."""

    def __init__(
        self,
        settings: SignInSettings,
        *,
        store: SessionStore | None = None,
        keys: IssuerKeys | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """`keys` and `client` let a test stand in for the provider's keys and endpoints
        (`dd_harness.testing.FakeIdentityProvider`)."""
        self.settings = settings
        self.store = store or SessionStore(settings.idle_s, settings.lifetime_s)
        self.authenticator = SessionAuthenticator(self.store)
        self._keys = keys or IssuerKeys(settings.provider.issuer)
        self._client = client
        self._configuration: dict[str, Any] | None = None

    @property
    def issuer(self) -> str:
        return self.settings.provider.issuer

    async def _send(self, request: httpx.Request) -> httpx.Response:
        if self._client is not None:
            return await self._client.send(request)
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_S) as client:
            return await client.send(request)

    async def configuration(self) -> dict[str, Any]:
        """The provider's discovery document, fetched once and kept."""
        if self._configuration is None:
            try:
                response = await self._send(httpx.Request("GET", configuration_url(self.issuer)))
                response.raise_for_status()
                self._configuration = checked_configuration(self.issuer, response.json())
            except (httpx.HTTPError, ValueError) as exc:
                raise Unauthenticated(
                    f"the sign-in settings of {self.issuer} could not be fetched: "
                    f"{type(exc).__name__}"
                ) from exc
        return self._configuration

    async def start(self, return_to: str | None) -> tuple[str, str]:
        """The provider's authorisation URL for a new sign-in, and its `state`."""
        configuration = await self.configuration()
        state, nonce = self.store.begin(safe_return_to(return_to))
        query = urlencode(
            {
                "client_id": self.settings.provider.client_id,
                "response_type": "code",
                # ADR-0029: `openid` only, which yields the iD and the name, and no email address.
                "scope": "openid",
                "redirect_uri": self.settings.redirect_uri,
                "state": state,
                "nonce": nonce,
            }
        )
        return f"{configuration['authorization_endpoint']}?{query}", state

    async def finish(
        self, code: str | None, state: str | None, browser_state: str | None
    ) -> tuple[str, str]:
        """A new session's identifier, and the page to return to, once the code from the
        provider is redeemed and its ID token verified. Raises `Unauthenticated` otherwise; no
        session is opened."""
        if not state or state != browser_state:
            raise Unauthenticated("this sign-in was not started in this browser")
        pending = self.store.take(state)
        if pending is None:
            raise Unauthenticated("the sign-in has expired or was already used: sign in again")
        if not code:
            raise Unauthenticated("the provider sent no code")
        principal = await self._redeem(code, pending.nonce)
        return self.store.create(principal), pending.return_to

    async def _redeem(self, code: str, nonce: str) -> Principal:
        configuration = await self.configuration()
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.settings.redirect_uri,
            # ORCID authenticates a client by `client_secret_post` only (ADR-0029).
            "client_id": self.settings.provider.client_id,
            "client_secret": self.settings.client_secret,
        }
        request = httpx.Request(
            "POST",
            configuration["token_endpoint"],
            data=form,
            headers={"Accept": "application/json"},
        )
        try:
            response = await self._send(request)
            answer = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise Unauthenticated(
                f"the provider's token endpoint could not be reached: {type(exc).__name__}"
            ) from exc
        if response.status_code != 200 or not isinstance(answer, dict):
            error = answer.get("error") if isinstance(answer, dict) else None
            raise Unauthenticated(
                f"the provider refused the code ({response.status_code} {error or ''})".strip()
            )
        token = answer.get("id_token")
        if not isinstance(token, str):
            raise Unauthenticated("the provider sent no ID token")
        # Off the event loop: verifying may fetch the issuer's keys. The token, and the access
        # token beside it, go no further than this function.
        return await asyncio.to_thread(
            verify_id_token, token, self.settings.provider, self._keys, nonce=nonce
        )
