"""What the deposit broker reads at start-up, from the environment
(docs/guide/operations/deposit-broker.md).

Every secret is read once, when the broker starts, as `NAME` in development or `NAME_FILE` in
deployment, where a relative path is resolved against systemd's `$CREDENTIALS_DIRECTORY`
(`dd_sdk.credentials.api_key`). A missing or malformed setting is a `SettingsError`, which stops
the broker in one line that never contains a secret.

Secrets, each as `NAME` or `NAME_FILE`:

- `DD_DEPOSIT_BROKER_KEY_ENCRYPTION_KEY`: 32 random bytes, base64. Seals every token at rest.
- `DD_DEPOSIT_BROKER_SUBJECT_KEY`: the broker's private EC P-256 key, as a JWK or PEM. Opens the
  pseudonym sealed in each grant and ticket. The harness is given its public half.
- `DD_DEPOSIT_BROKER_OAUTH_CLIENTS`: optional JSON, `{"<API root>": {"client_id": "…",
  "client_secret": "…"}}`: the deployment's OAuth application at each repository installation
  that offers OAuth. A repository without one is connected by pasting a token.

Other settings:

- `DD_DEPOSIT_BROKER_HARNESS_JWKS_URL` or `DD_DEPOSIT_BROKER_HARNESS_JWKS_FILE`: the harness's
  public signing keys. Exactly one is required.
- `DD_DEPOSIT_BROKER_STORE`: the SQLite file for sealed tokens. Required.
- `DD_DEPOSIT_BROKER_ALLOWED_BASE_URLS`: the repository API roots the broker may call,
  comma-separated, each `transport=https://…`, such as `zenodo=https://sandbox.zenodo.org/api`.
  Required: a grant naming any other is refused, which is what keeps a practice deployment off a
  production repository.
- `DD_DEPOSIT_BROKER_PUBLIC_URL`: where the browser reaches the broker through the reverse proxy,
  such as `https://datadir-dev.shef.ac.uk/deposit-broker`; the OAuth redirect URI is under it.
  Required when any OAuth client is set.
- `DD_DEPOSIT_BROKER_APP_URL`: the app's own origin, where the browser returns after connecting
  an account. Required when any OAuth client is set.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from joserfc.jwk import ECKey

from dd_deposit_broker import zenodo
from dd_deposit_broker.seal import KEY_ENCRYPTION_KEY_BYTES
from dd_deposit_broker.tokens import subject_key
from dd_sdk.credentials import ConfigError, api_key

KEY_ENCRYPTION_KEY = "DD_DEPOSIT_BROKER_KEY_ENCRYPTION_KEY"
SUBJECT_KEY = "DD_DEPOSIT_BROKER_SUBJECT_KEY"
OAUTH_CLIENTS = "DD_DEPOSIT_BROKER_OAUTH_CLIENTS"
HARNESS_JWKS_URL = "DD_DEPOSIT_BROKER_HARNESS_JWKS_URL"
HARNESS_JWKS_FILE = "DD_DEPOSIT_BROKER_HARNESS_JWKS_FILE"
STORE = "DD_DEPOSIT_BROKER_STORE"
ALLOWED_BASE_URLS = "DD_DEPOSIT_BROKER_ALLOWED_BASE_URLS"
PUBLIC_URL = "DD_DEPOSIT_BROKER_PUBLIC_URL"
APP_URL = "DD_DEPOSIT_BROKER_APP_URL"
# The transports the broker can deposit through.
TRANSPORTS = (zenodo.NAME,)


class SettingsError(ValueError):
    """The broker's configuration is unusable. It stops at start-up with this one line."""


@dataclass(frozen=True)
class DepositBrokerSettings:
    key_encryption_key: bytes = field(repr=False)
    subject_key: ECKey = field(repr=False)
    store: Path
    # API root -> transport.
    allowed: Mapping[str, str]
    oauth_clients: Mapping[str, zenodo.OAuthClient] = field(default_factory=dict, repr=False)
    harness_jwks_url: str | None = None
    harness_jwks_file: Path | None = None
    public_url: str | None = None
    app_url: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> DepositBrokerSettings:
        env = os.environ if env is None else env
        kek = _key_encryption_key(env)
        try:
            subject = subject_key(_secret(env, SUBJECT_KEY))
        except ValueError as exc:
            raise SettingsError(f"{SUBJECT_KEY}: {exc}") from None
        jwks_url, jwks_file = _text(env, HARNESS_JWKS_URL), _text(env, HARNESS_JWKS_FILE)
        if bool(jwks_url) == bool(jwks_file):
            raise SettingsError(f"set one of {HARNESS_JWKS_URL} or {HARNESS_JWKS_FILE}")
        if jwks_url and urlsplit(jwks_url).scheme not in {"http", "https"}:
            raise SettingsError(f"{HARNESS_JWKS_URL} is not an http(s) URL")
        store = _text(env, STORE)
        if not store:
            raise SettingsError(f"set {STORE} to the deposit broker's SQLite file")
        allowed = _allowed(_text(env, ALLOWED_BASE_URLS))
        clients = _oauth_clients(env, allowed)
        public_url = _https(env, PUBLIC_URL)
        app_url = _https(env, APP_URL)
        if clients and (public_url is None or app_url is None):
            raise SettingsError(f"connecting through OAuth needs {PUBLIC_URL} and {APP_URL}")
        return cls(
            key_encryption_key=kek,
            subject_key=subject,
            store=Path(store),
            allowed=allowed,
            oauth_clients=clients,
            harness_jwks_url=jwks_url or None,
            harness_jwks_file=Path(jwks_file) if jwks_file else None,
            public_url=public_url,
            app_url=app_url,
        )


def _secret(env: Mapping[str, str], name: str) -> str:
    try:
        return api_key(env, name)
    except ConfigError as exc:
        raise SettingsError(str(exc)) from None


def _text(env: Mapping[str, str], name: str) -> str:
    return (env.get(name) or "").strip()


def _https(env: Mapping[str, str], name: str) -> str | None:
    value = _text(env, name)
    if not value:
        return None
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.query or parts.fragment:
        raise SettingsError(f"{name} is not a plain https URL")
    return value.rstrip("/")


def _key_encryption_key(env: Mapping[str, str]) -> bytes:
    try:
        kek = base64.b64decode(_secret(env, KEY_ENCRYPTION_KEY), validate=True)
    except binascii.Error, ValueError:
        raise SettingsError(f"{KEY_ENCRYPTION_KEY} is not base64") from None
    if len(kek) != KEY_ENCRYPTION_KEY_BYTES:
        raise SettingsError(
            f"{KEY_ENCRYPTION_KEY} is not {KEY_ENCRYPTION_KEY_BYTES} bytes "
            f"(make one with: openssl rand -base64 {KEY_ENCRYPTION_KEY_BYTES})"
        )
    return kek


def base_url(value: str) -> str:
    """An API root as the broker compares them: https, no query, no trailing slash."""
    parts = urlsplit(value.strip())
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError("an API root must be an https URL")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("an API root carries no user, query or fragment")
    return value.strip().rstrip("/")


def _allowed(value: str) -> dict[str, str]:
    allowed: dict[str, str] = {}
    for entry in (e.strip() for e in value.split(",")):
        if not entry:
            continue
        transport, _, url = entry.partition("=")
        if transport not in TRANSPORTS:
            raise SettingsError(
                f"{ALLOWED_BASE_URLS}: each entry is transport=https://…, with a transport of "
                f"{', '.join(TRANSPORTS)}"
            )
        try:
            allowed[base_url(url)] = transport
        except ValueError as exc:
            raise SettingsError(f"{ALLOWED_BASE_URLS}: {exc}") from None
    if not allowed:
        raise SettingsError(f"set {ALLOWED_BASE_URLS} to the repository API roots it may call")
    return allowed


def _oauth_clients(
    env: Mapping[str, str], allowed: Mapping[str, str]
) -> dict[str, zenodo.OAuthClient]:
    if not (_text(env, OAUTH_CLIENTS) or _text(env, f"{OAUTH_CLIENTS}_FILE")):
        return {}
    try:
        data = json.loads(_secret(env, OAUTH_CLIENTS))
    except ValueError:
        raise SettingsError(f"{OAUTH_CLIENTS} is not JSON") from None
    if not isinstance(data, dict):
        raise SettingsError(f"{OAUTH_CLIENTS} maps each API root to a client")
    clients: dict[str, zenodo.OAuthClient] = {}
    for url, client in data.items():
        try:
            root = base_url(str(url))
        except ValueError as exc:
            raise SettingsError(f"{OAUTH_CLIENTS}: {exc}") from None
        if root not in allowed:
            raise SettingsError(f"{OAUTH_CLIENTS} names an API root not in {ALLOWED_BASE_URLS}")
        if (
            not isinstance(client, dict)
            or not isinstance(client.get("client_id"), str)
            or not isinstance(client.get("client_secret"), str)
            or not client["client_id"]
            or not client["client_secret"]
        ):
            raise SettingsError(f"{OAUTH_CLIENTS}: each client has a client_id and client_secret")
        clients[root] = zenodo.OAuthClient(client["client_id"], client["client_secret"])
    return clients
