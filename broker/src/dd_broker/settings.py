"""What the broker reads at start-up, from the environment (docs/guide/operations/model-broker.md).

Every secret is read once, when the broker starts, as an agent reads its model key
(`dd_sdk.credentials.api_key`): `NAME` in development, or `NAME_FILE` in deployment, where a
relative path is resolved against systemd's `$CREDENTIALS_DIRECTORY`. A missing or malformed
setting is a `SettingsError`, which stops the broker in one line that never contains a secret.

Secrets, each as `NAME` or `NAME_FILE`:

- `DD_BROKER_KEY_ENCRYPTION_KEY`: 32 random bytes, base64. Seals every key at rest. Required.
- `DD_BROKER_SUBJECT_KEY`: the broker's private EC P-256 key, as a JWK or PEM. Opens the
  pseudonym sealed in each grant. Required.
- `DD_BROKER_AGENT_CREDENTIALS`: JSON, `{"<agent id>": "<SHA-256 hex of its credential>"}`.
  Required.
- `ANTHROPIC_API_KEY`: the deployment's key, or a LiteLLM gateway key when
  `DD_BROKER_DEPLOYMENT_BASE_URL` is set. Without it, a call the deployment pays for is refused.

Other settings:

- `DD_BROKER_HARNESS_JWKS_URL` or `DD_BROKER_HARNESS_JWKS_FILE`: the harness's public signing
  keys. Exactly one is required.
- `DD_BROKER_STORE`: the SQLite file for sealed keys and token counts. Required.
- `DD_BROKER_DEPLOYMENT_BASE_URL`: where the deployment's calls go, such as the LiteLLM gateway
  (default: the provider).
- `DD_BROKER_ALLOWED_BASE_URLS`: origins a person's own account may name, comma-separated.
- `DD_BROKER_PRIVATE_BASE_URLS`: allowed origins that may resolve to private addresses.
"""

from __future__ import annotations

import base64
import binascii
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from joserfc.jwk import ECKey

from dd_broker.agents import AgentCredentials
from dd_broker.grants import subject_key
from dd_broker.guard import BaseUrlRefused, origin
from dd_broker.seal import KEY_ENCRYPTION_KEY_BYTES
from dd_sdk.credentials import ConfigError, api_key

KEY_ENCRYPTION_KEY = "DD_BROKER_KEY_ENCRYPTION_KEY"
SUBJECT_KEY = "DD_BROKER_SUBJECT_KEY"
AGENT_CREDENTIALS = "DD_BROKER_AGENT_CREDENTIALS"
HARNESS_JWKS_URL = "DD_BROKER_HARNESS_JWKS_URL"
HARNESS_JWKS_FILE = "DD_BROKER_HARNESS_JWKS_FILE"
STORE = "DD_BROKER_STORE"
DEPLOYMENT_KEY = "ANTHROPIC_API_KEY"
DEPLOYMENT_BASE_URL = "DD_BROKER_DEPLOYMENT_BASE_URL"
ALLOWED_BASE_URLS = "DD_BROKER_ALLOWED_BASE_URLS"
PRIVATE_BASE_URLS = "DD_BROKER_PRIVATE_BASE_URLS"


class SettingsError(ValueError):
    """The broker's configuration is unusable. It stops at start-up with this one line."""


@dataclass(frozen=True)
class BrokerSettings:
    key_encryption_key: bytes = field(repr=False)
    subject_key: ECKey = field(repr=False)
    agents: AgentCredentials = field(repr=False)
    store: Path
    harness_jwks_url: str | None = None
    harness_jwks_file: Path | None = None
    deployment_key: str | None = field(default=None, repr=False)
    deployment_base_url: str | None = None
    allowed_base_urls: tuple[str, ...] = ()
    private_base_urls: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> BrokerSettings:
        env = os.environ if env is None else env

        def secret(name: str) -> str:
            try:
                return api_key(env, name)
            except ConfigError as exc:
                raise SettingsError(str(exc)) from None

        def text(name: str) -> str:
            return (env.get(name) or "").strip()

        try:
            kek = base64.b64decode(secret(KEY_ENCRYPTION_KEY), validate=True)
        except binascii.Error, ValueError:
            raise SettingsError(f"{KEY_ENCRYPTION_KEY} is not base64") from None
        if len(kek) != KEY_ENCRYPTION_KEY_BYTES:
            raise SettingsError(
                f"{KEY_ENCRYPTION_KEY} is not {KEY_ENCRYPTION_KEY_BYTES} bytes "
                f"(make one with: openssl rand -base64 {KEY_ENCRYPTION_KEY_BYTES})"
            )
        try:
            subject = subject_key(secret(SUBJECT_KEY))
        except ValueError as exc:
            raise SettingsError(f"{SUBJECT_KEY}: {exc}") from None
        try:
            agents = AgentCredentials.from_json(secret(AGENT_CREDENTIALS))
        except ValueError as exc:
            raise SettingsError(f"{AGENT_CREDENTIALS}: {exc}") from None

        jwks_url, jwks_file = text(HARNESS_JWKS_URL), text(HARNESS_JWKS_FILE)
        if bool(jwks_url) == bool(jwks_file):
            raise SettingsError(f"set one of {HARNESS_JWKS_URL} or {HARNESS_JWKS_FILE}")
        if jwks_url and urlsplit(jwks_url).scheme not in {"http", "https"}:
            raise SettingsError(f"{HARNESS_JWKS_URL} is not an http(s) URL")

        store = text(STORE)
        if not store:
            raise SettingsError(f"set {STORE} to the broker's SQLite file")

        deployment_key = None
        if text(DEPLOYMENT_KEY) or text(f"{DEPLOYMENT_KEY}_FILE"):
            deployment_key = secret(DEPLOYMENT_KEY)
        deployment_base_url = text(DEPLOYMENT_BASE_URL) or None
        if deployment_base_url and urlsplit(deployment_base_url).scheme not in {"http", "https"}:
            raise SettingsError(f"{DEPLOYMENT_BASE_URL} is not an http(s) URL")

        def origins(name: str) -> tuple[str, ...]:
            entries = [entry for entry in text(name).split(",") if entry.strip()]
            try:
                return tuple(origin(entry) for entry in entries)
            except BaseUrlRefused as exc:
                raise SettingsError(f"{name}: {exc}") from None

        return cls(
            key_encryption_key=kek,
            subject_key=subject,
            agents=agents,
            store=Path(store),
            harness_jwks_url=jwks_url or None,
            harness_jwks_file=Path(jwks_file) if jwks_file else None,
            deployment_key=deployment_key,
            deployment_base_url=deployment_base_url.rstrip("/") if deployment_base_url else None,
            allowed_base_urls=origins(ALLOWED_BASE_URLS),
            private_base_urls=origins(PRIVATE_BASE_URLS),
        )
