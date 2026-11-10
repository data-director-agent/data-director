"""What the app's tests share beyond fixtures (`conftest.py`)."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from dd_agent_advisor_standards import factory as standards
from dd_app.config import settings_from_env
from dd_app.governance import Governance
from dd_harness.testing import TEST_PRINCIPAL, in_process

PATH_VARIABLES = ("DD_PROFILE", "DD_AGENTS_CONFIG", "DD_SOURCES_CONFIG", "DD_REPOSITORIES_DIR")
APP_URL = "http://app.test"
# The shell's component and browser tests are drawn from these, so each must be what the server
# says. Outside CI a test rewrites a fixture that has fallen behind, so running the tests locally
# keeps them current: commit what changed. In CI (`CI` set) a stale fixture fails instead, unless
# DD_WRITE_FIXTURES=1.
FIXTURES = Path(__file__).resolve().parents[1] / "web/fixtures"
# A re3data export pinned for a test: two repositories and the standards each declares.
ORDA = "r3d100012124"
ZENODO = "r3d100010468"
EXPORT = "re3data:export:2026-11"
# The fields a choice reads, as the export's registry.jsonl holds them.
RECORDS = (
    {
        "re3data_id": ORDA,
        "name": "ORDA - The University of Sheffield Research Data Catalogue and Repository",
        "metadata_standards": ["Dublin Core"],
    },
    {"re3data_id": ZENODO, "name": "Zenodo", "metadata_standards": ["DataCite Metadata Schema"]},
)


def pin_export(root: Path) -> Path:
    """A `sources.yaml` pinning a re3data export of `RECORDS`, as `dd-re3data fetch` builds."""
    root.mkdir(parents=True, exist_ok=True)
    data = "".join(json.dumps(r, sort_keys=True) + "\n" for r in RECORDS).encode()
    (root / "registry.jsonl").write_bytes(data)
    entry = {
        "snapshot_refs": [EXPORT],
        "path": "registry.jsonl",
        "id_field": "re3data_id",
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    config = root / "sources.yaml"
    config.write_text(yaml.safe_dump({"sources": [entry]}), "utf-8")
    return config


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


# AG-UI streams the shell replays (docs/specs/transport.md), one event per line, kept like the
# fixtures above. `scripts/record_ui_cassettes.py` rewrites them all.
CASSETTES = Path(__file__).resolve().parents[1] / "web/cassettes"


def check_cassette(name: str, events: list[dict[str, Any]]) -> None:
    """`events` is what the cassette `name` holds, one JSON object a line, compared as JSON."""
    path = CASSETTES / name
    text = "".join(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n" for e in events)
    held = (
        [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        if path.exists()
        else None
    )
    if held == events:
        return
    if _rewrite_fixtures():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return
    changed = ", ".join(_changed_keys(held, events)[:10])
    raise AssertionError(
        f"{path.name} is stale (changed: {changed}). Run `uv run python "
        "scripts/record_ui_cassettes.py`, which rewrites it, and commit the result."
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
