"""A registry built from the committed fixture: about 30 records cut from the re3data export of
2026-11 (`data/SOURCE.md`), through the same `registry.build` path as the real one."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from dd_agent_advisor_repository import registry
from dd_agent_advisor_repository.snapshot import Re3dataRegistry

FIXTURE = Path(__file__).with_name("data") / "re3data-export-fixture.zip"


def build_fixture(directory: Path) -> Re3dataRegistry:
    data = registry.build(FIXTURE)
    path = directory / "registry.jsonl"
    path.write_bytes(data)
    pin = registry.Pin(
        month="2026-11",
        archive="https://www.re3data.org/export/re3data-repositories-2026-11.zip",
        archive_sha256=hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        records=data.count(b"\n"),
        snapshot_sha256=hashlib.sha256(data).hexdigest(),
        fetched_at="2026-11-06T00:00:00+00:00",
    )
    pin.write(directory / "manifest.json")
    return Re3dataRegistry(path, directory / "manifest.json")


def session_registry(tmp_path_factory: pytest.TempPathFactory) -> Re3dataRegistry:
    """For a session-scoped `re3data` fixture in each test module."""
    return build_fixture(tmp_path_factory.mktemp("re3data"))
