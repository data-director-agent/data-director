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
"""

from __future__ import annotations

import os
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dd_harness.settings import StorageLocation, storage_location

DEFAULT_APP_URL = "http://127.0.0.1:7860"
DEFAULT_FEEDBACK_REPO = "data-director-agent/data-director"


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
        )
