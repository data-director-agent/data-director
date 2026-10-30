"""The project record: an append-only log that holds a project's inventory (ADR-0034)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from dd_harness import server
from dd_harness.projects import INVENTORY_ADDED, PROJECT_CREATED, ProjectError, ProjectStore
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.contract.models import FileInventory, IdentificationMethod, InventoryFile
from dd_sdk.evidence import input_hash


def inventory(*paths: str) -> dict[str, Any]:
    return FileInventory(
        inventory_tool="dd-inventory",
        inventory_tool_version="0.1.0",
        inventory_made_at=datetime(2026, 10, 30, tzinfo=UTC),
        inventory_files=[
            InventoryFile(
                file_path=path,
                file_size=10,
                file_sha256="a" * 64,
                file_media_type="text/csv",
                file_pronom_ids=["x-fmt/18"],
                file_identified_by=IdentificationMethod.EXTENSION,
            )
            for path in paths
        ],
    ).model_dump(mode="json", exclude_none=True)


@pytest.fixture
def store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


def test_a_project_holds_the_inventory_it_was_given(store: ProjectStore) -> None:
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    assert store.inventory(project_id) is None
    given = inventory("data/readings.csv")
    digest = store.add_inventory(project_id, given, acted_for=TEST_PRINCIPAL, caused_by="test")
    # The digest is the input hash the conductor records when an agent is given the inventory.
    assert digest == input_hash(given)
    assert store.inventory(project_id) == given

    created, added = store.events(project_id)
    assert created["event"] == PROJECT_CREATED
    assert added["event"] == INVENTORY_ADDED
    assert added["digest"] == digest
    assert added["file_count"] == 1
    for event in (created, added):
        assert event["project_id"] == project_id
        assert event["acted_for"]["principal_id"] == TEST_PRINCIPAL.principal_id
        assert event["caused_by"] == "test"
    assert created["event_id"] < added["event_id"]  # UUIDv7: in the order they happened


def test_the_log_is_appended_to_and_the_latest_inventory_wins(store: ProjectStore) -> None:
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    first, second = inventory("a.csv"), inventory("a.csv", "b.csv")
    store.add_inventory(project_id, first, acted_for=TEST_PRINCIPAL, caused_by="test")
    log = (store.root / project_id / "events.jsonl").read_text("utf-8")
    store.add_inventory(project_id, second, acted_for=TEST_PRINCIPAL, caused_by="test")
    store.add_inventory(project_id, first, acted_for=TEST_PRINCIPAL, caused_by="test")
    after = (store.root / project_id / "events.jsonl").read_text("utf-8")
    assert after.startswith(log)
    assert [e["event"] for e in store.events(project_id)] == [PROJECT_CREATED] + [
        INVENTORY_ADDED
    ] * 3
    assert store.inventory(project_id) == first
    # The same inventory twice is kept once.
    blobs = list((store.root / project_id / "blobs" / "sha256").iterdir())
    assert sorted(b.name for b in blobs) == sorted({input_hash(first), input_hash(second)})


def test_what_is_not_a_file_inventory_is_refused_and_nothing_is_recorded(
    store: ProjectStore,
) -> None:
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    absolute = inventory("data.csv")
    absolute["inventory_files"][0]["file_path"] = "/home/someone/data.csv"
    for document in ({"schema_class": "FileList", "files": []}, absolute):
        with pytest.raises(ProjectError, match="not a FileInventory"):
            store.add_inventory(project_id, document, acted_for=TEST_PRINCIPAL, caused_by="t")
    assert [e["event"] for e in store.events(project_id)] == [PROJECT_CREATED]
    assert not (store.root / project_id / "blobs").exists()


@pytest.mark.parametrize("project_id", ["0192c0de-0000-7000-8000-000000000000", "../escape", ""])
def test_an_unknown_project_is_refused(store: ProjectStore, project_id: str) -> None:
    with pytest.raises(ProjectError, match="no project"):
        store.add_inventory(project_id, inventory(), acted_for=TEST_PRINCIPAL, caused_by="t")
    with pytest.raises(ProjectError, match="no project"):
        store.events(project_id)


@pytest.fixture
def operator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "projects"
    monkeypatch.setenv("DD_PROJECTS_DIR", str(root))
    monkeypatch.setenv("DD_PRINCIPAL_ID", TEST_PRINCIPAL.principal_id)
    monkeypatch.setenv("DD_PRINCIPAL_NAME", TEST_PRINCIPAL.name)
    return root


def test_the_command_creates_a_project_and_adds_an_inventory(
    operator: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert server.main(["project", "create"]) == 0
    project_id = capsys.readouterr().out.strip()
    file = tmp_path / "inventory.json"
    file.write_text(json.dumps(inventory("data/readings.csv")), "utf-8")
    assert server.main(["project", "add-inventory", project_id, str(file)]) == 0
    digest = capsys.readouterr().out.strip()
    assert server.main(["project", "events", project_id]) == 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [e["event"] for e in events] == [PROJECT_CREATED, INVENTORY_ADDED]
    assert events[1]["digest"] == digest
    assert events[1]["caused_by"] == "dd-harness project add-inventory"
    assert ProjectStore(operator).inventory(project_id) == inventory("data/readings.csv")


def test_the_command_stops_without_a_projects_directory_or_a_principal(
    operator: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DD_PRINCIPAL_NAME")
    with pytest.raises(SystemExit, match="DD_PRINCIPAL_NAME unset"):
        server.main(["project", "create"])
    monkeypatch.delenv("DD_PROJECTS_DIR")
    with pytest.raises(SystemExit, match="DD_PROJECTS_DIR unset"):
        server.main(["project", "create"])


def test_the_command_refuses_a_file_that_is_not_an_inventory(
    operator: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    server.main(["project", "create"])
    project_id = capsys.readouterr().out.strip()
    file = tmp_path / "not-json.txt"
    file.write_text("hello", "utf-8")
    with pytest.raises(SystemExit, match=r"not-json\.txt"):
        server.main(["project", "add-inventory", project_id, str(file)])
    file.write_text("[]", "utf-8")
    with pytest.raises(SystemExit, match="not a JSON object"):
        server.main(["project", "add-inventory", project_id, str(file)])
