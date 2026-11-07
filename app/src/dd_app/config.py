"""The app's reference configuration: the files it supplies to the harness as defaults.

The harness has no defaults of its own (docs/specs/system.md). The app brings a reference set in
`app/config/` (its profile, agent list and source list), writes runs to `app/runs/` and keeps
projects in `app/projects/`. A `DD_*` variable still wins over each of them.
"""

from __future__ import annotations

from pathlib import Path

from dd_harness.settings import Settings

APP_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = APP_ROOT / "config"
# `profile.yaml` is a local copy of the committed `profile.yaml.example`, ignored by git so that
# it can be edited freely; without one, the example is used.
LOCAL_PROFILE = CONFIG_DIR / "profile.yaml"
EXAMPLE_PROFILE = CONFIG_DIR / "profile.yaml.example"
DEFAULT_PROFILE = LOCAL_PROFILE if LOCAL_PROFILE.exists() else EXAMPLE_PROFILE
DEFAULT_AGENTS_CONFIG = CONFIG_DIR / "agents.yaml"
DEFAULT_SOURCES_CONFIG = CONFIG_DIR / "sources.yaml"
DEFAULT_RUNS_DIR = APP_ROOT / "runs"
# Each project's log and the content its events added (`dd_harness.projects`).
DEFAULT_PROJECTS_DIR = APP_ROOT / "projects"
# The deployment's repository requirement sets (docs/specs/deposit.md, `dd_harness.requirements`).
DEFAULT_REPOSITORIES_DIR = CONFIG_DIR / "repositories"
# Example inputs the Run tab offers, each naming its class (`examples/README.md`).
EXAMPLES_DIR = CONFIG_DIR / "examples"
# Where `npm run build` in app/web writes the shell (docs/specs/app.md).
WEB_DIST = APP_ROOT / "web" / "dist"


def settings_from_env() -> Settings:
    """The environment's settings, with the app's reference set for any path left unset."""
    return Settings.from_env(
        runs_dir=DEFAULT_RUNS_DIR,
        profile=DEFAULT_PROFILE,
        agents_config=DEFAULT_AGENTS_CONFIG,
        sources_config=DEFAULT_SOURCES_CONFIG,
    )
