"""What the app's tests share beyond fixtures (`conftest.py`)."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from dd_agent_advisor_standards import factory as standards
from dd_app.config import settings_from_env
from dd_app.governance import Governance
from dd_harness.testing import TEST_PRINCIPAL, in_process

PATH_VARIABLES = ("DD_PROFILE", "DD_AGENTS_CONFIG", "DD_SOURCES_CONFIG")
APP_URL = "http://app.test"
# The shell's component and browser tests are drawn from these, so each must be what the server
# says. Outside CI a test rewrites a fixture that has fallen behind, so running the tests locally
# keeps them current: commit what changed. In CI (`CI` set) a stale fixture fails instead, unless
# DD_WRITE_FIXTURES=1.
FIXTURES = Path(__file__).resolve().parents[1] / "web/fixtures"


def _rewrite_fixtures() -> bool:
    if "DD_WRITE_FIXTURES" in os.environ:
        return os.environ["DD_WRITE_FIXTURES"] == "1"
    return not os.environ.get("CI")


def _changed_keys(old: Any, new: Any, where: str = "") -> list[str]:
    """Where `old` and `new` differ, as JSON paths, for the failure message."""
    if isinstance(old, dict) and isinstance(new, dict):
        return [
            change
            for key in sorted(old.keys() | new.keys())
            for change in _changed_keys(old.get(key), new.get(key), f"{where}.{key}")
        ]
    if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        return [
            change
            for i, (a, b) in enumerate(zip(old, new, strict=True))
            for change in _changed_keys(a, b, f"{where}[{i}]")
        ]
    return [] if old == new else [where or "."]


def check_fixture(name: str, body: dict[str, Any]) -> None:
    """`body` is what the fixture `name` holds; compared as JSON, so layout does not matter."""
    path = FIXTURES / name
    text = json.dumps(body, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    fresh = json.loads(text)
    held = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if held == fresh:
        return
    if _rewrite_fixtures():
        path.write_text(text, encoding="utf-8")
        return
    changed = ", ".join(_changed_keys(held, fresh)[:10])
    raise AssertionError(
        f"{path.name} is stale (changed: {changed}). Run `uv run pytest app/tests` locally, "
        "which rewrites it, and commit the result."
    )


def with_standards(governance: Governance) -> Governance:
    """`governance` with the standards advisor registered as the reference list would reach its
    service, but served in memory over A2A."""
    governance.conductor.registry.add(in_process(standards.build()))
    return governance


def configure_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """The app's reference set, a principal, and runs and projects written under `tmp_path`.

    The reference agent list names services these tests do not start, and whether one happens to
    be running would change what the server says, so it is replaced by an empty list. A test
    that needs an agent serves it in memory over A2A (`with_standards`).
    """
    for variable in PATH_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    no_remote_agents = tmp_path / "agents.yaml"
    no_remote_agents.write_text("agents: []\n", encoding="utf-8")
    monkeypatch.setenv("DD_AGENTS_CONFIG", str(no_remote_agents))
    for variable in ("DD_STANDARDS_RETRIEVAL", "DD_STANDARDS_EXPLAINER", "DD_SNAPSHOT_PATH"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("DD_PRINCIPAL_ID", TEST_PRINCIPAL.principal_id)
    monkeypatch.setenv("DD_PRINCIPAL_NAME", TEST_PRINCIPAL.name)
    monkeypatch.setenv("DD_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("DD_PROJECTS_DIR", str(tmp_path / "projects"))
    return tmp_path


def new_governance() -> Iterator[Governance]:
    yield with_standards(Governance.create(settings_from_env(), APP_URL))


def dist_dir(tmp_path: Path) -> Path:
    built = tmp_path / "dist"
    built.mkdir()
    (built / "index.html").write_text("<!doctype html><title>shell</title>", encoding="utf-8")
    return built
