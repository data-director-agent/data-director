"""What the app presents to GitHub when it files a problem report (docs/specs/app.md).

Two credentials are understood. A `StaticToken` is a fine-grained personal access token. An
`AppInstallation` is a GitHub App's private key: the app signs a short-lived JWT, exchanges it for
an installation token narrowed to one repository and to Issues, and keeps that token until just
before it expires. The App is the better choice for a deployment: it belongs to the organisation,
not a person, and its key never reaches GitHub as a bearer credential.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import httpx
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import RSAKey

from dd_sdk.credentials import ConfigError

GITHUB_API = "https://api.github.com"
API_VERSION = "2022-11-28"

TOKEN_VARIABLE = "DD_FEEDBACK_GITHUB_TOKEN"
APP_ID_VARIABLE = "DD_FEEDBACK_GITHUB_APP_ID"
INSTALLATION_VARIABLE = "DD_FEEDBACK_GITHUB_APP_INSTALLATION_ID"
APP_KEY_FILE_VARIABLE = "DD_FEEDBACK_GITHUB_APP_PRIVATE_KEY_FILE"

# GitHub accepts an app JWT that lives at most ten minutes, and tolerates a slow clock by an
# issued-at in the past.
JWT_LIFETIME_SECONDS = 540
JWT_BACKDATE_SECONDS = 60
# An installation token is replaced this long before it expires, so one is never sent as it lapses.
REFRESH_MARGIN_SECONDS = 60


class GitHubAuthError(RuntimeError):
    """GitHub would not give the app a token, or could not be reached."""


class TokenSource(Protocol):
    """Where the bearer token for GitHub's API comes from."""

    async def token(self, client: httpx.AsyncClient) -> str: ...

    def invalidate(self) -> bool:
        """Forget the token after GitHub refused it; True if asking again may give another."""
        ...


@dataclass(frozen=True)
class StaticToken:
    value: str

    async def token(self, client: httpx.AsyncClient) -> str:
        return self.value

    def invalidate(self) -> bool:
        return False


def headers(bearer: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {bearer}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
    }


@dataclass
class AppInstallation:
    """A GitHub App installed on one repository, `repo` as `owner/name`.

    `installation_id` may be left out: it is then found from the repository, which the App must be
    installed on. The key is read when this is made, so a bad one stops the server at start-up.
    """

    app_id: str
    private_key: str
    repo: str
    installation_id: str | None = None
    clock: Callable[[], float] = time.time
    _key: RSAKey = field(init=False, repr=False)
    _token: str | None = field(default=None, init=False, repr=False)
    _expires: float = field(default=0.0, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            self._key = RSAKey.import_key(self.private_key)
        except (JoseError, ValueError) as exc:
            raise ConfigError(
                f"{APP_KEY_FILE_VARIABLE}: not an RSA private key in PEM form"
            ) from exc

    def app_jwt(self) -> str:
        """The App's own short-lived credential, for asking about its installations."""
        now = int(self.clock())
        claims = {
            "iss": self.app_id,
            "iat": now - JWT_BACKDATE_SECONDS,
            "exp": now + JWT_LIFETIME_SECONDS,
        }
        return jwt.encode({"alg": "RS256"}, claims, self._key)

    async def token(self, client: httpx.AsyncClient) -> str:
        async with self._lock:
            if self._token is None or self.clock() >= self._expires - REFRESH_MARGIN_SECONDS:
                self._token, self._expires = await self._mint(client)
            return self._token

    def invalidate(self) -> bool:
        self._token = None
        return True

    async def _mint(self, client: httpx.AsyncClient) -> tuple[str, float]:
        bearer = headers(self.app_jwt())
        try:
            if self.installation_id is None:
                found = await client.get(
                    f"{GITHUB_API}/repos/{self.repo}/installation", headers=bearer
                )
                self.installation_id = str(_json(found, 200, "the App's installation")["id"])
            response = await client.post(
                f"{GITHUB_API}/app/installations/{self.installation_id}/access_tokens",
                headers=bearer,
                json={
                    "repositories": [self.repo.split("/", 1)[-1]],
                    "permissions": {"issues": "write"},
                },
            )
        except httpx.HTTPError as exc:
            raise GitHubAuthError(
                f"GitHub could not be reached for a token ({type(exc).__name__})."
            ) from exc
        granted = _json(response, 201, "an installation token")
        try:
            expires = datetime.fromisoformat(granted["expires_at"]).timestamp()
            return granted["token"], expires
        except (KeyError, TypeError, ValueError) as exc:
            raise GitHubAuthError("GitHub's installation token had an unexpected shape.") from exc


def _json(response: httpx.Response, expected: int, what: str) -> dict[str, Any]:
    if response.status_code != expected:
        raise GitHubAuthError(f"GitHub answered {response.status_code} for {what}.")
    try:
        body = response.json()
    except ValueError as exc:
        raise GitHubAuthError(f"GitHub's answer for {what} was not JSON.") from exc
    if not isinstance(body, dict):
        raise GitHubAuthError(f"GitHub's answer for {what} was not an object.")
    return body


def credential_file(env: Mapping[str, str], variable: str) -> str | None:
    """The text of the file `env[variable]` names, or None if it is unset.

    A relative path is resolved against `$CREDENTIALS_DIRECTORY`, as `dd_sdk.credentials.api_key`
    does, so a systemd `LoadCredential=` works. Unreadable or empty is a `ConfigError`.
    """
    file = env.get(variable)
    if not file:
        return None
    path = Path(file)
    if not path.is_absolute():
        directory = env.get("CREDENTIALS_DIRECTORY")
        if not directory:
            raise ConfigError(f"{variable}={file} is relative and CREDENTIALS_DIRECTORY is not set")
        path = Path(directory) / path
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ConfigError(f"{variable}: cannot read {path}: {exc.strerror}") from exc
    if not text:
        raise ConfigError(f"{variable}: {path} is empty")
    return text


def token_from_env(env: Mapping[str, str]) -> str | None:
    """The static token, from `DD_FEEDBACK_GITHUB_TOKEN` or the file `..._FILE`, or None."""
    value, file = (env.get(TOKEN_VARIABLE) or "").strip(), env.get(f"{TOKEN_VARIABLE}_FILE")
    if value and file:
        raise ConfigError(f"set {TOKEN_VARIABLE} or {TOKEN_VARIABLE}_FILE, not both")
    return value or credential_file(env, f"{TOKEN_VARIABLE}_FILE")


def source_from_env(env: Mapping[str, str], repo: str) -> TokenSource | None:
    """The credential the environment configures for `repo`, or None: reports are then off.

    A static token, or a GitHub App (`DD_FEEDBACK_GITHUB_APP_ID` with the key file, and
    optionally the installation). Configuring both, or half an App, is a `ConfigError`.
    """
    token = token_from_env(env)
    app_id = (env.get(APP_ID_VARIABLE) or "").strip()
    installation = (env.get(INSTALLATION_VARIABLE) or "").strip()
    key = credential_file(env, APP_KEY_FILE_VARIABLE)
    if token and (app_id or key):
        raise ConfigError(
            f"set a static token ({TOKEN_VARIABLE}) or a GitHub App ({APP_ID_VARIABLE}), not both"
        )
    if token:
        return StaticToken(token)
    if not (app_id or key or installation):
        return None
    if not (app_id and key):
        raise ConfigError(f"a GitHub App needs both {APP_ID_VARIABLE} and {APP_KEY_FILE_VARIABLE}")
    return AppInstallation(app_id, key, repo, installation or None)
