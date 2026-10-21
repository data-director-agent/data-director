"""The app's reference configuration: the files it supplies to the harness as defaults.

The harness has no defaults of its own (ADR-0022). The app brings a reference set in
`app/config/` (its profile, agent list and source list) and writes runs to `app/runs/`. A
`DD_*` variable still wins over each of them.
"""

from __future__ import annotations

from pathlib import Path

from dd_harness.settings import Settings

APP_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = APP_ROOT / "config"
DEFAULT_PROFILE = CONFIG_DIR / "profile.yaml"
DEFAULT_AGENTS_CONFIG = CONFIG_DIR / "agents.yaml"
DEFAULT_SOURCES_CONFIG = CONFIG_DIR / "sources.yaml"
DEFAULT_RUNS_DIR = APP_ROOT / "runs"


def settings_from_env() -> Settings:
    """The environment's settings, with the app's reference set for any path left unset."""
    return Settings.from_env(
        runs_dir=DEFAULT_RUNS_DIR,
        profile=DEFAULT_PROFILE,
        agents_config=DEFAULT_AGENTS_CONFIG,
        sources_config=DEFAULT_SOURCES_CONFIG,
    )
