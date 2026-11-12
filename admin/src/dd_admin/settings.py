"""What the admin service reads, from the environment. Every setting is optional: a page whose
setting is unset says so rather than failing, so the service also runs on a developer's machine.

| Variable | What it names |
|---|---|
| `DD_RUNS_DIR`, `DD_PROJECTS_DIR` | The app's run and project stores, as the app names them |
| `DD_AGENTS_CONFIG` | The `agents.yaml` the app reads |
| `DD_ADMIN_APP_URL` | The app, for `/api/about` (default `http://127.0.0.1:7860`) |
| `DD_ADMIN_DOCTOR` | The command that prints `data-director doctor --json` |
| `DD_ADMIN_DEPLOY_ROOT` | `/opt/data-director`: releases, `current`, failed commits |
| `DD_ADMIN_ETC` | `/etc/data-director`: the settings shown on the configuration page |
| `DD_ADMIN_SYSTEMD` | `yes` to read units' states and journals with `systemctl` and `journalctl` |
| `DD_FEEDBACK_REPO` | Where the app files feedback (default `data-director-agent/data-director`) |
| `DD_ADMIN_LITELLM_URL` | The LLM gateway (`deploy/llm-gateway/`), for prices and spend |
| `DD_ADMIN_LITELLM_KEY_FILE` | A read-only gateway key (else the unit's `litellm-key` credential) |
| `DD_ADMIN_MONTHLY_BUDGET` | A month's budget, in the gateway's currency; shown, not enforced |
"""

from __future__ import annotations

import os
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dd_harness.settings import SettingsError, StorageLocation, storage_location

DEFAULT_APP_URL = "http://127.0.0.1:7860"
DEFAULT_FEEDBACK_REPO = "data-director-agent/data-director"
# The name the gateway key is loaded under (LoadCredential=litellm-key:…), in the unit's drop-in.
LITELLM_CREDENTIAL = "litellm-key"


@dataclass(frozen=True)
class AdminSettings:
    runs: StorageLocation | None = None
    projects: StorageLocation | None = None
    agents_config: Path | None = None
    app_url: str = DEFAULT_APP_URL
    doctor: tuple[str, ...] = ()
    deploy_root: Path | None = None
    etc: Path | None = None
    systemd: bool = False
    feedback_repo: str = DEFAULT_FEEDBACK_REPO
    litellm_url: str | None = None
    litellm_key_file: Path | None = None
    monthly_budget: float | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> AdminSettings:
        env = os.environ if env is None else env

        def path(name: str) -> Path | None:
            value = env.get(name, "").strip()
            return Path(value) if value else None

        def store(name: str) -> StorageLocation | None:
            value = env.get(name, "").strip()
            return storage_location(value, name) if value else None

        return cls(
            runs=store("DD_RUNS_DIR"),
            projects=store("DD_PROJECTS_DIR"),
            agents_config=path("DD_AGENTS_CONFIG"),
            app_url=env.get("DD_ADMIN_APP_URL", "").strip() or DEFAULT_APP_URL,
            doctor=tuple(shlex.split(env.get("DD_ADMIN_DOCTOR", ""))),
            deploy_root=path("DD_ADMIN_DEPLOY_ROOT"),
            etc=path("DD_ADMIN_ETC"),
            systemd=env.get("DD_ADMIN_SYSTEMD", "").strip().lower() in {"1", "yes", "true"},
            feedback_repo=env.get("DD_FEEDBACK_REPO", "").strip() or DEFAULT_FEEDBACK_REPO,
            litellm_url=env.get("DD_ADMIN_LITELLM_URL", "").strip().rstrip("/") or None,
            litellm_key_file=path("DD_ADMIN_LITELLM_KEY_FILE") or _credential(env),
            monthly_budget=_budget(env.get("DD_ADMIN_MONTHLY_BUDGET", "").strip()),
        )


def _credential(env: Mapping[str, str]) -> Path | None:
    """The gateway key systemd loaded for the unit, if its drop-in loads one."""
    directory = env.get("CREDENTIALS_DIRECTORY", "").strip()
    if not directory:
        return None
    found = Path(directory) / LITELLM_CREDENTIAL
    return found if found.is_file() else None


def _budget(value: str) -> float | None:
    if not value:
        return None
    try:
        budget = float(value)
    except ValueError:
        budget = -1.0
    if not budget > 0 or budget == float("inf"):
        raise SettingsError(f"DD_ADMIN_MONTHLY_BUDGET must be a positive number, not {value!r}")
    return budget
