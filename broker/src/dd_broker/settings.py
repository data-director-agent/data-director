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
- `DD_BROKER_ADMIN_CREDENTIAL`: the SHA-256 hex digest of the operators' credential, which the
  admin service presents to read `GET /admin/summary` (`dd_broker.admin`). Optional; without it
  the route is not served.
- The deployment's key for each provider it pays for, or a LiteLLM gateway key when
  `DD_BROKER_DEPLOYMENT_BASE_URL` is set: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
  `GEMINI_API_KEY`, and `DD_MODEL_API_KEY` for `openai-compatible`, which the deployment pays for
  only through the gateway. Each is optional; a call the deployment would pay for, to a provider
  without its key, is refused.

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

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from joserfc.jwk import ECKey

from dd_broker import anthropic, chat_completions
from dd_broker.agents import AgentCredentials, OperatorCredential
from dd_broker.grants import subject_key
from dd_broker.guard import BaseUrlRefused, origin
from dd_broker.seal import KEY_ENCRYPTION_KEY_BYTES
from dd_sdk.credentials import ConfigError, api_key, key_encryption_key
from dd_sdk.harness_tokens import jwks_source

KEY_ENCRYPTION_KEY = "DD_BROKER_KEY_ENCRYPTION_KEY"
SUBJECT_KEY = "DD_BROKER_SUBJECT_KEY"
AGENT_CREDENTIALS = "DD_BROKER_AGENT_CREDENTIALS"
HARNESS_JWKS_URL = "DD_BROKER_HARNESS_JWKS_URL"
HARNESS_JWKS_FILE = "DD_BROKER_HARNESS_JWKS_FILE"
STORE = "DD_BROKER_STORE"
ADMIN_CREDENTIAL = "DD_BROKER_ADMIN_CREDENTIAL"
# The variable each provider's deployment key is read from, by provider.
DEPLOYMENT_KEYS = {
    anthropic.PROVIDER: "ANTHROPIC_API_KEY",
    **{name: p.deployment_key for name, p in chat_completions.PROVIDERS.items()},
}
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
    deployment_keys: Mapping[str, str] = field(default_factory=dict, repr=False)
    deployment_base_url: str | None = None
    allowed_base_urls: tuple[str, ...] = ()
    private_base_urls: tuple[str, ...] = ()
    operator: OperatorCredential | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> BrokerSettings:
        env = os.environ if env is None else env
        kek = _key_encryption_key(env)
        try:
            subject = subject_key(_secret(env, SUBJECT_KEY))
        except ValueError as exc:
            raise SettingsError(f"{SUBJECT_KEY}: {exc}") from None
        try:
            agents = AgentCredentials.from_json(_secret(env, AGENT_CREDENTIALS))
        except ValueError as exc:
            raise SettingsError(f"{AGENT_CREDENTIALS}: {exc}") from None

        try:
            jwks_url, jwks_file = jwks_source(env, HARNESS_JWKS_URL, HARNESS_JWKS_FILE)
        except ConfigError as exc:
            raise SettingsError(str(exc)) from None

        store = _text(env, STORE)
        if not store:
            raise SettingsError(f"set {STORE} to the broker's SQLite file")

        deployment_keys = {
            provider: _secret(env, name)
            for provider, name in DEPLOYMENT_KEYS.items()
            if _text(env, name) or _text(env, f"{name}_FILE")
        }
        deployment_base_url = _text(env, DEPLOYMENT_BASE_URL) or None
        if deployment_base_url and urlsplit(deployment_base_url).scheme not in {"http", "https"}:
            raise SettingsError(f"{DEPLOYMENT_BASE_URL} is not an http(s) URL")

        return cls(
            key_encryption_key=kek,
            subject_key=subject,
            agents=agents,
            store=Path(store),
            harness_jwks_url=jwks_url,
            harness_jwks_file=jwks_file,
            deployment_keys=deployment_keys,
            deployment_base_url=deployment_base_url.rstrip("/") if deployment_base_url else None,
            allowed_base_urls=_origins(env, ALLOWED_BASE_URLS),
            private_base_urls=_origins(env, PRIVATE_BASE_URLS),
            operator=_operator(env),
        )


def _secret(env: Mapping[str, str], name: str) -> str:
    try:
        return api_key(env, name)
    except ConfigError as exc:
        raise SettingsError(str(exc)) from None


def _operator(env: Mapping[str, str]) -> OperatorCredential | None:
    """The operators' credential digest, if the deployment set one."""
    if not (_text(env, ADMIN_CREDENTIAL) or _text(env, f"{ADMIN_CREDENTIAL}_FILE")):
        return None
    try:
        return OperatorCredential.from_digest(_secret(env, ADMIN_CREDENTIAL))
    except ValueError as exc:
        raise SettingsError(f"{ADMIN_CREDENTIAL}: {exc}") from None


def _text(env: Mapping[str, str], name: str) -> str:
    return (env.get(name) or "").strip()


def _key_encryption_key(env: Mapping[str, str]) -> bytes:
    """The key-encryption key `env` holds, decoded and of the right length."""
    try:
        return key_encryption_key(env, KEY_ENCRYPTION_KEY, KEY_ENCRYPTION_KEY_BYTES)
    except ConfigError as exc:
        raise SettingsError(str(exc)) from None


def _origins(env: Mapping[str, str], name: str) -> tuple[str, ...]:
    entries = [entry for entry in _text(env, name).split(",") if entry.strip()]
    try:
        return tuple(origin(entry) for entry in entries)
    except BaseUrlRefused as exc:
        raise SettingsError(f"{name}: {exc}") from None
