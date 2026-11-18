"""Pydantic mirrors of the core classes of a dataset's file inventory: `FileInventory`, its files,
parts and personal-data findings (docs/specs/projects.md, docs/specs/personal-data.md).

Kept apart from `models`, which re-exports every name here, so that neither grows past its size
limit. As there, field names and enum values are the LinkML slot and permissible-value names.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from dd_sdk.contract.base import SHA256_PATTERN, Frozen


class IdentificationMethod(StrEnum):
    SIGNATURE = "signature"
    CONTAINER = "container"
    EXTENSION = "extension"
    NONE = "none"
    RESEARCHER = "researcher"


class PersonalDataKind(StrEnum):
    """What a personal-data finding took the data to be (docs/specs/personal-data.md)."""

    EMAIL_ADDRESS = "email address"
    PHONE_NUMBER = "phone number"
    NHS_NUMBER = "NHS number"
    NATIONAL_INSURANCE_NUMBER = "National Insurance number"
    POSTCODE = "postcode"
    PASSPORT_NUMBER = "passport number"
    DRIVING_LICENCE_NUMBER = "driving licence number"
    BANK_ACCOUNT_NUMBER = "bank account number"
    PAYMENT_CARD_NUMBER = "payment card number"
    IP_ADDRESS = "IP address"
    PERSON_NAME = "person name"
    DIRECT_IDENTIFIER = "direct identifier"
    INDIRECT_IDENTIFIER = "indirect identifier"
    SPECIAL_CATEGORY = "special category"
    LOCATION = "location"


class FindingTarget(StrEnum):
    COLUMN = "column"
    FIELD_NAME = "field name"
    FILE_NAME = "file name"
    TEXT = "text"


class ProportionBand(StrEnum):
    UNDER_1 = "under 1%"
    FROM_1_TO_10 = "1 to 10%"
    FROM_10_TO_50 = "10 to 50%"
    OVER_50 = "over 50%"


class ConfidenceBand(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FileRole(StrEnum):
    DATA = "data"
    DOCUMENTATION = "documentation"
    CODE = "code"
    OTHER = "other"


class TableField(Frozen):
    """One field of a table, as a Frictionless Table Schema field descriptor."""

    name: str
    field_type: str | None = None
    field_format: str | None = None
    field_description: str | None = None


class InventoryFile(Frozen):
    file_path: str = Field(pattern=r"^[^/]")
    file_size: int
    file_sha256: str = Field(pattern=SHA256_PATTERN)
    file_media_type: str | None = None
    file_pronom_ids: list[str] = Field(default_factory=list)
    file_identified_by: IdentificationMethod
    file_fields: list[TableField] = Field(default_factory=list)
    file_description: str | None = None
    file_role: FileRole | None = None


class PersonalDataFinding(Frozen):
    """Where the inventory command found what may be personal data, never what
    (docs/specs/personal-data.md)."""

    finding_kind: PersonalDataKind
    finding_file: str = Field(pattern=r"^[^/]")
    finding_target: FindingTarget
    finding_column: str | None = None
    finding_proportion: ProportionBand | None = None
    finding_confidence: ConfidenceBand
    finding_detector: str
    finding_examined: int | None = Field(default=None, ge=0)  # bound not in the schema (#333)


PART_FOLDER_PATTERN = r"^[^/]+(/[^/]+)*$"


class InventoryPart(Frozen):
    """One scan of one folder in an inventory made of several (docs/specs/projects.md)."""

    part_folder: str = Field(pattern=PART_FOLDER_PATTERN)
    part_tool: str
    part_tool_version: str
    part_identified_with: str | None = None
    part_made_at: datetime
    part_limitations: list[str] = Field(default_factory=list)
    # Absent and empty differ: absent, no detector ran (docs/specs/personal-data.md).
    part_personal_data: list[PersonalDataFinding] | None = None


def _within(path: str, folder: str) -> bool:
    return path == folder or path.startswith(folder + "/")


def inventory_part_problems(inventory: Any) -> list[str]:
    """What is wrong with a `FileInventory` document's parts, which its schema cannot say: a
    folder with a `.` or `..` segment, a folder that is another's or lies inside another's, and a
    file under no part's folder. Empty for a document without parts, or with nothing wrong.

    Reads the document as JSON, so the store can call it on a document its schema accepted."""
    parts = inventory.get("inventory_parts") if isinstance(inventory, dict) else None
    if not parts:
        return []
    folders = [str(p.get("part_folder", "")) for p in parts if isinstance(p, dict)]
    problems = [
        f"part folder {f!r} has a . or .. segment"
        for f in folders
        if any(segment in {".", ".."} for segment in f.split("/"))
    ]
    for i, a in enumerate(folders):
        for b in folders[i + 1 :]:
            if _within(a, b) or _within(b, a):
                problems.append(f"part folders {a!r} and {b!r} overlap")
    for file in inventory.get("inventory_files") or []:
        path = str(file.get("file_path", "")) if isinstance(file, dict) else ""
        if not any(path.startswith(f + "/") for f in folders):
            problems.append(f"{path!r} is under no part's folder")
    return problems


class FileInventory(Frozen):
    """The facts about a dataset's files a project holds in place of the files
    (docs/specs/projects.md). Made of `inventory_parts` when it covers more than one folder."""

    schema_class: Literal["FileInventory"] = "FileInventory"
    inventory_files: list[InventoryFile] = Field(default_factory=list)
    inventory_tool: str
    inventory_tool_version: str
    inventory_identified_with: str | None = None
    inventory_made_at: datetime
    inventory_limitations: list[str] = Field(default_factory=list)
    inventory_parts: list[InventoryPart] | None = None
    # Absent and empty differ: absent, no detector ran (docs/specs/personal-data.md).
    inventory_personal_data: list[PersonalDataFinding] | None = None

    @model_validator(mode="after")
    def _parts_cover_the_files(self) -> FileInventory:
        problems = inventory_part_problems(self.model_dump(mode="json"))
        if problems:
            raise ValueError("; ".join(problems))
        return self
