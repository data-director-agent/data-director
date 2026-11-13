"""Model credentials, read once when an agent starts (docs/specs/policy-and-identity.md).

Only the agent that calls a model holds its key. `api_key(env)` finds it in one of two places:
`ANTHROPIC_API_KEY` in development, or `ANTHROPIC_API_KEY_FILE` in deployment. A relative file
path is resolved against `$CREDENTIALS_DIRECTORY`, where systemd's `LoadCredential=` puts the
file. An absolute path suits a container secret. If both are set, or neither, or the file is
empty, the result is a `ConfigError`. `dd_sdk.serve.main` reports it in one line and exits, so
the agent stops at start-up and does not start failing every run.

The key is passed to the model client explicitly. Nothing is taken from the provider SDK's own
credential chain, such as a CLI login in the home directory. A `ConfigError` message names the
variable or the path, never the key.

`model_endpoint(env)` is where a model-backed agent sends its calls, and with what credential
(docs/specs/model-accounts.md). With `DD_MODEL_BROKER_URL` set, the agent calls the model broker
with its own broker credential, `DD_MODEL_BROKER_CREDENTIAL` or `DD_MODEL_BROKER_CREDENTIAL_FILE`,
and holds no provider key. Otherwise it calls the provider with its key, as above.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

BROKER_URL = "DD_MODEL_BROKER_URL"
BROKER_CREDENTIAL = "DD_MODEL_BROKER_CREDENTIAL"
PROVIDER_KEY = "ANTHROPIC_API_KEY"
# Where the broker serves the Anthropic Messages API, below its base URL.
BROKER_ANTHROPIC_PATH = "/anthropic"


class ConfigError(ValueError):
    """An agent's configuration is unusable. The agent stops at start-up with this one line."""


def api_key(env: Mapping[str, str], name: str = "ANTHROPIC_API_KEY") -> str:
    """The key named `name`, taken from `env[name]` or from the file `env[name + "_FILE"]`."""
    file_var = f"{name}_FILE"
    value, file = (env.get(name) or "").strip(), env.get(file_var)
    if value and file:
        raise ConfigError(f"set {name} or {file_var}, not both")
    if value:
        return value
    if not file:
        raise ConfigError(f"no model key: set {name} (development) or {file_var} (deployment)")
    path = Path(file)
    if not path.is_absolute():
        directory = env.get("CREDENTIALS_DIRECTORY")
        if not directory:
            raise ConfigError(f"{file_var}={file} is relative and CREDENTIALS_DIRECTORY is not set")
        path = Path(directory) / path
    try:
        key = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ConfigError(f"{file_var}: cannot read {path}: {exc.strerror}") from exc
    if not key:
        raise ConfigError(f"{file_var}: {path} is empty")
    return key


@dataclass(frozen=True)
class ModelEndpoint:
    """Where a model client sends its calls: the provider (`base_url` None) with the provider key,
    or the model broker with the agent's own broker credential. `repr` never shows the credential.
    """

    api_key: str
    base_url: str | None = None

    @property
    def brokered(self) -> bool:
        return self.base_url is not None

    def __repr__(self) -> str:
        return f"ModelEndpoint(base_url={self.base_url!r})"


def model_endpoint(env: Mapping[str, str]) -> ModelEndpoint:
    """The endpoint a model-backed agent calls, read once at start-up.

    With `DD_MODEL_BROKER_URL` set, the broker's Anthropic interface and the agent's broker
    credential; a provider key set beside it is a `ConfigError`, because an agent that calls
    through the broker holds none (docs/specs/model-accounts.md, invariant 14). Otherwise the
    provider, with `api_key(env)`.
    """
    url = (env.get(BROKER_URL) or "").strip().rstrip("/")
    if not url:
        return ModelEndpoint(api_key(env, PROVIDER_KEY))
    if not url.startswith(("http://", "https://")):
        raise ConfigError(f"{BROKER_URL} is not an http or https URL")
    if env.get(PROVIDER_KEY) or env.get(f"{PROVIDER_KEY}_FILE"):
        raise ConfigError(
            f"set {BROKER_URL} or {PROVIDER_KEY}, not both: an agent that calls through the "
            "model broker holds no provider key"
        )
    try:
        credential = api_key(env, BROKER_CREDENTIAL)
    except ConfigError as exc:
        if env.get(BROKER_CREDENTIAL) or env.get(f"{BROKER_CREDENTIAL}_FILE"):
            raise
        raise ConfigError(
            f"no model broker credential: set {BROKER_CREDENTIAL} (development) or "
            f"{BROKER_CREDENTIAL}_FILE (deployment)"
        ) from exc
    return ModelEndpoint(credential, url + BROKER_ANTHROPIC_PATH)
