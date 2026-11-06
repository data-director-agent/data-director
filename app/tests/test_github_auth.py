"""GitHub App credentials for problem reports (docs/specs/app.md): the JWT, the installation
token, its caching, and how the environment chooses between a token and an App."""

from __future__ import annotations

import asyncio
import functools
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from joserfc import jwt
from joserfc.jwk import RSAKey

from dd_app import feedback, github_auth
from dd_app.github_auth import AppInstallation, GitHubAuthError, StaticToken
from dd_sdk.credentials import ConfigError

REPO = "data-director-agent/data-director"
KEY = RSAKey.generate_key(2048)
PEM = KEY.as_pem(private=True).decode()
NOW = 1_800_000_000.0


def sync(test: Callable[..., Awaitable[None]]) -> Callable[..., None]:
    """Run an async test to completion (the repository has no async pytest plugin)."""

    @functools.wraps(test)
    def run(*args: Any, **kwargs: Any) -> None:
        asyncio.run(test(*args, **kwargs))

    return run


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> float:
        return self.now


def github(
    seen: list[httpx.Request], expires_in: int = 3600, installation: int = 99
) -> httpx.AsyncClient:
    """A GitHub that knows one installation and mints `ghs_1`, `ghs_2`, ... on demand."""
    minted = 0

    def answer(request: httpx.Request) -> httpx.Response:
        nonlocal minted
        seen.append(request)
        if request.url.path == f"/repos/{REPO}/installation":
            return httpx.Response(200, json={"id": installation})
        if request.url.path == f"/app/installations/{installation}/access_tokens":
            minted += 1
            expires = int(NOW) + expires_in
            return httpx.Response(
                201,
                json={
                    "token": f"ghs_{minted}",
                    "expires_at": _iso(expires),
                },
            )
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(answer))


def _iso(seconds: int) -> str:
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def app(
    clock: Callable[[], float] | None = None, installation: str | None = None
) -> AppInstallation:
    return AppInstallation("12345", PEM, REPO, installation, clock=clock or Clock())


@sync
async def test_the_app_jwt_is_signed_for_the_app_and_short_lived() -> None:
    token = jwt.decode(app().app_jwt(), KEY)
    assert token.header["alg"] == "RS256"
    assert token.claims == {"iss": "12345", "iat": int(NOW) - 60, "exp": int(NOW) + 540}


@sync
async def test_the_installation_is_found_and_the_token_is_narrowed() -> None:
    seen: list[httpx.Request] = []
    source = app()
    assert await source.token(github(seen)) == "ghs_1"
    find, mint = seen
    assert find.method == "GET" and mint.method == "POST"
    # Both calls are made as the App, with a JWT that GitHub could verify.
    for request in seen:
        bearer = request.headers["authorization"].removeprefix("Bearer ")
        assert jwt.decode(bearer, KEY).claims["iss"] == "12345"
    assert json.loads(mint.content) == {
        "repositories": ["data-director"],
        "permissions": {"issues": "write"},
    }


@sync
async def test_a_configured_installation_is_not_looked_up() -> None:
    seen: list[httpx.Request] = []
    assert await app(installation="99").token(github(seen)) == "ghs_1"
    assert [r.method for r in seen] == ["POST"]


@sync
async def test_the_token_is_reused_until_just_before_it_expires() -> None:
    clock, seen = Clock(), list[httpx.Request]()
    source, client = app(clock, "99"), github(seen)
    assert await source.token(client) == "ghs_1"
    clock.now = NOW + 3600 - 61
    assert await source.token(client) == "ghs_1"
    clock.now = NOW + 3600 - 59
    assert await source.token(client) == "ghs_2"
    assert len(seen) == 2


@sync
async def test_invalidating_asks_for_a_new_token() -> None:
    source, client = app(installation="99"), github([])
    assert await source.token(client) == "ghs_1"
    assert source.invalidate() is True
    assert await source.token(client) == "ghs_2"
    assert StaticToken("t").invalidate() is False


@pytest.mark.parametrize("status", [401, 403, 404])
@sync
async def test_github_refusing_the_app_is_a_named_failure(status: int) -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(status)))
    with pytest.raises(GitHubAuthError, match=str(status)):
        await app(installation="99").token(client)


@sync
async def test_an_unreachable_github_is_a_named_failure() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    client = httpx.AsyncClient(transport=httpx.MockTransport(down))
    with pytest.raises(GitHubAuthError, match="ConnectError"):
        await app(installation="99").token(client)


def test_a_key_that_is_not_a_private_key_stops_start_up() -> None:
    with pytest.raises(ConfigError, match="PRIVATE_KEY_FILE"):
        AppInstallation("1", "not a key", REPO)


@sync
async def test_a_refused_token_is_replaced_once_when_filing_an_issue() -> None:
    clock, seen = Clock(), list[httpx.Request]()
    revoked = {"ghs_1"}

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.startswith("/app/installations/"):
            return httpx.Response(
                201, json={"token": f"ghs_{len(seen)}", "expires_at": _iso(int(NOW) + 3600)}
            )
        token = request.headers["authorization"].removeprefix("Bearer ")
        if token in revoked:
            return httpx.Response(401)
        return httpx.Response(201, json={"html_url": "https://github.test/i/7", "number": 7})

    client = httpx.AsyncClient(transport=httpx.MockTransport(answer))
    report = feedback.Report(kind="bug", title="t", description="d")
    created = await feedback.create_issue(
        report, "body", repo=REPO, source=app(clock, "99"), client=client
    )
    assert created == {"url": "https://github.test/i/7", "number": 7}
    posts = [r for r in seen if r.url.path.endswith("/issues")]
    assert len(posts) == 2


@sync
async def test_a_static_token_that_is_refused_is_not_retried() -> None:
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(401)

    client = httpx.AsyncClient(transport=httpx.MockTransport(answer))
    report = feedback.Report(kind="bug", title="t", description="d")
    with pytest.raises(feedback.FeedbackFailedError, match="401"):
        await feedback.create_issue(
            report, "body", repo=REPO, source=StaticToken("t"), client=client
        )
    assert len(seen) == 1


@sync
async def test_a_failure_to_get_a_token_is_a_failed_report() -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    report = feedback.Report(kind="bug", title="t", description="d")
    with pytest.raises(feedback.FeedbackFailedError, match="GitHub answered 401"):
        await feedback.create_issue(
            report, "body", repo=REPO, source=app(installation="99"), client=client
        )


def test_the_environment_chooses_a_token_an_app_or_nothing(tmp_path: Path) -> None:
    (tmp_path / "app.pem").write_text(PEM, encoding="utf-8")
    key = {github_auth.APP_KEY_FILE_VARIABLE: "app.pem", "CREDENTIALS_DIRECTORY": str(tmp_path)}
    app_env = {github_auth.APP_ID_VARIABLE: "12345", **key}

    assert github_auth.source_from_env({}, REPO) is None
    assert github_auth.source_from_env({github_auth.TOKEN_VARIABLE: "t"}, REPO) == StaticToken("t")

    source = github_auth.source_from_env({**app_env, github_auth.INSTALLATION_VARIABLE: "99"}, REPO)
    assert isinstance(source, AppInstallation)
    assert (source.app_id, source.repo, source.installation_id) == ("12345", REPO, "99")
    found = github_auth.source_from_env(app_env, REPO)
    assert isinstance(found, AppInstallation) and found.installation_id is None


def test_a_token_and_an_app_together_or_half_an_app_stop_start_up(tmp_path: Path) -> None:
    (tmp_path / "app.pem").write_text(PEM, encoding="utf-8")
    key = {github_auth.APP_KEY_FILE_VARIABLE: str(tmp_path / "app.pem")}
    app_id = {github_auth.APP_ID_VARIABLE: "12345"}
    token = {github_auth.TOKEN_VARIABLE: "t"}
    for env in ({**token, **app_id, **key}, {**token, **key}, app_id, key):
        with pytest.raises(ConfigError):
            github_auth.source_from_env(env, REPO)
    with pytest.raises(ConfigError, match="cannot read"):
        github_auth.source_from_env({**app_id, github_auth.APP_KEY_FILE_VARIABLE: "/nope"}, REPO)
    with pytest.raises(ConfigError, match="relative"):
        github_auth.source_from_env({**app_id, github_auth.APP_KEY_FILE_VARIABLE: "app.pem"}, REPO)
