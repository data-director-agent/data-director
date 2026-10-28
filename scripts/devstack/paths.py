"""Where the development stack's settings and sources are.

The other modules read these as `paths.NAME`, never by importing the name, so that tests can
point them at a scratch repository.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROOT_ENV = ROOT / ".env"
WORKBENCH_ENV = ROOT / "workbench" / ".env"
AGENT_ENV_DIR = ROOT / "workbench" / "agents"
AGENTS_CONFIG = ROOT / "app" / "config" / "agents.yaml"
PROFILE_EXAMPLE = ROOT / "app" / "config" / "profile.yaml.example"
PROFILE = ROOT / "app" / "config" / "profile.yaml"
WEB = ROOT / "app" / "web"
