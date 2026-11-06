"""The project record: an append-only log that holds a project's inventory
(docs/specs/projects.md).

What any backend must do is in the conformance kit (`dd_harness.testing.storage`, run by
`test_storage.py`). The tests here that read `store.root` are of the file backend's layout."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from requirement_sets import override, standard, write

from dd_harness import server
from dd_harness.projects import (
    INVENTORY_ADDED,
    PROJECT_CREATED,
    REPOSITORY_CHOSEN,
    ProjectError,
    ProjectStore,
    UnknownProjectError,
)
from dd_harness.requirements import load_requirements
from dd_harness.testing import TEST_PRINCIPAL, file_inventory
from dd_sdk.evidence import input_hash

inventory = file_inventory


@pytest.fixture
def store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


def test_a_read_waits_for_its_project_and_not_for_another(store: ProjectStore) -> None:
    """A read never sees part of an append, and one project's change never waits on another's."""
    busy = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    idle = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    read: list[str] = []
    with store._lock(busy):
        reader = threading.Thread(target=lambda: read.append(store.events(busy)[0]["event"]))
        reader.start()
        assert [e["event"] for e in store.events(idle)] == [PROJECT_CREATED]
        reader.join(timeout=0.2)
        assert reader.is_alive() and read == []
    reader.join(timeout=5)
    assert read == [PROJECT_CREATED]


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


@pytest.fixture
def repositories(tmp_path: Path) -> Path:
    return write(tmp_path / "repositories", ("standards", standard()), ("overrides", override()))


def test_a_project_records_the_repository_chosen_and_its_requirements(
    store: ProjectStore, repositories: Path
) -> None:
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    assert store.requirements(project_id) is None
    requirements = load_requirements(repositories)
    elsewhere = requirements.resolve("r3d100000001", "Elsewhere", ["Dublin Core"])
    store.choose_repository(project_id, elsewhere, acted_for=TEST_PRINCIPAL, caused_by="test")
    orda = requirements.resolve("r3d100012124", "ORDA", ["Dublin Core"])
    digest = store.choose_repository(project_id, orda, acted_for=TEST_PRINCIPAL, caused_by="test")

    # The last choice counts, and the merged set reads back as it was recorded.
    assert store.requirements(project_id) == orda.requirements()
    assert digest == input_hash(orda.requirements())
    first, last = store.events(project_id)[1:]
    assert first["event"] == last["event"] == REPOSITORY_CHOSEN
    assert len(first["warnings"]) == 2
    assert last["re3data_id"] == "r3d100012124"
    assert last["declared_standards"] == ["Dublin Core"]
    assert [s["ref"] for s in last["requirement_sets"]] == ["datacite-4@v1", "orda@v2"]
    assert last["digest"] == digest
    assert last["warnings"] == []
    with pytest.raises(ProjectError, match="no project"):
        store.choose_repository(
            "0" * 8 + "-0000-7000-8000-" + "0" * 12, orda, acted_for=TEST_PRINCIPAL, caused_by="t"
        )


def test_the_command_records_a_choice_and_warns_of_what_is_not_checked(
    operator: Path,
    repositories: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    server.main(["project", "create"])
    project_id = capsys.readouterr().out.strip()
    choose = ["project", "choose-repository", project_id, "--re3data", "r3d100000001"]
    choose += ["--name", "Elsewhere", "--standard", "DataCite Metadata Schema"]
    with pytest.raises(SystemExit, match="DD_REPOSITORIES_DIR unset"):
        server.main(choose)
    monkeypatch.setenv("DD_REPOSITORIES_DIR", str(repositories))
    assert server.main(choose) == 0
    out, err = capsys.readouterr()
    assert "warning: the deployment has no override for Elsewhere" in err
    (event,) = [
        e for e in ProjectStore(operator).events(project_id) if e["event"] == REPOSITORY_CHOSEN
    ]
    assert event["digest"] == out.strip()
    assert event["caused_by"] == "dd-harness project choose-repository"
    with pytest.raises(SystemExit, match="not a re3data identifier"):
        server.main([*choose[:4], "orda", *choose[5:]])


def test_a_project_is_named_by_its_title_and_a_blank_title_is_none(store: ProjectStore) -> None:
    named = store.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="  Soil cores 2024 ")
    unnamed = store.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="   ")
    assert store.events(named)[0]["title"] == "Soil cores 2024"
    assert "title" not in store.events(unnamed)[0]
    assert store.summary(unnamed)["title"] is None
    before = sorted(p.name for p in store.root.iterdir())
    with pytest.raises(ProjectError, match="at most 200"):
        store.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="x" * 201)
    assert sorted(p.name for p in store.root.iterdir()) == before


def test_a_conversation_in_an_unknown_project_is_refused(store: ProjectStore) -> None:
    unknown = "0" * 8 + "-0000-7000-8000-" + "0" * 12
    with pytest.raises(UnknownProjectError):
        store.start_conversation(unknown, acted_for=TEST_PRINCIPAL, caused_by="test")
    assert list(store.root.iterdir()) == []


def test_the_list_summarises_each_project_in_the_order_created(
    store: ProjectStore, repositories: Path
) -> None:
    first = store.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="First")
    second = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    store.add_inventory(first, inventory("a.csv"), acted_for=TEST_PRINCIPAL, caused_by="test")
    latest = inventory("a.csv", "b.csv")
    digest = store.add_inventory(first, latest, acted_for=TEST_PRINCIPAL, caused_by="test")
    orda = load_requirements(repositories).resolve("r3d100012124", "ORDA", ["Dublin Core"])
    store.choose_repository(first, orda, acted_for=TEST_PRINCIPAL, caused_by="test")
    store.start_conversation(first, acted_for=TEST_PRINCIPAL, caused_by="test")

    summaries = store.projects()
    assert [s["project_id"] for s in summaries] == [first, second]
    summary = summaries[0]
    assert summary["title"] == "First"
    assert summary["created_by"]["principal_id"] == TEST_PRINCIPAL.principal_id
    assert summary["inventory"]["digest"] == digest
    assert summary["inventory"]["file_count"] == 2
    assert summary["repository"]["repository_name"] == "ORDA"
    assert summary["repository"]["warnings"] == []
    assert summary["conversation_count"] == 1
    assert summary["documents"] == {"proposed": 0, "approved": 0, "rejected": 0}
    assert summaries[1]["inventory"] is None
    assert summaries[1]["repository"] is None


def test_the_command_names_a_project_and_lists_projects(
    operator: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert server.main(["project", "create", "--title", "Soil cores 2024"]) == 0
    project_id = capsys.readouterr().out.strip()
    assert server.main(["project", "list"]) == 0
    (line,) = capsys.readouterr().out.splitlines()
    listed = json.loads(line)
    assert listed["project_id"] == project_id
    assert listed["title"] == "Soil cores 2024"
