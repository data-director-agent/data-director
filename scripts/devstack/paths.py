"""Where the development stack's settings and sources are.

The other modules read these as `paths.NAME`, never by importing the name, so that tests can
point them at a scratch repository.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Development's copy of /etc/data-director/ (ADR-0026): the same files, under one ignored directory.
LOCAL_DIR = ROOT / "config" / "local"
EXAMPLES_DIR = ROOT / "config" / "examples"
APP_ENV = LOCAL_DIR / "app.env"
AGENTS_ENV = LOCAL_DIR / "agents.env"
AGENT_ENV_DIR = LOCAL_DIR / "agents"
CREDENTIALS_DIR = LOCAL_DIR / "credentials"
AGENTS_CONFIG = ROOT / "app" / "config" / "agents.yaml"
PROFILE_EXAMPLE = ROOT / "app" / "config" / "profile.yaml.example"
PROFILE = ROOT / "app" / "config" / "profile.yaml"
WEB = ROOT / "app" / "web"
