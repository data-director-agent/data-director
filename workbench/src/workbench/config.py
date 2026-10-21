"""The workbench's development configuration: the files it supplies to the harness as defaults.

The harness has no defaults of its own for these (ADR-0022). The workbench brings a development
set (its profiles, `agents.yaml`, `sources.yaml`, a `runs/` directory and a local `.env`), and a
`DD_*` variable still wins over each of them.
"""

from __future__ import annotations

from pathlib import Path

from dd_harness.settings import Settings

WORKBENCH_ROOT = Path(__file__).resolve().parents[2]
PROFILES_DIR = WORKBENCH_ROOT / "profiles"
DEFAULT_PROFILE = PROFILES_DIR / "default.yaml"
DEFAULT_RUNS_DIR = WORKBENCH_ROOT / "runs"
DEFAULT_AGENTS_CONFIG = WORKBENCH_ROOT / "agents.yaml"
DEFAULT_SOURCES_CONFIG = WORKBENCH_ROOT / "sources.yaml"
DEFAULT_ENV_FILE = WORKBENCH_ROOT / ".env"


def settings_from_env() -> Settings:
    """The environment's settings, with the workbench's files for any path left unset."""
    return Settings.from_env(
        runs_dir=DEFAULT_RUNS_DIR,
        profile=DEFAULT_PROFILE,
        agents_config=DEFAULT_AGENTS_CONFIG,
        sources_config=DEFAULT_SOURCES_CONFIG,
    )
