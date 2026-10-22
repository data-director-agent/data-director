"""Model credentials, read once when an agent starts (ADR-0026).

Only the agent that calls a model holds its key. `api_key(env)` finds it in one of two places:
`ANTHROPIC_API_KEY` in development, or `ANTHROPIC_API_KEY_FILE` in deployment. A relative file
path is resolved against `$CREDENTIALS_DIRECTORY`, where systemd's `LoadCredential=` puts the
file. An absolute path suits a container secret. If both are set, or neither, or the file is
empty, the result is a `ConfigError`. `dd_sdk.serve.main` reports it in one line and exits, so
the agent stops at start-up and does not start failing every run.

The key is passed to the model client explicitly. Nothing is taken from the provider SDK's own
credential chain, such as a CLI login in the home directory. A `ConfigError` message names the
variable or the path, never the key.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


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
