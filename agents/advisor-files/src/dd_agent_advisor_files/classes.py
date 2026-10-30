"""The input and payload classes of advisor.files, as Pydantic models (ADR-0019).

`schema/files.yaml` is the source; `ClassSchema.of` compares each model with the schema generated
from it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from dd_sdk.contract.models import Frozen, Grounded


class FileEntry(Frozen):
    name: str
    size_bytes: int | None = None
    media_type: str | None = None


class FileList(Frozen):
    schema_class: Literal["FileList"] = "FileList"
    files: list[FileEntry] = Field(default_factory=list)


class InventoryEntry(Frozen):
    name: str
    extension: str
    format_name: str
    media_type: str | None = None
    open_format: bool


class FileInventory(Grounded):
    schema_class: Literal["FileInventory"] = "FileInventory"
    entries: list[InventoryEntry] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
