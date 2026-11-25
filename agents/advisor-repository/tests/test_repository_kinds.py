"""The Repository Librarian takes the kinds of data from the project's inventory when the needs give
none (`kinds.py`, #1560): a researcher who has added an inventory is not asked what kinds of data
they hold before the search. Kinds the caller gave stand, and a file whose media type names no
kind is counted, not guessed."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from test_repository_agent import NEEDS, agent, invoke

from dd_agent_advisor_repository import kinds
from dd_agent_advisor_repository.classes import RepositoryNeeds, RepositoryOptions
from dd_agent_advisor_repository.given import with_project
from dd_harness.agent_slots import agent_slots
from dd_sdk.contract.inventory import FileInventory, IdentificationMethod, InventoryFile
from dd_sdk.contract.models import OutcomeStatus


def file(path: str, media_type: str | None) -> InventoryFile:
    return InventoryFile(
        file_path=path,
        file_size=10,
        file_sha256=hashlib.sha256(path.encode()).hexdigest(),
        file_media_type=media_type,
        file_identified_by=IdentificationMethod.EXTENSION,
    )


INVENTORY = FileInventory(
    inventory_tool="dd-inventory",
    inventory_tool_version="0.1.0",
    inventory_made_at=datetime(2026, 11, 23, tzinfo=UTC),
    inventory_files=[
        file("a.png", "image/png"),
        file("b.png", "image/png"),
        file("results.csv", "text/csv"),
        file("notes.txt", "text/plain"),
        file("raw.brml", None),
        file("odd.bin", "application/x-unheard-of"),
    ],
)


def test_each_kind_is_named_once_in_the_order_first_listed() -> None:
    found = kinds.from_inventory(INVENTORY)
    assert found.kinds == [
        kinds.kind("image/png"),
        kinds.kind("text/csv"),
        kinds.kind("text/plain"),
    ]
    assert len(set(found.kinds)) == len(found.kinds)


def test_a_file_whose_media_type_names_no_kind_is_counted() -> None:
    assert kinds.from_inventory(INVENTORY).unnamed == 2


def test_a_media_type_is_read_by_its_top_level_type_and_without_parameters() -> None:
    assert kinds.kind("image/tiff") == kinds.kind("image/png") is not None
    assert kinds.kind("text/csv; charset=utf-8") == kinds.kind("text/csv") is not None
    assert kinds.kind("application/x-unheard-of") is None


def test_empty_kinds_are_taken_from_the_inventory() -> None:
    given = with_project(RepositoryNeeds(themes=["materials"], project_file_inventory=INVENTORY))
    assert given.needs.data_kinds == kinds.from_inventory(INVENTORY).kinds
    assert given.from_inventory is not None


def test_kinds_the_caller_gave_stand() -> None:
    needs = RepositoryNeeds(
        themes=["materials"], data_kinds=["micrographs"], project_file_inventory=INVENTORY
    )
    given = with_project(needs)
    assert given.needs.data_kinds == ["micrographs"]
    assert given.from_inventory is None


def test_the_search_is_made_on_the_kinds_the_inventory_names(runs_dir: Path) -> None:
    """The caller gives the discipline and leaves the kinds of data out, as the orchestrator does
    in a project that holds an inventory."""
    needs = NEEDS.model_copy(update={"data_kinds": [], "project_file_inventory": INVENTORY})
    env = invoke(runs_dir, needs)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    searched = env.payload_as(RepositoryOptions).searched
    assert searched is not None
    assert any(k in q for k in kinds.from_inventory(INVENTORY).kinds for q in searched.queries)


def test_the_card_asks_the_conductor_for_the_projects_inventory() -> None:
    """The conductor fills `project_file_inventory` by slot name, from the card's schema."""
    assert "project_file_inventory" in agent_slots(agent().spec, "RepositoryNeeds")
