"""The Standards Librarian fills empty media types and fields from the project's inventory
(`GivenProjectInventory`, #1540): a researcher who has added an inventory is not asked what formats
and columns the data have. A value the input gives stands, and the result says what came from the
inventory."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from dd_agent_advisor_standards.classes import DatasetProfile
from dd_agent_advisor_standards.decided import filled
from dd_sdk.contract.inventory import FileInventory, IdentificationMethod, InventoryFile
from dd_sdk.contract.models import TableField


def file(path: str, media_type: str | None, *fields: str) -> InventoryFile:
    return InventoryFile(
        file_path=path,
        file_size=10,
        file_sha256=hashlib.sha256(path.encode()).hexdigest(),
        file_media_type=media_type,
        file_identified_by=IdentificationMethod.EXTENSION,
        file_fields=[TableField(name=name) for name in fields],
    )


INVENTORY = FileInventory(
    inventory_tool="dd-inventory",
    inventory_tool_version="0.1.0",
    inventory_made_at=datetime(2026, 11, 1, tzinfo=UTC),
    inventory_files=[
        file("a.csv", "text/csv", "sample_id", "mn_content"),
        file("b.csv", "text/csv", "sample_id"),
        file("scan.xy", "text/plain"),
        file("raw.brml", None),
    ],
)


def test_empty_media_types_and_fields_are_filled_from_the_inventory() -> None:
    profile, taken = filled(DatasetProfile(project_file_inventory=INVENTORY))

    assert profile.media_types == ["text/csv", "text/plain"]
    assert [f.name for f in profile.fields] == ["sample_id", "mn_content"]
    assert len(taken) == 2


def test_media_types_and_fields_the_input_gives_stand() -> None:
    given = DatasetProfile(
        media_types=["image/tiff"],
        fields=[TableField(name="intensity")],
        project_file_inventory=INVENTORY,
    )

    profile, taken = filled(given)

    assert profile.media_types == ["image/tiff"]
    assert [f.name for f in profile.fields] == ["intensity"]
    assert taken == []
