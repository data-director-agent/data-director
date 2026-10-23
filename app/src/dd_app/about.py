"""Which build is running: the app and harness versions and the commit (`GET /api/about`).

The commit comes from `DD_REVISION`, else from a `REVISION` file at the root of the release
(`deploy/deploy.sh` writes it, as a release has no `.git`), else from `git` in a development
checkout. A build that none of these identifies has no commit, and says so with null.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

# app/src/dd_app/about.py -> the repository (or release) root.
ROOT = Path(__file__).resolve().parents[3]
GIT_TIMEOUT_SECONDS = 5


def _version(distribution: str) -> str | None:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return None


def commit(env: Mapping[str, str] | None = None, root: Path = ROOT) -> str | None:
    """The full commit hash of this build, or None if it cannot be told."""
    env = os.environ if env is None else env
    if declared := (env.get("DD_REVISION") or "").strip():
        return declared
    try:
        if recorded := (root / "REVISION").read_text(encoding="utf-8").strip():
            return recorded
    except OSError:
        pass
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        return None
    return done.stdout.strip() or None if done.returncode == 0 else None


def about(env: Mapping[str, str] | None = None, root: Path = ROOT) -> dict[str, str | None]:
    return {
        "app_version": _version("data-director-app"),
        "harness_version": _version("data-director-harness"),
        "commit": commit(env, root),
    }
