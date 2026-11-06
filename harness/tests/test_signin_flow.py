"""Signing in through OpenID Connect, and the sessions it opens (docs/specs/policy-and-identity.md).

The flow is the harness's, and each way in serves its own routes; the app's tests cover those.
These run the flow itself against `FakeIdentityProvider`, so no test needs the network.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from dd_harness.identity import Unauthenticated
from dd_harness.sessions import PENDING_S, SESSION_COOKIE, SessionAuthenticator, SessionStore
from dd_harness.settings import Settings
from dd_harness.signin import CALLBACK_PATH, SignIn, SignInSettings, safe_return_to
from dd_harness.testing import TEST_PRINCIPAL, FakeIdentityProvider
from dd_sdk.credentials import ConfigError

JOSIAH = "0000-0002-1825-0097"


@dataclass
class Clock:
    now: float = field(default_factory=time.time)

    def __call__(self) -> float:
        return self.now


def settings_for(idp: FakeIdentityProvider, **changes: Any) -> SignInSettings:
    values: dict[str, Any] = {
        "provider": idp.provider,
        "client_secret": idp.client_secret,
        "public_url": "https://example.test",
    }
    return SignInSettings(**(values | changes))


def flow(idp: FakeIdentityProvider, settings: SignInSettings, **kwargs: Any) -> SignIn:
    return SignIn(
        settings, keys=idp.keys(), client=httpx.AsyncClient(transport=idp.transport()), **kwargs
    )


def signed_in(sign_in: SignIn, idp: FakeIdentityProvider, sub: str = JOSIAH) -> str:
    """Run the whole flow and return the new session's identifier."""

    async def go() -> str:
        url, state = await sign_in.start("/")
        query = parse_qs(urlsplit(idp.approve(url, sub)).query)
        session_id, _ = await sign_in.finish(query["code"][0], query["state"][0], state)
        return session_id

    return asyncio.run(go())


def test_the_flow_opens_a_session_for_the_person_who_signed_in():
    idp = FakeIdentityProvider()
    sign_in = flow(idp, settings_for(idp))
    session_id = signed_in(sign_in, idp)
    principal = sign_in.authenticator.principal_for({"cookie": f"{SESSION_COOKIE}={session_id}"})
    assert principal.principal_id == f"https://sandbox.orcid.org/{JOSIAH}"
    assert principal.assurance == "authenticated"


def test_a_way_in_names_its_own_callback_and_cookie():
    idp = FakeIdentityProvider()
    settings = settings_for(idp, public_url="https://example.test:8443/", callback_path="/back")
    assert settings.redirect_uri == "https://example.test:8443/back"
    sign_in = flow(idp, settings, session_cookie="dd_other_session")
    session_id = signed_in(sign_in, idp)
    # The app's cookie, on the same host, names no session here.
    assert sign_in.authenticator.session({"cookie": f"{SESSION_COOKIE}={session_id}"}) is None
    assert sign_in.authenticator.session({"cookie": f"dd_other_session={session_id}"}) is not None


def test_a_callback_with_another_browsers_state_is_refused():
    idp = FakeIdentityProvider()
    sign_in = flow(idp, settings_for(idp))

    async def go() -> None:
        url, _ = await sign_in.start("/")
        query = parse_qs(urlsplit(idp.approve(url)).query)
        await sign_in.finish(query["code"][0], query["state"][0], "another-browser")

    with pytest.raises(Unauthenticated, match="not started in this browser"):
        asyncio.run(go())


def test_a_session_ends_when_idle_and_a_sign_in_when_left():
    clock = Clock()
    store = SessionStore(idle_s=60, lifetime_s=3600, clock=clock)
    authenticator = SessionAuthenticator(store)
    session_id = store.create(TEST_PRINCIPAL)
    headers = {"cookie": f"{SESSION_COOKIE}={session_id}"}
    assert authenticator.session(headers) is not None
    clock.now += 61
    with pytest.raises(Unauthenticated):
        authenticator.principal_for(headers)
    state, _ = store.begin("/")
    clock.now += PENDING_S
    assert store.take(state) is None


@pytest.mark.parametrize(
    "value",
    [None, "", "https://evil.example/", "//evil.example/", "/\\evil.example", "agents", "/api/x"],
)
def test_signing_in_never_returns_to_another_site(value: str | None):
    assert safe_return_to(value) == "/"


def test_from_env_reads_the_public_url_the_way_in_names(tmp_path: Path):
    idp = FakeIdentityProvider()
    settings = Settings(
        runs_dir=tmp_path,
        profile=tmp_path / "profile.yaml",
        agents_config=tmp_path / "agents.yaml",
        sources_config=tmp_path / "sources.yaml",
        oidc_issuer=idp.issuer,
        oidc_client_id=idp.client_id,
    )
    env = {"DD_OIDC_CLIENT_SECRET": "s", "DD_EXAMPLE_PUBLIC_URL": "https://example.test:8443"}
    configured = SignInSettings.from_env(
        env, settings, "http://127.0.0.1:8000", public_url_variable="DD_EXAMPLE_PUBLIC_URL"
    )
    assert configured is not None
    assert configured.redirect_uri == f"https://example.test:8443{CALLBACK_PATH}"
    with pytest.raises(ConfigError, match="DD_OIDC_CLIENT_SECRET unset"):
        SignInSettings.from_env({}, settings, "http://x", public_url_variable="DD_X")
