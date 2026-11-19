"""The pause before packaging: what a person decides and confirms before a deposit package is built
(docs/specs/deposit.md, "The pause before packaging", invariants 20 to 22; Blueprint C2)."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from test_deposit import RECORD, approve, choose

from dd_harness import server
from dd_harness.deposit import PackageRefusedError, build_package, validate
from dd_harness.deposit_review import (
    CONFIRMATION_CHECK,
    CONFIRMATIONS,
    DECISION_CHECK,
    ItemDecision,
    UnknownItemError,
    confirm,
    decide_item,
    review,
)
from dd_harness.projects import (
    DEPOSIT_CHECKS_CONFIRMED,
    DEPOSIT_ITEM_DECIDED,
    PACKAGE_BUILT,
    ProjectError,
    ProjectStore,
)
from dd_harness.store import RunStore
from dd_harness.testing import TEST_PRINCIPAL, clear_review
from dd_sdk.contract.models import (
    DocumentKind,
    FileInventory,
    IdentificationMethod,
    InventoryFile,
    TableField,
)

# Shaped like dataset A of data-director-agent/sample-data: its problems are in contents, and its
# names are all the platform has to go on.
MOORLAND = (
    ("analysis/plot_temp_gradient.R", ()),
    ("calibration/sites.csv", ("node", "lat", "lon", "elev")),
    ("data/N01-N06_v3.csv", ("timestamp_utc", "node_id", "ta", "rh")),
    ("fieldnotes/fieldnotes_2024.txt", ()),
    ("governance/landowner-access-agreement.md", ()),
    ("reference/WeatherNest_Stn442_hourly.csv", ("time_utc", "temp_c")),
)
# What a person must decide on dataset A, by file and kind.
TO_DECIDE = {
    ("calibration/sites.csv", "coordinates"),
    ("fieldnotes/fieldnotes_2024.txt", "free_text"),
    ("governance/landowner-access-agreement.md", "governance"),
    ("reference/WeatherNest_Stn442_hourly.csv", "third_party"),
}
PLAIN = (("data/readings.csv", ("site", "value")), ("README.md", ()))


def inventory(
    files: tuple[tuple[str, tuple[str, ...]], ...],
    *,
    findings: list[dict[str, Any]] | None = None,
    salt: str = "",
) -> dict[str, Any]:
    """A `FileInventory` of `files`, each with its own digest (changed by `salt`), and with
    `findings` as its personal-data findings: absent when None, as from a command without a
    detector."""
    document = FileInventory(
        inventory_tool="dd-inventory",
        inventory_tool_version="0.1.0",
        inventory_made_at=datetime(2026, 11, 1, tzinfo=UTC),
        inventory_files=[
            InventoryFile(
                file_path=path,
                file_size=100 + n,
                file_sha256=f"{n:x}{salt and 'f'}".ljust(64, "0"),
                file_media_type="text/csv",
                file_identified_by=IdentificationMethod.EXTENSION,
                file_fields=[TableField(name=f, field_type="string") for f in fields],
            )
            for n, (path, fields) in enumerate(files, start=1)
        ],
    ).model_dump(mode="json", exclude_none=True)
    if findings is not None:
        document["inventory_personal_data"] = findings
    return document


@pytest.fixture
def projects(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def runs(tmp_path: Path) -> RunStore:
    return RunStore(tmp_path / "runs")


def project(
    projects: ProjectStore, runs: RunStore, tmp_path: Path, document: dict[str, Any]
) -> str:
    """A project with `document` as its inventory, ORDA chosen, and a metadata record and README
    approved: valid for ORDA, so that only the pause stands before the package."""
    project_id = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    projects.add_inventory(project_id, document, acted_for=TEST_PRINCIPAL, caused_by="test")
    choose(projects, project_id, tmp_path)
    approve(projects, runs, project_id, DocumentKind.METADATA_RECORD, json.dumps(RECORD))
    approve(projects, runs, project_id, DocumentKind.README)
    return project_id


def decide(projects: ProjectStore, project_id: str, item_id: str, decision: ItemDecision) -> None:
    decide_item(
        projects,
        project_id,
        item_id,
        decision,
        None,
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )


@pytest.mark.requirement("C2")
def test_dataset_a_waits_for_a_person_to_decide_each_marked_file(
    projects: ProjectStore, runs: RunStore, tmp_path: Path
) -> None:
    project_id = project(projects, runs, tmp_path, inventory(MOORLAND))
    validation = validate(projects, project_id)
    assert validation.conforms
    assert not validation.ready
    assert validation.review is not None
    assert {(i.path, i.kind) for i in validation.review.open_items} == TO_DECIDE
    # Each open item, and the missing confirmation, is a warning, not a violation.
    assert {r.component for r in validation.awaiting} == {DECISION_CHECK, CONFIRMATION_CHECK}
    assert all(r.severity == "warning" for r in validation.awaiting)
    with pytest.raises(PackageRefusedError):
        build_package(projects, runs, project_id, acted_for=TEST_PRINCIPAL, caused_by="test")
    assert PACKAGE_BUILT not in [e["event"] for e in projects.events(project_id)]

    # Deciding every item still leaves the confirmation.
    items = validation.review.open_items
    for item, decision in zip(items, ItemDecision, strict=False):
        decide(projects, project_id, item.item_id, decision)
    for item in items[len(ItemDecision) :]:
        decide(projects, project_id, item.item_id, ItemDecision.KEEP)
    still = validate(projects, project_id)
    assert still.review is not None and not still.review.open_items
    assert not still.ready
    assert {r.component for r in still.awaiting} == {CONFIRMATION_CHECK}

    confirm(projects, project_id, CONFIRMATIONS, acted_for=TEST_PRINCIPAL, caused_by="test")
    assert validate(projects, project_id).ready
    package = build_package(projects, runs, project_id, acted_for=TEST_PRINCIPAL, caused_by="test")
    assert package.validation.ready


@pytest.mark.requirement("C2")
def test_decisions_and_the_confirmation_are_in_the_log_and_the_package(
    projects: ProjectStore, runs: RunStore, tmp_path: Path
) -> None:
    project_id = project(projects, runs, tmp_path, inventory(MOORLAND))
    first = review(projects, project_id).open_items[0]
    decide_item(
        projects,
        project_id,
        first.item_id,
        ItemDecision.CHANGE,
        "Gate code removed from the copy deposited.",
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )
    clear_review(projects, project_id, acted_for=TEST_PRINCIPAL)

    events = projects.events(project_id)
    decided = [e for e in events if e["event"] == DEPOSIT_ITEM_DECIDED]
    listed = review(projects, project_id).items
    assert {e["item_id"] for e in decided} == {i.item_id for i in listed}
    (change,) = [e for e in decided if e["item_id"] == first.item_id]
    assert change["decision"] == ItemDecision.CHANGE
    assert change["note"]
    assert change["item"]["path"] == first.path
    assert change["acted_for"]["principal_id"] == TEST_PRINCIPAL.principal_id
    (confirmed,) = [e for e in events if e["event"] == DEPOSIT_CHECKS_CONFIRMED]
    assert {s["id"] for s in confirmed["statements"]} == set(CONFIRMATIONS)

    package = build_package(projects, runs, project_id, acted_for=TEST_PRINCIPAL, caused_by="test")
    built = projects.events(project_id)[-1]
    assert set(built["decided_items"]) == {e["item_id"] for e in decided}
    archive = zipfile.ZipFile(io.BytesIO(package.content))
    crate = json.loads(archive.read("ro-crate-metadata.json"))
    graph = {entity["@id"]: entity for entity in crate["@graph"]}
    for event in decided:
        action = graph[f"#deposit-decision-{event['item_id']}"]
        assert action["@type"] == "AssessAction"
        assert action["endTime"] == event["at"]
        assert graph[action["agent"]["@id"]]["name"] == TEST_PRINCIPAL.name
    assert graph["#deposit-checks-confirmed"]["@type"] == "AssessAction"
    mentioned = {m["@id"] for m in graph["./"]["mentions"]}
    assert "#deposit-checks-confirmed" in mentioned
    log = [json.loads(line) for line in archive.read("project-log.jsonl").splitlines()]
    assert DEPOSIT_CHECKS_CONFIRMED in {e["event"] for e in log}


def test_a_project_with_no_marks_still_waits_for_the_confirmation_and_says_what_was_not_checked(
    projects: ProjectStore, runs: RunStore, tmp_path: Path
) -> None:
    project_id = project(projects, runs, tmp_path, inventory(PLAIN, findings=[]))
    found = review(projects, project_id)
    assert found.items == ()
    assert found.paused
    assert found.not_checked
    validation = validate(projects, project_id)
    assert not validation.ready
    assert {r.component for r in validation.awaiting} == {CONFIRMATION_CHECK}
    assert validation.report_jsonld()["dd:not_checked"] == list(found.not_checked)

    confirm(projects, project_id, CONFIRMATIONS, acted_for=TEST_PRINCIPAL, caused_by="test")
    assert validate(projects, project_id).ready
    # Nothing to decide never reads as safe: what was not checked is still said.
    assert review(projects, project_id).not_checked == found.not_checked


def test_an_inventory_made_before_findings_existed_says_no_detector_ran(
    projects: ProjectStore, runs: RunStore, tmp_path: Path
) -> None:
    """Absent findings (no detector) and an empty list (a detector found nothing) are said
    apart (docs/specs/personal-data.md, invariant 2)."""
    without = review(projects, project(projects, runs, tmp_path, inventory(PLAIN)))
    nothing = review(projects, project(projects, runs, tmp_path, inventory(PLAIN, findings=[])))
    assert without.items == nothing.items == ()
    assert len(without.not_checked) == len(nothing.not_checked) == 2
    assert without.not_checked[0] == nothing.not_checked[0]
    assert without.not_checked[1] != nothing.not_checked[1]


@pytest.mark.requirement("C2")
def test_each_personal_data_finding_is_an_item_to_decide(
    projects: ProjectStore, runs: RunStore, tmp_path: Path
) -> None:
    finding = {
        "finding_kind": "email address",
        "finding_file": "data/readings.csv",
        "finding_target": "column",
        "finding_column": "site",
        "finding_proportion": "1 to 10%",
        "finding_confidence": "high",
        "finding_detector": "presidio-analyzer 2.2",
        "finding_examined": 120,
    }
    project_id = project(projects, runs, tmp_path, inventory(PLAIN, findings=[finding]))
    (item,) = review(projects, project_id).items
    assert (item.source, item.kind, item.path, item.column) == (
        "finding",
        "email address",
        "data/readings.csv",
        "site",
    )
    assert item.decision is None


def test_a_changed_file_or_inventory_asks_again(
    projects: ProjectStore, runs: RunStore, tmp_path: Path
) -> None:
    project_id = project(projects, runs, tmp_path, inventory(MOORLAND))
    clear_review(projects, project_id, acted_for=TEST_PRINCIPAL)
    assert not review(projects, project_id).paused

    # A new inventory in which every file changed: each item is new and the confirmation was
    # made against the old inventory.
    projects.add_inventory(
        project_id, inventory(MOORLAND, salt="x"), acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    again = review(projects, project_id)
    assert {(i.path, i.kind) for i in again.open_items} == TO_DECIDE
    assert again.confirmation is None


def test_a_decision_must_name_an_item_listed_now_and_every_statement_is_confirmed(
    projects: ProjectStore, runs: RunStore, tmp_path: Path
) -> None:
    project_id = project(projects, runs, tmp_path, inventory(MOORLAND))
    with pytest.raises(UnknownItemError):
        decide(projects, project_id, "0" * 24, ItemDecision.KEEP)
    item = review(projects, project_id).open_items[0]
    with pytest.raises(ProjectError):
        decide_item(
            projects,
            project_id,
            item.item_id,
            ItemDecision.KEEP,
            "x" * 5000,
            acted_for=TEST_PRINCIPAL,
            caused_by="test",
        )
    with pytest.raises(ProjectError):
        confirm(
            projects,
            project_id,
            ["ethics_approval"],
            acted_for=TEST_PRINCIPAL,
            caused_by="test",
        )
    events = {e["event"] for e in projects.events(project_id)}
    assert not events & {DEPOSIT_ITEM_DECIDED, DEPOSIT_CHECKS_CONFIRMED}

    # A later decision on the same item replaces the earlier one.
    decide(projects, project_id, item.item_id, ItemDecision.KEEP)
    decide(projects, project_id, item.item_id, ItemDecision.LEAVE_OUT)
    (now,) = [i for i in review(projects, project_id).items if i.item_id == item.item_id]
    assert now.decision is not None and now.decision["decision"] == ItemDecision.LEAVE_OUT


@pytest.fixture
def operator(monkeypatch: pytest.MonkeyPatch, projects: ProjectStore) -> None:
    monkeypatch.setenv("DD_PROJECTS_DIR", str(projects.root))
    monkeypatch.setenv("DD_PRINCIPAL_ID", TEST_PRINCIPAL.principal_id)
    monkeypatch.setenv("DD_PRINCIPAL_NAME", TEST_PRINCIPAL.name)


@pytest.mark.usefixtures("operator")
def test_the_commands_review_decide_and_confirm(
    projects: ProjectStore,
    runs: RunStore,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_id = project(projects, runs, tmp_path, inventory(MOORLAND))
    assert server.main(["project", "review", project_id]) == 1
    printed = json.loads(capsys.readouterr().out)
    for item in printed["items"]:
        args = ["project", "decide-item", project_id, item["item_id"], "keep", "--note", "Read."]
        assert server.main(args) == 0
    assert server.main(["project", "confirm-checks", project_id]) == 0
    capsys.readouterr()
    assert server.main(["project", "review", project_id]) == 0
    causes = {e["caused_by"] for e in projects.events(project_id)}
    assert {"dd-harness project decide-item", "dd-harness project confirm-checks"} <= causes
