"""A restart signs nobody out (#900): an app built afresh over the same session file, as after a
deployment restarts the server, accepts the cookie a person was given before it, and still refuses
one that was signed out."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from starlette.testclient import TestClient
from support import JSON_HEADERS, configure_env, dist_dir, with_standards
from test_sign_in import JOSIAH, PUBLIC_URL, come_back, provider_env, start

from dd_app.app import build_app
from dd_app.config import settings_from_env
from dd_app.governance import Governance
from dd_harness.sessions import SESSION_COOKIE
from dd_harness.signin import SignIn, SignInSettings
from dd_harness.testing import FakeIdentityProvider

Server = Callable[[], TestClient]


@pytest.fixture
def idp(env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeIdentityProvider:
    provider = FakeIdentityProvider()
    provider_env(monkeypatch, provider)
    monkeypatch.setenv("DD_SESSIONS_FILE", str(tmp_path / "sessions" / "app.db"))
    return provider


@pytest.fixture
def server(idp: FakeIdentityProvider, tmp_path: Path) -> Server:
    """Starts the app as `main` does, its sessions where the environment says: each call is the
    server started again."""
    dist = dist_dir(tmp_path)

    def started() -> TestClient:
        settings = settings_from_env()
        configured = SignInSettings.from_env(
            os.environ, settings, "http://127.0.0.1:7860", public_url_variable="DD_APP_PUBLIC_URL"
        )
        assert configured is not None
        flow = SignIn(
            configured, keys=idp.keys(), client=httpx.AsyncClient(transport=idp.transport())
        )
        governance = with_standards(Governance.create(settings, PUBLIC_URL, flow.authenticator))
        return TestClient(build_app(governance, dist, sign_in=flow), base_url=PUBLIC_URL)

    return started


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return configure_env(monkeypatch, tmp_path)


def signed_in(idp: FakeIdentityProvider, browser: TestClient) -> str:
    """Sign `browser` in, and return the session identifier its cookie holds."""
    come_back(browser, idp.approve(start(browser), JOSIAH))
    session_id = browser.cookies.get(SESSION_COOKIE)
    assert session_id
    return session_id


def holding(browser: TestClient, session_id: str) -> TestClient:
    browser.cookies.set(SESSION_COOKIE, session_id, domain="app.test")
    return browser


def test_a_person_is_still_signed_in_after_a_restart(
    idp: FakeIdentityProvider, server: Server
) -> None:
    session_id = signed_in(idp, server())
    assert holding(server(), session_id).get("/api/agents").status_code == 200


def test_signing_out_holds_across_a_restart(idp: FakeIdentityProvider, server: Server) -> None:
    before = server()
    session_id = signed_in(idp, before)
    assert before.post("/api/sign-out", headers=JSON_HEADERS).status_code == 204
    assert holding(server(), session_id).get("/api/agents").status_code == 401
