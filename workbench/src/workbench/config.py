"""The workbench's development configuration: the files it supplies to the harness as defaults.

The harness has no defaults of its own for these (ADR-0022). The workbench brings a development
set (its profiles, `agents.yaml`, `sources.yaml`, a `runs/` directory and a local `.env`), and a
`DD_*` variable still wins over each of them.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from dd_harness.settings import Settings

WORKBENCH_ROOT = Path(__file__).resolve().parents[2]
PROFILES_DIR = WORKBENCH_ROOT / "profiles"
DEFAULT_PROFILE = PROFILES_DIR / "default.yaml"
DEFAULT_RUNS_DIR = WORKBENCH_ROOT / "runs"
DEFAULT_AGENTS_CONFIG = WORKBENCH_ROOT / "agents.yaml"
DEFAULT_SOURCES_CONFIG = WORKBENCH_ROOT / "sources.yaml"
# The directory of settings files the `workbench` command reads when DD_CONFIG_DIR names one: the
# development tree `scripts/dev.py setup` creates (config/local), which the workbench does not own.
CONFIG_DIR_VARIABLE = "DD_CONFIG_DIR"
CONFIG_DIR_FILES = ("app.env", "agents.env")
# The example person every run acts for when the operator names no one (ADR-0018). Josiah
# Carberry is the fictitious researcher ORCID publishes for examples. Runs are recorded
# `assurance: asserted`, so a record naming him shows that nobody's identity was checked.
DEFAULT_PRINCIPAL_ID = "https://orcid.org/0000-0002-1825-0097"
DEFAULT_PRINCIPAL_NAME = "Josiah Carberry"


def settings_from_env() -> Settings:
    """The environment's settings, with the workbench's files for any path left unset, and the
    example principal when no one is named (and no OpenID Connect provider is configured)."""
    settings = Settings.from_env(
        runs_dir=DEFAULT_RUNS_DIR,
        profile=DEFAULT_PROFILE,
        agents_config=DEFAULT_AGENTS_CONFIG,
        sources_config=DEFAULT_SOURCES_CONFIG,
    )
    if not (settings.principal_id or settings.principal_name or settings.oidc_issuer):
        settings = replace(
            settings, principal_id=DEFAULT_PRINCIPAL_ID, principal_name=DEFAULT_PRINCIPAL_NAME
        )
    return settings
